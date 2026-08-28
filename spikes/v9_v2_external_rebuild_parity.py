#!/usr/bin/env python3
"""Fresh-process resource gate for the production external V2 rebuild.

The synthetic source behaves like a keyset-paged PostgreSQL snapshot without
retaining the requested evidence cardinality in Python.  It therefore measures
the rebuild rather than a list-backed test fixture.  Use ``--source-rows
200000`` for the release measurement; the focused test uses a smaller boundary
cardinality so ordinary CI remains practical.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import resource
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant.evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION  # noqa: E402
from quant.v9_production import FORMULA_VERSIONS  # noqa: E402
from quant.v9_v1_contract import HORIZONS, HORIZON_SECONDS  # noqa: E402
from quant.v9_v2_external_rebuild import rebuild_external_v2  # noqa: E402


NOW = 2_000_000_000.0
PAGE_SIZE = 4_096
Q3 = "q3_volatility"
DIRECTIONAL_VERSIONS = tuple(
    item for item in FORMULA_VERSIONS if item[0] != Q3
)
Q3_VERSION = dict(FORMULA_VERSIONS)[Q3]


def _rss_bytes() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


class SyntheticCursor:
    """Generate ordered source pages from integer positions in constant RAM."""

    def __init__(self, source_rows: int):
        # PostgreSQL orders the text horizon key lexicographically.  The V1
        # contract order is semantic rather than lexical, so the source fake
        # must keep those two orders distinct to exercise keyset advancement.
        self._source_horizons = tuple(sorted(HORIZONS))
        base, remainder = divmod(source_rows, len(HORIZONS))
        self._source_counts = tuple(
            base + int(index < remainder) for index in range(len(HORIZONS))
        )
        self._source_offsets = []
        total = 0
        for count in self._source_counts:
            self._source_offsets.append(total)
            total += count
        self._directional_counts = tuple(
            (count // 12) * 11 + count % 12 for count in self._source_counts
        )
        self._magnitude_counts = tuple(count // 12 for count in self._source_counts)
        self._positions = {False: 0, True: 0}
        self._last_keys: dict[bool, tuple[str, float, int] | None] = {
            False: None,
            True: None,
        }
        self._page: tuple[tuple[object, ...], ...] = ()
        self._snapshot = False
        self._advisory: str | None = None

    def execute(self, sql: str, parameters: tuple[object, ...]) -> None:
        if "pg_try_advisory_lock" in sql:
            self._advisory = "lock"
            self._page = ()
            return
        if "pg_advisory_unlock" in sql:
            self._advisory = "unlock"
            self._page = ()
            return
        self._advisory = None
        self._snapshot = "transaction_timestamp" in sql
        if self._snapshot or "FROM public." not in sql:
            self._page = ()
            return
        volatility = "volatility_forecasts" in sql
        if len(parameters) > 8:
            supplied = tuple(parameters[-4:-1])
            if supplied != self._last_keys[volatility]:
                raise AssertionError("external rebuild advanced the wrong keyset key")
        limit = int(parameters[-1])
        start = self._positions[volatility]
        rows = tuple(self._rows(volatility, start, limit))
        self._positions[volatility] += len(rows)
        self._page = rows
        if rows:
            last = rows[-1]
            self._last_keys[volatility] = (
                str(last[5]),
                float(last[6]),
                int(last[0]),
            )

    def fetchone(self) -> tuple[float]:
        if self._advisory is not None:
            return (True,)
        return (NOW,)

    def fetchall(self) -> tuple[tuple[object, ...], ...]:
        return self._page

    def close(self) -> None:
        return None

    def _rows(self, volatility: bool, start: int, limit: int):
        counts = self._magnitude_counts if volatility else self._directional_counts
        remaining = limit
        position = start
        for horizon_index, count in enumerate(counts):
            if position >= count:
                position -= count
                continue
            take = min(remaining, count - position)
            for local in range(position, position + take):
                yield self._row(volatility, horizon_index, local)
            remaining -= take
            if not remaining:
                return
            position = 0

    def _row(self, volatility: bool, horizon_index: int, local: int):
        horizon = self._source_horizons[horizon_index]
        seconds = HORIZON_SECONDS[horizon]
        source_offset = self._source_offsets[horizon_index]
        if volatility:
            sample = local
            family_index = 11
            quant_id = Q3
            formula = Q3_VERSION
        else:
            sample, family_index = divmod(local, 11)
            quant_id, formula = DIRECTIONAL_VERSIONS[family_index]
        record_id = source_offset + sample * 12 + family_index + 1
        cutoff = float(sample * seconds)
        maturity = cutoff + seconds
        cycle = f"{horizon}-{sample:08d}"
        target = float((sample % 17) + 1)
        if volatility:
            return (
                record_id,
                quant_id,
                formula,
                cycle,
                "COIN",
                horizon,
                cutoff,
                maturity,
                float((sample % 13) + 1),
                cutoff,
                DATA_SCHEMA_VERSION,
                SOURCE_SPEC_VERSION,
                maturity,
                cutoff,
                maturity,
                True,
            )
        source_as_of = None if quant_id == "q10_options_vol" else cutoff
        return (
            record_id,
            quant_id,
            formula,
            cycle,
            "COIN",
            horizon,
            cutoff,
            maturity,
            float((sample + family_index) % 19),
            cutoff,
            DATA_SCHEMA_VERSION,
            SOURCE_SPEC_VERSION,
            source_as_of,
            target,
            maturity,
            cutoff,
            maturity,
            True,
        )


class SyntheticConnection:
    def __init__(self, source_rows: int):
        self._cursor = SyntheticCursor(source_rows)

    def cursor(self) -> SyntheticCursor:
        return self._cursor

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


def run(source_rows: int, root: Path, max_rss_delta_bytes: int) -> dict[str, object]:
    if source_rows < 72:
        raise ValueError("source_rows must cover every frozen family/horizon slot")
    root.mkdir(parents=True, exist_ok=True)
    baseline = _rss_bytes()
    started = time.perf_counter()
    result = rebuild_external_v2(
        database_url="postgresql://synthetic",
        workspace_root=root,
        state_as_of=NOW - 1,
        connect=lambda _url: SyntheticConnection(source_rows),
        publish=False,
    )
    peak = _rss_bytes()
    elapsed = time.perf_counter() - started
    receipt = result.receipt
    directional_rows = sum(
        (count // 12) * 11 + count % 12
        for count in SyntheticCursor(source_rows)._source_counts
    )
    magnitude_rows = source_rows - directional_rows
    expected_pages = math.ceil(directional_rows / PAGE_SIZE) + math.ceil(
        magnitude_rows / PAGE_SIZE
    )
    leftovers = tuple(root.glob("atom-v2-external-rebuild-*"))
    if receipt.source_rows_read != source_rows:
        raise AssertionError("external rebuild did not read every synthetic source row")
    if receipt.pages_read != expected_pages:
        raise AssertionError("external rebuild receipt contains the wrong page count")
    if receipt.state_id != result.state.state_id:
        raise AssertionError("receipt does not identify the published candidate state")
    if receipt.evidence_manifest_hash != result.state.evidence_manifest_hash:
        raise AssertionError("receipt does not identify the candidate evidence manifest")
    if receipt.temporary_disk_peak_bytes != result.temporary_disk_peak_bytes:
        raise AssertionError("receipt does not contain the measured disk peak")
    if len(receipt.per_family_horizon_admitted_counts) != 72:
        raise AssertionError("external rebuild receipt does not cover all 72 slots")
    if len(receipt.per_family_horizon_effective_n) != 72:
        raise AssertionError("external rebuild effective-N table is incomplete")
    if result.state.creation_status != "VALID":
        raise AssertionError("external rebuild candidate is not valid")
    if leftovers:
        raise AssertionError("external rebuild did not clean its owned workspace")
    delta = max(0, peak - baseline)
    if delta >= max_rss_delta_bytes:
        raise AssertionError(
            f"external rebuild RSS delta {delta} exceeds {max_rss_delta_bytes}"
        )
    return {
        "state": result.state.creation_status,
        "state_id": result.state.state_id,
        "state_hash": result.state.state_hash,
        "receipt": "PRESENT",
        "receipt_sha256": receipt.receipt_sha256,
        "state_id_match": True,
        "manifest_match": True,
        "source_rows_read": receipt.source_rows_read,
        "admitted_rows": receipt.admitted_rows,
        "family_horizon_slots": len(
            receipt.per_family_horizon_admitted_counts
        ),
        "pages_read": receipt.pages_read,
        "baseline_rss_bytes": baseline,
        "peak_rss_bytes": peak,
        "peak_rss_delta_bytes": delta,
        "temporary_disk_peak_bytes": result.temporary_disk_peak_bytes,
        "cleanup": True,
        "elapsed_seconds": elapsed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-rows", type=int, default=8_208)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--max-rss-delta-bytes", type=int, default=128 * 1024 * 1024
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.source_rows, args.root, args.max_rss_delta_bytes),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
