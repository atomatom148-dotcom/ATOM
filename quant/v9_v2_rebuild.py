"""Explicit offline V2 rebuild command; never imported by the web runtime.

Run with ``python -m quant.v9_v2_rebuild`` from a background job.  The command
holds one PostgreSQL advisory lock from snapshot acquisition through atomic
state/receipt publication.  It does not delete or supersede existing states.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
import resource
import sys
import time

from .v9_production import PostgresV2StateBuilder
from .v9_v2_state_store import PostgresV2StateStore


_OWNER_LOCK = 0x41544F4D56325242  # "ATOMV2RB"


@dataclass(frozen=True, slots=True)
class SupplementalBuildTelemetry:
    """Noncanonical operational telemetry; deliberately absent from receipts."""

    elapsed_seconds: float
    peak_rss_bytes: int
    temporary_disk_peak_bytes: int


def rebuild(database_url: str, *, connect=None) -> tuple[str, SupplementalBuildTelemetry]:
    """Build and atomically publish one state while holding the rebuild lease."""

    if connect is None:
        import psycopg
        connect = psycopg.connect
    owner = connect(database_url)
    cursor = owner.cursor()
    started = time.perf_counter()
    try:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (_OWNER_LOCK,))
        row = cursor.fetchone()
        if row is None or row[0] is not True:
            raise RuntimeError("V2_REBUILD_ALREADY_RUNNING")
        builder = PostgresV2StateBuilder(database_url, connect=connect)
        state = builder.build()
        if builder.last_receipt is None:
            raise RuntimeError("V2_REBUILD_RECEIPT_UNAVAILABLE")
        result = PostgresV2StateStore(database_url, connect=connect).insert_with_receipt(
            state, builder.last_receipt,
        )
        rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
        return result, SupplementalBuildTelemetry(
            elapsed_seconds=time.perf_counter() - started,
            peak_rss_bytes=rss,
            temporary_disk_peak_bytes=0,
        )
    finally:
        try:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (_OWNER_LOCK,))
        finally:
            cursor.close()
            owner.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="offline ATOM V9 V2 rebuild worker")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    result, telemetry = rebuild(args.database_url)
    json.dump({"publication": result, "telemetry": asdict(telemetry)}, sys.stdout,
              sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
