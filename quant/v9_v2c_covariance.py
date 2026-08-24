"""Pure V9 V2-C residual covariance estimation.

The caller supplies the frozen V2-A dataset and V2-B result.  This module does
not read or write evidence and deliberately produces no live forecast.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import sys

from quant.v9_v2a_dataset import (
    DIRECTIONAL_FAMILIES, FamilyLineage, TargetIdentity, V2ADataset,
    v2a_dataset_hash,
)
from quant.v9_v2b_calibration import (
    V2BCalibration, effective_n, v2b_component_hash,
)


METHOD_VERSION = "V9-V2C-2"
OAS_METHOD = "STANDARD_COMPLETE_CASE_OAS"
EPSILON_RELATIVE = math.sqrt(sys.float_info.epsilon)
EPSILON_ABSOLUTE = sys.float_info.min


Matrix = tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class V2CCovariance:
    method_version: str
    horizon: str
    dataset_hash: str
    v2b_component_hash: str
    ordered_quant_ids: tuple[str, ...]
    ordered_formula_versions: tuple[str, ...]
    ordered_family_lineage: tuple[FamilyLineage, ...]
    pairwise_raw_synchronized_n_matrix: Matrix
    pairwise_effective_n_matrix: Matrix
    pair_support_boolean_matrix: tuple[tuple[bool, ...], ...]
    raw_pairwise_covariance_matrix: Matrix
    complete_case_quant_ids: tuple[str, ...]
    complete_case_n: int
    duplicate_groups: tuple[tuple[str, ...], ...]
    empirical_complete_case_covariance_matrix: Matrix
    shrinkage_method: str | None
    shrinkage_intensity: float | None
    pooled_variance: float | None
    psd_projected_matrix: Matrix
    stabilized_covariance_matrix: Matrix
    minimum_eigenvalue_before: float | None
    minimum_eigenvalue_after: float | None
    clipped_eigenvalue_count: int
    psd_correction_frobenius_norm: float | None
    psd_relative_correction: float | None
    numerical_ridge: float | None
    condition_number_after_ridge: float | None
    dependence_modeled: bool
    status: str
    reason_codes: tuple[str, ...]


def _matrix(rows: list[list[float]]) -> Matrix:
    return tuple(tuple(0.0 if value == 0.0 else float(value) for value in row)
                 for row in rows)


def _jacobi(source: list[list[float]]) -> tuple[list[float], list[list[float]]]:
    """Deterministic binary64 Jacobi eigensolver for a real symmetric matrix."""
    n = len(source)
    a = [row[:] for row in source]
    q = [[float(i == j) for j in range(n)] for i in range(n)]
    if n < 2:
        return ([a[0][0]] if n else []), q
    for _ in range(max(32, 100 * n * n)):
        off, p, r = max((abs(a[i][j]), i, j)
                        for i in range(n) for j in range(i + 1, n))
        scale = max(1.0, max(abs(a[i][i]) for i in range(n)))
        if off <= 8.0 * sys.float_info.epsilon * scale:
            break
        tau = (a[r][r] - a[p][p]) / (2.0 * a[p][r])
        t = math.copysign(1.0, tau) / (abs(tau) + math.sqrt(1.0 + tau*tau))
        c = 1.0 / math.sqrt(1.0 + t*t)
        s = t*c
        app, arr, apr = a[p][p], a[r][r], a[p][r]
        a[p][p] = app - t*apr
        a[r][r] = arr + t*apr
        a[p][r] = a[r][p] = 0.0
        for k in range(n):
            if k not in (p, r):
                akp, akr = a[k][p], a[k][r]
                a[k][p] = a[p][k] = c*akp - s*akr
                a[k][r] = a[r][k] = s*akp + c*akr
            qkp, qkr = q[k][p], q[k][r]
            q[k][p], q[k][r] = c*qkp - s*qkr, s*qkp + c*qkr
    order = sorted(range(n), key=lambda i: (a[i][i], i))
    return [a[i][i] for i in order], [[q[row][i] for i in order] for row in range(n)]


def _psd(source: list[list[float]]) -> tuple[list[list[float]], float, float, int, float, float]:
    n = len(source)
    b = [[(source[i][j] + source[j][i])/2.0 for j in range(n)] for i in range(n)]
    values, vectors = _jacobi(b)
    clipped = [max(0.0, value) for value in values]
    out = [[math.fsum(vectors[i][k]*clipped[k]*vectors[j][k] for k in range(n))
            for j in range(n)] for i in range(n)]
    out = [[(out[i][j]+out[j][i])/2.0 for j in range(n)] for i in range(n)]
    correction = math.sqrt(math.fsum((out[i][j]-b[i][j])**2
                                     for i in range(n) for j in range(n)))
    norm = math.sqrt(math.fsum(b[i][j]**2 for i in range(n) for j in range(n)))
    after, _ = _jacobi(out)
    return out, min(values), min(after), sum(x < 0.0 for x in values), correction, correction/max(norm, sys.float_info.min)


def _oas(rows: list[list[float]]) -> tuple[list[list[float]], list[list[float]], float, float]:
    n, p = len(rows), len(rows[0])
    means = [math.fsum(row[j] for row in rows)/n for j in range(p)]
    centered = [[row[j]-means[j] for j in range(p)] for row in rows]
    s = [[math.fsum(row[i]*row[j] for row in centered)/n
          for j in range(p)] for i in range(p)]
    if p == 1:
        return s, [s[0][:]], 1.0, s[0][0]
    t1 = math.fsum(s[i][i] for i in range(p))
    t2 = math.fsum(s[i][j]*s[j][i] for i in range(p) for j in range(p))
    numerator = (1.0-2.0/p)*t2 + t1*t1
    denominator = (n+1.0-2.0/p)*(t2-t1*t1/p)
    delta = min(1.0, max(0.0, numerator/denominator)) if denominator > 0.0 else 1.0
    pooled = t1/p
    sigma = [[(1.0-delta)*s[i][j] + (delta*pooled if i == j else 0.0)
              for j in range(p)] for i in range(p)]
    return s, sigma, delta, pooled


def build_v2c_covariance(dataset: V2ADataset, calibration: V2BCalibration) -> V2CCovariance:
    """Build the immutable covariance state for one V2-A horizon cohort."""
    if dataset.dataset_hash != v2a_dataset_hash(dataset):
        raise ValueError("invalid V2-A dataset hash")
    manifest = dict(calibration.input_manifest)
    if (len(manifest) != len(calibration.input_manifest) or
            manifest.get(dataset.horizon) != dataset.dataset_hash):
        raise ValueError("V2-B input manifest does not match V2-A dataset")
    calibration_hash = v2b_component_hash(calibration, dataset.horizon)
    subsets = {item.quant_id: item for item in dataset.directional_subsets}
    quant_ids = tuple(q for q in DIRECTIONAL_FAMILIES if q in subsets)
    calibrations = {}
    for item in calibration.directional:
        key = (item.horizon, item.quant_id, item.formula_version,
               item.data_schema_version, item.source_spec_version,
               item.dataset_hash)
        if key in calibrations:
            raise ValueError("duplicate V2-B directional calibration lineage")
        calibrations[key] = item
    lineage_by_quant = {item.quant_id: item for item in dataset.family_lineage}
    ordered_lineage = tuple(lineage_by_quant[q] for q in quant_ids)
    selected = [calibrations.get((
        dataset.horizon, q, subsets[q].formula_version,
        lineage_by_quant[q].data_schema_version,
        lineage_by_quant[q].source_spec_version, dataset.dataset_hash,
    )) for q in quant_ids]
    formulas = tuple(subsets[q].formula_version for q in quant_ids)
    targets = {row.identity: row.target_bps for row in dataset.skeleton}
    residuals: list[dict[TargetIdentity, float]] = []
    reasons: set[str] = set()
    for q, cal in zip(quant_ids, selected):
        values: dict[TargetIdentity, float] = {}
        if cal is None or cal.status == "UNAVAILABLE":
            reasons.add("V2B_CALIBRATION_UNAVAILABLE")
        else:
            if cal.status != "MATURE":
                reasons.add("V2B_CALIBRATION_PROVISIONAL")
            for observation in subsets[q].observations:
                value = targets[observation.target_identity] - (
                    cal.calibration_intercept + cal.calibration_slope*observation.value_bps)
                if not math.isfinite(value):
                    reasons.add("NONFINITE_RESIDUAL")
                    continue
                values[observation.target_identity] = value
        residuals.append(values)

    p = len(quant_ids)
    counts = [[0.0]*p for _ in range(p)]
    neffs = [[0.0]*p for _ in range(p)]
    support = [[False]*p for _ in range(p)]
    pair_cov = [[0.0]*p for _ in range(p)]
    pair_ids = {(x.left_quant_id, x.right_quant_id): x.target_identities
                for x in dataset.pair_support}
    for i in range(p):
        for j in range(i, p):
            identities = (tuple(row.target_identity for row in subsets[quant_ids[i]].observations)
                          if i == j else pair_ids.get((quant_ids[i], quant_ids[j]), ()))
            pairs = [(residuals[i][identity], residuals[j][identity]) for identity in identities
                     if identity in residuals[i] and identity in residuals[j]]
            n = len(pairs)
            counts[i][j] = counts[j][i] = float(n)
            if n:
                left = math.fsum(x for x, _ in pairs)/n
                right = math.fsum(y for _, y in pairs)/n
                scores = tuple((x-left)*(y-right) for x, y in pairs)
                en = effective_n(scores).effective_n
                neffs[i][j] = neffs[j][i] = en
                ok = n >= 2 and en > 1.0
                support[i][j] = support[j][i] = ok
                covariance = math.fsum(scores)/(n-1) if ok else 0.0
                pair_cov[i][j] = pair_cov[j][i] = covariance
            if not support[i][j]:
                reasons.add("PAIR_COVARIANCE_UNSUPPORTED")

    complete_rows: list[list[float]] = []
    for identity in dataset.complete_case_target_identities:
        if all(identity in series for series in residuals):
            complete_rows.append([series[identity] for series in residuals])
        else:
            reasons.add("COMPLETE_CASE_INTEGRITY_REJECTED")
    complete_n = len(complete_rows)

    representatives: list[int] = []
    groups: list[list[int]] = []
    if complete_rows:
        for j in range(p):
            match = None
            for group_index, rep in enumerate(representatives):
                difference = max(abs(row[j]-row[rep]) for row in complete_rows)
                rms_j = math.sqrt(math.fsum(row[j]**2 for row in complete_rows)/complete_n)
                rms_r = math.sqrt(math.fsum(row[rep]**2 for row in complete_rows)/complete_n)
                if difference <= EPSILON_RELATIVE*max(rms_j, rms_r, sys.float_info.min):
                    match = group_index; break
            if match is None:
                representatives.append(j); groups.append([j])
            else:
                groups[match].append(j)
    duplicate_groups = tuple(tuple(quant_ids[j] for j in group) for group in groups if len(group) > 1)

    empirical = [[0.0]*p for _ in range(p)]
    candidate: list[list[float]] | None = None
    delta = pooled = None
    shrinkage = None
    dependence = False
    if complete_n >= 2 and p and len(representatives):
        collapsed = [[row[j] for j in representatives] for row in complete_rows]
        empirical_c, sigma_c, delta, pooled = _oas(collapsed)
        for gi, group_i in enumerate(groups):
            for gj, group_j in enumerate(groups):
                for i in group_i:
                    for j in group_j:
                        empirical[i][j] = empirical_c[gi][gj]
        candidate = [[sigma_c[next(k for k,g in enumerate(groups) if i in g)]
                              [next(k for k,g in enumerate(groups) if j in g)]
                      for j in range(p)] for i in range(p)]
        shrinkage = OAS_METHOD
        dependence = True
    else:
        reasons.add("COMPLETE_CASE_DEPENDENCE_UNAVAILABLE")
        positive = [pair_cov[i][i] for i in range(p)
                    if support[i][i] and math.isfinite(pair_cov[i][i]) and pair_cov[i][i] > 0.0]
        if positive:
            pooled = math.fsum(positive)/len(positive)
            diagonal = []
            for i in range(p):
                value = pair_cov[i][i] if support[i][i] and pair_cov[i][i] > 0.0 else pooled
                if value == pooled and not (support[i][i] and pair_cov[i][i] > 0.0):
                    reasons.add("POOLED_VARIANCE_FALLBACK")
                diagonal.append(value)
            candidate = [[diagonal[i] if i == j else 0.0 for j in range(p)] for i in range(p)]

    psd_matrix = [[0.0]*p for _ in range(p)]
    stable = [[0.0]*p for _ in range(p)]
    min_before = min_after = correction = relative = ridge = condition = None
    clipped = 0
    status = "UNAVAILABLE"
    if candidate is not None and all(math.isfinite(x) for row in candidate for x in row):
        psd_matrix, min_before, min_after, clipped, correction, relative = _psd(candidate)
        trace = math.fsum(psd_matrix[i][i] for i in range(p))
        if p and math.isfinite(trace) and trace > 0.0:
            ridge = max(EPSILON_ABSOLUTE, EPSILON_RELATIVE*trace/p)
            stable = [[psd_matrix[i][j] + (ridge if i == j else 0.0)
                       for j in range(p)] for i in range(p)]
            eigenvalues, _ = _jacobi(stable)
            condition = max(eigenvalues)/min(eigenvalues)
            material = relative > EPSILON_RELATIVE
            if material:
                reasons.add("MATERIAL_PSD_CORRECTION")
            mature = (dependence and complete_n >= 2 and all(selected) and
                      all(item.status == "MATURE" for item in selected if item) and
                      all(support[i][j] for i in range(p) for j in range(p)) and
                      pooled is not None and math.isfinite(pooled) and pooled > 0.0 and
                      not material and
                      "COMPLETE_CASE_INTEGRITY_REJECTED" not in reasons)
            status = "MATURE" if mature else "PROVISIONAL"
    if status == "UNAVAILABLE":
        reasons.add("SUPPORTED_POSITIVE_SCALE_UNAVAILABLE")
        dependence = False
    return V2CCovariance(
        METHOD_VERSION, dataset.horizon, dataset.dataset_hash,
        calibration_hash, quant_ids, formulas,
        ordered_lineage,
        _matrix(counts), _matrix(neffs), tuple(tuple(row) for row in support), _matrix(pair_cov),
        tuple(quant_ids[j] for j in representatives), complete_n, duplicate_groups,
        _matrix(empirical), shrinkage, delta, pooled, _matrix(psd_matrix), _matrix(stable),
        min_before, min_after, clipped, correction, relative, ridge, condition,
        dependence, status, tuple(sorted(reasons)))


# Construction alias consistent with V2-A and V2-B.
estimate_v2c_covariance = build_v2c_covariance