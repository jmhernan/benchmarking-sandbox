"""Fieller's interval for a ratio of means: a port of bench_press `FiellerInterval.compute` (5fd6396).

Applied to per-process means it is the proposal's process-level interval (§3.3). The arithmetic is
the same as bench_press's, in the same order (plain left-to-right sums), so with
`t_quantile="bench_press"` the results agree to rounding error. The default uses the exact t
quantile instead of bench_press's Hill approximation.
"""

import math
from collections.abc import Sequence
from typing import Literal

from scipy import stats

from .interval import RatioInterval
from .quantiles import student_t_quantile

TQuantile = Literal["exact", "bench_press"]

ESTIMAND = "ratio of arithmetic means"


def t_quantile(p: float, df: float, method: TQuantile = "exact") -> float:
    if method == "bench_press":
        return student_t_quantile(p, df)
    return float(stats.t.ppf(p, max(df, 1.0)))


def _mean(xs: Sequence[float]) -> float:
    total = 0.0
    for x in xs:
        total += x
    return total / len(xs)


def _variance(xs: Sequence[float], mean: float) -> float:
    if len(xs) <= 1:
        return 0.0
    total = 0.0
    for x in xs:
        d = x - mean
        total += d * d
    return total / (len(xs) - 1)


def _covariance(a: Sequence[float], mean_a: float, b: Sequence[float], mean_b: float) -> float:
    n = len(a)
    if n <= 1 or n != len(b):
        return 0.0
    total = 0.0
    for i in range(n):
        total += (a[i] - mean_a) * (b[i] - mean_b)
    return total / (n - 1)


def _clamp(x: float, lo: float, hi: float) -> float:
    return min(max(x, lo), hi)


def _degrees_of_freedom(n_a: int, n_b: int, v_a: float, v_b: float, paired: bool) -> float:
    if paired:
        return _clamp(n_a - 1.0, 1.0, 10000.0)
    num = (v_a + v_b) * (v_a + v_b)
    den_a = (v_a * v_a) / (n_a - 1) if n_a > 1 and v_a > 0.0 else 0.0
    den_b = (v_b * v_b) / (n_b - 1) if n_b > 1 and v_b > 0.0 else 0.0
    if den_a + den_b > 0.0:
        return _clamp(num / (den_a + den_b), 1.0, 10000.0)
    return _clamp(n_a + n_b - 2.0, 1.0, 10000.0)


def _discriminant(v_a, v_b, v_ab, ratio, g, g_cov, paired) -> float:
    base = v_a * (1.0 - g) + ratio * ratio * v_b
    raw = base - 2.0 * ratio * v_ab + g_cov * v_ab if paired else base
    scale = v_a + ratio * ratio * v_b
    return 0.0 if (raw < 0.0 and raw >= -1e-12 * scale) else raw


def _p_value(mean_a, mean_b, v_a, v_b, v_ab, df) -> float:
    """Two-sided test of mean_a = mean_b; rejects at level α exactly when the bounded Fieller interval excludes 1."""
    se2 = v_a + v_b - 2.0 * v_ab
    if se2 <= 0.0:
        return 1.0 if mean_a == mean_b else 0.0
    return float(2.0 * stats.t.sf(abs(mean_a - mean_b) / math.sqrt(se2), df))


def fieller(
    a: Sequence[float],
    b: Sequence[float],
    conf: float = 0.95,
    paired: bool = False,
    t_method: TQuantile = "exact",
) -> RatioInterval:
    """Interval for mean(a) / mean(b).

    With `paired=True` and equal lengths, uses the covariance between a[i] and b[i] (df = n - 1);
    otherwise Welch–Satterthwaite df. Mirrors bench_press's handling of n < 2, a zero denominator
    mean, zero variance, g >= 1 (unbounded) and a negative discriminant.
    """
    a = [float(x) for x in a]
    b = [float(x) for x in b]
    n_a, n_b = len(a), len(b)
    use_paired = paired and n_a == n_b
    method = f"fieller{'-paired' if use_paired else ''}"

    def result(ratio, lower, upper, g, valid, df=math.nan, p=math.nan):
        return RatioInterval(
            method=method,
            estimand=ESTIMAND,
            ratio=ratio,
            lower=lower,
            upper=upper,
            conf=conf,
            df=df,
            is_valid=valid,
            p_value=p,
            g=g,
            paired=use_paired,
        )

    if n_a < 2 or n_b < 2:
        return result(math.nan, math.nan, math.nan, math.inf, False)

    mean_a, mean_b = _mean(a), _mean(b)
    if mean_b == 0.0:
        return result(math.inf, -math.inf, math.inf, math.inf, False)

    ratio = mean_a / mean_b
    v_a = _variance(a, mean_a) / n_a
    v_b = _variance(b, mean_b) / n_b
    if v_a == 0.0 and v_b == 0.0:
        return result(ratio, ratio, ratio, 0.0, True, p=1.0 if mean_a == mean_b else 0.0)

    v_ab = _covariance(a, mean_a, b, mean_b) / n_a if use_paired else 0.0
    df = _degrees_of_freedom(n_a, n_b, v_a, v_b, use_paired)
    p_value = _p_value(mean_a, mean_b, v_a, v_b, v_ab, df)

    t = t_quantile(1.0 - (1.0 - conf) / 2.0, df, t_method)
    g = (t * t * v_b) / (mean_b * mean_b)
    if g >= 1.0 or math.isnan(g) or math.isinf(g):
        return result(ratio, -math.inf, math.inf, g, False, df, p_value)

    g_cov = (t * t * v_ab) / (mean_b * mean_b) if use_paired else 0.0
    disc = _discriminant(v_a, v_b, v_ab, ratio, g, g_cov, use_paired)
    if disc < 0.0 or math.isnan(disc):
        return result(ratio, ratio, ratio, g, False, df, p_value)

    margin = (t / abs(mean_b)) * math.sqrt(disc)
    center = ratio - g_cov
    return result(ratio, (center - margin) / (1.0 - g), (center + margin) / (1.0 - g), g, True, df, p_value)
