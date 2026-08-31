"""Focused H2-D-2 freeze checks.

The freeze protects observable replay behavior and exact canary parity. It
intentionally does not pin implementation-file hashes or attempt to recognize
every theoretical Python execution mechanism.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "quant" / "historical_batch_h2d.py"
ROOT_FREEZE = ROOT / "FREEZE.md"
PHASES = ROOT / "PHASES.md"
FREEZE = ROOT / "docs" / "h2-d2-freeze.md"
BASELINES = ROOT / "docs" / "h2-d2-canary-baselines.json"
H2D4_DECISION = ROOT / "docs" / "h2-d4-compute-decision.md"
H2D5_FREEZE = ROOT / "docs" / "h2-d5-freeze.md"
H2D6_FREEZE = ROOT / "docs" / "h2-d6-persistence-gate-freeze.md"
Q10_AUDIT = ROOT / "docs" / "audits" / "h2d-2026-07-22-q10-options-vol.md"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")

QUANTS = [
    "q1_momentum", "q2_mean_reversion", "q3_volatility", "q4_stat_arb",
    "q5_microstructure", "q6_volume_liquidity", "q7_relative_value",
    "q8_cross_asset", "q9_factor", "q10_options_vol", "q11_regime",
    "q12_event_session",
]
HORIZONS = ["30S", "1M", "5M", "15M", "30M", "1H"]
METRIC_FIELDS = [
    "quant_id", "horizon", "eligible_count", "resolved_count",
    "directional_wins", "directional_losses", "directional_accuracy", "rmse",
    "mae", "bias", "coverage",
]

EXPECTED_SESSIONS = {
    "2026-06-15": {
        "replay_run_id": "h2a-2026-06-15-persistence-v3",
        "git_commit": "a9cc73ddd892c3518bda1145075cbd4de6873513",
        "dataset_digest": "c1dda6101424404b94ad39973f4c6a4a0feb67e90b537bae7f94a264130e6b3e",
        "configuration_digest": "dcd7f3af8fba60047ff965a22fc9dbf5f05734f97913c502f3d972f21cf46385",
        "session_digest": "e35a1130ae7f6e12ea4783aebd7a988e7dcff0f659a179566193e62368e23627",
        "artifact_sha256": "1edb32a8f46a757637459dcfa348480df0968a6531f8590c3c784d0d4e9a9860",
        "manifest_content_sha256": "a9f5a0d1621a8e682ede3ff0d12c70cff7da79c474e008df9aa2d17652028a8d",
        "forecast_ordered_content_sha256": "4b570e1c9e35c9459b79145ab9f827e93484068d99207481df4a5c6aab43517f",
        "outcome_ordered_content_sha256": "e1f14e02922a2c58faea0447796fe33ba6950ca44659c72fc39f62babaefa1a9",
        "frame_count": 11229,
        "forecast_count": 808488,
        "forecast_available_count": 729684,
        "forecast_unavailable_count": 78804,
        "outcome_count": 67374,
        "outcome_available_count": 63398,
        "outcome_unavailable_count": 3976,
    },
    "2026-07-22": {
        "replay_run_id": "h2d-2026-07-22",
        "git_commit": "fa3438f9444b624b973e7a3dc5efe89fea2dc6ca",
        "dataset_digest": "18a334e44983635dd4794385ee25f9497b8be865d255bafbcab28f3286c41aa9",
        "configuration_digest": "2fb3d521ddb0310458251225bf25a3e1759304d468f6bfa72ee92c6dd967a7d1",
        "session_digest": "cd687a7ab67d4f1a29c46780b37e4fb81562eb9eb28e1d43d367820299f1ab96",
        "artifact_sha256": "2145555052691e45880475198c9983e6816feba508015b14ebe23025cbe9931b",
        "manifest_content_sha256": "8f886e9c8a3b6245ddc143c31e16af081e6ace93dbafe1ecf27dd2077c5c7b0e",
        "forecast_ordered_content_sha256": "aaad291213da2908caa12bc3568ac08f0bff5700ffd56dfdfafd8aea146c72c9",
        "outcome_ordered_content_sha256": "2ff12383dd8abbf8c16942ba8713c90312fd4863e8f4be2f4b49a81e0061e531",
        "db3_forecast_sha256": "413e3bacb29155e2c03ad666a47dd6ab42759015f75f68c9ecbff7d06b1494e1",
        "db3_outcome_sha256": "d3a820111a3a8a9f68a02f738fcb98b8c5bebc13e20336d46e47394a9632e532",
        "frame_count": 10445,
        "forecast_count": 752040,
        "forecast_available_count": 679057,
        "forecast_unavailable_count": 72983,
        "outcome_count": 62670,
        "outcome_available_count": 59271,
        "outcome_unavailable_count": 3399,
    },
}


def _payload() -> dict:
    return json.loads(BASELINES.read_text(encoding="utf-8"))


def _law(path: Path = FREEZE) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_manifest_is_behavioral_not_a_source_hash_lock() -> None:
    payload = _payload()
    assert "sequential_runtime_source_hash_contract" not in payload
    assert "sequential_runtime_source_sha256" not in payload
    assert payload["freeze_version"] == "H2-D-2"
    assert payload["current_runtime_version"] == "H2-D-1"
    assert payload["capture_mode"] == "read_only"
    assert payload["parallel_runtime_enabled"] is False
    assert payload["future_canary_worker_limit"] == 2


def test_two_certified_session_baselines_are_exact_and_complete() -> None:
    sessions = _payload()["sessions"]
    assert [item["historical_session"] for item in sessions] == list(EXPECTED_SESSIONS)
    for session in sessions:
        expected = EXPECTED_SESSIONS[session["historical_session"]]
        assert session["execution_stage"] == "REPLAY_COMPLETE"
        assert session["certification_status"] == "CERTIFIED"
        for key, value in expected.items():
            assert session[key] == value
        assert session["forecast_count"] == session["frame_count"] * 12 * 6
        assert session["outcome_count"] == session["frame_count"] * 6
        assert session["forecast_available_count"] + session["forecast_unavailable_count"] == session["forecast_count"]
        assert session["outcome_available_count"] + session["outcome_unavailable_count"] == session["outcome_count"]
        for key, value in session.items():
            if key.endswith(("digest", "sha256")):
                assert isinstance(value, str) and HEX_64.fullmatch(value)


def test_ordered_content_hash_contract_is_exact() -> None:
    contract = _payload()["ordered_content_hash_contract"]
    assert contract == {
        "algorithm": "sha256_utf8_newline_join_v1",
        "row_value": "stored lowercase content_sha256",
        "separator": "\n",
        "trailing_separator": False,
        "key_component_order": {
            "cutoff_at": "ascending_utc_instant",
            "quant_id": "ascending_unsigned_utf8_bytes",
            "horizon": "ascending_unsigned_utf8_bytes",
        },
        "database_collation": "forbidden",
        "forecast_order": ["cutoff_at", "quant_id", "horizon"],
        "outcome_order": ["cutoff_at", "horizon"],
        "bytewise_order_examples": {
            "quant_id": [
                "q10_options_vol", "q11_regime", "q12_event_session",
                "q1_momentum", "q2_mean_reversion", "q3_volatility",
                "q4_stat_arb", "q5_microstructure", "q6_volume_liquidity",
                "q7_relative_value", "q8_cross_asset", "q9_factor",
            ],
            "horizon": ["15M", "1H", "1M", "30M", "30S", "5M"],
        },
    }


def test_metric_hash_contract_pins_exact_numerical_serialization() -> None:
    contract = _payload()["metric_hash_contract"]
    assert contract["algorithm"] == "sha256_utf8_metric_array_v1"
    assert contract["quant_order"] == QUANTS
    assert contract["horizon_order"] == HORIZONS
    assert contract["field_order"] == METRIC_FIELDS
    assert contract["integer_fields"] == ["eligible_count", "resolved_count"]
    assert contract["nullable_integer_fields"] == ["directional_wins", "directional_losses"]
    assert contract["nullable_float_fields"] == ["directional_accuracy", "rmse", "mae", "bias"]
    assert contract["required_float_fields"] == ["coverage"]
    assert contract["float_encoding"] == "finite_ieee754_binary64_python_float_hex_string"
    assert contract["null_encoding"] == "json_null"
    assert contract["json_encoding"] == {
        "ensure_ascii": False, "allow_nan": False, "sort_keys": False,
        "item_separator": ",", "key_separator": ":", "trailing_newline": False,
    }
    assert contract["digest_encoding"] == "lowercase_hex"


def test_current_orchestrator_remains_plain_sequential_h2d1() -> None:
    tree = ast.parse(BATCH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert not imported_roots.intersection({"asyncio", "concurrent", "multiprocessing", "threading"})
    assert not any(isinstance(node, (ast.AsyncFor, ast.AsyncFunctionDef)) for node in ast.walk(tree))

    execute = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "execute")
    day_loops = [
        node for node in ast.walk(execute)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name) and node.target.id == "day"
        and isinstance(node.iter, ast.Name) and node.iter.id == "days"
    ]
    assert len(day_loops) == 1
    stage_calls = []
    for node in ast.walk(day_loops[0]):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "run_json":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                stage_calls.append((node.lineno, node.args[1].value))
    assert [stage for _, stage in sorted(stage_calls)] == ["H1", "H2B", "H2C_RESOLVE", "H2C_SCORE"]


def test_freeze_requires_exact_behavior_parity_and_no_writes() -> None:
    law = _law()
    required = (
        "exactly two isolated worker processes",
        "Everything inside one date remains chronological and sequential",
        "forecast_count = frame_count × 12 × 6", "outcome_count = frame_count × 6",
        "72 metric objects field-for-field", "zero evidence writes",
        "Any numerical, lineage, count, hash, duplicate, ordering, or receipt mismatch fails",
        "H2-D-2 changes no runtime",
    )
    for clause in required:
        assert clause in law


def test_root_freeze_and_phase_boundary_remain_explicit() -> None:
    root_law = _law(ROOT_FREEZE)
    phases = _law(PHASES)
    compute_decision = _law(H2D4_DECISION)
    assert "H2-D-2 is a design freeze only" in root_law
    assert "not unrelated runtime or V9 source-file hashes" in root_law
    assert "H2-D-3 — Parallel Canary (complete)" in phases
    assert "No within-date concurrency or evidence writes" in phases
    assert "H2-D-4 — Compute decision (complete)" in phases
    scale_law = _law(H2D5_FREEZE)
    assert "H2-D-5 — Scaled replay (complete)" in phases
    assert "exactly four certified sessions" in scale_law
    assert "exactly two ordered batches of two worker processes" in scale_law
    assert "No evidence insert, update, delete, repair, or recertification" in scale_law
    assert "H2-D-6 remains a separate gate" in scale_law
    persistence_law = _law(H2D6_FREEZE)
    assert "H2-D-6 — Historical-persistence gate (implementation authorized)" in phases
    assert "one exact idempotent persistence retry" in persistence_law
    assert "return `0` writes" in persistence_law
    assert "authorizes no new historical date" in persistence_law
    assert "keep current Render and Supabase tiers" in compute_decision
    assert "1.9470569578619206" in compute_decision
    assert "Evidence writes | `0`" in compute_decision


def test_q10_audit_uses_frames_not_outcomes_in_forecast_equation() -> None:
    audit = Q10_AUDIT.read_text(encoding="utf-8")
    assert "10,445 frames × 12 families × 6 horizons" in audit
    assert "62,670 frames ×" not in audit
