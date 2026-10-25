import pytest

from bench_stats.stats.design import (
    allocate_budget,
    gate_power,
    half_width,
    optimal_trials,
    processes_for_half_width,
    processes_for_power,
)


def test_proposal_e6_budget_allocation():
    """Proposal E6: c1 = 0.1 s, c2 = 2 s, 120 s, sigma1 = sigma2 = 1%."""
    assert optimal_trials(0.1, 2.0, 0.01, 0.01) == pytest.approx(4.47, abs=0.01)
    expected = {1: (28.6, 0.73), 2: (27.3, 0.65), 5: (24.0, 0.62), 15: (17.1, 0.69), 50: (8.6, 0.96), 200: (2.7, 1.68)}
    for n, (P, hw) in expected.items():
        a = allocate_budget(120, 0.1, 2.0, 0.01, 0.01, n=n)
        assert a.processes == pytest.approx(P, abs=0.05)
        assert 100 * a.half_width == pytest.approx(hw, abs=0.005)


def test_proposal_e4_power_within_3pp():
    """Proposal E4 (simulated, n = 15, sigma1 = sigma2 = 1%, delta = 3%)."""
    e4 = {(3, 1.05): 0.33, (3, 1.07): 0.84, (5, 1.05): 0.69, (5, 1.07): 1.00, (10, 1.05): 0.98, (20, 1.05): 1.00}
    for (P, theta), sim in e4.items():
        assert gate_power(P, 15, 0.01, 0.01, theta, 0.03) == pytest.approx(sim, abs=0.03), (P, theta)
    assert gate_power(10, 15, 0.01, 0.01, 1.03, 0.03) < 0.05


def test_processes_for_targets_are_minimal():
    P = processes_for_half_width(0.01, 16, 0.015, 0.01)
    assert half_width(P, 16, 0.015, 0.01) <= 0.01 < half_width(P - 1, 16, 0.015, 0.01)
    P = processes_for_power(1.06, 0.03, 16, 0.015, 0.01)
    assert gate_power(P, 16, 0.015, 0.01, 1.06, 0.03) >= 0.8 > gate_power(P - 1, 16, 0.015, 0.01, 1.06, 0.03)
    assert processes_for_power(1.03, 0.03, 16, 0.015, 0.01) is None


def test_autocorrelation_inflation_raises_requirements():
    assert processes_for_half_width(0.01, 16, 0.015, 0.01, f=2.5) > processes_for_half_width(0.01, 16, 0.015, 0.01)
    assert optimal_trials(0.1, 2.0, 0.01, 0.01, f=2.5) > optimal_trials(0.1, 2.0, 0.01, 0.01)
