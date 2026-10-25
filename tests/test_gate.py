import math

import pytest

from bench_stats.stats.current_rule import EQUIVALENT, FASTER, INCONCLUSIVE, NEUTRAL, REGRESSION, classify
from bench_stats.stats.gate import Verdict, gate, gate_interval
from bench_stats.stats.interval import RatioInterval

D = 0.03


@pytest.mark.parametrize(
    ("lower", "upper", "verdict", "detectable"),
    [
        (1.05, 1.10, Verdict.FASTER, True),
        (0.90, 0.95, Verdict.SLOWER, True),
        (0.99, 1.01, Verdict.NO_CHANGE, False),
        (1.005, 1.02, Verdict.NO_CHANGE, True),
        (0.98, 0.995, Verdict.NO_CHANGE, True),
        (1.01, 1.05, Verdict.INCONCLUSIVE, True),
        (0.95, 1.01, Verdict.INCONCLUSIVE, False),
        (0.90, 1.10, Verdict.INCONCLUSIVE, False),
    ],
)
def test_gate_regions(lower, upper, verdict, detectable):
    g = gate(lower, upper, D)
    assert g.verdict == verdict
    assert g.detectable == detectable


def test_gate_band_is_symmetric_on_log_scale_and_strict():
    up, down = 1 + D, 1 / (1 + D)
    assert gate(up, 1.2, D).verdict == Verdict.INCONCLUSIVE
    assert gate(math.nextafter(up, 2), 1.2, D).verdict == Verdict.FASTER
    assert gate(0.8, down, D).verdict == Verdict.INCONCLUSIVE
    assert gate(0.8, math.nextafter(down, 0), D).verdict == Verdict.SLOWER
    assert gate(math.nextafter(down, 2), math.nextafter(up, 0), D).verdict == Verdict.NO_CHANGE


def test_gate_unbounded_and_invalid_delta():
    assert gate(-math.inf, math.inf, D).verdict == Verdict.INCONCLUSIVE
    bad = RatioInterval("fieller", "", 1.0, -math.inf, math.inf, 0.95, 3, False)
    assert gate_interval(bad, D).reason == "unbounded interval"
    with pytest.raises(ValueError):
        gate(0.9, 1.1, 0)


def test_gate_labels():
    assert gate(1.05, 1.10, D).label == "faster ≥ 3%"
    assert gate(1.005, 1.02, D).label == "no meaningful change (detectable but < 3%)"
    assert gate(0.9, 1.1, D).label.startswith("inconclusive")


def test_upstream_threshold_rule_differs_at_edges_and_on_equivalence():
    up = 1 + D
    # Upstream is inclusive at the band edge; the proposal's gate is strict.
    assert classify(1.05, up, 1.1, up, 1.1, D)[0] == FASTER
    assert gate(up, 1.1, D).verdict == Verdict.INCONCLUSIVE
    # Upstream calls Equivalent from the 90% interval even when the 95% one leaves the band.
    assert classify(1.0, 0.965, 1.035, 0.975, 1.025, D)[0] == EQUIVALENT
    assert gate(0.965, 1.035, D).verdict == Verdict.INCONCLUSIVE
    assert classify(1.0, 0.9, 1.1, 0.92, 1.08, D)[0] == INCONCLUSIVE


def test_today_band_without_threshold():
    assert classify(1.04, 1.01, 1.07, 1.02, 1.06)[0] == NEUTRAL
    assert classify(1.051, 1.01, 1.09, 1.02, 1.08)[0] == FASTER
    assert classify(0.94, 0.90, 0.98, 0.91, 0.97)[0] == REGRESSION
    assert classify(1.2, 0.99, 1.4, 1.0, 1.3)[0] == NEUTRAL
