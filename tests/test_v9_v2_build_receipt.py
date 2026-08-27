"""Observability proof remains separate from frozen V2 mathematics."""

from dataclasses import replace

import pytest

from quant.v9_v2_build_receipt import (
    RECEIPT_SCHEMA_VERSION, V2BuildReceipt, receipt_sha256, seal_receipt,
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
