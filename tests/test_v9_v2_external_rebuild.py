"""Full-horizon integration contract for the offline external V2 command."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from quant.evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from quant.v9_production import (
    FORMULA_VERSIONS, FORMULA_VERSION_MAP, PostgresV2StateBuilder,
)
from quant.v9_v1_contract import (
    HORIZONS, HORIZON_SECONDS, MAGNITUDE_BPS, QUANT_IDS, V1SlotObservation,
    build_v1_input,
)
from quant.v9_v2_external_rebuild import main, rebuild_external_v2
from quant.v9_v2d_evidence_state import serialize_v2_evidence_state
from quant.v9_v3_synthesis import synthesize_v3


NOW = 2_000_000_000.0


def _source_rows():
    directional = []
    magnitude = []
    record_id = 1
    for horizon in HORIZONS:
        seconds = HORIZON_SECONDS[horizon]
        for sample in range(4):
            cutoff = float(sample * seconds)
            maturity = cutoff + seconds
            for quant_id, formula in FORMULA_VERSIONS:
                if quant_id == "q3_volatility":
                    magnitude.append((
                        record_id, quant_id, formula, f"{horizon}-{sample}",
                        "COIN", horizon, cutoff, maturity, float(sample + 1),
                        cutoff, DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION,
                        maturity, cutoff, maturity,
                    ))
                else:
                    # Q10 is deliberately certified unavailable without a
                    # source-as-of proof; all other frozen families are causal.
                    source_as_of = None if quant_id == "q10_options_vol" else cutoff
                    directional.append((
                        record_id, quant_id, formula, f"{horizon}-{sample}",
                        "COIN", horizon, cutoff, maturity,
                        float(sample + record_id % 3), cutoff,
                        DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION,
                        source_as_of, float(sample * 2 + 1), maturity,
                        cutoff, maturity,
                    ))
                record_id += 1
    return directional, magnitude


class Cursor:
    def __init__(self, directional, magnitude):
        self.directional = directional
        self.magnitude = magnitude
        self.volatility = False
        self.parameters = ()
        self.snapshot = False

    def execute(self, sql, parameters):
        self.parameters = parameters
        self.snapshot = "transaction_timestamp" in sql
        self.volatility = "volatility_forecasts" in sql

    def fetchone(self):
        return (NOW,)

    def fetchall(self):
        rows = self.magnitude if self.volatility else self.directional
        if len(self.parameters) > 7:
            key = tuple(self.parameters[-4:-1])
            rows = [row for row in rows if (row[5], row[6], row[0]) > key]
        return rows[:4096]

    def close(self): pass


class Connection:
    def __init__(self, directional, magnitude):
        self.cursor_value = Cursor(directional, magnitude)
    def cursor(self): return self.cursor_value
    def rollback(self): pass
    def close(self): pass


def _connect_factory():
    directional, magnitude = _source_rows()
    return lambda _url: Connection(directional, magnitude)


def test_external_pipeline_builds_all_72_slots_matches_legacy_and_restores_v3(
        tmp_path, monkeypatch):
    connect = _connect_factory()
    legacy = PostgresV2StateBuilder("postgresql://fixture", connect=connect).build(
        state_as_of=NOW - 1)
    monkeypatch.setattr(
        PostgresV2StateBuilder, "build",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy full-memory builder invoked")),
    )
    result = rebuild_external_v2(
        database_url="postgresql://fixture", workspace_root=tmp_path,
        state_as_of=NOW - 1, connect=_connect_factory(), publish=False,
    )
    assert serialize_v2_evidence_state(result.state) == serialize_v2_evidence_state(legacy)
    assert result.state.state_hash == legacy.state_hash
    assert result.state.state_id == legacy.state_id
    assert result.state.evidence_manifest_hash == legacy.evidence_manifest_hash
    assert tuple(item.horizon for item in result.state.horizon_state_tuple) == HORIZONS
    assert len(result.receipt.per_family_horizon_admitted_counts) == 72
    assert all(count == 0 for horizon, quant_id, count
               in result.receipt.per_family_horizon_admitted_counts
               if quant_id == "q10_options_vol")
    assert result.temporary_disk_peak_bytes > 0
    assert not list(tmp_path.glob("atom-v2-external-rebuild-*"))

    cutoff = datetime.fromtimestamp(NOW, timezone.utc)
    state_as_of = datetime.fromtimestamp(result.state.state_as_of, timezone.utc)
    slots = []
    versions = dict(FORMULA_VERSIONS)
    for quant_id in QUANT_IDS:
        for horizon in HORIZONS:
            slots.append(V1SlotObservation(
                quant_id, versions[quant_id], horizon, HORIZON_SECONDS[horizon],
                MAGNITUDE_BPS if quant_id == "q3_volatility" else "DIRECTIONAL_BPS",
                None, cutoff, cutoff, cutoff, "MISSING", DATA_SCHEMA_VERSION,
                SOURCE_SPEC_VERSION,
            ))
    v1 = build_v1_input(
        cycle_id="restore", cutoff_at=cutoff,
        target_spec_id=result.state.target_spec_id,
        data_schema_version=result.state.target_data_schema_version,
        source_spec_version=result.state.target_source_spec_version, slots=slots,
        evidence_state_id=result.state.state_id,
        evidence_state_version=result.state.state_version,
        evidence_state_hash=result.state.state_hash,
        evidence_state_as_of=state_as_of,
    )
    output = synthesize_v3(v1, result.state)
    assert len(output.horizon_results) == 6
    assert v1.evidence_state_id == result.state.state_id


def test_command_dispatches_external_pipeline_not_legacy(tmp_path, monkeypatch, capsys):
    called = []
    state = type("State", (), {
        "state_id": "id", "state_hash": "a" * 64,
        "evidence_manifest_hash": "b" * 64,
    })()
    receipt = type("Receipt", (), {"receipt_sha256": "c" * 64})()
    monkeypatch.setattr(
        "quant.v9_v2_external_rebuild.rebuild_external_v2",
        lambda **kwargs: (called.append(kwargs) or type("Result", (), {
            "state": state, "receipt": receipt, "publication_status": None,
            "temporary_disk_peak_bytes": 123,
        })()),
    )
    monkeypatch.setattr(
        PostgresV2StateBuilder, "build",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy full-memory builder invoked")),
    )
    assert main(["--database-url", "postgresql://fixture",
                 "--workspace-root", str(tmp_path), "--validate-only"]) == 0
    assert called and called[0]["publish"] is False
    assert '"temporary_disk_peak_bytes": 123' in capsys.readouterr().out
