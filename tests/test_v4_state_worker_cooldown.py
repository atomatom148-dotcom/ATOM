from datetime import datetime, timedelta, timezone
import threading

from quant.evidence_outbox import V4StateBuildWorker
from quant.v9_v1_contract import HORIZONS
from quant.v9_v4d_integration import OperationalMetrics


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_state_builder_coalesces_latest_snapshot_during_cooldown():
    first_attempt = threading.Event()
    second_attempt = threading.Event()
    due = threading.Event()
    built = threading.Event()

    class Builder:
        def __init__(self):
            self.current = None
            self.built = []

        def prepare(self, **candidate):
            self.current = candidate

        def build_and_publish(self):
            self.built.append(self.current)
            built.set()
            return "INSERT"

    class Scheduler:
        def __init__(self, builder):
            self.builder = builder
            self.attempts = 0

        def note_new_outcome(self):
            pass

        def run_if_due(self, *, force=False):
            self.attempts += 1
            if self.attempts == 1:
                first_attempt.set()
            elif self.attempts == 2:
                second_attempt.set()
            if not force and not due.is_set():
                return "SKIPPED_RATE_LIMIT"
            return self.builder.build_and_publish()

    cohorts = {horizon: ("cohort", "a" * 64) for horizon in HORIZONS}
    builder = Builder()
    metrics = OperationalMetrics()
    worker = V4StateBuildWorker(
        builder, Scheduler(builder), metrics=metrics,
    )
    worker.submit(symbol="COIN", state_as_of=NOW, cohorts=cohorts,
                  new_outcome=True)
    worker.start()
    assert first_attempt.wait(1)

    newest = NOW + timedelta(seconds=29)
    worker.submit(symbol="COIN", state_as_of=newest, cohorts=cohorts,
                  new_outcome=True)
    assert second_attempt.wait(1)
    due.set()
    assert built.wait(2)
    worker.stop()

    assert builder.built[0]["state_as_of"] == newest
    assert len(builder.built) == 1
    assert dict(metrics.snapshot().counters)[
        "v4_state_build_worker.coalesced"] == 1
