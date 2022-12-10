import asyncio
import collections
import logging
from collections.abc import AsyncIterable
from typing import Callable, Optional

from elasticsearch import AsyncElasticsearch

from es2loki.aio import wait_task
from es2loki.state.types import State


class ElasticsearchScroller(AsyncIterable[tuple[dict, State]]):
    def __init__(
        self,
        es: AsyncElasticsearch,
        es_index: str,
        es_batch_size: int,
        stop_event: asyncio.Event,
        make_sort: Callable[[], list],
        make_search_after: Callable[[], Optional[list]],
        timestamp_field: str,
        max_date: Optional[str] = None,
        es_timeout: int = 120,
    ):
        self.es = es
        self.es_index = es_index
        self.es_batch_size = es_batch_size
        self.es_timeout = es_timeout
        self.stop_event = stop_event
        self._max_date = max_date
        self._timestamp_field = timestamp_field

        self._sort = make_sort()
        self._search_after = make_search_after()

        self.logger = logging.getLogger("es_scroller")
        self._buffer = collections.deque()
        self._buffer_lock = asyncio.Lock()
        self._buffer_refill_coro = None

    @property
    def is_running(self) -> bool:
        return not self.stop_event.is_set()

    def __aiter__(self):
        return self

    async def __anext__(self) -> tuple[dict, State]:
        if not self.is_running:
            raise StopAsyncIteration()

        if len(self._buffer) == 0:
            if (
                self._buffer_refill_coro is not None
                and not self._buffer_refill_coro.done()
            ):
                await self._buffer_refill_coro
            else:
                await self._refill_buffer()

            if len(self._buffer) == 0:  # no more entries
                raise StopAsyncIteration()

        if (
            self._buffer_refill_coro is None
            and len(self._buffer) < 2 * self.es_batch_size // 3
        ):
            self._refill_buffer_bg()

        doc = self._buffer.popleft()
        return doc, State(
            timestamp=doc.get("_source", {}).get(self._timestamp_field),
            value=doc["sort"],
        )

    def _refill_buffer_bg(self) -> bool:
        if not self.is_running:
            return False

        if self._buffer_refill_coro is not None:
            return False

        def on_done(f):
            self._buffer_refill_coro = None
            if f.cancelled():
                return

            exc = f.exception()
            if exc is not None:
                self.logger.exception(exc)

        self._buffer_refill_coro = asyncio.create_task(self._refill_buffer())
        self._buffer_refill_coro.add_done_callback(on_done)
        return True

    async def _refill_buffer(self):
        async with self._buffer_lock:
            result = None
            while self.is_running:
                try:
                    query = None
                    if self._max_date:
                        query = {
                            "range": {self._timestamp_field: {"lt": self._max_date}}
                        }
                    result, finished = await wait_task(
                        self.es.search(
                            index=self.es_index,
                            size=self.es_batch_size,
                            query=query,
                            search_after=self._search_after,
                            sort=self._sort,
                            request_timeout=self.es_timeout,
                        ),
                        event=self.stop_event,
                    )
                    if finished:
                        return

                    if result.get("error"):
                        self.logger.error(
                            "errors while searching index=%s search_after=%s: %s",
                            self.es_index,
                            self._search_after,
                            result,
                        )
                        await wait_task(asyncio.sleep(2), event=self.stop_event)
                        continue

                    if result.get("timed_out", False):
                        self.logger.error(
                            "es search timed out. index=%s search_after=%s",
                            self.es_index,
                            self._search_after,
                        )
                        await wait_task(asyncio.sleep(2), event=self.stop_event)
                        continue

                    shards = result.get("_shards", {})
                    failed_shards = shards.get("failed", 0)
                    ok_shards = shards.get("successful", 0)
                    total_shards = shards.get("total", 0)
                    if failed_shards + ok_shards < total_shards:
                        self.logger.error(
                            "some shards are not returning data. "
                            "total=%d ok=%d failed=%d. index=%s search_after=%s",
                            total_shards,
                            ok_shards,
                            failed_shards,
                            self.es_index,
                            self._search_after,
                        )
                        await wait_task(asyncio.sleep(2), event=self.stop_event)
                        continue

                    failures = shards.get("failures", [])
                    if failures:
                        self.logger.error(
                            "got failures for index=%s search_after=%s: %s",
                            self.es_index,
                            self._search_after,
                            failures,
                        )
                        await wait_task(asyncio.sleep(2), event=self.stop_event)
                        continue
                    break
                except Exception as e:
                    self.logger.exception(e)
                    await wait_task(asyncio.sleep(2), event=self.stop_event)
                    continue

            if not result:
                return

            hits = result.get("hits", {}).get("hits", [])
            if not hits:
                return

            self._buffer.extend(hits)
            self._search_after = hits[-1]["sort"]
