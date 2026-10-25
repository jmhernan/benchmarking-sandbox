"""The practical-significance gate from the proposal (§4.1).

Given a ratio interval [L, U] (> 1 means the candidate is faster) and a threshold δ, with a band
that is symmetric on the log scale:

| Verdict              | Condition                    |
|----------------------|------------------------------|
| faster ≥ δ           | L > 1 + δ                    |
| slower ≥ δ           | U < 1 / (1 + δ)              |
| no meaningful change | 1/(1+δ) < L and U < 1 + δ    |
| inconclusive         | otherwise, or unbounded      |

"No meaningful change" carries a sub-label, "detectable but < δ", when the interval also excludes 1.

Differences from upstream `--threshold` (`current_rule`): upstream uses ≥/≤ at the band edges and the
90% interval for Equivalent (TOST at α = 5% per side). Here one 95% interval decides every label, so
"no meaningful change" is TOST at α = 2.5% per side.
"""

import math
from dataclasses import dataclass
from enum import StrEnum

from .interval import RatioInterval


class Verdict(StrEnum):
    FASTER = "faster"
    SLOWER = "slower"
    NO_CHANGE = "no meaningful change"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class GateResult:
    verdict: Verdict
    delta: float
    detectable: bool
    reason: str = ""

    @property
    def label(self) -> str:
        pct = f"{100 * self.delta:g}%"
        match self.verdict:
            case Verdict.FASTER:
                return f"faster ≥ {pct}"
            case Verdict.SLOWER:
                return f"slower ≥ {pct}"
            case Verdict.NO_CHANGE:
                return f"no meaningful change (detectable but < {pct})" if self.detectable else "no meaningful change"
            case _:
                return f"inconclusive ({self.reason})" if self.reason else "inconclusive"


def gate(lower: float, upper: float, delta: float) -> GateResult:
    """Classify a ratio interval [lower, upper] against a relative threshold delta (0.03 = 3%)."""
    if delta <= 0:
        raise ValueError(f"delta must be positive, got {delta}")
    if not (math.isfinite(lower) and math.isfinite(upper)) or lower > upper:
        return GateResult(Verdict.INCONCLUSIVE, delta, False, "unbounded interval")
    up = 1.0 + delta
    down = 1.0 / up
    detectable = not (lower <= 1.0 <= upper)
    if lower > up:
        return GateResult(Verdict.FASTER, delta, True)
    if upper < down:
        return GateResult(Verdict.SLOWER, delta, True)
    if down < lower and upper < up:
        return GateResult(Verdict.NO_CHANGE, delta, detectable)
    return GateResult(Verdict.INCONCLUSIVE, delta, detectable, "interval crosses the ±δ band")


def gate_interval(interval: RatioInterval, delta: float) -> GateResult:
    if not interval.bounded:
        return GateResult(Verdict.INCONCLUSIVE, delta, False, "unbounded interval")
    return gate(interval.lower, interval.upper, delta)
