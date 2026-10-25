import math

import numpy as np
import pytest
from scipy import stats

from bench_stats.stats.fieller import fieller
from bench_stats.stats.paired import paired_log_ratio
from bench_stats.stats.welch_log import welch_log


@pytest.fixture
def rng():
    return np.random.default_rng(42)


def test_paired_log_ratio_matches_one_sample_t(rng):
    shared = rng.normal(0, 0.02, 8)
    a = 1000 * np.exp(shared + rng.normal(0.03, 0.005, 8))
    b = 1000 * np.exp(shared + rng.normal(0.0, 0.005, 8))
    r = paired_log_ratio(a, b)
    d = np.log(a) - np.log(b)
    lo, hi = stats.t.interval(0.95, d.size - 1, d.mean(), stats.sem(d))
    assert r.lower == pytest.approx(math.exp(lo), rel=1e-12)
    assert r.upper == pytest.approx(math.exp(hi), rel=1e-12)
    assert r.p_value == pytest.approx(stats.ttest_1samp(d, 0).pvalue, rel=1e-10)


def test_paired_needs_equal_lengths():
    with pytest.raises(ValueError):
        paired_log_ratio([1, 2, 3], [1, 2])


def test_welch_log_matches_scipy(rng):
    a = rng.lognormal(0.02, 0.01, 6)
    b = rng.lognormal(0.0, 0.02, 9)
    r = welch_log(a, b)
    test = stats.ttest_ind(np.log(a), np.log(b), equal_var=False)
    assert r.p_value == pytest.approx(test.pvalue, rel=1e-10)
    assert r.lower < r.ratio < r.upper


def test_fieller_p_value_agrees_with_interval(rng):
    """The bounded Fieller interval excludes 1 exactly when its p-value is below 1 - conf."""
    for _ in range(500):
        n = rng.integers(3, 12)
        paired = bool(rng.integers(2))
        a = 1000 * (1 + rng.normal(rng.normal(0, 0.01), 0.01, n))
        b = 1000 * (1 + rng.normal(0, 0.01, n))
        r = fieller(a, b, paired=paired)
        if r.bounded:
            assert r.excludes_one == (r.p_value < 0.05), (r, a, b)


def test_paired_fieller_narrower_with_shared_process_effect(rng):
    shared = rng.normal(0, 0.03, 10)
    a = 1000 * np.exp(shared + rng.normal(0, 0.005, 10))
    b = 1000 * np.exp(shared + rng.normal(0, 0.005, 10))
    paired, unpaired = fieller(a, b, paired=True), fieller(a, b)
    assert paired.relative_half_width < unpaired.relative_half_width / 3


def test_interval_degenerate_cases():
    assert not fieller([1.0], [1.0, 2.0]).is_valid
    assert not welch_log([1.0], [1.0, 2.0]).is_valid
    assert not paired_log_ratio([1.0], [1.0]).is_valid
    r = fieller([2.0, 2.0], [1.0, 1.0])
    assert r.ratio == r.lower == r.upper == 2.0 and r.p_value == 0.0
