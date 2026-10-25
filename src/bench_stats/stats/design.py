"""Experiment design: how many processes and trials (proposal §5.3, Kalibera & Jones 2013).

On the log-ratio scale, with P processes per version and n trials per process,

    Var(log θ̂) ≈ 2 (sigma2² + f·sigma1²/n) / P,

where f is the variance inflation from autocorrelation inside a process (1 for independent trials).
Every sigma is a fraction on the log scale (0.01 = 1%). Costs are in seconds: c1 per trial, c2 per
process (startup, warmup, calibration).
"""

import math
from dataclasses import dataclass

from scipy import stats


def log_ratio_se(P: float, n: float, sigma1: float, sigma2: float, f: float = 1.0) -> float:
    return math.sqrt(2.0 * (sigma2**2 + f * sigma1**2 / n) / P)


def half_width(P: float, n: float, sigma1: float, sigma2: float, conf: float = 0.95, f: float = 1.0) -> float:
    """Normal-approximation half-width of the interval for log θ (≈ relative half-width)."""
    return stats.norm.ppf(1 - (1 - conf) / 2) * log_ratio_se(P, n, sigma1, sigma2, f)


def optimal_trials(c1: float, c2: float, sigma1: float, sigma2: float, f: float = 1.0) -> float:
    """n* = sqrt((c2/c1)·(f·sigma1²/sigma2²)): trials per process minimising variance for a fixed budget."""
    if sigma2 <= 0:
        return math.inf
    return math.sqrt((c2 / c1) * (f * sigma1**2) / sigma2**2)


@dataclass(frozen=True)
class Allocation:
    trials: float
    processes: float
    half_width: float


def allocate_budget(
    budget: float, c1: float, c2: float, sigma1: float, sigma2: float, n: float | None = None,
    conf: float = 0.95, f: float = 1.0,
) -> Allocation:
    """Processes per version that fit a total budget (both versions), at n trials (default n*)."""
    if n is None:
        n = optimal_trials(c1, c2, sigma1, sigma2, f)
    P = budget / (2.0 * (c2 + n * c1))
    return Allocation(n, P, half_width(P, n, sigma1, sigma2, conf, f))


def processes_for_half_width(
    h: float, n: float, sigma1: float, sigma2: float, conf: float = 0.95, f: float = 1.0
) -> int:
    """Smallest P per version whose normal-approximation half-width is at most h."""
    z = stats.norm.ppf(1 - (1 - conf) / 2)
    return max(2, math.ceil(2.0 * z**2 * (sigma2**2 + f * sigma1**2 / n) / h**2))


def gate_power(
    P: int, n: float, sigma1: float, sigma2: float, theta: float, delta: float,
    conf: float = 0.95, f: float = 1.0,
) -> float:
    """P(gate says "faster ≥ δ") when the true speedup is θ: P(lower bound of log θ̂ > log(1 + δ)).

    Noncentral t approximation. The interval's Welch df is estimated and usually below 2(P - 1); an
    effective df of 1.5(P - 1) reproduces the proposal's simulated power (E4) within 2 pp for
    P = 3–10. A4 checks it more widely.
    """
    if P < 2:
        return 0.0
    df = 1.5 * (P - 1)
    se = log_ratio_se(P, n, sigma1, sigma2, f)
    ncp = (math.log(theta) - math.log1p(delta)) / se
    return float(stats.nct.sf(stats.t.ppf(1 - (1 - conf) / 2, df), df, ncp))


def processes_for_power(
    theta: float, delta: float, n: float, sigma1: float, sigma2: float,
    power: float = 0.8, conf: float = 0.95, f: float = 1.0, max_processes: int = 1000,
) -> int | None:
    """Smallest P per version reaching `power` for "faster ≥ δ" at true θ > 1 + δ; None if out of reach."""
    if theta <= 1.0 + delta:
        return None
    for P in range(2, max_processes + 1):
        if gate_power(P, n, sigma1, sigma2, theta, delta, conf, f) >= power:
            return P
    return None
