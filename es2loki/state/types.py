from dataclasses import dataclass, field


@dataclass
class State:
    timestamp: str = 0
    transferred: int = 0
    value: list = field(default_factory=list)

    @property
    def iszero(self):
        return self.timestamp == 0
