#!/usr/bin/env python3
"""Non-production benchmark for the V2 external-memory architecture spike.

This deliberately measures only the proposed page-to-disk and ordered-pass
boundary.  It neither imports production V2 code nor connects to a database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sqlite3
import tempfile
import time
from pathlib import Path


PAGE_SIZE = 4_096


def canonical_row(record_id: int) -> bytes:
    horizon = ("30S", "1M", "5M", "15M", "30M", "1H")[record_id % 6]
    row = [horizon, float(1_700_000_000 + record_id).hex(), record_id,
           f"cycle-{record_id:09d}", (record_id % 20_001 - 10_000) / 100.0]
    return json.dumps(row, separators=(",", ":"), ensure_ascii=True).encode()


def run(row_count: int, root: Path | None = None) -> dict[str, object]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="atom-v2-spike-", dir=root) as name:
        workspace = Path(name)
        database = workspace / "working.sqlite3"
        connection = sqlite3.connect(database)
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("CREATE TABLE evidence (horizon TEXT NOT NULL, cutoff INTEGER NOT NULL, record_id INTEGER NOT NULL, payload BLOB NOT NULL, PRIMARY KEY (horizon, cutoff, record_id)) WITHOUT ROWID")
        expected = hashlib.sha256()
        for page_start in range(0, row_count, PAGE_SIZE):
            rows = []
            for record_id in range(page_start, min(page_start + PAGE_SIZE, row_count)):
                payload = canonical_row(record_id)
                decoded = json.loads(payload)
                rows.append((decoded[0], record_id, record_id, payload))
            connection.executemany("INSERT INTO evidence VALUES (?, ?, ?, ?)", rows)
            connection.commit()
        connection.execute("VACUUM")
        disk_bytes = sum(path.stat().st_size for path in workspace.iterdir())
        observed = hashlib.sha256()
        scanned = 0
        for (payload,) in connection.execute(
                "SELECT payload FROM evidence ORDER BY horizon, cutoff, record_id"):
            observed.update(payload)
            scanned += 1
        # Recreate the expected total order arithmetically.  Do not sort a
        # Python list here: that would invalidate the bounded-memory measure.
        for remainder in (3, 5, 1, 4, 0, 2):  # lexical horizon order
            for record_id in range(remainder, row_count, 6):
                expected.update(canonical_row(record_id))
        connection.close()
        if scanned != row_count or observed.digest() != expected.digest():
            raise AssertionError("ordered external pass changed canonical rows")
        result = {
            "rows": row_count,
            "page_size": PAGE_SIZE,
            "pages": (row_count + PAGE_SIZE - 1) // PAGE_SIZE,
            "ordered_sha256": observed.hexdigest(),
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "temporary_disk_bytes": disk_bytes,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
        }
    result["workspace_removed"] = not workspace.exists()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rows", type=int)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.rows < 0:
        parser.error("rows must be non-negative")
    print(json.dumps(run(args.rows, args.root), sort_keys=True))


if __name__ == "__main__":
    main()
