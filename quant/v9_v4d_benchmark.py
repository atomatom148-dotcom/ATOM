"""Deterministic V4D performance harnesses (not used by production paths)."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Sequence

from quant.v9_v1_contract import V1Input
from quant.v9_v2d_evidence_state import V2EvidenceState
from quant.v9_v3_synthesis import V3HorizonResult, synthesize_v3
from quant.v9_v4c_predictive import CompactHorizonState, final_numbers


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    evaluation_count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    maximum_ms: float
    threshold_ms: float
    status: str


def _report(samples: list[float], count: int, threshold: float) -> BenchmarkReport:
    samples.sort()
    at = lambda p: samples[max(0, math.ceil(p * len(samples)) - 1)]
    p99 = at(.99)
    return BenchmarkReport(count, at(.50), at(.95), p99, samples[-1], threshold,
                           "PASS" if p99 <= threshold else "FAIL")


def benchmark_v4(results: Sequence[V3HorizonResult],
                 states: Sequence[CompactHorizonState | None], *,
                 evaluations: int = 100_000, warmup: int = 1_000) -> BenchmarkReport:
    """Measure only frozen pure live six-horizon calculations."""
    if len(results) != 6 or len(states) != 6 or evaluations < 100_000:
        raise ValueError("six horizons and at least 100,000 evaluations required")
    evaluate = lambda: tuple(final_numbers(result, state)
                             for result, state in zip(results, states))
    for _ in range(warmup): evaluate()
    samples = []
    for _ in range(evaluations):
        started = time.perf_counter_ns(); evaluate()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return _report(samples, evaluations, 10.0)


def benchmark_v3(v1: V1Input, v2: V2EvidenceState, *, cycles: int = 10_000,
                 warmup: int = 100) -> BenchmarkReport:
    """Measure complete frozen deterministic six-horizon synthesis."""
    if cycles < 10_000:
        raise ValueError("at least 10,000 cycles required")
    for _ in range(warmup): synthesize_v3(v1, v2)
    samples = []
    for _ in range(cycles):
        started = time.perf_counter_ns(); synthesize_v3(v1, v2)
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return _report(samples, cycles, 100.0)


__all__ = ["BenchmarkReport", "benchmark_v3", "benchmark_v4"]
