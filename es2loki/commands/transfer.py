import asyncio
import datetime
import json
import logging
import os
import time
from collections.abc import AsyncIterable
from typing import MutableMapping, Optional

from elasticsearch import AsyncElasticsearch

from es2loki.aio import wait_task
from es2loki.aio.pool import AsyncPool
from es2loki.commands import Command
from es2loki.es import ElasticsearchScroller
from es2loki.loki import Loki, LokiBatch
from es2loki.state import StateStore
from es2loki.state.db import DBStateStore
from es2loki.state.dummy import DummyStateStore
from es2loki.state.types import State
from es2loki.utils import seconds_to_str, size_str


class BaseTransfer(Command):
    state_store: StateStore

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("execute_timeout", 128)
        super().__init__(*args, **kwargs)

        self.dry_run = os.getenv("DRY_RUN") == "1"

        es_hosts = os.getenv("ELASTIC_HOSTS", "http://localhost:9200")
        es_user = os.getenv("ELASTIC_USER")
        es_password = os.getenv("ELASTIC_PASSWORD")
        self.es_index = os.getenv("ELASTIC_INDEX")
        self.es_batch_size = int(os.getenv("ELASTIC_BATCH_SIZE", 3000))
        self.es_timeout = int(os.getenv("ELASTIC_TIMEOUT", 120))
        self.es_max_date = os.getenv("ELASTIC_MAX_DATE")
        self.es_timestamp_field = os.getenv("ELASTIC_TIMESTAMP_FIELD", "@timestamp")

        loki_url = os.getenv("LOKI_URL", "http://localhost:3100")
        loki_username = os.getenv("LOKI_USERNAME")
        loki_password = os.getenv("LOKI_PASSWORD")
        loki_tenant_id = os.getenv("LOKI_TENANT_ID")
        self.loki_batch_size = int(os.getenv("LOKI_BATCH_SIZE", 1 * 1024 * 1024))
        self.loki_pool_load_factor = int(os.getenv("LOKI_POOL_LOAD_FACTOR", 10))
        self.loki_push_mode = os.getenv("LOKI_PUSH_MODE", "pb")
        self.loki_wait_timeout = float(os.getenv("LOKI_WAIT_TIMEOUT", 0))

        self.state_start_over = bool(int(os.getenv("STATE_START_OVER", 0)))
        self.state_mode = os.getenv("STATE_MODE", "none")
        self.state_db_url = os.getenv(
            "STATE_DB_URL", "postgres://127.0.0.1:5432/postgres"
        )

        if self.state_mode == "db":
            self.state_store = DBStateStore(
                name=self.es_index,
                url=self.state_db_url,
                dry_run=self.dry_run,
            )
        elif self.state_mode == "none":
            self.state_store = DummyStateStore(
                dry_run=self.dry_run,
            )
        else:
            raise ValueError("Unknown STATE_MODE. Possible values are: (db, none)")

        self.es = self.make_elastic_client(
            hosts=es_hosts,
            user=es_user,
            password=es_password,
        )
        self.loki = Loki(
            url=loki_url,
            username=loki_username,
            password=loki_password,
            tenant_id=loki_tenant_id,
            use_gzip=self.loki_push_mode == "gzip",
            use_pb=self.loki_push_mode == "pb",
            dry_run=self.dry_run,
        )
        self.total_docs = 0
        self.transferred_docs = 0
        self._speed = 0
        self._eta = 0
        self._eta_calc = None

        self.loki_batch = LokiBatch()
        self._latest_state = None
        self.loki_pool = None

        self._flush_lock = asyncio.Lock()

    @property
    def latest_state(self) -> State:
        return self._latest_state

    @staticmethod
    def make_elastic_client(
        hosts: str,
        user: str,
        password: str,
    ):
        kwargs = {
            "hosts": hosts.split(","),
        }
        if user and password:
            kwargs["http_auth"] = (user, password)

        return AsyncElasticsearch(**kwargs)

    async def _get_total_docs(self):
        body = None
        if self.es_max_date:
            query = {"range": {self.es_timestamp_field: {"lt": self.es_max_date}}}
            body = {"query": query}
        while self.is_running:
            try:
                return (await self.es.count(index=self.es_index, body=body))["count"]
            except Exception as e:
                self.logger.error("error retrieving total docs count: %s", e)
                await asyncio.sleep(1.0)

    async def execute(self):
        self.loki_pool = AsyncPool(
            num_workers=1,  # should not write to Loki in parallel
            name="loki_pool",
            logger=self.logger,
            worker_co=self.send_to_loki,
            load_factor=self.loki_pool_load_factor,
        )

        await self.state_store.init(stop_event=self.stop_event)
        if self.stop_event.is_set():
            return

        if self.state_start_over:
            await self.state_store.cleanup()

        self._latest_state = await self.state_store.load()
        self.transferred_docs = self.latest_state.transferred
        self.logger.info("starting from state %s", self.latest_state)

        self.total_docs, _ = await wait_task(
            self._get_total_docs(), event=self.stop_event
        )
        if not self.is_running:
            return

        if self.total_docs == 0:
            self.logger.info("no docs found in es")
            return

        self.logger.info(
            "progress: %d/%d (%.2f%%)",
            self.transferred_docs,
            self.total_docs,
            self.transferred_docs / self.total_docs * 100,
        )

        self.loki_pool.start()
        self._eta_calc = asyncio.create_task(self._calc_eta())

        await self.es_scroll()
        self.logger.info("finished es_scroll")

        if self.is_running and self.loki_batch.total_docs > 0:
            self.logger.info("%d rows left in batch", self.loki_batch.total_docs)
            await self.flush_batch()

        self.logger.info("waiting for loki pool to finish")
        await self.loki_pool.join()

        self.stop_event.set()
        self._eta_calc.cancel()

    def make_es_sort(self) -> list:
        return [
            {self.es_timestamp_field: {"unmapped_type": "date", "order": "asc"}},
            {"log.offset": {"order": "asc"}},
        ]

    def make_es_search_after(self) -> Optional[list]:
        state = self.latest_state
        if not state or state.iszero:
            return None
        return state.value

    def make_es_scroller(self) -> AsyncIterable[tuple[dict, State]]:
        return ElasticsearchScroller(
            es=self.es,
            es_index=self.es_index,
            es_batch_size=self.es_batch_size,
            stop_event=self.stop_event,
            es_timeout=self.es_timeout,
            max_date=self.es_max_date,
            make_sort=self.make_es_sort,
            make_search_after=self.make_es_search_after,
            timestamp_field=self.es_timestamp_field,
        )

    async def es_scroll(self):
        scroller = self.make_es_scroller()
        async for doc, state in scroller:
            await self.process_es_doc(doc, state)

    async def process_es_doc(self, doc: dict, state: State):
        source = doc["_source"]
        if not source:
            return

        timestamp = self.extract_doc_ts(source)
        if not timestamp:
            return

        labels = self.extract_doc_labels(source) or {}
        self.enrich_labels(timestamp, labels)
        entry = json.dumps(source, sort_keys=True)

        self.loki_batch.push(labels=labels, timestamp=timestamp, entry=entry)
        self._latest_state = state

        if self.loki_batch.total_size >= self.loki_batch_size:
            async with self._flush_lock:
                await self.flush_batch()
                self.loki_batch = LokiBatch()

    async def flush_batch(self):
        if not self.loki_batch.total_docs:
            return

        await wait_task(
            self.loki_pool.push(self.loki_batch, self.latest_state),
            event=self.stop_event,
        )

    async def send_to_loki(self, batch: LokiBatch, state: State):
        _, transferred_size = await self.loki.push(batch, stop_event=self.stop_event)

        self.transferred_docs += batch.total_docs
        self.logger.info(
            "transferred %d streams of %s (enc: %s). total: %d/%d docs (%.2f%%) eta: %s speed: %.2f docs/s",
            batch.streams_count,
            size_str(batch.total_size),
            size_str(transferred_size),
            self.transferred_docs,
            self.total_docs,
            self.transferred_docs / self.total_docs * 100,
            seconds_to_str(self._eta),
            self._speed,
        )
        await self.state_store.save(state, self.transferred_docs)

        if self.loki_wait_timeout:
            await wait_task(
                asyncio.sleep(self.loki_wait_timeout), event=self.stop_event
            )

    def extract_doc_labels(self, source: dict) -> Optional[MutableMapping[str, str]]:
        return {}

    def extract_doc_ts(self, source: dict) -> Optional[datetime.datetime]:
        timestamp_val = source.get(self.es_timestamp_field)
        if not timestamp_val:
            return None

        iso_dt = timestamp_val.rstrip("Z")
        return datetime.datetime.fromisoformat(iso_dt)

    def enrich_labels(
        self, timestamp: datetime.datetime, labels: MutableMapping[str, str]
    ):
        labels["imported"] = "yes"
        labels["import_month"] = timestamp.strftime("%Y%m")

    async def _calc_eta(self):
        while self.is_running:
            last_ts = time.monotonic()
            last_transferred_value = self.transferred_docs

            _, finished = await wait_task(asyncio.sleep(10), event=self.stop_event)
            if finished:
                return

            now = time.monotonic()
            time_delta = now - last_ts
            docs_added = self.transferred_docs - last_transferred_value

            self._speed = docs_added / time_delta
            self._eta = (
                (self.total_docs - self.transferred_docs) / self._speed
                if self._speed > 0
                else 0
            )


def run_transfer(cmd: BaseTransfer, setup_logging: bool = True) -> int:
    if setup_logging:
        logging.basicConfig(
            format="%(created)f %(asctime)s.%(msecs)03d [%(name)s] %(levelname)s: %(message)s",
            level=logging.DEBUG,
        )
        logging.getLogger("elasticsearch").setLevel(logging.WARNING)
        logging.getLogger("charset_normalizer").setLevel(logging.ERROR)

    return cmd.start()
