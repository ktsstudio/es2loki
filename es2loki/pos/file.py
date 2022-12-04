import asyncio
import json
import os
from dataclasses import asdict

from es2loki.pos import Positions, PositionsStore


class FilePositionsStore(PositionsStore):
    def __init__(self, *, persist_dir: str, file_suffix: str, dry_run: bool = False):
        super().__init__(dry_run=dry_run)
        self.persist_dir = persist_dir
        if not self.persist_dir:
            raise ValueError("persist directory is invalid")

        self.positions_file = os.path.join(
            self.persist_dir, f"positions-{file_suffix}.txt"
        )

        self._pos_lock = asyncio.Lock()

    async def init(self, stop_event: asyncio.Event):
        if not os.path.exists(self.persist_dir):
            os.mkdir(self.persist_dir)

    async def load(self) -> Positions:
        if not os.path.exists(self.positions_file):
            return Positions()

        with open(self.positions_file, "r") as pos_file:
            contents = pos_file.read()
            if contents:
                return Positions(**json.loads(contents))

        return Positions()

    async def save(self, pos: Positions, transferred_docs: int):
        async with self._pos_lock:
            pos.transferred = transferred_docs

            with open(self.positions_file, "w") as f:
                if self.dry_run:
                    self.logger.info("[DRY_RUN] saving positions to file")
                else:
                    self.logger.info("saving positions to file")
                    f.write(json.dumps(asdict(pos)))

    async def cleanup(self):
        if not os.path.exists(self.positions_file):
            return

        if self.dry_run:
            self.logger.info("[DRY_RUN] cleaning up positions %s", self.positions_file)
        else:
            self.logger.info("cleaning up positions %s", self.positions_file)
            os.unlink(self.positions_file)
