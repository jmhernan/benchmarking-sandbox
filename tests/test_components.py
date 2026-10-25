import math

import numpy as np
import pytest

from bench_stats.stats.components import (
    ar1_inflation,
    outlier_processes,
    upstream_share,
    variance_components,
)

from .conftest import decode
from .helpers import ar1_trials


def test_recovers_known_sigmas_within_5_percent():
    rng = np.random.default_rng(1)
    vc = variance_components(ar1_trials(rng, 400, 16, sigma1=0.015, sigma2=0.01), n_boot=200)
    assert vc.sigma1 == pytest.approx(0.015, rel=0.05)
    assert vc.sigma2 == pytest.approx(0.01, rel=0.05)
    assert vc.sigma1_ci[0] < 0.015 < vc.sigma1_ci[1]
    assert vc.sigma2_ci[0] < 0.01 < vc.sigma2_ci[1]
    assert vc.k == pytest.approx(math.sqrt(vc.inflation + 16 * vc.sigma2**2 / vc.sigma1**2))


def test_autocorrelation_is_not_counted_as_between_process_variance():
    rng = np.random.default_rng(2)
    est = [variance_components(ar1_trials(rng, 40, 16, 0.015, rho=0.6), n_boot=10) for _ in range(100)]
    ar = np.mean([v.sigma2 for v in est])
    iid = np.mean([v.sigma2_iid for v in est])
    rho = np.mean([v.rho for v in est])
    assert ar < 0.25 * iid
    assert rho == pytest.approx(0.6, abs=0.05)
    assert np.mean([v.upstream_share for v in est]) > 0.15


def test_unbalanced_and_single_trial_processes():
    rng = np.random.default_rng(3)
    trials = [t[: rng.integers(1, 17)] for t in ar1_trials(rng, 30, 16, 0.01, sigma2=0.01)]
    trials[0] = trials[0][:1]
    vc = variance_components(trials, n_boot=100)
    assert vc.processes == 30
    assert 0.005 < vc.sigma2 < 0.02


def test_rejects_too_little_data():
    with pytest.raises(ValueError):
        variance_components([[1.0, 2.0]])
    with pytest.raises(ValueError):
        variance_components([[1.0], [2.0]])


def test_upstream_share_matches_bench_press(golden):
    for case in golden["components"]:
        expected = case["result"]
        ours = upstream_share(case["process_trials_ns"])
        if expected is None:
            assert math.isnan(ours)
        else:
            assert ours == pytest.approx(decode(expected["between_process_share"]), rel=1e-9, abs=1e-15)


def test_drift_and_outliers_are_flagged():
    rng = np.random.default_rng(4)
    drifting = variance_components(ar1_trials(rng, 30, 16, 0.01, drift=0.002), n_boot=10)
    assert drifting.drift_detected
    assert drifting.sigma2_drift < drifting.sigma2
    flat = variance_components(ar1_trials(rng, 30, 16, 0.01, sigma2=0.005), n_boot=10)
    assert not flat.drift_detected

    values = 1000 * np.exp(rng.normal(0, 0.01, 12))
    values[7] *= 1.2
    assert outlier_processes(values) == (7,)
    assert outlier_processes(values[:4]) == ()


def test_ar1_inflation():
    assert ar1_inflation(0.0, 16) == pytest.approx(1.0)
    rho, n = 0.5, 10
    k = np.arange(1, n)
    assert ar1_inflation(rho, n) == pytest.approx(1 + 2 * np.sum((1 - k / n) * rho**k))
    assert ar1_inflation(0.9, 1000) == pytest.approx((1 + 0.9) / (1 - 0.9), rel=0.02)
