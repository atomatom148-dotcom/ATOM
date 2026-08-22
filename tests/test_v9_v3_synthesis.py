import math

from quant.v9_v3_synthesis import _optimize, _psd2, RHO


def test_parameter_uncertainty_and_roundoff_psd_rules():
    assert math.isclose(_psd2(((1.0, 0.25), (0.25, 2.0)), 3.0)[0], 20.5)
    # A tiny asymmetric perturbation is accepted and symmetrized.
    value = _psd2(((1.0, 0.25), (0.25 + RHO, 2.0)), 3.0)
    assert value is not None and math.isfinite(value[0])
    assert _psd2(((1.0, 0.25), (0.5, 2.0)), 3.0) is None
    assert _psd2(((1.0, 0.0), (0.0, -1.0)), 3.0) is None


def test_simplex_minimum_variance_diagonal_solution():
    solved = _optimize([[1.0, 0.0], [0.0, 4.0]])
    assert solved is not None
    weights, variance, residual = solved
    assert all(math.isclose(x, y) for x, y in zip(weights, [0.8, 0.2]))
    assert math.isclose(variance, 0.8)
    assert residual < 1e-12


def test_singular_identically_zero_support_is_usable():
    solved = _optimize([[0.0, 0.0], [0.0, 0.0]])
    assert solved is not None
    weights, variance, residual = solved
    assert weights == [0.5, 0.5]
    assert variance == 0.0
    assert residual == 0.0


def test_full_simplex_kkt_selects_boundary_support():
    # The unconstrained stationary point has a negative second weight; the
    # enumerated singleton is therefore the valid minimum.
    solved = _optimize([[1.0, 2.0], [2.0, 10.0]])
    assert solved is not None
    weights, variance, _ = solved
    assert weights == [1.0, 0.0]
    assert variance == 1.0
