"""Multiple comparisons across a suite (proposal §4.3, plan A2 `multiplicity.py`).

Benjamini–Hochberg controls the false discovery rate of the "detectable" label (interval excludes 1)
across the benchmarks in a run. Expected false flags under the null are reported per label:

- "detectable" (interval excludes 1): 1 - conf per benchmark when nothing changed;
- gate "≥ δ" claims: about 0 when nothing changed, at most (1 - conf)/2 per benchmark at the
  boundary θ = 1 + δ.
"""

from collections.abc import Sequence

import numpy as np


def benjamini_hochberg(p_values: Sequence[float], q: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """Return (rejected, adjusted p-values). NaN p-values are never rejected and stay NaN."""
    p = np.asarray(p_values, float)
    adjusted = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m == 0:
        return np.zeros(p.shape, bool), adjusted
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    adj = np.empty(m)
    adj[order] = np.minimum(ranked, 1.0)
    adjusted[ok] = adj
    return np.where(ok, adjusted <= q, False), adjusted


def expected_false_flags(n_benchmarks: int, conf: float = 0.95) -> dict[str, float]:
    """Expected false flags per run if no benchmark changed, by label, without FDR control."""
    alpha = 1.0 - conf
    return {
        "detectable (interval excludes 1)": n_benchmarks * alpha,
        "gate ≥ δ, worst case at θ = 1 + δ": n_benchmarks * alpha / 2,
    }
