"""L-1 evidence ledger throughput: the batched paths are the per-record paths.

Every test here compares the L-1 batch path against the frozen per-record path
on identical inputs and asserts identical statement text, parameters, lock
identities and order, row contents, hashes, identities, per-record statuses,
``FinalizedV4PersistenceResult`` tuples, and ``TerminalDeliveryError``
dispositions.  Only commit placement may differ.  See
``docs/l-1-evidence-ledger-throughput-freeze.md``.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import unittest

from quant.evidence import PostgresEvidenceStore
from quant.evidence_outbox import (
    EvidenceLedgerWorker, EvidenceOutbox, QuoteEvidenceWork,
    TerminalDeliveryError,
)
from quant.history import MidpointObservation
from quant.v9_v4a_evidence import (
    COMMIT_PROOF_METHOD, COMMIT_PROOF_MISSING_REASON, ForecastRecord,
    V4AWriter, _canonical, _forecast_math, build_outcome, canonical_sha256,
    canonical_target_identity,
)
from quant.v9_v4d_integration import OperationalMetrics, V4DCycleOutput


UTC = timezone.utc
HORIZON_SECONDS = (("30S", 30), ("1M", 60), ("5M", 300),
                   ("15M", 900), ("30M", 1800), ("1H", 3600))
CUTOFF = datetime(2026, 9, 2, 14, 30, 0, tzinfo=UTC)
PERSISTED_AT = datetime(2026, 9, 2, 14, 30, 1, tzinfo=UTC)
PROOF_OBSERVED_AT = datetime(2026, 9, 2, 14, 30, 2, tzinfo=UTC)
CONFLICT = "FORECAST_DUPLICATE_CONFLICT"


def _forecast(horizon: str, seconds: int, *, cycle_id: str = "cycle-1",
              cutoff: datetime = CUTOFF, expected: float = 1.5) -> ForecastRecord:
    record = ForecastRecord(
        "", "", "ATOM_TRUE_V9_V4_1", "ATOM_TRUE_V9_V4A_1", "PRODUCTION",
        "v9v4cohort:" + "a" * 64, "a" * 64, "COIN", cutoff,
        cutoff + timedelta(seconds=seconds), horizon, seconds, cycle_id,
        "ATOM_TRUE_V9_V3_1", "ATOM_TRUE_V9_V3", "v9v2state:" + "b" * 64,
        "ATOM_TRUE_V9_V2_1", "b" * 64, cutoff.timestamp(), expected, 2.0,
        None, "MATURE", (), cutoff_midpoint=100.0,
    )
    digest = canonical_sha256(_forecast_math(record))
    return replace(record, forecast_record_id="v9v4f:" + digest,
                   forecast_record_hash=digest)


def _exact_six(**kwargs) -> tuple[ForecastRecord, ...]:
    return tuple(_forecast(horizon, seconds, **kwargs)
                 for horizon, seconds in HORIZON_SECONDS)


def _stored_json(record: ForecastRecord) -> str:
    stored = V4AWriter._without_commit_proof(record)
    return json.dumps(_canonical(asdict(stored)), sort_keys=True)


class _FakeLedger:
    """Deterministic responder shared by every fake connection in one test."""

    def __init__(self):
        self.forecast_rows: dict[tuple, list] = {}
        self.outcome_rows: dict[tuple, list] = {}
        self.cycle_rows: list = []
        self.records: dict[str, ForecastRecord] = {}
        self.proof_observed_at = PROOF_OBSERVED_AT
        self.fail_batched_proof = False
        self.fail_single_proof_for: set[str] = set()

    def register(self, *records: ForecastRecord) -> None:
        for record in records:
            self.records[record.forecast_record_id] = record

    def _proof_row(self, record_id: str) -> tuple:
        record = self.records[record_id]
        return (record.forecast_record_id, record.forecast_record_hash,
                self.proof_observed_at, record.target_endpoint,
                self.proof_observed_at < record.target_endpoint,
                COMMIT_PROOF_METHOD)

    def respond(self, sql: str, params) -> tuple:
        if sql.startswith("SELECT pg_catalog.pg_advisory_xact_lock"):
            return ()
        if sql.startswith("SELECT forecast_record_hash, record_json "
                          "FROM atom_v9_v4_forecasts WHERE symbol"):
            return tuple(self.forecast_rows.get(tuple(params), ()))
        if sql.startswith("SELECT outcome_record_hash, record_json "
                          "FROM atom_v9_v4_outcomes WHERE"):
            return tuple(self.outcome_rows.get(tuple(params), ()))
        if sql.startswith("INSERT INTO atom_v9_v4_forecasts"):
            return ()
        if sql.startswith("INSERT INTO atom_v9_v4_outcomes"):
            return ()
        if ("unnest(%s::text[])" in sql and
                "record_forecast_commit_proof" in sql):
            if self.fail_batched_proof:
                raise RuntimeError("batched proof statement failed")
            return tuple(self._proof_row(record_id) for record_id in params[0])
        if "FROM atom_v9_internal.record_forecast_commit_proof(%s)" in sql:
            if params[0] in self.fail_single_proof_for:
                raise RuntimeError("single proof statement failed")
            return (self._proof_row(params[0]),)
        if "read_forecast_commit_proof" in sql:
            return ()
        if "f.horizon IN (%s,%s,%s,%s,%s,%s)" in sql:
            return tuple(self.cycle_rows)
        raise AssertionError("unexpected statement: " + sql[:80])


class _Cursor:
    def __init__(self, connection):
        self._connection = connection
        self._rows: tuple = ()

    def execute(self, sql: str, params=None) -> None:
        self._connection.statements.append((sql, params))
        self._rows = tuple(self._connection.ledger.respond(sql, params))

    def fetchall(self) -> list:
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _Connection:
    autocommit = False

    def __init__(self, ledger: _FakeLedger):
        self.ledger = ledger
        self.statements: list = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, name: str | None = None) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1
        self.statements.append(("COMMIT", None))

    def rollback(self) -> None:
        self.rollbacks += 1
        self.statements.append(("ROLLBACK", None))


def _without_transaction_control(statements: list) -> list:
    return [item for item in statements if item[0] not in ("COMMIT", "ROLLBACK")]


def _is_proof_statement(statement) -> bool:
    return "record_forecast_commit_proof" in statement[0]


def _proof_ids(statements: list) -> list:
    """Return the proof-observation ids in issue order, batched or single."""
    ids: list = []
    for sql, params in statements:
        if not _is_proof_statement((sql, params)):
            continue
        if "unnest(%s::text[])" in sql:
            ids.extend(params[0])
        else:
            ids.append(params[0])
    return ids


class BatchedForecastPersistenceParityTests(unittest.TestCase):
    def _sequential(self, ledger, records):
        connection = _Connection(ledger)
        writer = V4AWriter(connection)
        results = []
        for record in records:
            stored = writer.persist_forecast(record, PERSISTED_AT)
            results.append((writer.last_write_status, stored))
            if writer.last_write_status == CONFLICT:
                break
        return connection, tuple(results)

    def _batched(self, ledger, records):
        connection = _Connection(ledger)
        writer = V4AWriter(connection)
        return connection, writer.persist_forecasts(records, PERSISTED_AT)

    def test_batch_issues_identical_statements_with_one_commit(self):
        ledger = _FakeLedger()
        six = _exact_six()
        sequential_connection, sequential = self._sequential(ledger, six)
        batched_connection, batched = self._batched(ledger, six)
        self.assertEqual(
            _without_transaction_control(batched_connection.statements),
            _without_transaction_control(sequential_connection.statements))
        self.assertEqual(sequential_connection.commits, 6)
        self.assertEqual(batched_connection.commits, 1)
        self.assertEqual(batched_connection.rollbacks, 0)
        self.assertEqual(batched, sequential)
        self.assertEqual([status for status, _ in batched], ["INSERT"] * 6)
        for _status, stored in batched:
            self.assertIsNone(stored.persisted_at)
            self.assertIs(stored.persistence_proof_eligible, False)
            self.assertEqual(stored.persistence_reason, COMMIT_PROOF_MISSING_REASON)
        lock_statements = [
            params for sql, params in batched_connection.statements
            if sql.startswith("SELECT pg_catalog.pg_advisory_xact_lock")]
        self.assertEqual(lock_statements, [
            (V4AWriter._logical_lock_id("FORECAST", record.logical_key),)
            for record in six])

    def test_conflict_at_every_position_commits_the_prefix_and_stops(self):
        six = _exact_six()
        for position in range(6):
            with self.subTest(position=position):
                ledger = _FakeLedger()
                ledger.forecast_rows[six[position].logical_key] = [
                    ("f" * 64, None)]
                sequential_connection, sequential = self._sequential(ledger, six)
                batched_connection, batched = self._batched(ledger, six)
                self.assertEqual(len(batched), position + 1)
                self.assertEqual(batched, sequential)
                self.assertEqual(batched[-1][0], CONFLICT)
                self.assertEqual(batched[-1][1].persistence_reason, CONFLICT)
                self.assertEqual(
                    _without_transaction_control(batched_connection.statements),
                    _without_transaction_control(sequential_connection.statements))
                self.assertEqual(batched_connection.commits, 1)
                self.assertEqual(batched_connection.rollbacks, 0)
                inserted = [params[0] for sql, params in batched_connection.statements
                            if sql.startswith("INSERT INTO atom_v9_v4_forecasts")]
                self.assertEqual(
                    inserted, [record.forecast_record_id for record in six[:position]])

    def test_multiple_distinct_hashes_is_a_conflict_in_both_paths(self):
        six = _exact_six()
        ledger = _FakeLedger()
        ledger.forecast_rows[six[2].logical_key] = [("1" * 64, None), ("2" * 64, None)]
        _connection, sequential = self._sequential(ledger, six)
        _connection, batched = self._batched(ledger, six)
        self.assertEqual(batched, sequential)
        self.assertEqual(batched[-1][0], CONFLICT)
        self.assertEqual(len(batched), 3)

    def test_idempotent_record_returns_the_stored_original_in_both_paths(self):
        six = _exact_six()
        ledger = _FakeLedger()
        ledger.forecast_rows[six[1].logical_key] = [
            (six[1].forecast_record_hash, _stored_json(six[1]))]
        sequential_connection, sequential = self._sequential(ledger, six)
        batched_connection, batched = self._batched(ledger, six)
        self.assertEqual(batched, sequential)
        self.assertEqual(batched[1][0], "IDEMPOTENT")
        self.assertEqual(batched[1][1].forecast_record_hash,
                         six[1].forecast_record_hash)
        self.assertEqual(
            _without_transaction_control(batched_connection.statements),
            _without_transaction_control(sequential_connection.statements))
        inserted = [params[0] for sql, params in batched_connection.statements
                    if sql.startswith("INSERT INTO atom_v9_v4_forecasts")]
        self.assertEqual(len(inserted), 5)

    def test_batch_writer_sql_surface_is_select_and_insert_only(self):
        ledger = _FakeLedger()
        connection, _results = self._batched(ledger, _exact_six())
        for sql, _params in _without_transaction_control(connection.statements):
            self.assertTrue(sql.startswith("SELECT ") or sql.startswith("INSERT "), sql)


class BatchedCommitProofParityTests(unittest.TestCase):
    def test_one_statement_reproduces_the_per_record_proofs(self):
        six = _exact_six()
        ledger = _FakeLedger()
        ledger.register(*six)
        stored = tuple(V4AWriter._without_commit_proof(record) for record in six)
        sequential_connection = _Connection(ledger)
        sequential_writer = V4AWriter(sequential_connection)
        sequential = tuple(sequential_writer.record_forecast_commit_proof(record)
                           for record in stored)
        batched_connection = _Connection(ledger)
        batched_writer = V4AWriter(batched_connection)
        batched = batched_writer.record_forecast_commit_proofs(stored)
        self.assertEqual(batched, sequential)
        for record in batched:
            self.assertEqual(record.persisted_at, PROOF_OBSERVED_AT)
            self.assertIs(record.persistence_proof_eligible, True)
            self.assertIsNone(record.persistence_reason)
        proof_statements = [item for item in batched_connection.statements
                            if _is_proof_statement(item)]
        self.assertEqual(len(proof_statements), 1)
        self.assertIn("unnest(%s::text[]) WITH ORDINALITY", proof_statements[0][0])
        self.assertIn("JOIN LATERAL atom_v9_internal.record_forecast_commit_proof(",
                      proof_statements[0][0])
        self.assertIn("ORDER BY requested.proof_order", proof_statements[0][0])
        self.assertEqual(proof_statements[0][1],
                         ([record.forecast_record_id for record in six],))
        self.assertEqual(_proof_ids(batched_connection.statements),
                         _proof_ids(sequential_connection.statements))
        self.assertEqual(batched_connection.commits, 1)
        self.assertEqual(sequential_connection.commits, 6)

    def test_late_observation_is_ineligible_in_both_paths(self):
        six = _exact_six()
        ledger = _FakeLedger()
        ledger.register(*six)
        ledger.proof_observed_at = CUTOFF + timedelta(seconds=45)
        stored = tuple(V4AWriter._without_commit_proof(record) for record in six)
        sequential = tuple(V4AWriter(_Connection(ledger)).record_forecast_commit_proof(record)
                           for record in stored)
        batched = V4AWriter(_Connection(ledger)).record_forecast_commit_proofs(stored)
        self.assertEqual(batched, sequential)
        self.assertIs(batched[0].persistence_proof_eligible, False)
        self.assertIs(batched[1].persistence_proof_eligible, True)

    def test_batch_failure_falls_back_to_the_per_record_proofs(self):
        six = _exact_six()
        ledger = _FakeLedger()
        ledger.register(*six)
        ledger.fail_batched_proof = True
        stored = tuple(V4AWriter._without_commit_proof(record) for record in six)
        sequential_connection = _Connection(ledger)
        sequential = tuple(V4AWriter(sequential_connection).record_forecast_commit_proof(record)
                           for record in stored)
        batched_connection = _Connection(ledger)
        batched = V4AWriter(batched_connection).record_forecast_commit_proofs(stored)
        self.assertEqual(batched, sequential)
        self.assertEqual(batched_connection.rollbacks, 1)
        self.assertEqual(batched_connection.commits, 6)
        statements = batched_connection.statements
        self.assertIn("unnest(%s::text[])", statements[0][0])
        self.assertEqual(statements[1], ("ROLLBACK", None))
        self.assertEqual(_without_transaction_control(statements[2:]),
                         _without_transaction_control(sequential_connection.statements))

    def test_fallback_preserves_the_per_record_failure_disposition(self):
        six = _exact_six()
        ledger = _FakeLedger()
        ledger.register(*six)
        ledger.fail_batched_proof = True
        ledger.fail_single_proof_for = {six[2].forecast_record_id}
        stored = tuple(V4AWriter._without_commit_proof(record) for record in six)
        sequential_connection = _Connection(ledger)
        sequential_writer = V4AWriter(sequential_connection)
        with self.assertRaises(RuntimeError):
            for record in stored:
                sequential_writer.record_forecast_commit_proof(record)
        batched_connection = _Connection(ledger)
        with self.assertRaises(RuntimeError):
            V4AWriter(batched_connection).record_forecast_commit_proofs(stored)
        self.assertEqual(_without_transaction_control(batched_connection.statements[2:]),
                         _without_transaction_control(sequential_connection.statements))

    def test_empty_batch_issues_nothing(self):
        connection = _Connection(_FakeLedger())
        self.assertEqual(V4AWriter(connection).record_forecast_commit_proofs(()), ())
        self.assertEqual(connection.statements, [])


class BatchedOutcomePersistenceParityTests(unittest.TestCase):
    def _outcomes(self, forecasts):
        previous_at = CUTOFF + timedelta(seconds=20)
        endpoint_at = CUTOFF + timedelta(seconds=61)
        return tuple(build_outcome(
            forecast=forecast,
            target_identity=canonical_target_identity(forecast),
            endpoint_observation_at=endpoint_at,
            target_resolved_at=endpoint_at,
            actual_return_bps=12.5,
            previous_observation_at=previous_at,
        ) for forecast in forecasts)

    def _sequential(self, ledger, outcomes):
        connection = _Connection(ledger)
        writer = V4AWriter(connection)
        results = []
        for outcome in outcomes:
            stored = writer.persist_outcome(outcome, PERSISTED_AT)
            results.append((writer.last_write_status, stored))
            if writer.last_write_status == "OUTCOME_CONFLICT":
                break
        return connection, tuple(results)

    def _batched(self, ledger, outcomes):
        connection = _Connection(ledger)
        return connection, V4AWriter(connection).persist_outcomes(outcomes, PERSISTED_AT)

    def test_batch_issues_identical_statements_with_one_commit(self):
        ledger = _FakeLedger()
        outcomes = self._outcomes(_exact_six()[:2])
        sequential_connection, sequential = self._sequential(ledger, outcomes)
        batched_connection, batched = self._batched(ledger, outcomes)
        self.assertEqual(batched, sequential)
        self.assertEqual([status for status, _ in batched], ["INSERT", "INSERT"])
        self.assertEqual(
            _without_transaction_control(batched_connection.statements),
            _without_transaction_control(sequential_connection.statements))
        self.assertEqual(batched_connection.commits, 1)
        self.assertEqual(sequential_connection.commits, 2)
        for _status, stored in batched:
            self.assertEqual(stored.created_at, PERSISTED_AT)

    def test_conflict_at_every_position_commits_the_prefix_and_stops(self):
        outcomes = self._outcomes(_exact_six()[:3])
        for position in range(3):
            with self.subTest(position=position):
                ledger = _FakeLedger()
                ledger.outcome_rows[outcomes[position].logical_key] = [("e" * 64, None)]
                sequential_connection, sequential = self._sequential(ledger, outcomes)
                batched_connection, batched = self._batched(ledger, outcomes)
                self.assertEqual(batched, sequential)
                self.assertEqual(len(batched), position + 1)
                self.assertEqual(batched[-1][0], "OUTCOME_CONFLICT")
                self.assertEqual(
                    _without_transaction_control(batched_connection.statements),
                    _without_transaction_control(sequential_connection.statements))
                self.assertEqual(batched_connection.commits, 1)

    def test_idempotent_outcome_returns_the_stored_original_in_both_paths(self):
        outcomes = self._outcomes(_exact_six()[:2])
        ledger = _FakeLedger()
        original = replace(outcomes[1], created_at=PERSISTED_AT)
        ledger.outcome_rows[outcomes[1].logical_key] = [
            (outcomes[1].outcome_record_hash,
             json.dumps(_canonical(asdict(original)), sort_keys=True))]
        _connection, sequential = self._sequential(ledger, outcomes)
        _connection, batched = self._batched(ledger, outcomes)
        self.assertEqual(batched, sequential)
        self.assertEqual(batched[1][0], "IDEMPOTENT")


class _RawStore:
    def __init__(self):
        self.calls: list = []

    def record_cycle_and_resolve(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))

    def rebind_connection(self, connection) -> None:
        pass


def _worker(ledger: _FakeLedger, *, batch_enabled: bool, submissions: list,
            finalized_capture: list):
    metrics = OperationalMetrics()
    connection = _Connection(ledger)
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(metrics=metrics), evidence_store=_RawStore(),
        connection=connection, metrics=metrics, load_pending=False,
        state_build_submit=lambda **kwargs: submissions.append(kwargs),
        simulation_submit=lambda output, results: finalized_capture.append(results),
        wall_clock=lambda: PERSISTED_AT,
        batch_enabled=batch_enabled,
    )
    return worker, connection, metrics


def _bracket_item(new_cycle: tuple[ForecastRecord, ...]) -> QuoteEvidenceWork:
    previous = MidpointObservation((CUTOFF + timedelta(seconds=20)).timestamp(), 100.0)
    current = MidpointObservation((CUTOFF + timedelta(seconds=61)).timestamp(), 101.0)
    output = V4DCycleOutput(new_cycle[0].cycle_id, "COIN", new_cycle[0].cutoff_at,
                            None, None, None, (), (), (), "UNAVAILABLE")
    return QuoteEvidenceWork(
        sequence=1, cycle_id=new_cycle[0].cycle_id,
        previous_observation=previous, current_observation=current,
        received_at=CUTOFF + timedelta(seconds=62),
        directional=(), q3=(), v4=new_cycle, v4d_output=output,
    )


class LedgerWorkerGateTests(unittest.TestCase):
    def _run(self, *, batch_enabled: bool, ledger: _FakeLedger | None = None,
             pending: tuple[ForecastRecord, ...] = (), new_cycle=None):
        ledger = ledger or _FakeLedger()
        new_cycle = new_cycle or _exact_six(
            cycle_id="cycle-1", cutoff=CUTOFF + timedelta(seconds=61))
        ledger.register(*new_cycle)
        submissions: list = []
        finalized: list = []
        worker, connection, metrics = _worker(
            ledger, batch_enabled=batch_enabled, submissions=submissions,
            finalized_capture=finalized)
        worker._pending = list(pending)
        item = _bracket_item(new_cycle)
        error = None
        try:
            worker.process(item)
        except TerminalDeliveryError as raised:
            error = raised
        return {
            "worker": worker, "connection": connection, "metrics": metrics,
            "submissions": submissions, "finalized": finalized,
            "error": error, "item": item,
        }

    def _pending_cycle(self, ledger: _FakeLedger) -> tuple[ForecastRecord, ...]:
        previous_cycle = _exact_six(cycle_id="cycle-0", cutoff=CUTOFF)
        proven = tuple(replace(
            record, persisted_at=PROOF_OBSERVED_AT,
            persistence_proof_eligible=True, persistence_reason=None,
        ) for record in previous_cycle)
        ledger.register(*previous_cycle)
        ledger.cycle_rows = [
            (record.forecast_record_hash, _stored_json(record))
            for record in previous_cycle]
        return proven

    def test_gate_off_uses_only_the_per_record_methods(self):
        ledger = _FakeLedger()
        pending = self._pending_cycle(ledger)
        run = self._run(batch_enabled=False, ledger=ledger, pending=pending)
        self.assertIsNone(run["error"])
        statements = run["connection"].statements
        self.assertFalse(any("unnest(%s::text[])" in sql and
                             "record_forecast_commit_proof" in sql
                             for sql, _ in statements))
        single_proofs = [item for item in statements if _is_proof_statement(item)]
        self.assertEqual(len(single_proofs), 6)
        self.assertEqual(len(run["finalized"]), 1)
        self.assertEqual([result.status for result in run["finalized"][0]],
                         ["INSERTED"] * 6)

    def test_gate_on_without_batch_capable_writer_uses_the_per_record_path(self):
        ledger = _FakeLedger()
        run_off = self._run(batch_enabled=False, ledger=ledger)

        class _PerRecordOnly:
            def __init__(self, writer):
                self._writer = writer
                self.last_write_status = None

            def persist_forecast(self, record, persisted_at):
                stored = self._writer.persist_forecast(record, persisted_at)
                self.last_write_status = self._writer.last_write_status
                return stored

            def record_forecast_commit_proof(self, record):
                return self._writer.record_forecast_commit_proof(record)

            def persist_outcome(self, record, created_at):
                stored = self._writer.persist_outcome(record, created_at)
                self.last_write_status = self._writer.last_write_status
                return stored

        submissions: list = []
        finalized: list = []
        worker, connection, _metrics = _worker(
            ledger, batch_enabled=True, submissions=submissions,
            finalized_capture=finalized)
        worker._writer = _PerRecordOnly(worker._writer)
        worker.process(_bracket_item(_exact_six(
            cycle_id="cycle-1", cutoff=CUTOFF + timedelta(seconds=61))))
        self.assertEqual(_without_transaction_control(connection.statements),
                         _without_transaction_control(run_off["connection"].statements))
        self.assertEqual(finalized, run_off["finalized"])

    def test_gate_on_is_statement_for_statement_parity_with_gate_off(self):
        off_ledger, on_ledger = _FakeLedger(), _FakeLedger()
        off = self._run(batch_enabled=False, ledger=off_ledger,
                        pending=self._pending_cycle(off_ledger))
        on = self._run(batch_enabled=True, ledger=on_ledger,
                       pending=self._pending_cycle(on_ledger))
        self.assertIsNone(off["error"])
        self.assertIsNone(on["error"])
        off_statements = [item for item in _without_transaction_control(
            off["connection"].statements) if not _is_proof_statement(item)]
        on_statements = [item for item in _without_transaction_control(
            on["connection"].statements) if not _is_proof_statement(item)]
        self.assertEqual(on_statements, off_statements)
        self.assertEqual(_proof_ids(on["connection"].statements),
                         _proof_ids(off["connection"].statements))
        self.assertEqual(on["finalized"], off["finalized"])
        self.assertEqual(on["worker"]._pending, off["worker"]._pending)
        self.assertEqual(on["submissions"], off["submissions"])
        self.assertEqual(on["worker"]._last_sequence, off["worker"]._last_sequence)
        self.assertEqual(
            dict(on["metrics"].snapshot().counters).get("outcome_resolution.INSERT"),
            dict(off["metrics"].snapshot().counters).get("outcome_resolution.INSERT"))
        self.assertEqual(
            dict(on["metrics"].snapshot().counters).get("outcome_resolution.INSERT"), 2)
        self.assertLess(on["connection"].commits, off["connection"].commits)
        # The exact-six persist once, the proofs observe once, the bracket's
        # outcomes persist once; the remaining commits are the recovery reads.
        self.assertEqual(
            on["connection"].commits - off["connection"].commits,
            -(5 + 5 + 1))

    def test_gate_on_state_candidate_submission_matches_gate_off(self):
        off_ledger, on_ledger = _FakeLedger(), _FakeLedger()
        off = self._run(batch_enabled=False, ledger=off_ledger,
                        pending=self._pending_cycle(off_ledger))
        on = self._run(batch_enabled=True, ledger=on_ledger,
                       pending=self._pending_cycle(on_ledger))
        self.assertEqual(len(off["submissions"]), 1)
        self.assertEqual(on["submissions"], off["submissions"])
        self.assertIs(on["submissions"][0]["new_outcome"], True)

    def test_forecast_conflict_disposition_matches_at_every_horizon(self):
        for position in range(6):
            with self.subTest(position=position):
                new_cycle = _exact_six(cycle_id="cycle-1",
                                       cutoff=CUTOFF + timedelta(seconds=61))
                runs = {}
                for enabled in (False, True):
                    ledger = _FakeLedger()
                    ledger.forecast_rows[new_cycle[position].logical_key] = [
                        ("f" * 64, None)]
                    runs[enabled] = self._run(
                        batch_enabled=enabled, ledger=ledger, new_cycle=new_cycle)
                for enabled in (False, True):
                    self.assertIsInstance(runs[enabled]["error"], TerminalDeliveryError)
                    self.assertEqual(str(runs[enabled]["error"]), CONFLICT)
                    self.assertEqual(runs[enabled]["finalized"], [])
                off_statements = [item for item in _without_transaction_control(
                    runs[False]["connection"].statements) if not _is_proof_statement(item)]
                on_statements = [item for item in _without_transaction_control(
                    runs[True]["connection"].statements) if not _is_proof_statement(item)]
                self.assertEqual(on_statements, off_statements)
                self.assertEqual(_proof_ids(runs[True]["connection"].statements),
                                 _proof_ids(runs[False]["connection"].statements))
                self.assertEqual(_proof_ids(runs[True]["connection"].statements),
                                 [record.forecast_record_id
                                  for record in new_cycle[:position]])

    def test_outcome_conflict_disposition_matches_at_every_position(self):
        for position in range(2):
            with self.subTest(position=position):
                runs = {}
                for enabled in (False, True):
                    ledger = _FakeLedger()
                    pending = self._pending_cycle(ledger)
                    due = pending[position]
                    outcome_key = (due.forecast_record_id,
                                   canonical_target_identity(due))
                    ledger.outcome_rows[outcome_key] = [("e" * 64, None)]
                    runs[enabled] = self._run(
                        batch_enabled=enabled, ledger=ledger, pending=pending)
                for enabled in (False, True):
                    self.assertIsInstance(runs[enabled]["error"], TerminalDeliveryError)
                    self.assertEqual(str(runs[enabled]["error"]), "OUTCOME_CONFLICT")
                self.assertEqual(
                    _without_transaction_control(runs[True]["connection"].statements),
                    _without_transaction_control(runs[False]["connection"].statements))
                self.assertEqual(runs[True]["submissions"], runs[False]["submissions"])

    def test_gate_on_proof_fallback_inside_the_worker(self):
        off_ledger, on_ledger = _FakeLedger(), _FakeLedger()
        on_ledger.fail_batched_proof = True
        off = self._run(batch_enabled=False, ledger=off_ledger)
        on = self._run(batch_enabled=True, ledger=on_ledger)
        self.assertIsNone(on["error"])
        self.assertEqual(on["finalized"], off["finalized"])
        self.assertEqual(on["worker"]._pending, off["worker"]._pending)
        statements = on["connection"].statements
        batched_index = next(index for index, (sql, _) in enumerate(statements)
                             if "unnest(%s::text[])" in sql and
                             "record_forecast_commit_proof" in sql)
        self.assertEqual(statements[batched_index + 1], ("ROLLBACK", None))
        self.assertEqual(_proof_ids(statements[batched_index + 2:]),
                         _proof_ids(off["connection"].statements))

    def test_gate_on_keeps_the_frozen_fifo_order(self):
        ledger = _FakeLedger()
        pending = self._pending_cycle(ledger)
        run = self._run(batch_enabled=True, ledger=ledger, pending=pending)
        connection = run["connection"]
        statements = _without_transaction_control(connection.statements)
        first_outcome = next(index for index, (sql, _) in enumerate(statements)
                             if sql.startswith("INSERT INTO atom_v9_v4_outcomes"))
        first_forecast = next(index for index, (sql, _) in enumerate(statements)
                              if sql.startswith("INSERT INTO atom_v9_v4_forecasts"))
        proof_index = next(index for index, item in enumerate(statements)
                           if _is_proof_statement(item))
        self.assertLess(first_outcome, first_forecast)
        self.assertLess(first_forecast, proof_index)
        store_calls = run["worker"]._store.calls
        self.assertEqual(len(store_calls), 1)


class _ProofCursor:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql: str, params=None) -> None:
        self._connection.statements.append((sql, params))
        if self._connection.error is not None:
            raise self._connection.error

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _ProofConnection:
    def __init__(self, ledger):
        self.ledger = ledger
        self.statements: list = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.error: Exception | None = None

    def cursor(self):
        return _ProofCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _exc, _tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False


class _SqlStateError(RuntimeError):
    def __init__(self, sqlstate: str):
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


class PersistentProofSessionTests(unittest.TestCase):
    def _store(self, *, persistent: bool):
        store = PostgresEvidenceStore(
            "postgresql://example/atom", proof_session_persistent=persistent)
        connections: list = []

        def connect(_url):
            connection = _ProofConnection(None)
            connections.append(connection)
            return connection

        store._connect = connect
        return store, connections

    def _publish(self, store):
        store._record_publication_proofs(
            (), observation_epoch=1.0, resolution_symbol="COIN",
            volatility_forecasts=(), resolution_enabled=True)

    def test_gate_off_opens_one_connection_per_cycle(self):
        store, connections = self._store(persistent=False)
        self._publish(store)
        self._publish(store)
        self.assertEqual(len(connections), 2)
        self.assertTrue(all(connection.closed for connection in connections))
        self.assertEqual([connection.commits for connection in connections], [1, 1])
        self.assertEqual(len(connections[0].statements), 2)

    def test_gate_on_reuses_one_secondary_session_with_a_commit_per_cycle(self):
        store, connections = self._store(persistent=True)
        self._publish(store)
        self._publish(store)
        self.assertEqual(len(connections), 1)
        self.assertFalse(connections[0].closed)
        self.assertEqual(connections[0].commits, 2)
        self.assertEqual(len(connections[0].statements), 4)

    def test_gate_on_and_off_issue_identical_statements(self):
        off, off_connections = self._store(persistent=False)
        on, on_connections = self._store(persistent=True)
        self._publish(off)
        self._publish(on)
        self.assertEqual(on_connections[0].statements, off_connections[0].statements)

    def test_gate_on_discards_the_session_on_failure_and_reopens_lazily(self):
        store, connections = self._store(persistent=True)
        self._publish(store)
        connections[0].error = RuntimeError("connection reset")
        with self.assertRaises(RuntimeError):
            self._publish(store)
        self.assertTrue(connections[0].closed)
        self.assertEqual(connections[0].rollbacks, 1)
        self.assertIsNone(store._proof_connection)
        self._publish(store)
        self.assertEqual(len(connections), 2)
        self.assertIs(store._proof_connection, connections[1])

    def test_gate_on_preserves_missing_infrastructure_handling(self):
        store, connections = self._store(persistent=True)
        self._publish(store)
        connections[0].error = _SqlStateError("42883")
        self._publish(store)  # returns without raising, exactly as before
        self.assertTrue(connections[0].closed)
        self.assertIsNone(store._proof_connection)


class WebGateTests(unittest.TestCase):
    def test_gate_reads_exactly_one(self):
        from quant.web import _evidence_ledger_batch_enabled
        self.assertTrue(_evidence_ledger_batch_enabled(
            {"ATOM_EVIDENCE_LEDGER_BATCH_ENABLED": "1"}))
        for value in ("0", "true", "yes", "", " 1"):
            self.assertFalse(_evidence_ledger_batch_enabled(
                {"ATOM_EVIDENCE_LEDGER_BATCH_ENABLED": value}), value)
        self.assertFalse(_evidence_ledger_batch_enabled({}))


if __name__ == "__main__":
    unittest.main()
