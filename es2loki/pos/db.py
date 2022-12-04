import asyncio

from tortoise import Model, Tortoise, fields

from es2loki.pos import Positions, PositionsStore


class PositionsModel(Model):
    class Meta:
        table = "positions"

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255, unique=True)
    timestamp = fields.BigIntField()
    log_offset = fields.IntField()
    transferred = fields.IntField()

    def to_positions(self) -> Positions:
        return Positions(
            timestamp=self.timestamp,
            log_offset=self.log_offset,
            transferred=self.transferred,
        )


class DBPositionsStore(PositionsStore):
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
                    db_url=self._url, modules={"models": ["es2loki.pos.db"]}
                )
                await Tortoise.generate_schemas()
                self.logger.error("connected successfully to db")
                return
            except Exception as e:
                self.logger.error("error creating db: %s", e)
                await asyncio.sleep(1.0)

    async def init(self, stop_event: asyncio.Event):
        await self.connect(stop_event)

    async def load(self) -> Positions:
        row = await PositionsModel.filter(name=self.name).get_or_none()
        if row is None:
            return Positions()
        return row.to_positions()

    async def save(self, pos: Positions, transferred_docs: int):
        m = PositionsModel(
            name=self.name,
            timestamp=pos.timestamp,
            log_offset=pos.log_offset,
            transferred=transferred_docs,
        )
        if self.dry_run:
            self.logger.info("[DRY_RUN] saving positions to db")
        else:
            self.logger.info("saving positions to db")
            await m.save(update_fields=["timestamp", "log_offset", "transferred"])

    async def cleanup(self):
        if self.dry_run:
            self.logger.info("[DRY_RUN] cleaning up positions %s", self.name)
        else:
            self.logger.info("cleaning up positions %s", self.name)
            await PositionsModel.filter(name=self.name).delete()
