from dataclasses import dataclass


@dataclass
class Positions:
    timestamp: int = 0
    log_offset: int = 0
    transferred: int = 0

    @property
    def iszero(self):
        return self.timestamp == 0
