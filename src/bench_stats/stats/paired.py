"""Paired estimator for group mode (plan A2): a one-sample t interval on per-process log ratios.

In `Benchmark.compare` groups every variant runs inside the same processes, so they share each
process's offset. Differencing within a process removes it; independent-samples Fieller would
count it twice and waste precision.
"""

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats

from .interval import RatioInterval

ESTIMAND = "ratio of geometric means (paired by process)"


def paired_log_ratio(a: Sequence[float], b: Sequence[float], conf: float = 0.95) -> RatioInterval:
    """Interval for the geometric mean of a[p] / b[p] over processes p (a, b aligned by process)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape:
        raise ValueError(f"paired samples need equal lengths, got {a.size} and {b.size}")
    d = np.log(a) - np.log(b)
    P = d.size
    if P < 2:
        return RatioInterval("paired-log", ESTIMAND, math.nan, math.nan, math.nan, conf, math.nan, False, paired=True)
    m, sd = d.mean(), d.std(ddof=1)
    df = P - 1
    if sd == 0.0:
        r = math.exp(m)
        return RatioInterval("paired-log", ESTIMAND, r, r, r, conf, df, True, 1.0 if m == 0 else 0.0, paired=True)
    se = sd / math.sqrt(P)
    t = stats.t.ppf(1 - (1 - conf) / 2, df)
    p = float(2 * stats.t.sf(abs(m) / se, df))
    return RatioInterval(
        "paired-log", ESTIMAND, math.exp(m), math.exp(m - t * se), math.exp(m + t * se), conf, df, True, p,
        paired=True,
    )
