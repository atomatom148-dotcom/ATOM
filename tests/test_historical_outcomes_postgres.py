"""Real PostgreSQL H2-C migration/security checks.

Set H2C_TEST_DATABASE_URL to a disposable, empty database owned by the login.
The fixture intentionally refuses a non-empty database and never targets production.
"""
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

URL = os.environ.get("H2C_TEST_DATABASE_URL")

@unittest.skipUnless(URL and psycopg, "H2C_TEST_DATABASE_URL disposable PostgreSQL required")
class HistoricalOutcomePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = psycopg.connect(URL, autocommit=True)
        with cls.db.cursor() as c:
            c.execute("SELECT count(*) FROM pg_catalog.pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p')")
            if c.fetchone()[0]:
                raise RuntimeError("H2C_TEST_DATABASE_URL must identify an empty disposable database")
            c.execute("CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN; CREATE ROLE h2c_public_test NOLOGIN")
            c.execute(Path("supabase/migrations/20260826042317_create_historical_replay_evidence.sql").read_text())
            # This is the exact proposed migration, not a test copy.
            c.execute(Path("supabase/migrations/20260826144639_create_historical_replay_outcomes.sql").read_text())
            c.execute(Path("supabase/migrations/20260826160458_h2_c_outcome_integrity_repair.sql").read_text())
            c.execute("SET ROLE atom_historical_replay_writer")
            c.execute("""INSERT INTO public.atom_historical_replay_runs VALUES
              ('pg-h2c','2026-06-15','REPLAY_COMPLETE','CERTIFIED','abcdef0',
               repeat('a',64),repeat('b',64),repeat('c',64),repeat('d',64),11229,
               '{}'::jsonb,808488,0,'{}'::jsonb,'{}'::jsonb,'data-v','source-v',now(),repeat('e',64))""")
            c.execute("RESET ROLE")
        cls.db.autocommit = False

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def tearDown(self):
        self.db.rollback()

    def test_exact_migration_privileges_immutability_and_all_identities(self):
        with self.db.cursor() as c:
            c.execute("SET ROLE atom_historical_outcome_resolver")
            c.execute("SELECT count(*) FROM public.atom_historical_replay_runs")
            self.assertEqual(c.fetchone()[0], 1)
            c.execute("SELECT count(*) FROM public.atom_historical_replay_forecasts")
            self.assertEqual(c.fetchone()[0], 0)
            c.execute("""INSERT INTO public.atom_historical_replay_outcomes
              SELECT 'pg-h2c', timestamp '2026-06-15 13:30:00+00' + n*interval '1 second', h,
               NULL,'UNAVAILABLE','NO_TARGET',NULL,NULL,NULL,NULL,'data-v','source-v','COIN_MIDPOINT_LOG_RETURN_BPS_1',repeat('a',64),repeat('f',64),now()
              FROM generate_series(0,11228) n CROSS JOIN
               (VALUES ('30S'),('1M'),('5M'),('15M'),('30M'),('1H')) horizons(h)""")
            c.execute("SELECT count(*) FROM public.atom_historical_replay_outcomes")
            self.assertEqual(c.fetchone()[0], 67374)
            for statement in ("UPDATE public.atom_historical_replay_outcomes SET unavailable_reason='X' WHERE replay_run_id='pg-h2c'",
                              "DELETE FROM public.atom_historical_replay_outcomes WHERE replay_run_id='pg-h2c'",
                              "TRUNCATE public.atom_historical_replay_outcomes"):
                with self.assertRaises(psycopg.Error):
                    c.execute("SAVEPOINT mutation")
                    c.execute(statement)
                c.execute("ROLLBACK TO mutation")
            c.execute("RESET ROLE")
            for role in ("atom_historical_replay_writer","atom_historical_score_reader",
                         "anon","authenticated","service_role","h2c_public_test"):
                c.execute("SET ROLE "+role)
                c.execute("SAVEPOINT denied")
                with self.assertRaises(psycopg.Error):
                    c.execute("INSERT INTO public.atom_historical_replay_outcomes (replay_run_id,cutoff_at,horizon,availability_status,unavailable_reason,data_schema_version,source_schema_version,resolution_spec_version,outcome_source_dataset_digest,content_sha256,resolved_at) VALUES ('pg-h2c',now(),'30S','UNAVAILABLE','X','d','s','COIN_MIDPOINT_LOG_RETURN_BPS_1',repeat('a',64),repeat('a',64),now())")
                c.execute("ROLLBACK TO denied")
                c.execute("RESET ROLE")
            c.execute("SET ROLE atom_historical_score_reader")
            c.execute("SELECT count(*) FROM public.atom_historical_replay_outcomes")
            self.assertEqual(c.fetchone()[0], 67374)
            c.execute("RESET ROLE")

    def test_missing_or_invalid_outcome_lineage_is_rejected(self):
        with self.db.cursor() as c:
            c.execute("SET ROLE atom_historical_outcome_resolver")
            statements = (
                """INSERT INTO public.atom_historical_replay_outcomes
                    (replay_run_id,cutoff_at,horizon,availability_status,
                     unavailable_reason,data_schema_version,source_schema_version,
                     content_sha256,resolved_at)
                    VALUES ('pg-h2c','2026-06-15 13:30+00','30S','UNAVAILABLE',
                     'X','d','s',repeat('a',64),now())""",
                """INSERT INTO public.atom_historical_replay_outcomes
                    (replay_run_id,cutoff_at,horizon,availability_status,
                     unavailable_reason,data_schema_version,source_schema_version,
                     resolution_spec_version,outcome_source_dataset_digest,
                     content_sha256,resolved_at)
                    VALUES ('pg-h2c','2026-06-15 13:30+00','30S','UNAVAILABLE',
                     'X','d','s','CHANGED','bad',repeat('a',64),now())""",
            )
            for statement in statements:
                c.execute("SAVEPOINT lineage")
                with self.assertRaises(psycopg.Error):
                    c.execute(statement)
                c.execute("ROLLBACK TO lineage")
            c.execute("RESET ROLE")

    def test_nonfinite_values_are_rejected(self):
        with self.db.cursor() as c:
            c.execute("SET ROLE atom_historical_outcome_resolver")
            for values in ((float("nan"),100,101), (1,float("inf"),101),
                           (1,100,float("-inf"))):
                statement="""INSERT INTO public.atom_historical_replay_outcomes
                  (replay_run_id,cutoff_at,horizon,actual_return_bps,availability_status,
                   cutoff_midpoint_at,cutoff_midpoint,target_midpoint_at,target_midpoint,
                   data_schema_version,source_schema_version,resolution_spec_version,outcome_source_dataset_digest,content_sha256,resolved_at)
                  VALUES ('pg-h2c','2026-06-15 14:00+00','30S',%s,'AVAILABLE',
                   '2026-06-15 14:00+00',%s,'2026-06-15 14:00:30+00',%s,
                   'd','s','COIN_MIDPOINT_LOG_RETURN_BPS_1',repeat('a',64),repeat('a',64),now())"""
                c.execute("SAVEPOINT finite")
                with self.assertRaises(psycopg.Error): c.execute(statement, values)
                c.execute("ROLLBACK TO finite")
            c.execute("RESET ROLE")

    def test_real_retry_conflict_and_partial_transaction_rollback(self):
        from quant.historical_outcomes import HistoricalOutcome, HistoricalOutcomeResolver
        now = datetime(2026, 6, 16, tzinfo=timezone.utc)
        row = HistoricalOutcome("pg-h2c", now, "30S", None, "UNAVAILABLE",
            "NO_TARGET", None, None, None, None, "data-v", "source-v",
            "COIN_MIDPOINT_LOG_RETURN_BPS_1", "a"*64, now)
        with self.db.cursor() as c:
                c.execute("SET ROLE atom_historical_outcome_resolver")
                c.execute("SELECT count(*) FROM public.atom_historical_replay_outcomes")
                before = c.fetchone()[0]
                with self.assertRaisesRegex(RuntimeError, "H2C_UNVERIFIED_REPLAY"):
                    HistoricalOutcomeResolver(self.db).resolve("pg-h2c", ())
                c = self.db.cursor()
                c.execute("SET ROLE atom_historical_outcome_resolver")
                c.execute("SELECT count(*) FROM public.atom_historical_replay_outcomes")
                self.assertEqual(c.fetchone()[0], before)
                self.assertEqual(HistoricalOutcomeResolver._write(c, "pg-h2c", [row]), 1)
                self.db.commit()
                c.execute("SET ROLE atom_historical_outcome_resolver")
                self.assertEqual(HistoricalOutcomeResolver._write(c, "pg-h2c", [row]), 0)
                with self.assertRaisesRegex(RuntimeError, "H2C_OUTCOME_CONFLICT"):
                    HistoricalOutcomeResolver._write(c, "pg-h2c",
                        [replace(row, unavailable_reason="DIFFERENT")])
                self.db.rollback()

                # The first batch is inserted, a later conflicting batch fails,
                # and rolling back the enclosing resolver transaction removes it.
                partial = replace(row, cutoff_at=now+timedelta(seconds=1))
                c.execute("SET ROLE atom_historical_outcome_resolver")
                self.assertEqual(HistoricalOutcomeResolver._write(c, "pg-h2c", [partial]), 1)
                with self.assertRaisesRegex(RuntimeError, "H2C_OUTCOME_CONFLICT"):
                    HistoricalOutcomeResolver._write(c, "pg-h2c",
                        [replace(row, unavailable_reason="DIFFERENT")])
                self.db.rollback()
                c.execute("SET ROLE atom_historical_outcome_resolver")
                c.execute("SELECT count(*) FROM public.atom_historical_replay_outcomes WHERE replay_run_id='pg-h2c' AND cutoff_at=%s", (partial.cutoff_at,))
                self.assertEqual(c.fetchone()[0], 0)
                self.db.rollback()
