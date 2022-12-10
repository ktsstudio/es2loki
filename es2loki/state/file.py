import asyncio
import json
import os
from dataclasses import asdict

from es2loki.state import State, StateStore


class FileStateStore(StateStore):
    def __init__(self, *, state_dir: str, file_suffix: str, dry_run: bool = False):
        super().__init__(dry_run=dry_run)
        self.persist_dir = state_dir
        if not self.persist_dir:
            raise ValueError("persist directory is invalid")

        self.state_file = os.path.join(self.persist_dir, f"state-{file_suffix}.txt")

        self._state_lock = asyncio.Lock()

    async def init(self, stop_event: asyncio.Event):
        if not os.path.exists(self.persist_dir):
            os.mkdir(self.persist_dir)

    async def load(self) -> State:
        if not os.path.exists(self.state_file):
            return State()

        with open(self.state_file, "r") as state_file:
            contents = state_file.read()
            if contents:
                return State(**json.loads(contents))

        return State()

    async def save(self, state: State, transferred_docs: int):
        async with self._state_lock:
            state.transferred = transferred_docs

            with open(self.state_file, "w") as f:
                if self.dry_run:
                    self.logger.info("[DRY_RUN] saving state to file")
                else:
                    self.logger.info("saving state to file")
                    f.write(json.dumps(asdict(state)))

    async def cleanup(self):
        if not os.path.exists(self.state_file):
            return

        if self.dry_run:
            self.logger.info("[DRY_RUN] cleaning up state %s", self.state_file)
        else:
            self.logger.info("cleaning up state %s", self.state_file)
            os.unlink(self.state_file)
