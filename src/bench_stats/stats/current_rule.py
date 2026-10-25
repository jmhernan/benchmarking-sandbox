"""bench_press's verdict rule as of 5fd6396, ported so every comparison against "today" uses the real rule.

Delta-table semantics (`MarkdownReporter._formatDeltaRow` → `_computeFiellerVerdict` →
`_classifyMovement` / `_classifyThresholdMovement`), with `--gate` on (the default):

- unstable baseline or candidate, fewer than 2 samples, or an invalid 95% Fieller interval:
  Unresolved;
- `--threshold 0`: Neutral if the 95% interval contains 1, otherwise Faster/Regression only when the
  point speedup is at least 1.05 or at most 0.95 (the ±5% band), else Neutral;
- `--threshold δ > 0`: Faster/Regression if the whole 95% interval clears 1+δ or 1/(1+δ);
  Equivalent if the 90% interval lies inside [1/(1+δ), 1+δ]; otherwise Inconclusive.

`samples` are what bench_press puts into Fieller: per-process means when P > 1, raw trials when P = 1.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .fieller import fieller

FASTER = "🚀 Faster"
REGRESSION = "⚠️ Regression"
NEUTRAL = "➖ ⚪ Neutral"
EQUIVALENT = "✅ Equivalent"
INCONCLUSIVE = "➖ ⚪ Inconclusive"
UNRESOLVED = "❓ Unresolved"


@dataclass(frozen=True)
class TodayVerdict:
    status: str
    direction: int
    speedup: float
    lower: float = math.nan
    upper: float = math.nan
    lower90: float = math.nan
    upper90: float = math.nan
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def resolved(self) -> bool:
        return self.status != UNRESOLVED

    @property
    def flags_change(self) -> bool:
        return self.direction != 0


def _metrics_mean(samples: Sequence[float]) -> float:
    # BenchmarkMetrics.fromSamples sums the *sorted* samples.
    total = 0.0
    for x in sorted(samples):
        total += x
    return total / len(samples) if samples else 0.0


def classify(
    speedup: float,
    lower: float,
    upper: float,
    lower90: float,
    upper90: float,
    threshold: float = 0.0,
) -> tuple[str, int]:
    """`_classifyMovement` for a resolved interval (delta-table labels)."""
    if threshold > 0.0:
        up = 1.0 + threshold
        down = 1.0 / up
        if lower >= up:
            return FASTER, 1
        if upper <= down:
            return REGRESSION, -1
        if lower90 >= down and upper90 <= up:
            return EQUIVALENT, 0
        return INCONCLUSIVE, 0
    if lower <= 1.0 <= upper:
        return NEUTRAL, 0
    if speedup >= 1.05:
        return FASTER, 1
    if speedup <= 0.95:
        return REGRESSION, -1
    return NEUTRAL, 0


def today_verdict(
    baseline: Sequence[float],
    current: Sequence[float],
    threshold: float = 0.0,
    baseline_stable: bool = True,
    current_stable: bool = True,
    paired: bool = False,
) -> TodayVerdict:
    """The status bench_press prints for baseline vs current (speedup = baseline / current)."""
    base_mean, cur_mean = _metrics_mean(baseline), _metrics_mean(current)
    speedup = base_mean / cur_mean if (cur_mean > 0.0 and base_mean > 0.0) else 1.0

    if not (baseline_stable and current_stable):
        reasons = tuple(
            r
            for r, bad in (
                ("baseline samples unstable", not baseline_stable),
                ("candidate samples unstable", not current_stable),
            )
            if bad
        )
        return TodayVerdict(UNRESOLVED, 0, speedup, reasons=reasons)
    if len(baseline) < 2 or len(current) < 2:
        return TodayVerdict(UNRESOLVED, 0, speedup, reasons=("unbounded CI",))

    i95 = fieller(baseline, current, 0.95, paired, t_method="bench_press")
    if not i95.is_valid or math.isnan(i95.lower) or math.isnan(i95.upper):
        return TodayVerdict(UNRESOLVED, 0, speedup, reasons=("unbounded CI",))
    i90 = fieller(baseline, current, 0.90, paired, t_method="bench_press")
    status, direction = classify(speedup, i95.lower, i95.upper, i90.lower, i90.upper, threshold)
    return TodayVerdict(status, direction, speedup, i95.lower, i95.upper, i90.lower, i90.upper)
