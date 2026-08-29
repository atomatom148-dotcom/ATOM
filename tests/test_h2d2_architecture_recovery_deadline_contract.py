from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "docs" / "h2-d2-freeze.md"


def _law() -> str:
    return " ".join(FREEZE.read_text(encoding="utf-8").split())


def test_claiming_has_supervisor_owned_pre_guardian_recovery() -> None:
    law = _law()
    required = (
        "A fsynced `CLAIMING` record is supervisor-owned",
        "monotonic heartbeat sequence",
        "heartbeat age is never a lease",
        "readability of an exact coordinator `pidfd`",
        "absence of the recorded backend's global advisory-lock ownership",
        "aborted-before-guardian receipt",
        "creates no worker",
        "no manual record edit, age-based reset",
        "pre-guardian recovery fault test",
    )
    for phrase in required:
        assert phrase in law


def test_stage_and_date_deadlines_are_finite_absolute_and_fail_closed() -> None:
    law = _law()
    required = (
        "positive finite monotonic-runtime deadline for each named stage",
        "positive finite whole-date deadline",
        "whole-date deadline is absolute",
        "Every provider/network/database call must have its own finite operation",
        "independent monotonic watchdog",
        "Deadline expiry irrevocably fails that generation",
        "same generation can never resume, restart, or be readmitted",
        "Expiration of the cleanup deadline does not authorize abandonment",
        "Separate deadline fault tests must hang provider I/O",
        "Normal completion uses the same bounded",
    )
    for phrase in required:
        assert phrase in law


def test_failed_generation_and_operator_authorized_replay_are_distinct() -> None:
    law = _law()
    required = (
        "Every failed generation is irrevocably terminal",
        "There is no blind, timed, or automatic replay",
        "authorize a separate new generation with a new generation ID",
        "fresh supervisor compare-and-swap",
        "complete admission from the beginning",
        "new generation admission fails before worker start",
        "does not alter, reopen, supersede, or continue the failed generation",
    )
    for phrase in required:
        assert phrase in law
    assert "the retry fails" not in law


def test_architecture_change_remains_runtime_disabled() -> None:
    law = _law()
    assert "H2-D-2 still authorizes no runtime" in law
    assert "H2-D-2 adds no multiprocessing/executor/async runtime" in law
