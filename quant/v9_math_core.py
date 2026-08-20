"""Pure, read-only boundary for the simplified V9 mathematical core."""

from dataclasses import dataclass
from math import isfinite


V9_HORIZONS = ("30S", "1M", "5M", "15M", "30M", "1H")


@dataclass(frozen=True, slots=True)
class V9QuantFamily:
    """An immutable copy of one canonical quant family's exact-six output."""

    quant_id: str
    formula_version: str
    horizon_values: tuple[float | None, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "horizon_values", tuple(self.horizon_values))
        if len(self.horizon_values) != len(V9_HORIZONS):
            raise ValueError("quant family must contain the exact six horizons")


@dataclass(frozen=True, slots=True)
class V9MathInput:
    """Immutable snapshot accepted by the V9 mathematical core boundary.

    ``families`` is deliberately an open-ended tuple rather than twelve named
    fields.  Each tuple position in a family's values corresponds to
    ``V9_HORIZONS`` and is an independent numerical input.
    """

    symbol: str
    as_of_epoch: float
    families: tuple[V9QuantFamily, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "families", tuple(self.families))
        if not isfinite(self.as_of_epoch):
            raise ValueError("as_of_epoch must be finite")


@dataclass(frozen=True, slots=True)
class V9MathState:
    """The deterministic numerical state emitted by the boundary."""

    symbol: str
    as_of_epoch: float
    status: str


class V9MathCore:
    """Observe an already-computed immutable quant snapshot."""

    @staticmethod
    def evaluate(value: V9MathInput) -> V9MathState:
        return V9MathState(
            symbol=value.symbol,
            as_of_epoch=value.as_of_epoch,
            status="OBSERVING" if value.families else "EMPTY",
        )


__all__ = ["V9_HORIZONS", "V9MathCore", "V9MathInput", "V9MathState", "V9QuantFamily"]
