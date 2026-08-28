"""Canonical, read-only provenance receipt for an offline V2 state build."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math


RECEIPT_SCHEMA_VERSION = "V9-V2-BUILD-RECEIPT-1"


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
    temporary_disk_peak_bytes: int
    evidence_manifest_hash: str
    receipt_sha256: str


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


def seal_receipt(receipt: V2BuildReceipt) -> V2BuildReceipt:
    if receipt.receipt_sha256:
        raise ValueError("receipt is already sealed")
    if not math.isfinite(receipt.state_as_of) or not math.isfinite(receipt.build_elapsed_seconds):
        raise ValueError("receipt contains non-finite values")
    if receipt.rejected_rows != receipt.source_rows_read - receipt.admitted_rows:
        raise ValueError("receipt row accounting does not balance")
    counters = (
        receipt.stored_forecast_rows, receipt.resolved_evidence_rows,
        receipt.source_rows_read, receipt.eligible_rows, receipt.admitted_rows,
        receipt.rejected_rows, receipt.pages_read, receipt.page_size,
        receipt.peak_rss_bytes, receipt.temporary_disk_peak_bytes,
    )
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
           for value in counters) or receipt.page_size != 4_096:
        raise ValueError("receipt contains invalid counters")
    if receipt.eligible_rows > receipt.source_rows_read:
        raise ValueError("eligible rows exceed source rows")
    if receipt.admitted_rows > receipt.eligible_rows:
        raise ValueError("admitted rows exceed eligible rows")
    if receipt.source_rows_read and (
            receipt.first_source_identity is None or
            receipt.last_source_identity is None):
        raise ValueError("non-empty receipt requires source identity bounds")
    if not receipt.source_rows_read and (
            receipt.first_source_identity is not None or
            receipt.last_source_identity is not None):
        raise ValueError("empty receipt cannot have source identity bounds")
    if (len(receipt.evidence_manifest_hash) != 64 or
            any(character not in "0123456789abcdef"
                for character in receipt.evidence_manifest_hash)):
        raise ValueError("receipt evidence manifest hash is invalid")
    sealed = replace(receipt, receipt_sha256=receipt_sha256(receipt))
    return sealed


def serialize_v2_build_receipt(receipt: V2BuildReceipt) -> str:
    if receipt.receipt_sha256 != receipt_sha256(receipt):
        raise ValueError("receipt hash mismatch")
    return json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":"),
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
        converted[name] = tuple(tuple(row) for row in rows)
    try:
        receipt = V2BuildReceipt(**converted)
    except TypeError as error:
        raise ValueError("receipt payload shape is invalid") from error
    if serialize_v2_build_receipt(receipt) != json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False):
        raise ValueError("receipt payload is not canonical")
    return receipt
