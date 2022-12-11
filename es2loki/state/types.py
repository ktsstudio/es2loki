from dataclasses import dataclass, field
from typing import Optional


@dataclass
class State:
    timestamp: Optional[str] = None
    transferred: int = 0
    value: list = field(default_factory=list)

    @property
    def iszero(self):
        return self.timestamp is None
