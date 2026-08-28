"""Canonical, read-only provenance receipt for an offline V2 state build."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math


RECEIPT_SCHEMA_VERSION = "V9-V2-BUILD-RECEIPT-1"
RESOURCE_RECEIPT_SCHEMA_VERSION = "V9-V2-BUILD-RECEIPT-2"


@dataclass(frozen=True, slots=True)
class V2BuildReceipt:
    receipt_schema_version: str
    state_id: str
    state_as_of: float
    stored_forecast_rows: int
    resolved_evidence_rows: int
    source_rows_read: int
    eligible_rows: int
    admitted_rows: int
    rejected_rows: int
    pages_read: int
    page_size: int
    first_source_identity: str | None
    last_source_identity: str | None
    per_horizon_admitted_counts: tuple[tuple[str, int], ...]
    per_family_horizon_admitted_counts: tuple[tuple[str, str, int], ...]
    per_family_horizon_effective_n: tuple[tuple[str, str, float], ...]
    build_elapsed_seconds: float
    peak_rss_bytes: int
    evidence_manifest_hash: str
    receipt_sha256: str
    temporary_disk_peak_bytes: int | None = None


def _identity_payload(receipt: V2BuildReceipt) -> dict[str, object]:
    """Return stable evidence identity; volatile resource telemetry is metadata."""

    payload = asdict(receipt)
    payload.pop("receipt_sha256")
    payload.pop("build_elapsed_seconds")
    payload.pop("peak_rss_bytes")
    payload.pop("temporary_disk_peak_bytes")
    return payload


def receipt_sha256(receipt: V2BuildReceipt) -> str:
    encoded = json.dumps(_identity_payload(receipt), sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_nonnegative_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _validate_receipt_contents(receipt: V2BuildReceipt) -> None:
    """Enforce the frozen receipt contract for both new and stored values."""

    if receipt.receipt_schema_version not in (
            RECEIPT_SCHEMA_VERSION, RESOURCE_RECEIPT_SCHEMA_VERSION):
        raise ValueError("receipt schema version is invalid")
    if receipt.receipt_schema_version == RECEIPT_SCHEMA_VERSION:
        if receipt.temporary_disk_peak_bytes is not None:
            raise ValueError("v1 receipt cannot contain temporary disk telemetry")
    elif not _is_nonnegative_int(receipt.temporary_disk_peak_bytes):
        raise ValueError("v2 receipt requires temporary disk telemetry")
    if (
        not isinstance(receipt.state_id, str)
        or not receipt.state_id.startswith("v9v2:")
        or not _is_sha256(receipt.state_id.removeprefix("v9v2:"))
    ):
        raise ValueError("receipt state identity is invalid")
    if (
        isinstance(receipt.state_as_of, bool)
        or not isinstance(receipt.state_as_of, (int, float))
        or not math.isfinite(float(receipt.state_as_of))
    ):
        raise ValueError("receipt contains non-finite values")
    if (
        isinstance(receipt.build_elapsed_seconds, bool)
        or not isinstance(receipt.build_elapsed_seconds, (int, float))
        or not math.isfinite(float(receipt.build_elapsed_seconds))
    ):
        raise ValueError("receipt contains non-finite values")
    if receipt.build_elapsed_seconds < 0:
        raise ValueError("receipt resource telemetry is invalid")

    counters = (
        receipt.stored_forecast_rows, receipt.resolved_evidence_rows,
        receipt.source_rows_read, receipt.eligible_rows, receipt.admitted_rows,
        receipt.rejected_rows, receipt.pages_read, receipt.page_size,
        receipt.peak_rss_bytes,
    )
    if (any(not _is_nonnegative_int(value) for value in counters)
            or receipt.page_size != 4_096):
        raise ValueError("receipt contains invalid counters")
    if receipt.rejected_rows != receipt.source_rows_read - receipt.admitted_rows:
        raise ValueError("receipt row accounting does not balance")
    if receipt.eligible_rows > receipt.source_rows_read:
        raise ValueError("eligible rows exceed source rows")
    if receipt.admitted_rows > receipt.eligible_rows:
        raise ValueError("admitted rows exceed eligible rows")
    if receipt.receipt_schema_version == RESOURCE_RECEIPT_SCHEMA_VERSION:
        if receipt.source_rows_read != receipt.stored_forecast_rows:
            raise ValueError("v2 receipt source rows must equal stored forecasts")
        if receipt.resolved_evidence_rows > receipt.stored_forecast_rows:
            raise ValueError("v2 receipt resolved evidence exceeds stored forecasts")
        if receipt.eligible_rows > receipt.resolved_evidence_rows:
            raise ValueError("v2 receipt eligible rows exceed resolved evidence")

    bounds = (receipt.first_source_identity, receipt.last_source_identity)
    if receipt.source_rows_read and any(
            not isinstance(value, str) or not value for value in bounds):
        raise ValueError("non-empty receipt requires source identity bounds")
    if not receipt.source_rows_read and any(value is not None for value in bounds):
        raise ValueError("empty receipt cannot have source identity bounds")
    if not _is_sha256(receipt.evidence_manifest_hash):
        raise ValueError("receipt evidence manifest hash is invalid")

    horizon_counts: dict[str, int] = {}
    if not isinstance(receipt.per_horizon_admitted_counts, tuple):
        raise ValueError("receipt count table is invalid")
    for row in receipt.per_horizon_admitted_counts:
        if (
            not isinstance(row, tuple)
            or len(row) != 2
            or not isinstance(row[0], str)
            or not row[0]
            or not _is_nonnegative_int(row[1])
            or row[0] in horizon_counts
        ):
            raise ValueError("receipt count table is invalid")
        horizon_counts[row[0]] = row[1]
    if sum(horizon_counts.values()) != receipt.admitted_rows:
        raise ValueError("receipt count table does not balance")

    family_counts: dict[tuple[str, str], int] = {}
    if not isinstance(receipt.per_family_horizon_admitted_counts, tuple):
        raise ValueError("receipt count table is invalid")
    for row in receipt.per_family_horizon_admitted_counts:
        if (
            not isinstance(row, tuple)
            or len(row) != 3
            or not isinstance(row[0], str)
            or not row[0]
            or not isinstance(row[1], str)
            or not row[1]
            or not _is_nonnegative_int(row[2])
            or (row[0], row[1]) in family_counts
        ):
            raise ValueError("receipt count table is invalid")
        family_counts[(row[0], row[1])] = row[2]
    grouped = {
        horizon: sum(count for (item_horizon, _family), count in family_counts.items()
                     if item_horizon == horizon)
        for horizon in horizon_counts
    }
    if (any(horizon not in horizon_counts for horizon, _family in family_counts)
            or grouped != horizon_counts):
        raise ValueError("receipt count table does not balance")

    effective_n_keys: set[tuple[str, str]] = set()
    if not isinstance(receipt.per_family_horizon_effective_n, tuple):
        raise ValueError("receipt count table is invalid")
    for row in receipt.per_family_horizon_effective_n:
        key = (row[0], row[1]) if isinstance(row, tuple) and len(row) == 3 else None
        value = row[2] if key is not None else None
        if (
            key is None
            or not isinstance(key[0], str)
            or not key[0]
            or not isinstance(key[1], str)
            or not key[1]
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
            or key in effective_n_keys
            or key not in family_counts
            or value > family_counts[key]
        ):
            raise ValueError("receipt count table is invalid")
        effective_n_keys.add(key)
    if effective_n_keys != set(family_counts):
        raise ValueError("receipt count table is incomplete")


def seal_receipt(receipt: V2BuildReceipt) -> V2BuildReceipt:
    if receipt.receipt_sha256:
        raise ValueError("receipt is already sealed")
    _validate_receipt_contents(receipt)
    sealed = replace(receipt, receipt_sha256=receipt_sha256(receipt))
    return sealed


def serialize_v2_build_receipt(receipt: V2BuildReceipt) -> str:
    if receipt.receipt_sha256 != receipt_sha256(receipt):
        raise ValueError("receipt hash mismatch")
    _validate_receipt_contents(receipt)
    payload = asdict(receipt)
    if receipt.receipt_schema_version == RECEIPT_SCHEMA_VERSION:
        payload.pop("temporary_disk_peak_bytes")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def deserialize_v2_build_receipt(payload: str | dict[str, object]) -> V2BuildReceipt:
    """Decode and verify canonical receipt JSON from immutable storage."""
    value = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(value, dict):
        raise ValueError("receipt payload is not an object")
    converted = dict(value)
    for name in ("per_horizon_admitted_counts",
                 "per_family_horizon_admitted_counts",
                 "per_family_horizon_effective_n"):
        rows = converted.get(name)
        if not isinstance(rows, list):
            raise ValueError("receipt count table is invalid")
        try:
            converted[name] = tuple(tuple(row) for row in rows)
        except TypeError as error:
            raise ValueError("receipt count table is invalid") from error
    try:
        receipt = V2BuildReceipt(**converted)
    except TypeError as error:
        raise ValueError("receipt payload shape is invalid") from error
    _validate_receipt_contents(receipt)
    if serialize_v2_build_receipt(receipt) != json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False):
        raise ValueError("receipt payload is not canonical")
    return receipt
