"""Phase C1 volatility/friction evidence.

This module classifies only the quality of market evidence.  It does not write
forecasts, choose a direction, assign a probability, or mutate the Phase B
pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

from .models import SetupState


@dataclass(frozen=True)
class VolFrictionPolicy:
    """Explicit thresholds for the small C1 evidence gate."""

    minimum_volatility: float
    maximum_friction: float

    def __post_init__(self) -> None:
        for name, value in (
            ("minimum_volatility", self.minimum_volatility),
            ("maximum_friction", self.maximum_friction),
        ):
            if not _is_non_negative_finite(value):
                raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True)
class VolFrictionEvidence:
    """Truthful result of applying the C1 gate to two scalar observations."""

    setup_state: SetupState
    volatility: Optional[float]
    friction: Optional[float]
    reason_codes: tuple[str, ...]


def evaluate_vol_friction(
    volatility: Optional[float],
    friction: Optional[float],
    policy: VolFrictionPolicy,
) -> VolFrictionEvidence:
    """Classify volatility and friction without inventing missing evidence.

    Invalid observations are unavailable.  Excess friction blocks a setup;
    otherwise insufficient volatility is a valid non-setup.  Observations on
    either threshold pass, making the comparison deterministic at boundaries.
    """

    reasons: list[str] = []
    if volatility is None:
        reasons.append("MISSING_VOLATILITY")
    elif not _is_non_negative_finite(volatility):
        reasons.append("INVALID_VOLATILITY")

    if friction is None:
        reasons.append("MISSING_FRICTION")
    elif not _is_non_negative_finite(friction):
        reasons.append("INVALID_FRICTION")

    if reasons:
        return VolFrictionEvidence(
            setup_state=SetupState.UNAVAILABLE,
            volatility=volatility,
            friction=friction,
            reason_codes=tuple(reasons),
        )

    # The checks above narrow both observations to valid floats at runtime.
    assert volatility is not None
    assert friction is not None
    if friction > policy.maximum_friction:
        return VolFrictionEvidence(
            SetupState.BLOCKED,
            volatility,
            friction,
            ("FRICTION_TOO_HIGH",),
        )
    if volatility < policy.minimum_volatility:
        return VolFrictionEvidence(
            SetupState.NO_SETUP,
            volatility,
            friction,
            ("VOLATILITY_TOO_LOW",),
        )
    return VolFrictionEvidence(
        SetupState.QUALIFIED,
        volatility,
        friction,
        (),
    )


def _is_non_negative_finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


__all__ = ["VolFrictionEvidence", "VolFrictionPolicy", "evaluate_vol_friction"]
