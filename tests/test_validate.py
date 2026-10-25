import csv
import math

import numpy as np
import pytest

from bench_stats.validate import experiments as ex
from bench_stats.validate.generator import ROBUSTNESS, Scenario, _launch_indices, simulate_group, simulate_pair
from bench_stats.validate.run import run


def test_launch_order_matches_bench_press_abba_baab():
    b, c = _launch_indices(4, 4, "interleaved")
    order = "".join("b" if i in b else "c" for i in range(8))
    assert order == "bccbcbbc"
    b, c = _launch_indices(3, 3, "sequential")
    assert list(b) == [0, 1, 2] and list(c) == [3, 4, 5]
    b, c = _launch_indices(4, 3, "interleaved")
    assert len(b) == 4 and len(c) == 3


@pytest.mark.parametrize("name", [n for n in ROBUSTNESS if "outlier" not in n and "separate" not in n])
def test_scenarios_match_their_true_ratio(name):
    s = ROBUSTNESS[name]
    rng = np.random.default_rng(1)
    ratios = []
    for _ in range(1500):
        b, c = simulate_pair(rng, s, 10, 1.05)
        ratios.append(np.mean([t.mean() for t in b]) / np.mean([t.mean() for t in c]))
    assert np.mean(ratios) == pytest.approx(s.true_ratio(1.05), rel=1e-3)


def test_normal_model_has_the_requested_spreads():
    s = Scenario(sigma1=0.02, sigma2=0.01, n=50)
    rng = np.random.default_rng(2)
    b, c = simulate_pair(rng, s, 400, 1.0)
    within = np.mean([np.std(np.log(t), ddof=1) for t in b])
    between = np.std([np.log(t).mean() for t in b], ddof=1)
    assert within == pytest.approx(0.02, rel=0.03)
    assert between == pytest.approx(math.sqrt(0.01**2 + 0.02**2 / 50), rel=0.1)
    assert len(c) == 400


def test_group_simulation_shares_process_effects():
    rng = np.random.default_rng(3)
    b, c = simulate_group(rng, 200, 1.0, sigma_shared=0.02, sigma_variant=0.001)
    mb, mc = np.log([t.mean() for t in b]), np.log([t.mean() for t in c])
    assert np.corrcoef(mb, mc)[0, 1] > 0.9


def test_experiment_cells_return_rates():
    row = ex.grid_cell(P=5, sigma1=0.01, sigma2=0.01, theta=1.0, reps=60, seed=(1,), components_reps=20)
    for k in ("covers", "excludes_1", "gate_no_change", "today_covers", "upstream_P_equivalent", "sigma2_hat"):
        assert 0 <= row[k] <= 1, k
    row = ex.robust_cell("one outlier process (+5%)", P=10, theta=1.05, reps=40, seed=(2,), components_reps=10)
    assert 0 <= row["outlier_flag_true"] <= 1
    row = ex.group_cell(P=5, theta=1.0, sigma_shared=0.01, reps=40, seed=(3,))
    assert row["paired_median_half_width"] < row["unpaired_median_half_width"]
    row = ex.suite_chunk("5 at +5%", reps=5, seed=(4,))
    assert row["effects"] == 5 and row["reps"] == 5
    rows = ex.design_chunk("σ₁ = σ₂ = 1%", pilots=1, seed=(5,), exp_reps=20)
    assert {"shipped_achieved", "point_achieved", "conservative_achieved"} <= rows[0].keys()
    row = ex.power_cell(P=5, theta=1.05, sigma1=0.01, sigma2=0.01, rho=0.0, reps=50, seed=(6,))
    assert 0 <= row["simulated"] <= 1 and 0 <= row["analytic"] <= 1
    row = ex.ci_cell(P=5, sigma2=0.01, rho=0.0, reps=5, seed=(7,), n_boot=50)
    assert 0 <= row["covers_s2"] <= 1
    row = ex.outlier_cell(P=10, shift_sd=12, reps=50, seed=(8,))
    assert row["detected"] > 0.8


def test_cells_are_reproducible():
    a = ex.grid_cell(P=3, sigma1=0.01, sigma2=0.005, theta=1.02, reps=30, seed=(9, 9), components_reps=0)
    b = ex.grid_cell(P=3, sigma1=0.01, sigma2=0.005, theta=1.02, reps=30, seed=(9, 9), components_reps=0)
    assert a == b


def test_run_writes_outputs(tmp_path):
    run(tmp_path, scale=0.005, only=["group", "outlier"], workers=2)
    assert (tmp_path / "summary.md").read_text().startswith("# A4 simulation validation")
    rows = list(csv.DictReader((tmp_path / "group.csv").open()))
    assert len(rows) == 16
    assert (tmp_path / "run_info.json").exists()
