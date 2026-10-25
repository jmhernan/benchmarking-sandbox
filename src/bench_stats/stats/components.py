"""Variance components of per-process trials (proposal §3.4, plan A2 `components.py`).

Model on the log scale, for process p and trial j:

    y_pj = mu + a_p + e_pj,   a_p ~ N(0, sigma2²),   e_pj an AR(1) series with variance sigma1²

- sigma1: trial-to-trial noise inside one process;
- sigma2: process-to-process spread (layout, ASLR, JIT/AOT code placement, session drift);
- k: how many times too narrow a single-process interval is, sqrt(f + n·sigma2²/sigma1²), where f is
  the AR(1) variance inflation of a process mean. With independent trials (f = 1) this is the
  proposal's k = sqrt(1 + n·sigma2²/sigma1²).

The main estimator allows for lag-1 autocorrelation inside processes. Ignoring it counts slow
within-process drift as between-process variance (plan §0.2), so three other estimates are
reported next to it:

- `sigma2_iid`: the same moment estimator with independent trials (classical one-way ANOVA when
  balanced);
- `sigma2_drift`: from differences of *successive* process means, robust to slow drift across the
  session (launch order is assumed to be list order, as bench_press writes it);
- `upstream_share`: bench_press's `ProcessVarianceComponents.between_process_share`, ported exactly.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats

OUTLIER_ALPHA = 0.01
# Below these, the lag-1 correlation and the launch-order drift test are too unstable to report.
MIN_TRIALS_FOR_RHO = 8
MIN_PROCESSES_FOR_DRIFT = 5


@dataclass(frozen=True)
class VarianceComponents:
    processes: int
    mean_trials: float
    sigma1: float
    sigma2: float
    k: float
    icc: float
    rho: float
    inflation: float
    sigma2_iid: float
    sigma2_drift: float
    sigma1_ci: tuple[float, float]
    sigma2_ci: tuple[float, float]
    k_ci: tuple[float, float]
    upstream_share: float
    von_neumann: float
    launch_spearman: float
    launch_spearman_p: float
    outlier_processes: tuple[int, ...]
    # False when autocorrelation was off or there were too few trials per process (ρ = 0 assumed).
    rho_estimated: bool = True

    @property
    def drift_detected(self) -> bool:
        return self.processes >= MIN_PROCESSES_FOR_DRIFT and self.launch_spearman_p < 0.01



def ar1_inflation(rho: float | np.ndarray, n: int | np.ndarray) -> np.ndarray:
    """n·Var(mean of n AR(1) values)/sigma²  =  1 + 2 Σ_{k<n} (1 - k/n) rho^k."""
    rho = np.asarray(rho, float)
    n = np.asarray(n)
    n_max = int(np.max(n))
    if n_max < 2:
        return np.ones(np.broadcast_shapes(rho.shape, n.shape))
    lags = np.arange(1, n_max)
    weights = np.clip(1.0 - lags / n[..., None], 0.0, None)
    return 1.0 + 2.0 * np.sum(weights * rho[..., None] ** lags, axis=-1)


def _pad(trials: Sequence[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = np.array([len(t) for t in trials])
    Y = np.zeros((len(trials), n.max()))
    mask = np.zeros_like(Y, dtype=bool)
    for i, t in enumerate(trials):
        Y[i, : len(t)] = t
        mask[i, : len(t)] = True
    return Y, mask, n


def _estimate(Y: np.ndarray, mask: np.ndarray, n: np.ndarray, autocorrelation: bool = True) -> dict[str, np.ndarray]:
    """Moment estimates, vectorised over any leading batch dimensions of Y (..., P, n_max)."""
    m = np.sum(Y * mask, -1) / n
    R = (Y - m[..., None]) * mask
    multi = n >= 2
    ss = np.sum(R**2, -1)
    ss_total = np.sum(ss * multi, -1)
    n_bar = n[multi].mean() if multi.any() else 1.0

    if autocorrelation and n_bar >= MIN_TRIALS_FOR_RHO:
        lag = np.sum(R[..., 1:] * R[..., :-1], -1)
        with np.errstate(invalid="ignore", divide="ignore"):
            rho_hat = np.where(ss_total > 0, np.sum(lag * multi, -1) / ss_total, 0.0)
        # Marriott–Pope: E[rho_hat] ≈ rho - (1 + 3 rho) / n when the mean is estimated.
        rho = np.clip((n_bar * rho_hat + 1.0) / (n_bar - 3.0), -0.9, 0.95)
    else:
        rho = np.zeros(ss_total.shape)
    f = ar1_inflation(rho[..., None], n)

    denom = np.sum((n - f) * multi, -1)
    with np.errstate(invalid="ignore", divide="ignore"):
        s1sq = np.where(denom > 0, ss_total / denom, np.nan)
    tau2 = s1sq[..., None] * f / n
    s_m2 = np.var(m, axis=-1, ddof=1)
    s2sq = np.maximum(0.0, s_m2 - tau2.mean(-1))
    f_bar = f.mean(-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        k = np.sqrt(f_bar + n.mean() * s2sq / s1sq)
    dm = np.diff(m, axis=-1)
    s2sq_drift = np.maximum(0.0, 0.5 * np.mean(dm**2, -1) - tau2.mean(-1))
    return dict(s1=np.sqrt(s1sq), s2=np.sqrt(s2sq), k=k, rho=rho, f=f_bar, s2_drift=np.sqrt(s2sq_drift), m=m)


def upstream_share(process_trials_ns: Sequence[Sequence[float]]) -> float:
    """Exact port of bench_press `ProcessVarianceComponents.compute` (5fd6396): between_process_share
    on raw nanoseconds, with the first-difference within-process mean square. NaN where it returns null."""
    procs = [[float(x) for x in p] for p in process_trials_ns if len(p) > 0]
    if len(procs) < 2:
        return math.nan
    total, total_sq, weighted, diff_sq, diff_count = 0, 0.0, 0.0, 0.0, 0
    means = []
    for trials in procs:
        n = len(trials)
        total += n
        total_sq += n * n
        s = 0.0
        for x in trials:
            s += x
        p_mean = s / n
        means.append(p_mean)
        weighted += n * p_mean
        for t in range(n - 1):
            d = trials[t + 1] - trials[t]
            diff_sq += d * d
            diff_count += 1
    if diff_count == 0:
        return math.nan
    P = len(procs)
    k0 = (total - total_sq / total) / (P - 1)
    grand = weighted / total
    between = 0.0
    for trials, p_mean in zip(procs, means):
        d = p_mean - grand
        between += len(trials) * d * d
    ms_between = between / (P - 1)
    ms_within = 0.5 * (diff_sq / diff_count)
    var_between = max(0.0, (ms_between - ms_within) / k0) if k0 > 0.0 else 0.0
    total_var = var_between + ms_within
    return var_between / total_var if total_var > 0.0 else 0.0


def outlier_processes(process_values: Sequence[float], alpha: float = OUTLIER_ALPHA) -> tuple[int, ...]:
    """Indices of outlier processes by Rosner's generalized ESD test on log values (flagged, not removed).

    Tests for up to max(1, P // 5) outliers and keeps the chance of flagging anything in a clean
    normal sample at about `alpha`. A robust z-score rule (|z| > 3.5) was tried first and flagged
    9–20% of clean benchmarks at P = 5–40, because it tests every process separately. Needs at
    least 5 processes.
    """
    y = np.log(np.asarray(process_values, float))
    n = y.size
    if n < 5:
        return ()
    idx = np.arange(n)
    removed: list[int] = []
    n_outliers = 0
    for i in range(1, max(1, n // 5) + 1):
        sd = y[idx].std(ddof=1)
        if sd == 0:
            break
        dev = np.abs(y[idx] - y[idx].mean())
        j = int(np.argmax(dev))
        r = dev[j] / sd
        m = n - i + 1
        t = stats.t.ppf(1 - alpha / (2 * m), m - 2)
        crit = (m - 1) * t / math.sqrt((m - 2 + t**2) * m)
        removed.append(int(idx[j]))
        idx = np.delete(idx, j)
        if r > crit:
            n_outliers = i
    return tuple(sorted(removed[:n_outliers]))


def variance_components(
    process_trials: Sequence[Sequence[float]],
    autocorrelation: bool = True,
    conf: float = 0.95,
    n_boot: int = 1000,
    seed: int = 0,
) -> VarianceComponents:
    """Estimate sigma1, sigma2 and k from per-process trial times (any positive unit).

    Intervals come from a parametric bootstrap of the fitted model (AR(1) within processes, normal
    process effects, the same trial counts) with percentile limits; `n_boot=0` skips them (NaN). They are approximate,
    especially for sigma2 near 0 and for few processes; A4 measures their coverage.
    """
    raw = [np.asarray(t, float) for t in process_trials if len(t) > 0]
    trials = [np.log(t) for t in raw]
    P = len(trials)
    if P < 2:
        raise ValueError(f"need at least 2 non-empty processes, got {P}")
    Y, mask, n = _pad(trials)
    if not (n >= 2).any():
        raise ValueError("need at least one process with 2 or more trials")
    est = _estimate(Y, mask, n, autocorrelation)
    iid = _estimate(Y, mask, n, autocorrelation=False)
    s1, s2, rho = float(est["s1"]), float(est["s2"]), float(est["rho"])

    lo, hi = 100 * (1 - conf) / 2, 100 * (1 + conf) / 2
    if n_boot > 0:
        rng = np.random.default_rng(seed)
        n_max = Y.shape[1]
        e = np.empty((n_boot, P, n_max))
        e[..., 0] = rng.standard_normal((n_boot, P))
        innov = math.sqrt(1.0 - rho**2)
        for j in range(1, n_max):
            e[..., j] = rho * e[..., j - 1] + innov * rng.standard_normal((n_boot, P))
        Yb = s2 * rng.standard_normal((n_boot, P, 1)) + s1 * e
        boot = _estimate(Yb, mask, n, autocorrelation)
    else:
        boot = {"s1": np.array([]), "s2": np.array([]), "k": np.array([])}

    def ci(x: np.ndarray) -> tuple[float, float]:
        x = x[np.isfinite(x)]
        if x.size == 0:
            return (math.nan, math.nan)
        return (float(np.percentile(x, lo)), float(np.percentile(x, hi)))

    m = est["m"]
    if P >= MIN_PROCESSES_FOR_DRIFT and np.var(m) > 0:
        rs, rs_p = stats.spearmanr(np.arange(P), m)
        von_neumann = float(np.mean(np.diff(m) ** 2) / (2 * np.var(m, ddof=1)))
    else:
        rs, rs_p, von_neumann = math.nan, math.nan, math.nan

    return VarianceComponents(
        processes=P,
        mean_trials=float(n.mean()),
        sigma1=s1,
        sigma2=s2,
        k=float(est["k"]),
        icc=s2**2 / (s2**2 + s1**2) if s1 > 0 else math.nan,
        rho=rho,
        inflation=float(est["f"]),
        sigma2_iid=float(iid["s2"]),
        sigma2_drift=float(est["s2_drift"]),
        sigma1_ci=ci(boot["s1"]),
        sigma2_ci=ci(boot["s2"]),
        k_ci=ci(boot["k"]),
        upstream_share=upstream_share(raw),
        von_neumann=von_neumann,
        launch_spearman=float(rs),
        launch_spearman_p=float(rs_p),
        outlier_processes=outlier_processes(np.exp(m)),
        rho_estimated=autocorrelation and float(n[n >= 2].mean()) >= MIN_TRIALS_FOR_RHO,
    )
