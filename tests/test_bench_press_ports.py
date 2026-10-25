"""Ports must reproduce bench_press 5fd6396 (fixture written by bench/tool/golden_bench_press.dart)."""

import math

import pytest

from bench_stats.stats.fieller import fieller
from bench_stats.stats.quantiles import normal_quantile, student_t_quantile

from .conftest import decode


def close(x, y, rel=1e-9):
    if isinstance(y, float) and (math.isnan(y) or math.isinf(y)):
        return (math.isnan(x) and math.isnan(y)) or x == y
    return x == pytest.approx(y, rel=rel, abs=1e-12)


def test_student_t_quantile_matches_bench_press(golden):
    for case in golden["quantiles"]["student_t"]:
        assert close(student_t_quantile(case["p"], case["df"]), case["value"]), case


def test_normal_quantile_matches_bench_press(golden):
    for case in golden["quantiles"]["normal"]:
        assert close(normal_quantile(case["p"]), case["value"]), case


def test_quantiles_reject_out_of_range():
    for p in (0.0, 1.0, -0.5, 1.5):
        with pytest.raises(ValueError):
            normal_quantile(p)
    for p in (0.5, 1.0):
        with pytest.raises(ValueError):
            student_t_quantile(p, 10.0)


def test_fieller_matches_bench_press(golden):
    assert len(golden["fieller"]) > 400
    for case in golden["fieller"]:
        r = fieller(case["a"], case["b"], case["conf"], case["paired_requested"], t_method="bench_press")
        assert r.is_valid == case["is_valid"], case
        assert r.paired == case["paired"], case
        for ours, theirs in ((r.ratio, "ratio"), (r.lower, "lower"), (r.upper, "upper"), (r.g, "g")):
            assert close(ours, decode(case[theirs])), (theirs, ours, case[theirs])


def test_exact_t_differs_from_bench_press_only_slightly(golden):
    for case in golden["fieller"]:
        if not case["is_valid"] or len(case["a"]) < 5:
            continue
        exact = fieller(case["a"], case["b"], case["conf"], case["paired_requested"])
        width_bp = decode(case["upper"]) - decode(case["lower"])
        width_exact = exact.upper - exact.lower
        assert abs(width_exact - width_bp) <= 1e-3 * width_bp + 1e-9 * abs(exact.ratio), case


@pytest.mark.parametrize("threshold", [0.0, 0.03, 0.05])
def test_current_rule_matches_bench_press_delta_table(golden, threshold):
    from bench_stats.stats.current_rule import today_verdict

    verdicts = golden["verdicts"]
    expected = verdicts[f"threshold_{threshold}"]
    assert len(expected) == len(verdicts["cases"])
    for case in verdicts["cases"]:
        v = today_verdict(
            case["baseline"],
            case["current"],
            threshold,
            case["baseline_stable"],
            case["current_stable"],
        )
        assert v.status == expected[case["name"]]["status"], (case["name"], v)
        if v.resolved:
            lo, hi = expected[case["name"]]["ci"].strip("[]").replace(" x", "").split(", ")
            assert f"{v.lower:.2f}" == lo and f"{v.upper:.2f}" == hi
