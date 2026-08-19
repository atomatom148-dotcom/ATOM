"""Minimal single-owner forecast writer for Phase B2."""

from __future__ import annotations

import hashlib
import json

from .models import ExactSixBundle, HORIZONS, HorizonForecast, SetupState, Snapshot


_HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)


class UnifiedQuant:
    """Turn one snapshot into one exact-six, non-predictive bundle."""

    def __init__(self, policy_version: str = "phase-b2") -> None:
        self.policy_version = policy_version

    def write(self, snapshot: Snapshot, *, cycle_id: str) -> ExactSixBundle:
        """Write all six horizon rows from the same point-in-time snapshot.

        Phase B2 has no forecasting model.  A usable snapshot therefore yields
        an honest ``NO_SETUP`` rather than an invented direction or probability;
        an unusable snapshot yields ``UNAVAILABLE`` and preserves its reasons.
        """

        usable = snapshot.is_usable()
        setup_state = SetupState.NO_SETUP if usable else SetupState.UNAVAILABLE
        reason_codes = (
            []
            if usable
            else list(snapshot.reason_codes or ["UNUSABLE_SNAPSHOT"])
        )
        cutoff_epoch = snapshot.asof_epoch
        rows = [
            HorizonForecast(
                horizon=horizon,
                setup_state=setup_state,
                reason_codes=list(reason_codes),
                cutoff_epoch=cutoff_epoch,
                maturity_epoch=cutoff_epoch + seconds,
            )
            for horizon, seconds in zip(HORIZONS, _HORIZON_SECONDS)
        ]

        return ExactSixBundle(
            cycle_id=cycle_id,
            symbol=snapshot.symbol,
            cutoff_epoch=cutoff_epoch,
            snapshot_hash=_snapshot_hash(snapshot),
            policy_version=self.policy_version,
            rows=rows,
        )


def _snapshot_hash(snapshot: Snapshot) -> str:
    """Return a stable digest of all snapshot evidence consumed by the writer."""

    payload = {
        "asof_epoch": snapshot.asof_epoch,
        "ask": snapshot.ask,
        "bar_close": snapshot.bar_close,
        "bid": snapshot.bid,
        "fresh": snapshot.fresh,
        "last": snapshot.last,
        "reason_codes": snapshot.reason_codes,
        "source": snapshot.source,
        "symbol": snapshot.symbol,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["UnifiedQuant"]
