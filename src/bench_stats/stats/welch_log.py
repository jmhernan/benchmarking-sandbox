"""Welch interval on log process means: a cross-check for Fieller (plan A2).

It targets the ratio of geometric means of the per-process means, not of arithmetic means. The
two agree closely when process means vary by a few percent.
"""

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats

from .interval import RatioInterval

ESTIMAND = "ratio of geometric means"


def welch_log(a: Sequence[float], b: Sequence[float], conf: float = 0.95) -> RatioInterval:
    """Interval for exp(mean(log a) - mean(log b)) with Welch–Satterthwaite df."""
    la, lb = np.log(np.asarray(a, float)), np.log(np.asarray(b, float))
    if la.size < 2 or lb.size < 2:
        return RatioInterval("welch-log", ESTIMAND, math.nan, math.nan, math.nan, conf, math.nan, False)
    d = la.mean() - lb.mean()
    va, vb = la.var(ddof=1) / la.size, lb.var(ddof=1) / lb.size
    se2 = va + vb
    if se2 == 0.0:
        r = math.exp(d)
        return RatioInterval("welch-log", ESTIMAND, r, r, r, conf, math.inf, True, 1.0 if d == 0 else 0.0)
    df = se2**2 / (va**2 / (la.size - 1) + vb**2 / (lb.size - 1))
    se = math.sqrt(se2)
    t = stats.t.ppf(1 - (1 - conf) / 2, df)
    p = float(2 * stats.t.sf(abs(d) / se, df))
    return RatioInterval(
        "welch-log", ESTIMAND, math.exp(d), math.exp(d - t * se), math.exp(d + t * se), conf, float(df), True, p
    )
