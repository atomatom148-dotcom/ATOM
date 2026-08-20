"""Minimal single-owner forecast writer for Phase B2."""

from __future__ import annotations

import hashlib
import json

from .ledger import Ledger, LedgerRecord
from .models import ExactSixBundle, HORIZONS, HorizonForecast, SetupState, Snapshot


_HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)


def write_cycle(
    snapshot: Snapshot,
    ledger: Ledger,
    *,
    cycle_id: str,
    cutoff_epoch: float,
    committed_at_epoch: float,
    policy_version: str = "phase-b2",
    quant_id: str = "unified-quant",
    formula_version: str = "legacy",
) -> LedgerRecord:
    """Write and commit all six rows from one point-in-time snapshot.

    Phase B2 has no forecasting model. A usable snapshot therefore yields an
    honest ``NO_SETUP`` rather than an invented direction or probability; an
    unusable snapshot yields ``UNAVAILABLE`` and preserves its reasons.
    """

    usable = snapshot.is_usable()
    setup_state = SetupState.NO_SETUP if usable else SetupState.UNAVAILABLE
    reason_codes = (
        [] if usable else list(snapshot.reason_codes or ["UNUSABLE_SNAPSHOT"])
    )
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

    bundle = ExactSixBundle(
        cycle_id=cycle_id,
        symbol=snapshot.symbol,
        cutoff_epoch=cutoff_epoch,
        snapshot_hash=_snapshot_hash(snapshot),
        policy_version=policy_version,
        rows=rows,
        quant_id=quant_id,
        formula_version=formula_version,
    )
    return ledger.commit(bundle, committed_at_epoch=committed_at_epoch)


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


__all__ = ["write_cycle"]
