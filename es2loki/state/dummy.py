from es2loki.state import State, StateStore


class DummyStateStore(StateStore):
    async def load(self) -> State:
        return State()

    async def save(self, state: State, transferred_docs: int):
        self.logger.info("skipping state save when DummyStateStore is in use")
