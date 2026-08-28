"""Observability proof remains separate from frozen V2 mathematics."""

from dataclasses import asdict, replace
import json

import pytest

from quant.v9_v2_build_receipt import (
    RECEIPT_SCHEMA_VERSION, RESOURCE_RECEIPT_SCHEMA_VERSION, V2BuildReceipt,
    deserialize_v2_build_receipt, receipt_sha256, seal_receipt,
    serialize_v2_build_receipt,
)


def _receipt(**changes):
    value = V2BuildReceipt(
        RECEIPT_SCHEMA_VERSION, "v9v2:" + "a" * 64, 1_800_000_000.0,
        200_000, 200_000, 200_000, 199_999, 199_998, 2, 49, 4_096,
        "directional:1m:0x1.0p+0:1",
        "magnitude:24h:0x1.0p+1:200000",
        (("1m", 199_998),),
        (("1m", "q1_momentum", 199_998),
         ("1m", "q10_options_vol", 0)),
        (("1m", "q1_momentum", 123.25),
         ("1m", "q10_options_vol", 0.0)),
        12.5, 123_456_789, "b" * 64, "",
    )
    return replace(value, **changes)


def test_receipt_balances_counts_and_represents_unavailable_family():
    receipt = seal_receipt(_receipt())
    assert receipt.source_rows_read == receipt.admitted_rows + receipt.rejected_rows
    assert ("1m", "q10_options_vol", 0) in receipt.per_family_horizon_admitted_counts
    assert ("1m", "q10_options_vol", 0.0) in receipt.per_family_horizon_effective_n
    assert receipt.receipt_sha256 == receipt_sha256(receipt)
    assert '"receipt_sha256"' in serialize_v2_build_receipt(receipt)


def test_exact_retry_hash_ignores_only_resource_telemetry():
    first = seal_receipt(_receipt())
    retry = seal_receipt(_receipt(build_elapsed_seconds=999.0, peak_rss_bytes=999))
    assert retry.receipt_sha256 == first.receipt_sha256


def test_modified_terminal_source_identity_changes_hash():
    first = seal_receipt(_receipt())
    changed = seal_receipt(_receipt(
        last_source_identity="magnitude:24h:0x1.0p+1:200001"))
    assert changed.receipt_sha256 != first.receipt_sha256


def test_unbalanced_receipt_fails_closed():
    with pytest.raises(ValueError, match="does not balance"):
        seal_receipt(_receipt(rejected_rows=1))


@pytest.mark.parametrize(
    ("rows", "pages"),
    [(65_535, 16), (65_536, 16), (65_537, 17), (200_000, 49)],
)
def test_required_keyset_page_totals_have_no_hidden_ceiling(rows, pages):
    page_size = 4_096
    identities = range(1, rows + 1)
    observed = []
    for start in range(0, rows, page_size):
        observed.extend(identities[start:start + page_size])
    assert len(observed) == rows
    assert len(set(observed)) == rows
    assert observed[-1] == rows
    assert (rows + page_size - 1) // page_size == pages


def test_sealed_receipt_cannot_be_resealed():
    with pytest.raises(ValueError, match="already sealed"):
        seal_receipt(seal_receipt(_receipt()))


@pytest.mark.parametrize(
    "changes",
    (
        {"state_as_of": float("inf")},
        {"build_elapsed_seconds": float("nan")},
    ),
)
def test_nonfinite_receipt_values_fail_closed(changes):
    with pytest.raises(ValueError, match="non-finite"):
        seal_receipt(_receipt(**changes))


def test_tampered_sealed_receipt_cannot_be_serialized():
    receipt = seal_receipt(_receipt())
    tampered = replace(receipt, admitted_rows=receipt.admitted_rows - 1)
    with pytest.raises(ValueError, match="hash mismatch"):
        serialize_v2_build_receipt(tampered)


def test_canonical_receipt_round_trip_preserves_frozen_bytes():
    receipt = seal_receipt(_receipt())
    encoded = serialize_v2_build_receipt(receipt)

    assert deserialize_v2_build_receipt(encoded) == receipt
    assert serialize_v2_build_receipt(
        deserialize_v2_build_receipt(json.loads(encoded)),
    ) == encoded
    assert receipt.receipt_sha256 == (
        "f26c73e1174ca93227e86bdd5635569d6bc931f6fc2660b8a776396215b4550d"
    )
    assert "temporary_disk_peak_bytes" not in encoded


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"receipt_schema_version": "OTHER"}, "schema"),
        ({"eligible_rows": 200_001}, "eligible rows exceed"),
        ({"build_elapsed_seconds": -1.0}, "resource telemetry"),
        ({"peak_rss_bytes": True}, "invalid counters"),
        ({"per_horizon_admitted_counts": (("1m", -1),)}, "count table"),
    ),
)
def test_deserialize_revalidates_semantics_even_with_matching_hash(changes, message):
    invalid = replace(_receipt(), **changes)
    invalid = replace(invalid, receipt_sha256=receipt_sha256(invalid))
    payload = asdict(invalid)
    payload.pop("temporary_disk_peak_bytes")
    payload = json.loads(json.dumps(payload))

    with pytest.raises(ValueError, match=message):
        deserialize_v2_build_receipt(payload)


def test_deserialize_rejects_malformed_count_table_shape_as_value_error():
    receipt = seal_receipt(_receipt())
    payload = json.loads(serialize_v2_build_receipt(receipt))
    payload["per_horizon_admitted_counts"] = [["1m"]]

    with pytest.raises(ValueError, match="count table"):
        deserialize_v2_build_receipt(payload)


def test_resource_receipt_round_trip_includes_disk_without_hashing_telemetry():
    first = seal_receipt(replace(
        _receipt(),
        receipt_schema_version=RESOURCE_RECEIPT_SCHEMA_VERSION,
        temporary_disk_peak_bytes=248_316_014,
    ))
    retry = seal_receipt(replace(
        _receipt(),
        receipt_schema_version=RESOURCE_RECEIPT_SCHEMA_VERSION,
        build_elapsed_seconds=999.0,
        peak_rss_bytes=999,
        temporary_disk_peak_bytes=999_999,
    ))

    encoded = serialize_v2_build_receipt(first)
    decoded = deserialize_v2_build_receipt(encoded)
    assert decoded == first
    assert json.loads(encoded)["temporary_disk_peak_bytes"] == 248_316_014
    assert retry.receipt_sha256 == first.receipt_sha256
    assert first.receipt_sha256 != seal_receipt(_receipt()).receipt_sha256


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"source_rows_read": 199_999, "rejected_rows": 1},
         "source rows must equal stored"),
        ({"resolved_evidence_rows": 200_001},
         "resolved evidence exceeds stored"),
        ({"resolved_evidence_rows": 199_998},
         "eligible rows exceed resolved"),
    ),
)
def test_resource_receipt_distinguishes_source_resolution_and_eligibility(
        changes, message):
    value = replace(
        _receipt(),
        receipt_schema_version=RESOURCE_RECEIPT_SCHEMA_VERSION,
        temporary_disk_peak_bytes=1,
        **changes,
    )
    with pytest.raises(ValueError, match=message):
        seal_receipt(value)


@pytest.mark.parametrize(
    "disk",
    (None, -1, True, 1.5),
)
def test_resource_receipt_requires_nonnegative_integer_disk_telemetry(disk):
    with pytest.raises(ValueError, match="requires temporary disk telemetry"):
        seal_receipt(replace(
            _receipt(),
            receipt_schema_version=RESOURCE_RECEIPT_SCHEMA_VERSION,
            temporary_disk_peak_bytes=disk,
        ))


def test_v1_receipt_rejects_disk_field_and_deserializer_requires_it_absent():
    with pytest.raises(ValueError, match="v1 receipt cannot contain"):
        seal_receipt(replace(_receipt(), temporary_disk_peak_bytes=1))

    receipt = seal_receipt(_receipt())
    payload = json.loads(serialize_v2_build_receipt(receipt))
    payload["temporary_disk_peak_bytes"] = None
    with pytest.raises(ValueError, match="not canonical"):
        deserialize_v2_build_receipt(payload)


def test_v2_deserializer_rejects_missing_disk_telemetry():
    receipt = seal_receipt(replace(
        _receipt(),
        receipt_schema_version=RESOURCE_RECEIPT_SCHEMA_VERSION,
        temporary_disk_peak_bytes=1,
    ))
    payload = json.loads(serialize_v2_build_receipt(receipt))
    payload.pop("temporary_disk_peak_bytes")

    with pytest.raises(ValueError, match="requires temporary disk telemetry"):
        deserialize_v2_build_receipt(payload)
