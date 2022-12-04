import asyncio
import datetime
import json
import logging
from asyncio import CancelledError
from functools import cached_property
from typing import Mapping, Optional, cast

import aiohttp
from frozendict import frozendict
from snappy import snappy
from yarl import URL

from es2loki.proto.logproto_pb2 import PushRequest, StreamAdapter
from es2loki.utils import gzip_encode, size_str

logger = logging.getLogger(__name__)


class LokiBatch:
    def __init__(self):
        self._streams: dict[Mapping[str, str], list[tuple[str, str]]] = {}
        self._pb_streams: dict[Mapping[str, str], StreamAdapter] = {}
        self._req = PushRequest()

    def push(
        self, *, labels: Mapping[str, str], timestamp: datetime.datetime, entry: str
    ):
        labels = frozendict(labels)

        if labels not in self._streams:
            self._streams[labels] = []
            stream = StreamAdapter()
            stream.labels = self._labels_to_str(labels)
            self._pb_streams[labels] = stream

        timestamp_nano = int(timestamp.timestamp() * 1000) * 1_000_000

        self._streams[labels].append((str(timestamp_nano), entry))

        pb_entry = self._pb_streams[labels].entries.add()
        pb_entry.timestamp.FromNanoseconds(timestamp_nano)
        pb_entry.line = entry

    @property
    def streams_count(self) -> int:
        return len(self._streams)

    @property
    def total_size(self) -> int:
        total = 0
        for stream in self._streams.values():
            total += sum((len(entry[1]) for entry in stream))
        return total

    @property
    def total_docs(self) -> int:
        return sum((len(stream) for stream in self._streams.values()))

    def serialize_json(self):
        return {
            "streams": [
                {
                    "stream": dict(labels),
                    "values": values,
                }
                for labels, values in self._streams.items()
            ]
        }

    def serialize_pb(self) -> bytes:
        req = PushRequest()
        req.streams.extend(list(self._pb_streams.values()))
        return req.SerializeToString()

    @staticmethod
    def _labels_to_str(labels: Mapping[str, str]):
        arr = []
        for key, value in labels.items():
            arr.append(f'{key}="{value}"')

        arr.sort()
        return "{" + ", ".join(arr) + "}"

    def get_printable_stats(self):
        lines = []
        for labels, stream in self._streams.items():
            labels_str = self._labels_to_str(labels)
            stream_size = sum((len(entry[1]) for entry in stream))
            line = f"{labels_str} => count={len(stream)} size={size_str(stream_size)}"
            lines.append(line)
        return "\n".join(lines)


class Loki:
    def __init__(
        self,
        url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        tenant_id: Optional[str] = None,
        use_gzip: bool = True,
        use_pb: bool = True,
        dry_run: bool = False,
    ):
        self.url = url
        self.username = username
        self.password = password
        self.tenant_id = tenant_id
        self._session = None
        self._dry_run = dry_run

        if self.username and self.password:
            self._auth = aiohttp.BasicAuth(login=self.username, password=self.password)
        else:
            self._auth = None

        self._use_gzip = use_gzip
        self._use_pb = use_pb
        self._headers = {}

        if self.tenant_id:
            self._headers["X-Scope-OrgId"] = self.tenant_id

        if self._use_pb:
            self._headers["Content-Type"] = "application/x-protobuf"
        else:
            self._headers["Content-Type"] = "application/json; charset=utf8"
            if use_gzip:
                self._headers["Content-Encoding"] = "gzip"

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    @cached_property
    def api_push_url(self):
        return URL(self.url) / "loki/api/v1/push"

    async def _push(
        self, data: bytes, batch: LokiBatch, stop_event: asyncio.Event
    ) -> tuple[int, int]:
        status = None
        while status is None or status < 200 or status > 300:
            if stop_event.is_set():
                raise CancelledError("stopping loki push")

            if self._dry_run:
                logger.info(
                    "[DRY_RUN] sending loki push request to %s", self.api_push_url
                )
                status = 200
            else:
                try:
                    async with self.session.request(
                        "POST",
                        self.api_push_url,
                        data=data,
                        headers=self._headers,
                        auth=self._auth,
                    ) as result:
                        status = result.status

                        if not (200 <= status < 300):
                            resp = await result.text()
                            logger.info(
                                "loki push - %d: %s. stats:\n%s",
                                status,
                                resp,
                                batch.get_printable_stats(),
                            )
                            await asyncio.sleep(2.0)
                            continue
                except Exception as e:
                    logger.exception("error while sending to loki: %s", e)
                    await asyncio.sleep(2.0)
                    continue

            return cast(int, status), len(data)

    async def push_json(
        self, batch: LokiBatch, stop_event: asyncio.Event
    ) -> tuple[int, int]:
        data = batch.serialize_json()
        data_encoded = json.dumps(data).encode("utf-8")

        if self._use_gzip:
            data_encoded = gzip_encode(data_encoded)

        return await self._push(data_encoded, batch, stop_event)

    async def push_pb(
        self, batch: LokiBatch, stop_event: asyncio.Event
    ) -> tuple[int, int]:
        data = batch.serialize_pb()
        data = snappy.compress(data)

        return await self._push(data, batch, stop_event)

    async def push(
        self, batch: LokiBatch, stop_event: asyncio.Event
    ) -> tuple[int, int]:
        if self._use_pb:
            return await self.push_pb(batch, stop_event)
        return await self.push_json(batch, stop_event)
