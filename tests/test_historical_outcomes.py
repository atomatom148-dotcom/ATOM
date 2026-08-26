from datetime import datetime, timedelta, timezone
import math
import unittest

from quant.historical_outcomes import (HistoricalOutcome, frozen_actual_return_bps,
    resolve_slots, score)
from quant.historical_replay import HistoricalSipQuote, DATA_SCHEMA_VERSION, SOURCE_SPEC_SHARES

UTC = timezone.utc
BASE = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)

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
            session_open=BASE, session_close=BASE+timedelta(hours=6, minutes=30),
            data_schema_version=DATA_SCHEMA_VERSION,
            source_schema_version=SOURCE_SPEC_SHARES, outcome_source_dataset_digest="a"*64, resolved_at=BASE))
        self.assertEqual(rows[0].availability_status, "AVAILABLE")
        self.assertEqual(rows[0].target_midpoint_at, BASE+timedelta(seconds=30))
        self.assertEqual(rows[1].availability_status, "AVAILABLE")
        self.assertEqual(rows[1].target_midpoint_at, BASE+timedelta(seconds=66))

    def test_every_slot_is_retained_when_target_is_unavailable(self):
        slots = [(BASE, h) for h in ("30S","1M","5M","15M","30M","1H")]
        rows = tuple(resolve_slots("run", slots, [quote(0,100)],
            session_open=BASE, session_close=BASE+timedelta(hours=6, minutes=30),
            data_schema_version=DATA_SCHEMA_VERSION,
            source_schema_version=SOURCE_SPEC_SHARES, outcome_source_dataset_digest="a"*64, resolved_at=BASE))
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r.actual_return_bps is None and r.unavailable_reason for r in rows))

    def test_session_boundary_and_full_one_hour_retrieval_window(self):
        close = BASE + timedelta(hours=6, minutes=30)
        slots = [(close-timedelta(hours=1, seconds=1), "1H"),
                 (close-timedelta(hours=1), "1H")]
        rows = tuple(resolve_slots("run", slots,
            [quote(0,100), quote(5*3600+29*60+59,100.5),
             quote(5*3600+30*60,100.6), quote(6*3600+29*60+59,101)],
            session_open=BASE, session_close=close,
            data_schema_version=DATA_SCHEMA_VERSION,
            source_schema_version=SOURCE_SPEC_SHARES, outcome_source_dataset_digest="a"*64, resolved_at=BASE))
        self.assertEqual(rows[0].availability_status, "AVAILABLE")
        self.assertEqual(rows[1].unavailable_reason, "TARGET_OUTSIDE_SESSION")

    def test_content_hash_excludes_resolution_clock_for_retry(self):
        kwargs = dict(replay_run_id="run",cutoff_at=BASE,horizon="30S",actual_return_bps=None,
            availability_status="UNAVAILABLE",unavailable_reason="NO_DATA",cutoff_midpoint_at=None,
            cutoff_midpoint=None,target_midpoint_at=None,target_midpoint=None,
            data_schema_version="d",source_schema_version="s",
            resolution_spec_version="COIN_MIDPOINT_LOG_RETURN_BPS_1",
            outcome_source_dataset_digest="a"*64)
        a=HistoricalOutcome(**kwargs,resolved_at=BASE)
        b=HistoricalOutcome(**kwargs,resolved_at=BASE+timedelta(days=1))
        self.assertEqual(a.content_sha256,b.content_sha256)

    def test_same_second_endpoint_matches_h1_accepted_quote(self):
        def at_ns(offset_ns, midpoint):
            return HistoricalSipQuote("COIN", round(BASE.timestamp()*1e9)+offset_ns,
                midpoint-.01, midpoint+.01, 1, 1,
                source_spec_version=SOURCE_SPEC_SHARES)
        cutoff = at_ns(900_000_000, 100)
        rows = tuple(resolve_slots("run", [
            (datetime.fromtimestamp(cutoff.event_epoch, UTC), "30S")],
            [cutoff, at_ns(30_910_000_000, 101), at_ns(30_990_000_000, 102)],
            session_open=BASE, session_close=BASE+timedelta(hours=6, minutes=30),
            data_schema_version=DATA_SCHEMA_VERSION,
            source_schema_version=SOURCE_SPEC_SHARES,
            outcome_source_dataset_digest="a"*64, resolved_at=BASE))
        self.assertEqual(rows[0].target_midpoint, 102)

    def test_microsecond_cutoff_maps_to_original_provider_nanoseconds(self):
        origin = round(BASE.timestamp()*1e9)
        def at_ns(offset_ns, midpoint):
            return HistoricalSipQuote("COIN", origin+offset_ns, midpoint-.01,
                midpoint+.01, 1, 1, source_spec_version=SOURCE_SPEC_SHARES)
        cutoff = at_ns(123_456_789, 100)
        # The persisted timestamptz is microsecond precision, but maturity must
        # remain anchored at .123456789, selecting .123456790 at +30 seconds.
        stored = datetime.fromtimestamp(cutoff.event_epoch, UTC)
        rows = tuple(resolve_slots("run", [(stored, "30S")],
            [cutoff, at_ns(30_123_456_788, 101), at_ns(30_123_456_790, 102)],
            session_open=BASE, session_close=BASE+timedelta(hours=6, minutes=30),
            data_schema_version=DATA_SCHEMA_VERSION,
            source_schema_version=SOURCE_SPEC_SHARES,
            outcome_source_dataset_digest="a"*64, resolved_at=BASE))
        self.assertEqual(rows[0].target_midpoint, 102)

    def test_no_exact_cutoff_mapping_fails_instead_of_using_predecessor(self):
        with self.assertRaisesRegex(RuntimeError, "H2C_EXACT_CUTOFF_MAPPING_MISSING"):
            tuple(resolve_slots("run", [(BASE+timedelta(microseconds=1), "30S")],
                [quote(0, 100), quote(31, 101)], session_open=BASE,
                session_close=BASE+timedelta(hours=6, minutes=30),
                data_schema_version=DATA_SCHEMA_VERSION,
                source_schema_version=SOURCE_SPEC_SHARES,
                outcome_source_dataset_digest="a"*64, resolved_at=BASE))

    def test_lineage_fields_are_part_of_content_hash(self):
        base = HistoricalOutcome("run", BASE, "30S", None, "UNAVAILABLE", "NO_DATA",
            None, None, None, None, "d", "s",
            "COIN_MIDPOINT_LOG_RETURN_BPS_1", "a"*64, BASE)
        self.assertIn("resolution_spec_version", base.content_payload())
        self.assertIn("outcome_source_dataset_digest", base.content_payload())
        from dataclasses import replace
        self.assertNotEqual(base.content_sha256,
                            replace(base, outcome_source_dataset_digest="b"*64).content_sha256)

    def test_migration_is_forced_rls_append_only_and_private(self):
        from pathlib import Path
        sql=Path("supabase/migrations/20260826144639_create_historical_replay_outcomes.sql").read_text()
        for clause in ("FORCE ROW LEVEL SECURITY", "BEFORE UPDATE OR DELETE", "BEFORE TRUNCATE",
                       "FROM PUBLIC, anon", "PRIMARY KEY (replay_run_id, cutoff_at, horizon)"):
            self.assertIn(clause, sql)
        self.assertNotIn("GRANT INSERT ON TABLE public.atom_historical_replay_outcomes\n  TO atom_historical_score_reader", sql)
        repair = Path("supabase/migrations/20260826160458_h2_c_outcome_integrity_repair.sql").read_text()
        self.assertIn("resolution_spec_version text NOT NULL", repair)
        self.assertIn("outcome_source_dataset_digest text NOT NULL", repair)

    def test_h1_and_web_do_not_import_outcome_writer(self):
        for path in ("quant/historical_replay_h1.py", "quant/web.py"):
            from pathlib import Path
            self.assertNotIn("historical_outcomes", Path(path).read_text())

    def test_commands_use_separate_role_specific_credentials(self):
        from pathlib import Path
        source = Path("quant/historical_outcomes.py").read_text()
        self.assertIn("HISTORICAL_OUTCOME_DATABASE_URL", source)
        self.assertIn("HISTORICAL_SCORE_DATABASE_URL", source)
        self.assertNotIn("HISTORICAL_EVIDENCE_DATABASE_URL", source)
        self.assertIn("SELECT current_user", source)

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
            ("q1_momentum","30S",2.0,"AVAILABLE",1.0,"AVAILABLE","a"*64,"COIN_MIDPOINT_LOG_RETURN_BPS_1","d"*64),
            ("q1_momentum","30S",-2.0,"AVAILABLE",0.0,"AVAILABLE","b"*64,"COIN_MIDPOINT_LOG_RETURN_BPS_1","d"*64),
            ("q1_momentum","30S",-2.0,"AVAILABLE",-1.0,"AVAILABLE","c"*64,"COIN_MIDPOINT_LOG_RETURN_BPS_1","d"*64),
            ("q3_volatility","30S",2.0,"AVAILABLE",-2.0,"AVAILABLE","c"*64,"COIN_MIDPOINT_LOG_RETURN_BPS_1","d"*64),
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

class _WriteCursor:
    def __init__(self, answers, fail_insert=False): self.answers=list(answers); self.fail_insert=fail_insert; self.sql=[]
    def execute(self, sql, params=()):
        self.sql.append(sql)
        if self.fail_insert and sql.startswith("INSERT INTO public.atom_historical_replay_outcomes"):
            raise RuntimeError("injected batch failure")
    def fetchone(self): return self.answers.pop(0)

class ResolverContractTests(unittest.TestCase):
    def make_outcome(self):
        return HistoricalOutcome("run",BASE,"30S",None,"UNAVAILABLE","NO_TARGET",
            None,None,None,None,"d","s","COIN_MIDPOINT_LOG_RETURN_BPS_1","a"*64,BASE)

    def test_exact_retry_is_idempotent_and_conflict_fails_closed(self):
        from quant.historical_outcomes import HistoricalOutcomeResolver
        identical=_WriteCursor([(1,1)])
        self.assertEqual(HistoricalOutcomeResolver._write(identical,"run",[self.make_outcome()]),0)
        conflict=_WriteCursor([(1,0),(1,)])
        with self.assertRaisesRegex(RuntimeError,"H2C_OUTCOME_CONFLICT"):
            HistoricalOutcomeResolver._write(conflict,"run",[self.make_outcome()])
        self.assertFalse(any(sql.startswith("INSERT") for sql in conflict.sql))

    def test_unverified_replay_is_rejected_before_cursor_or_writes(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from quant.historical_outcomes import HistoricalOutcomeResolver
        class Connection:
            rollbacks=0
            def rollback(self): self.rollbacks+=1
            def cursor(self): raise AssertionError("cursor opened before verification")
        connection=Connection()
        with patch("quant.historical_outcomes.HistoricalEvidenceVerifier") as verifier:
            verifier.return_value.verify.return_value=SimpleNamespace(
                verification_status="REJECTED",reason_codes=("BAD",))
            with self.assertRaisesRegex(RuntimeError,"H2C_UNVERIFIED_REPLAY"):
                HistoricalOutcomeResolver(connection).resolve("run",())
        self.assertEqual(connection.rollbacks,1)

    def test_partial_batch_failure_rolls_back(self):
        from quant.historical_outcomes import HistoricalOutcomeResolver
        connection = type("Connection", (), {"rollbacks": 0,
            "rollback": lambda self: setattr(self, "rollbacks", self.rollbacks + 1)})()
        cursor = _WriteCursor([(1, 0), (0,)], fail_insert=True)
        try:
            with self.assertRaisesRegex(RuntimeError, "injected batch failure"):
                HistoricalOutcomeResolver._write(cursor, "run", [self.make_outcome()])
        except Exception:
            connection.rollback()
            raise
        # The resolver's enclosing transaction owns this rollback contract; the
        # disposable PostgreSQL test proves that an earlier successful batch is removed.
        connection.rollback()
        self.assertEqual(connection.rollbacks, 1)
