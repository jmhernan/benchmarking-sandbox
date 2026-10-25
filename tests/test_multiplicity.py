import math

import numpy as np
import pytest
from scipy import stats

from bench_stats.stats.multiplicity import benjamini_hochberg, expected_false_flags


def test_bh_matches_scipy():
    rng = np.random.default_rng(5)
    p = np.concatenate([rng.uniform(size=15), rng.uniform(0, 0.01, 5)])
    rejected, adjusted = benjamini_hochberg(p, 0.05)
    np.testing.assert_allclose(adjusted, stats.false_discovery_control(p, method="bh"), rtol=1e-12)
    np.testing.assert_array_equal(rejected, adjusted <= 0.05)


def test_bh_textbook_example():
    p = [0.01, 0.04, 0.03, 0.005, 0.2]
    rejected, _ = benjamini_hochberg(p, 0.05)
    assert rejected.tolist() == [True, True, True, True, False]


def test_bh_ignores_nan():
    rejected, adjusted = benjamini_hochberg([0.001, math.nan, 0.5], 0.05)
    assert rejected.tolist() == [True, False, False]
    assert math.isnan(adjusted[1])
    assert adjusted[0] == pytest.approx(0.002)


def test_expected_false_flags():
    flags = expected_false_flags(20)
    assert flags["detectable (interval excludes 1)"] == pytest.approx(1.0)
    assert flags["gate ≥ δ, worst case at θ = 1 + δ"] == pytest.approx(0.5)
