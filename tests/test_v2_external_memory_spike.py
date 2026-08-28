from pathlib import Path

import pytest

import spikes.v2_external_memory_benchmark as benchmark
from spikes.v2_external_memory_benchmark import PAGE_SIZE, run


def test_spike_preserves_page_boundary_order_and_cleans_workspace(tmp_path: Path):
    result = run(PAGE_SIZE + 1, tmp_path)

    assert result["rows"] == PAGE_SIZE + 1
    assert result["pages"] == 2
    assert result["workspace_removed"] is True
    assert list(tmp_path.iterdir()) == []


def test_spike_cleans_workspace_after_interrupted_build(tmp_path: Path, monkeypatch):
    def interrupt(_record_id: int) -> bytes:
        raise KeyboardInterrupt

    monkeypatch.setattr(benchmark, "canonical_row", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run(1, tmp_path)

    assert list(tmp_path.iterdir()) == []
