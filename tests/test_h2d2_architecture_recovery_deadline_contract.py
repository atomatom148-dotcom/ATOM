from pathlib import Path


FREEZE = Path(__file__).resolve().parents[1] / "docs" / "h2-d2-freeze.md"


def _law() -> str:
    return " ".join(FREEZE.read_text(encoding="utf-8").split())


def test_canary_is_two_processes_two_dates_and_read_only() -> None:
    law = _law()
    for clause in (
        "Exactly two certified dates",
        "exactly two isolated worker processes",
        "Everything inside one date remains chronological and sequential",
        "Every database connection used by the canary is read-only",
        "zero evidence writes",
    ):
        assert clause in law


def test_canary_fails_closed_without_building_a_scheduler() -> None:
    law = _law()
    for clause in (
        "A worker failure fails the canary",
        "No automatic retry, replacement worker, distributed queue, or production scheduler",
        "Each worker and the whole canary must have a finite timeout",
        "terminate and join both workers before returning",
        "no surviving worker",
    ):
        assert clause in law


def test_promotion_requires_exact_behavior_and_numerical_parity() -> None:
    law = _law()
    for clause in (
        "same two dates sequentially",
        "Parallel output must match that control exactly",
        "forecast_count = frame_count × 12 × 6",
        "outcome_count = frame_count × 6",
        "72 metric objects field-for-field",
        "Any numerical, lineage, count, hash, duplicate, ordering, or receipt mismatch fails",
    ):
        assert clause in law
