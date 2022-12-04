import asyncio
import logging

from .types import Positions


class PositionsStore:
    def __init__(self, dry_run: bool = False):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.dry_run = dry_run

    async def init(self, stop_event: asyncio.Event):
        pass

    async def load(self) -> Positions:
        raise NotImplementedError

    async def save(self, pos: Positions, transferred_docs: int):
        raise NotImplementedError

    async def cleanup(self):
        raise NotImplementedError
