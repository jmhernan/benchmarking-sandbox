import numpy as np
import pytest

from bench_stats.compare import compare, compare_groups, compare_runs, recommend_design
from bench_stats.io import Run, load_run
from bench_stats.stats.current_rule import UNRESOLVED
from bench_stats.stats.gate import Verdict

from .helpers import ar1_trials, make_record


def _run(records):
    return Run(path=None, version=1, timestamp="", environment={}, records=tuple(records))


def test_group_comparison_is_paired(suite_path):
    suite = compare_groups(load_run(suite_path))
    (c,) = suite.comparisons
    assert c.paired and c.interval.paired
    assert c.cross_check.method == "paired-log"
    assert c.interval.ratio == pytest.approx(200 / 180, rel=0.02)
    assert c.gate.verdict == Verdict.FASTER
    assert c.bh_detectable


def test_known_effect_is_detected_and_identical_is_not():
    rng = np.random.default_rng(6)
    base = make_record(ar1_trials(rng, 10, 16, 0.01, sigma2=0.01, mean=1000))
    same = make_record(ar1_trials(rng, 10, 16, 0.01, sigma2=0.01, mean=1000))
    faster = make_record(ar1_trials(rng, 10, 16, 0.01, sigma2=0.01, mean=1000 / 1.10))
    assert compare(base, faster).gate.verdict == Verdict.FASTER
    assert compare(base, same).gate.verdict in (Verdict.NO_CHANGE, Verdict.INCONCLUSIVE)
    assert compare(base, faster).today.direction == 1


def test_single_process_warns_and_is_inconclusive():
    rng = np.random.default_rng(7)
    a = make_record(ar1_trials(rng, 1, 16, 0.01))
    b = make_record(ar1_trials(rng, 1, 16, 0.01, mean=900))
    c = compare(a, b)
    assert not c.interval.is_valid
    assert c.gate.verdict == Verdict.INCONCLUSIVE
    assert any("1 process" in w for w in c.warnings)
    assert c.today.resolved  # bench_press still prints a verdict from the batch-level samples


def test_unstable_side_is_unresolved_today_and_warned():
    rng = np.random.default_rng(8)
    a = make_record(ar1_trials(rng, 5, 8, 0.01), stable=False)
    b = make_record(ar1_trials(rng, 5, 8, 0.01))
    c = compare(a, b)
    assert c.today.status == UNRESOLVED
    assert any("unstable" in w for w in c.warnings)
    assert c.interval.is_valid


def test_paired_requires_equal_process_counts():
    rng = np.random.default_rng(9)
    with pytest.raises(ValueError):
        compare(make_record(ar1_trials(rng, 4, 8, 0.01)), make_record(ar1_trials(rng, 5, 8, 0.01)), paired=True)


def test_compare_runs_matches_keys_and_applies_bh():
    rng = np.random.default_rng(10)

    def suite(effect):
        return _run(
            make_record(ar1_trials(rng, 8, 8, 0.01, sigma2=0.005, mean=1000 / (effect if i < 3 else 1.0)), name=f"b{i}")
            for i in range(20)
        )

    base, cand = suite(1.0), suite(1.08)
    cand = _run(cand.records + (make_record(ar1_trials(rng, 8, 8, 0.01), name="new"),))
    result = compare_runs(base, cand, delta=0.03)
    assert len(result.comparisons) == 20
    assert result.only_candidate == ("new:aot",)
    flagged = {c.name for c in result.comparisons if c.bh_detectable}
    assert {"b0", "b1", "b2"} <= flagged
    assert len(flagged) <= 5
    assert result.counts()[Verdict.FASTER] == 3
    assert result.expected_false_flags["detectable (interval excludes 1)"] == pytest.approx(1.0)


def test_recommend_design_uses_record_costs():
    rng = np.random.default_rng(11)
    rec = make_record(ar1_trials(rng, 20, 16, 0.015, sigma2=0.012, mean=1e5), batch=1000, warmup_seconds=2.0)
    vc = compare(rec, rec).components_baseline
    hint = recommend_design(rec, vc, delta=0.03)
    assert hint.c1 == pytest.approx(0.1, rel=0.05)
    assert hint.c2 == pytest.approx(2.0)
    assert 2 <= hint.trials_per_process <= 200
    assert hint.processes_per_version is not None and hint.power >= 0.8


def test_recommend_design_when_sigma2_is_zero():
    rng = np.random.default_rng(12)
    rec = make_record(ar1_trials(rng, 20, 16, 0.01, mean=1e5), batch=1000, warmup_seconds=2.0)
    vc = compare(rec, rec).components_baseline
    vc = type(vc)(**{**vc.__dict__, "sigma2": 0.0})
    hint = recommend_design(rec, vc, delta=0.03, max_trials=200, conservative=False)
    assert hint.trials_per_process == 200
    assert hint.processes_per_version == 5  # floor: never fewer than 5
    assert recommend_design(rec, vc, delta=0.03).sigma2_used == 0.0
    conservative = recommend_design(rec, vc, delta=0.03, conservative=True)
    assert conservative.sigma2_used == vc.sigma2_ci[1] > 0
    assert conservative.trials_per_process < 200
