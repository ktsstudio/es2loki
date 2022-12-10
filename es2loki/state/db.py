import asyncio

from tortoise import Model, Tortoise, fields

from es2loki.state import State, StateStore


class StateModel(Model):
    class Meta:
        table = "state"

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255, unique=True)
    transferred = fields.IntField()
    timestamp = fields.CharField(max_length=100)
    value = fields.JSONField()

    def to_state(self) -> State:
        return State(
            timestamp=self.timestamp,
            value=self.value,
            transferred=self.transferred,
        )


class DBStateStore(StateStore):
    def __init__(
        self,
        *,
        name: str,
        url: str = "postgres://127.0.0.1:5432/es2loki",
        dry_run: bool = False
    ):
        super().__init__(dry_run=dry_run)
        self._url = url
        self.name = name

    async def connect(self, stop_event: asyncio.Event):
        while not stop_event.is_set():
            try:
                await Tortoise.init(
                    db_url=self._url, modules={"models": ["es2loki.state.db"]}
                )
                await Tortoise.generate_schemas()
                self.logger.error("connected successfully to db")
                return
            except Exception as e:
                self.logger.error("error creating db: %s", e)
                await asyncio.sleep(1.0)

    async def init(self, stop_event: asyncio.Event):
        await self.connect(stop_event)

    async def load(self) -> State:
        row = await StateModel.filter(name=self.name).get_or_none()
        if row is None:
            return State()
        return row.to_state()

    async def save(self, state: State, transferred_docs: int):
        m = StateModel(
            name=self.name,
            timestamp=state.timestamp,
            value=state.value,
            transferred=transferred_docs,
        )
        if self.dry_run:
            self.logger.info("[DRY_RUN] saving state to db")
        else:
            self.logger.info("saving state to db")
            await m.save(update_fields=["timestamp", "log_offset", "transferred"])

    async def cleanup(self):
        if self.dry_run:
            self.logger.info("[DRY_RUN] cleaning up state %s", self.name)
        else:
            self.logger.info("cleaning up state %s", self.name)
            await StateModel.filter(name=self.name).delete()
