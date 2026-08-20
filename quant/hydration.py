"""Exact restoration of previously stored exact-six evidence for Phase D4."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import math
from typing import Any

from .ledger import Ledger, LedgerRecord
from .models import ExactSixBundle, HorizonForecast, SetupState


_RECORD_KEYS = {"bundle", "committed_at_epoch"}
_BUNDLE_KEYS = {
    "cycle_id",
    "symbol",
    "cutoff_epoch",
    "snapshot_hash",
    "policy_version",
    "rows",
}
_ROW_KEYS = {
    "horizon",
    "setup_state",
    "direction",
    "probability",
    "reason_codes",
    "cutoff_epoch",
    "maturity_epoch",
}


def store_exact_six(record: LedgerRecord) -> dict[str, Any]:
    """Return a detached, JSON-compatible representation of stored evidence."""

    bundle = record.bundle
    return {
        "bundle": bundle.to_dict(),
        "committed_at_epoch": record.committed_at_epoch,
    }


def hydrate_exact_six(
    stored_evidence: Mapping[str, object],
    ledger: Ledger,
) -> LedgerRecord:
    """Restore one exact-six record without producing or altering a forecast."""

    evidence = _mapping_with_exact_keys(
        stored_evidence, _RECORD_KEYS, "stored evidence"
    )
    bundle_values = _mapping_with_exact_keys(
        evidence["bundle"], _BUNDLE_KEYS, "stored bundle"
    )
    rows_value = bundle_values["rows"]
    if (
        not isinstance(rows_value, Sequence)
        or isinstance(rows_value, (str, bytes, bytearray))
    ):
        raise ValueError("stored rows must be a sequence")

    rows: list[HorizonForecast] = []
    for index, stored_row in enumerate(rows_value):
        row = _mapping_with_exact_keys(
            stored_row, _ROW_KEYS, f"stored row {index}"
        )
        reason_codes = row["reason_codes"]
        if (
            not isinstance(reason_codes, Sequence)
            or isinstance(reason_codes, (str, bytes, bytearray))
            or any(not isinstance(reason, str) for reason in reason_codes)
        ):
            raise ValueError("stored reason_codes must be a sequence of strings")

        try:
            setup_state = SetupState(
                _required_string(row["setup_state"], "setup_state")
            )
        except ValueError as error:
            raise ValueError("stored setup_state is invalid") from error
        direction = row["direction"]
        if direction is not None and not isinstance(direction, str):
            raise ValueError("stored direction must be a string or null")
        probability = row["probability"]
        if probability is not None:
            probability = _finite_number(probability, "probability")

        rows.append(
            HorizonForecast(
                horizon=_required_string(row["horizon"], "horizon"),
                setup_state=setup_state,
                direction=direction,
                probability=probability,
                reason_codes=list(reason_codes),
                cutoff_epoch=_finite_number(row["cutoff_epoch"], "row cutoff"),
                maturity_epoch=_finite_number(
                    row["maturity_epoch"], "row maturity"
                ),
            )
        )

    bundle = ExactSixBundle(
        cycle_id=_required_string(bundle_values["cycle_id"], "cycle_id"),
        symbol=_required_string(bundle_values["symbol"], "symbol"),
        cutoff_epoch=_finite_number(bundle_values["cutoff_epoch"], "cutoff"),
        snapshot_hash=_required_string(
            bundle_values["snapshot_hash"], "snapshot_hash"
        ),
        policy_version=_required_string(
            bundle_values["policy_version"], "policy_version"
        ),
        rows=rows,
    )
    return ledger.commit(
        bundle,
        committed_at_epoch=_finite_number(
            evidence["committed_at_epoch"], "commit timestamp"
        ),
    )


def _mapping_with_exact_keys(
    value: object, keys: set[str], label: str
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"{label} must contain its exact stored fields")
    return value


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"stored {label} must be a non-empty string")
    return value


def _finite_number(value: object, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"stored {label} must be finite")
    return deepcopy(value)


__all__ = ["hydrate_exact_six", "store_exact_six"]
