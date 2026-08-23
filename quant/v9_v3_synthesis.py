"""Pure, deterministic V9-V3 directional forecast synthesis.

The function in this module consumes only the immutable V1 and V2D values
supplied by its caller.  In particular it does not hydrate, wait, retry, scan
history, or access persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Sequence

from quant.v9_v1_contract import (
    CONTRACT_VERSION as V1_CONTRACT_VERSION, DIRECTIONAL_BPS, HORIZONS,
    HORIZON_SECONDS, V1Input,
)
from quant.v9_v2d_evidence_state import (
    DirectionalCalibrationState, HorizonEvidenceState, V2EvidenceState,
)


CONTRACT_VERSION = "V9-V3"
MODEL_VERSION = "ATOM-TRUE-V9-V3"
CANONICAL_FAMILIES = (
    "q1_momentum", "q2_mean_reversion", "q4_stat_arb", "q5_microstructure",
    "q6_volume_liquidity", "q7_relative_value", "q8_cross_asset", "q9_factor",
    "q10_options_vol", "q11_regime", "q12_event_session",
)
_TOL = 1e-10


@dataclass(frozen=True, slots=True)
class V3HorizonResult:
    horizon: str
    horizon_seconds: int
    expected_return_bps: float | None
    predictive_variance_bps2: float | None
    status: str
    used_quant_ids: tuple[str, ...]
    weights: tuple[float, ...]
    directional_input_count: int
    covariance_mode: str | None
    q3_used: bool = False
    q3_diagnostic_magnitude_bps: float | None = None
    gamma: float = 0.0
    phi: float = 1.0
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class V3Output:
    model_version: str
    cycle_id: str
    symbol: str
    computation_status: str
    horizon_results: tuple[V3HorizonResult, ...]


def _jacobi(matrix: Sequence[Sequence[float]]) -> tuple[list[float], list[list[float]]]:
    """Symmetric Jacobi eigensystem, with canonical eigenvector signs."""
    n = len(matrix); a = [list(row) for row in matrix]
    v = [[float(i == j) for j in range(n)] for i in range(n)]
    for _ in range(max(1, 80 * n * n)):
        p, q, largest = 0, 0, 0.0
        for i in range(n):
            for j in range(i + 1, n):
                if abs(a[i][j]) > largest: p, q, largest = i, j, abs(a[i][j])
        if largest <= 1e-13 * max(1.0, max(abs(a[i][i]) for i in range(n))): break
        angle = .5 * math.atan2(2.0 * a[p][q], a[q][q] - a[p][p])
        c, s = math.cos(angle), math.sin(angle)
        for k in range(n):
            if k not in (p, q):
                akp, akq = a[k][p], a[k][q]
                a[k][p] = a[p][k] = c * akp - s * akq
                a[k][q] = a[q][k] = s * akp + c * akq
        app, aqq, apq = a[p][p], a[q][q], a[p][q]
        a[p][p] = c*c*app - 2*c*s*apq + s*s*aqq
        a[q][q] = s*s*app + 2*c*s*apq + c*c*aqq
        a[p][q] = a[q][p] = 0.0
        for k in range(n):
            vkp, vkq = v[k][p], v[k][q]
            v[k][p], v[k][q] = c*vkp - s*vkq, s*vkp + c*vkq
    return [a[i][i] for i in range(n)], v


def _pinv_solve(a: Sequence[Sequence[float]], b: Sequence[float], *, psd=True) -> list[float] | None:
    vals, vecs = _jacobi(a); scale = max(1.0, *(abs(x) for x in vals))
    if psd and min(vals, default=0.0) < -_TOL * scale: return None
    answer = [0.0] * len(a)
    for k, value in enumerate(vals):
        projection = sum(vecs[i][k] * b[i] for i in range(len(a)))
        if abs(value) <= _TOL * scale:
            if abs(projection) > 1e-8 * max(1.0, max(map(abs, b), default=0.0)): return None
            continue
        for i in range(len(a)): answer[i] += vecs[i][k] * projection / value
    return answer


def _cholesky_solve(a: Sequence[Sequence[float]], b: Sequence[float]) -> list[float] | None:
    """Solve a positive-definite system using deterministic Cholesky."""
    n = len(a); lower = [[0.0] * n for _ in range(n)]
    scale = max(1.0, max((abs(value) for row in a for value in row), default=0.0))
    for i in range(n):
        for j in range(i + 1):
            value = a[i][j] - sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                if value <= _TOL * scale: return None
                lower[i][j] = math.sqrt(value)
            else:
                lower[i][j] = value / lower[j][j]
    y = [0.0] * n
    for i in range(n): y[i] = (b[i] - sum(lower[i][j]*y[j] for j in range(i))) / lower[i][i]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (y[i] - sum(lower[j][i]*x[j] for j in range(i + 1, n))) / lower[i][i]
    return x


def _face_solution(block: Sequence[Sequence[float]]) -> list[float] | None:
    direct = _cholesky_solve(block, [1.0] * len(block))
    if direct is not None:
        denominator = sum(direct)
        return None if denominator <= _TOL else [value / denominator for value in direct]
    n = len(block)
    kkt = [[0.0] * (n + 1) for _ in range(n + 1)]
    for i in range(n):
        for j in range(n): kkt[i][j] = 2.0 * block[i][j]
        kkt[i][n] = kkt[n][i] = 1.0
    solved = _pinv_solve(kkt, [0.0] * n + [1.0], psd=False)
    if solved is None: return None
    residual = [sum(kkt[i][j]*solved[j] for j in range(n + 1)) - (1.0 if i == n else 0.0)
                for i in range(n + 1)]
    return solved[:n] if max(map(abs, residual), default=0.0) <= 1e-7 else None


def _optimize(omega: tuple[tuple[float, ...], ...]) -> tuple[tuple[float, ...], float] | None:
    n = len(omega)
    vals, _ = _jacobi(omega); scale = max(1.0, max((abs(x) for x in vals), default=0.0))
    if min(vals, default=0.0) < -_TOL * scale: return None
    if max((abs(x) for row in omega for x in row), default=0.0) <= _TOL:
        return (tuple(1.0/n for _ in range(n)), 0.0)
    best = None
    # Enumerating faces is deterministic and also handles singular face KKT systems.
    for mask in range(1, 1 << n):
        active = [i for i in range(n) if mask >> i & 1]
        block = [[omega[i][j] for j in active] for i in active]
        solution = _face_solution(block)
        if solution is None: continue
        w = [0.0] * n
        for i, value in zip(active, solution): w[i] = value
        if any(value < -1e-8 for value in w): continue
        w = [max(0.0, value) for value in w]
        gradients = [sum(omega[i][j]*w[j] for j in range(n)) for i in range(n)]
        lam = sum(w[i]*gradients[i] for i in range(n))
        if (any(abs(gradients[i]-lam) > 2e-7*scale for i in active) or
                any(gradients[i] < lam-2e-7*scale for i in range(n) if i not in active)):
            continue
        q = sum(w[i]*omega[i][j]*w[j] for i in range(n) for j in range(n))
        candidate = (q, tuple(w))
        if best is None or candidate < best: best = candidate
    return None if best is None else (best[1], max(0.0, best[0]))


def _largest_supported(ids: tuple[str, ...], state: HorizonEvidenceState) -> tuple[str, ...]:
    positions = {quant_id: index for index, quant_id in enumerate(state.ordered_quant_ids)}
    best: tuple[str, ...] = ()
    for mask in range(1, 1 << len(ids)):
        candidate = tuple(ids[i] for i in range(len(ids)) if mask >> i & 1)
        if len(candidate) < len(best): continue
        ok = all(state.pair_support_boolean_matrix[positions[a]][positions[b]]
                 for a in candidate for b in candidate)
        candidate_rank = tuple(ids.index(item) for item in candidate)
        best_rank = tuple(ids.index(item) for item in best)
        if ok and (len(candidate) > len(best) or candidate_rank < best_rank): best = candidate
    return best


def _unavailable(horizon: str, *reasons: str) -> V3HorizonResult:
    return V3HorizonResult(horizon, HORIZON_SECONDS[horizon], None, None,
                           "UNAVAILABLE", (), (), 0, None,
                           reason_codes=tuple(sorted(set(reasons))))


def _same_instant(value: datetime | None, epoch_seconds: float) -> bool:
    return (isinstance(value, datetime) and value.tzinfo is not None and
            math.isclose(value.timestamp(), epoch_seconds, rel_tol=0.0, abs_tol=1e-6))


def _v1_evidence_compatible(v1: V1Input, v2: V2EvidenceState) -> bool:
    """Require the complete frozen V1/V2D identity, not merely a matching hash."""
    return (
        v1.contract_version == V1_CONTRACT_VERSION and
        v1.symbol == v2.symbol and
        tuple(v1.horizons) == HORIZONS and
        v1.evidence_state_id == v2.state_id and
        v1.evidence_state_version == v2.state_version and
        v1.evidence_state_hash == v2.state_hash and
        _same_instant(v1.evidence_state_as_of, v2.state_as_of) and
        isinstance(v2.state_as_of, (int, float)) and
        not isinstance(v2.state_as_of, bool) and
        math.isfinite(v2.state_as_of) and
        v2.state_as_of <= v1.cutoff_at.timestamp() and
        v1.target_spec_id == v2.target_spec_id and
        v1.data_schema_version == v2.target_data_schema_version and
        v1.source_spec_version == v2.target_source_spec_version
    )


def _eligible_v1_slot(slot: object, calibration: DirectionalCalibrationState,
                      v1: V1Input, horizon: str) -> bool:
    """Recheck every frozen FRESH/causal/finite/version eligibility predicate."""
    value = slot.value_bps
    return (
        slot.quant_id == calibration.quant_id and
        slot.horizon == horizon and
        slot.horizon_seconds == HORIZON_SECONDS[horizon] and
        slot.numerical_type == DIRECTIONAL_BPS and
        slot.availability_state == "FRESH" and
        slot.formula_version == calibration.formula_version and
        slot.data_schema_version == v1.data_schema_version and
        slot.source_spec_version == v1.source_spec_version and
        isinstance(value, (int, float)) and not isinstance(value, bool) and
        math.isfinite(value) and
        isinstance(slot.forecast_cutoff_at, datetime) and
        slot.forecast_cutoff_at.tzinfo is not None and
        slot.forecast_cutoff_at == v1.cutoff_at and
        all(isinstance(item, datetime) and item.tzinfo is not None and
            item <= v1.cutoff_at
            for item in (slot.source_as_of_at, slot.available_at))
    )


def synthesize_v3(v1: V1Input, v2: V2EvidenceState) -> V3Output:
    """Synthesize six horizons with no external I/O or temporal fallback."""
    evidence_compatible = _v1_evidence_compatible(v1, v2)
    by_horizon = {item.horizon: item for item in v2.horizon_state_tuple}
    results = []
    for horizon in HORIZONS:
        state = by_horizon.get(horizon)
        if state is None or not evidence_compatible:
            results.append(_unavailable(horizon, "V2_EVIDENCE_VERSION_MISMATCH")); continue
        calibrations = {item.quant_id: item for item in state.directional_calibrations}
        slots = {item.quant_id: item for item in v1.slots if item.horizon == horizon}
        eligible = tuple(q for q in CANONICAL_FAMILIES
                         if q in calibrations and q in slots and
                         calibrations[q].status != "UNAVAILABLE" and
                         _eligible_v1_slot(slots[q], calibrations[q], v1, horizon))
        if not eligible:
            results.append(_unavailable(horizon, "NO_ELIGIBLE_DIRECTIONAL_FAMILY")); continue
        if len(eligible) == 1:
            used, mode = eligible, "SINGLE_FAMILY_RESIDUAL_VARIANCE"
        elif state.stabilized_covariance_matrix is None:
            results.append(_unavailable(horizon, "COVARIANCE_UNAVAILABLE")); continue
        else:
            used = _largest_supported(eligible, state)
            if not used:
                results.append(_unavailable(horizon, "NO_COVARIANCE_COMPATIBLE_FAMILY")); continue
            mode = "FULL_DEPENDENCE" if len(used) == len(eligible) else "PRINCIPAL_SUBSET"
        xs, uncertainty = [], []
        for qid in used:
            cal, raw = calibrations[qid], float(slots[qid].value_bps)
            xs.append(cal.calibration_intercept + cal.calibration_slope * raw)
            z0, z1 = 1.0, raw; cov = cal.calibration_parameter_covariance_2x2
            uncertainty.append(z0*z0*cov[0][0] + 2*z0*z1*cov[0][1] + z1*z1*cov[1][1])
        if not all(math.isfinite(x) and math.isfinite(u) and u >= -_TOL for x, u in zip(xs, uncertainty)):
            results.append(_unavailable(horizon, "NONFINITE_OR_INVALID_UNCERTAINTY")); continue
        if len(used) == 1:
            omega = ((calibrations[used[0]].residual_variance + max(0.0, uncertainty[0]),),)
        else:
            pos = {q: i for i, q in enumerate(state.ordered_quant_ids)}
            omega = tuple(tuple(state.stabilized_covariance_matrix[pos[a]][pos[b]] +
                                (max(0.0, uncertainty[i]) if i == j else 0.0)
                                for j, b in enumerate(used)) for i, a in enumerate(used))
        if not all(math.isfinite(value) for row in omega for value in row):
            results.append(_unavailable(horizon, "NONFINITE_OMEGA")); continue
        solved = _optimize(omega)
        if solved is None:
            results.append(_unavailable(horizon, "OMEGA_NOT_PSD_OR_KKT_FAILURE")); continue
        weights, variance = solved
        mu = sum(w*x for w, x in zip(weights, xs))
        q3 = slots.get("q3_volatility")
        diagnostic = (float(q3.value_bps) if q3 and q3.availability_state == "FRESH" and
                      q3.value_bps is not None and math.isfinite(q3.value_bps) else None)
        provisional = (state.covariance_status == "PROVISIONAL" or
                       any(calibrations[q].status == "PROVISIONAL" for q in used))
        results.append(V3HorizonResult(
            horizon, HORIZON_SECONDS[horizon], mu, variance,
            "PROVISIONAL" if provisional else "MATURE", used, weights, len(eligible),
            mode, q3_diagnostic_magnitude_bps=diagnostic,
            reason_codes=("DIAGONAL_PROVISIONAL",) if
            state.covariance_status == "PROVISIONAL" and not state.dependence_modeled else (),
        ))
    overall = ("UNAVAILABLE" if all(r.status == "UNAVAILABLE" for r in results) else
               "MATURE" if all(r.status == "MATURE" for r in results) else "PROVISIONAL")
    return V3Output(MODEL_VERSION, v1.cycle_id, v1.symbol, overall, tuple(results))
