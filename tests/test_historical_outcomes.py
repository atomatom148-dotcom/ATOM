from datetime import datetime, timedelta, timezone
import math
import unittest

from quant.historical_outcomes import (HistoricalOutcome, frozen_actual_return_bps,
    resolve_slots, score)
from quant.historical_replay import HistoricalSipQuote, DATA_SCHEMA_VERSION, SOURCE_SPEC_SHARES

UTC = timezone.utc
BASE = datetime(2026, 6, 15, 14, 30, tzinfo=UTC)

def quote(seconds, midpoint):
    return HistoricalSipQuote("COIN", round((BASE.timestamp()+seconds)*1e9),
        midpoint-.01, midpoint+.01, 1, 1, source_spec_version=SOURCE_SPEC_SHARES)

class OutcomeTests(unittest.TestCase):
    def test_frozen_log_return_target_positive_negative_and_zero(self):
        self.assertAlmostEqual(frozen_actual_return_bps(100, 101), 10000*math.log(1.01))
        self.assertLess(frozen_actual_return_bps(101, 100), 0)
        self.assertEqual(frozen_actual_return_bps(100, 100), 0)

    def test_strict_bracket_and_five_second_timing(self):
        rows = tuple(resolve_slots("run", [(BASE, "30S"), (BASE, "1M")],
            [quote(0,100), quote(29,101), quote(30,102), quote(66,103)],
            data_schema_version=DATA_SCHEMA_VERSION,
            source_schema_version=SOURCE_SPEC_SHARES, resolved_at=BASE))
        self.assertEqual(rows[0].availability_status, "AVAILABLE")
        self.assertEqual(rows[0].target_midpoint_at, BASE+timedelta(seconds=30))
        self.assertEqual(rows[1].unavailable_reason, "TARGET_ENDPOINT_DELAY_EXCEEDED")

    def test_every_slot_is_retained_when_target_is_unavailable(self):
        slots = [(BASE, h) for h in ("30S","1M","5M","15M","30M","1H")]
        rows = tuple(resolve_slots("run", slots, [quote(0,100)],
            data_schema_version=DATA_SCHEMA_VERSION,
            source_schema_version=SOURCE_SPEC_SHARES, resolved_at=BASE))
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r.actual_return_bps is None and r.unavailable_reason for r in rows))

    def test_content_hash_excludes_resolution_clock_for_retry(self):
        kwargs = dict(replay_run_id="run",cutoff_at=BASE,horizon="30S",actual_return_bps=None,
            availability_status="UNAVAILABLE",unavailable_reason="NO_DATA",cutoff_midpoint_at=None,
            cutoff_midpoint=None,target_midpoint_at=None,target_midpoint=None,
            data_schema_version="d",source_schema_version="s")
        a=HistoricalOutcome(**kwargs,resolved_at=BASE)
        b=HistoricalOutcome(**kwargs,resolved_at=BASE+timedelta(days=1))
        self.assertEqual(a.content_sha256,b.content_sha256)

    def test_migration_is_forced_rls_append_only_and_private(self):
        from pathlib import Path
        sql=Path("supabase/migrations/20260826144639_create_historical_replay_outcomes.sql").read_text()
        for clause in ("FORCE ROW LEVEL SECURITY", "BEFORE UPDATE OR DELETE", "BEFORE TRUNCATE",
                       "FROM PUBLIC, anon", "PRIMARY KEY (replay_run_id, cutoff_at, horizon)"):
            self.assertIn(clause, sql)
        self.assertNotIn("GRANT INSERT ON TABLE public.atom_historical_replay_outcomes\n  TO atom_historical_score_reader", sql)

    def test_h1_and_web_do_not_import_outcome_writer(self):
        for path in ("quant/historical_replay_h1.py", "quant/web.py"):
            from pathlib import Path
            self.assertNotIn("historical_outcomes", Path(path).read_text())

class _Cursor:
    def __init__(self, connection, named=False):
        self.connection=connection; self.named=named; self.rows=[]; self.index=0; self.itersize=0
    def execute(self, sql, params=()):
        if self.named:
            self.rows=list(self.connection.join_rows)
        elif "dataset_digest" in sql: self.rows=[("dataset","configuration")]
        elif "count(*) FROM public.atom_historical_replay_forecasts" in sql: self.rows=[(len(self.connection.join_rows),)]
        elif "count(*) FROM public.atom_historical_replay_outcomes" in sql: self.rows=[(3,)]
        else: raise AssertionError("scoring issued unexpected SQL: "+sql)
    def fetchone(self): return self.rows.pop(0) if self.rows else None
    def fetchmany(self,n):
        out=self.rows[self.index:self.index+n]; self.index+=len(out); return out
    def close(self): pass

class _Connection:
    def __init__(self, rows): self.join_rows=rows; self.statements=[]
    def cursor(self, name=None, binary=False): return _Cursor(self, name is not None)

class ScoringTests(unittest.TestCase):
    def _connection(self):
        return _Connection([
            ("q1_momentum","30S",2.0,"AVAILABLE",1.0,"AVAILABLE","a"*64),
            ("q1_momentum","30S",-2.0,"AVAILABLE",0.0,"AVAILABLE","b"*64),
            ("q1_momentum","30S",-2.0,"AVAILABLE",-1.0,"AVAILABLE","c"*64),
            ("q3_volatility","30S",2.0,"AVAILABLE",-2.0,"AVAILABLE","c"*64),
        ])
    def test_directional_positive_zero_negative_and_q3_magnitude(self):
        receipt=score(self._connection(),"run",fetch_size=2)
        q1=next(m for m in receipt.metrics if (m.quant_id,m.horizon)==("q1_momentum","30S"))
        q3=next(m for m in receipt.metrics if (m.quant_id,m.horizon)==("q3_volatility","30S"))
        self.assertEqual((q1.directional_wins,q1.directional_losses,q1.directional_accuracy),(2,1,2/3))
        self.assertEqual((q3.rmse,q3.mae,q3.bias),(0.0,0.0,0.0))
        self.assertIsNone(q3.directional_accuracy)
    def test_scoring_receipt_is_deterministic_and_select_only(self):
        self.assertEqual(score(self._connection(),"run"),score(self._connection(),"run"))
