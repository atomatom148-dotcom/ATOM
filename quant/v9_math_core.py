"""Pure numerical boundary for the future simplified V9 mathematical core."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class V9MathInput:
    """The complete input accepted by the V9 mathematical core boundary."""

    symbol: str
    as_of_epoch: float

    def __post_init__(self) -> None:
        if not isfinite(self.as_of_epoch):
            raise ValueError("as_of_epoch must be finite")


@dataclass(frozen=True)
class V9MathState:
    """The deterministic numerical state emitted by the boundary."""

    symbol: str
    as_of_epoch: float
    status: str


class V9MathCore:
    """Evaluate the isolated Phase 1A mathematical boundary."""

    @staticmethod
    def evaluate(value: V9MathInput) -> V9MathState:
        return V9MathState(
            symbol=value.symbol,
            as_of_epoch=value.as_of_epoch,
            status="EMPTY",
        )
