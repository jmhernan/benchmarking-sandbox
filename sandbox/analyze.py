"""Exploratory analysis of the sample benchmark series in ../data.

Run with: conda run -n perfBench python sandbox/analyze.py
Outputs (tables + PNG plots) go to sandbox/output/.
Values are assumed to be microseconds (unconfirmed).

Model used for exploration: a smooth, slowly drifting *baseline* (fast mode,
tracked with a low rolling quantile) plus one-sided slowdowns (isolated spikes and
multi-iteration "slow episodes"). Warmup is where the baseline is still above its
final level.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import ruptures as rpt
from scipy import stats
from statsmodels.tsa.stattools import acf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(exist_ok=True)

SIZES = (10, 100, 1000, 10000)
# block: iterations per block median for PELT; base_w: rolling-quantile window (baseline)
CFG = {
    100: dict(block=1, min_size=2, base_w=9),
    1000: dict(block=5, min_size=4, base_w=51),
    10000: dict(block=20, min_size=5, base_w=101),
}
BASE_Q = 0.10  # baseline = rolling 10th percentile
DELTA_MIN = 0.02  # smallest level shift (log scale, ~2%) worth reporting
STEADY_TOL = 0.03  # steady state: baseline within 3% of its final level
EPISODE_FACTOR = 1.10  # slow episode: rolling median > 10% above long-window baseline
EPISODE_W = 31
EPISODE_MIN_LEN = 20
B = 2000
BLOCKS = [1, 10, 25, 50, 100, 250]
RNG = np.random.default_rng(20261013)


def load(n):
    return np.loadtxt(DATA / f"data_{n}.txt", dtype=float)


def rolling(x, w, fn, **kw):
    s = pl.Series(x)
    f = {"median": s.rolling_median, "quantile": s.rolling_quantile}[fn]
    return f(window_size=w, center=True, min_samples=1, **kw).to_numpy()


def baseline(x, w):
    return rolling(x, w, "quantile", quantile=BASE_Q, interpolation="linear")


# ---------- changepoints ----------
def _merge_small(y, cps, delta_min):
    """Drop the changepoint with the smallest level jump until all jumps >= delta_min."""
    cps = list(cps)
    while cps:
        edges = [0, *cps, len(y)]
        meds = [np.median(y[a:b]) for a, b in zip(edges[:-1], edges[1:])]
        jumps = np.abs(np.diff(meds))
        i = int(np.argmin(jumps))
        if jumps[i] >= delta_min:
            break
        cps.pop(i)
    return cps


def pelt_changepoints(x, n, delta_min=DELTA_MIN):
    """PELT (l2) on log block-medians, BIC-style penalty, then merge jumps < delta_min."""
    cfg = CFG[n]
    blk = cfg["block"]
    m = len(x) // blk
    y = np.log(np.median(x[: m * blk].reshape(m, blk), axis=1))
    d = np.diff(y)
    sigma = max(stats.median_abs_deviation(d, scale="normal") / np.sqrt(2), 0.005)
    pen = 2 * sigma**2 * np.log(m)
    bk = rpt.Pelt(model="l2", min_size=cfg["min_size"], jump=1).fit(y).predict(pen=pen)[:-1]
    bk = _merge_small(y, bk, delta_min)
    return [int(b * blk) for b in bk]


def segments(x, cps):
    edges = [0, *cps, len(x)]
    rows = []
    for a, b in zip(edges[:-1], edges[1:]):
        seg = x[a:b]
        rows.append(dict(start=a, end=b, n=b - a, median=float(np.median(seg)),
                         p10=float(np.percentile(seg, 10)), mean=float(seg.mean())))
    return pl.DataFrame(rows)


# ---------- warmup / steady state ----------
def final_level(b):
    return float(np.median(b[-max(5, len(b) // 5):]))


def warmup_bounds(x, n, tol):
    """(first_reach, last_exit): optimistic and conservative steady-state start."""
    b = baseline(x, CFG[n]["base_w"])
    lim = final_level(b) * (1 + tol)
    over = np.where(b > lim)[0]
    first = int(np.argmax(b <= lim))
    last = 0 if len(over) == 0 else int(over[-1] + 1)
    return first, last


def slow_episodes(x, n, start):
    """Contiguous runs where the rolling median exceeds the long-window baseline."""
    w = CFG[n]["base_w"] * 4
    ref = baseline(x, w)
    slow = rolling(x, EPISODE_W, "median") > EPISODE_FACTOR * ref
    slow[:start] = False
    runs, i = [], 0
    while i < len(x):
        if slow[i]:
            j = i
            while j < len(x) and slow[j]:
                j += 1
            if j - i >= EPISODE_MIN_LEN:
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


# ---------- uncertainty ----------
def ess_from_acf(x, max_lag=500):
    """Effective sample size via the initial positive sequence of the ACF."""
    rho = acf(x, nlags=min(max_lag, len(x) // 2), fft=True)[1:]
    s = 0.0
    for r in rho:
        if r <= 0:
            break
        s += r
    return len(x) / (1 + 2 * s)


STATS = {
    "mean": lambda a: a.mean(axis=1),
    "median": lambda a: np.median(a, axis=1),
    "trim10": lambda a: stats.trim_mean(a, 0.1, axis=1),
}


def circular_block_bootstrap(x, block, B, chunk=250):
    """Resample whole blocks (circular) and return the distribution of every statistic."""
    n = len(x)
    k = int(np.ceil(n / block))
    out = {name: [] for name in STATS}
    for done in range(0, B, chunk):
        c = min(chunk, B - done)
        starts = RNG.integers(0, n, size=(c, k))
        idx = (starts[:, :, None] + np.arange(block)) % n
        samp = x[idx.reshape(c, -1)[:, :n]]
        for name, fn in STATS.items():
            out[name].append(fn(samp))
    return {k_: np.concatenate(v) for k_, v in out.items()}


def bootstrap_table(x, label):
    rows = []
    points = {name: float(fn(x[None, :])[0]) for name, fn in STATS.items()}
    for b in BLOCKS:
        if b > len(x) // 4:
            continue
        dists = circular_block_bootstrap(x, b, B)
        for name, dist in dists.items():
            lo, hi = np.percentile(dist, [2.5, 97.5])
            p = points[name]
            rows.append(dict(series=label, stat=name, block=b, n=len(x), point=p,
                             se=float(dist.std(ddof=1)), lo=float(lo), hi=float(hi),
                             rel_halfwidth_pct=100 * (hi - lo) / 2 / p))
    return pl.DataFrame(rows)


# ---------- spikes ----------
def spike_table(x, label):
    base = np.median(x)
    mad = stats.median_abs_deviation(x, scale="normal")
    rules = [("rel +10%", 1.10 * base), ("rel +25%", 1.25 * base),
             ("rel +50%", 1.5 * base), ("median+5*MADn", base + 5 * mad),
             ("Tukey 3*IQR", np.percentile(x, 75) + 3 * stats.iqr(x))]
    return pl.DataFrame([
        dict(series=label, rule=r, threshold=float(t),
             spike_frac_pct=100 * float((x > t).mean()), median=float(base),
             mad_normal=float(mad)) for r, t in rules])


# ---------- plots ----------
def plot_series(n, x, cps, first, last, episodes, post, path):
    fig, ax = plt.subplots(1, 3, figsize=(18, 4.8))
    ax[0].plot(x, lw=0.4, color="0.6", label="raw")
    if n in CFG:
        ax[0].plot(baseline(x, CFG[n]["base_w"]), lw=1.3, color="C0",
                   label=f"baseline (rolling p{int(BASE_Q * 100)})")
        ax[0].plot(rolling(x, EPISODE_W, "median"), lw=0.8, color="C1",
                   label=f"rolling median ({EPISODE_W})")
    for c in cps:
        ax[0].axvline(c, color="C3", ls="--", lw=0.7)
    ax[0].axvline(first, color="C2", lw=1.5, label=f"steady first-reach ({STEADY_TOL:.0%})")
    ax[0].axvline(last, color="C4", lw=1.5, label="steady last-exit")
    for a, b in episodes:
        ax[0].axvspan(a, b, color="orange", alpha=0.25)
    ax[0].set_yscale("log")
    ax[0].set(title=f"data_{n}: PELT changepoints (red), slow episodes (orange)",
              xlabel="iteration", ylabel="time (assumed µs)")
    ax[0].legend(fontsize=7)
    ax[1].hist(np.log10(post), bins=60, color="C0")
    ax[1].set(title=f"post-steady log10 distribution (n={len(post)})", xlabel="log10(time)")
    if len(post) > 20:
        lags = min(60, len(post) // 2)
        ax[2].bar(range(lags + 1), acf(post, nlags=lags, fft=True), width=0.8)
        ax[2].axhline(1.96 / np.sqrt(len(post)), color="r", ls=":")
        ax[2].set(title="ACF of post-steady series", xlabel="lag")
    else:
        ax[2].text(0.5, 0.5, "too few post-steady points", ha="center")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_bootstrap(boot, path):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for series, df in boot.group_by("series", maintain_order=True):
        for name in ("mean", "median"):
            d = df.filter(pl.col("stat") == name).sort("block")
            ax[0 if name == "mean" else 1].plot(d["block"], d["se"], marker="o",
                                                label=series[0])
    for a, name in zip(ax, ("mean", "median")):
        a.set(xscale="log", xlabel="block length (iterations; 1 = iid)",
              ylabel="bootstrap SE", title=f"SE of the {name}")
        a.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    pl.Config.set_tbl_rows(100)
    pl.Config.set_tbl_cols(20)
    pl.Config.set_tbl_width_chars(220)
    seg_frames, warm_rows, spike_frames, boot_frames = [], [], [], []
    ess_rows, sens_rows, episode_rows = [], [], []
    for n in SIZES:
        x = load(n)
        label = f"data_{n}"
        print(f"\n===== {label} (n={len(x)}) =====")
        if n == 10:
            print("too short for changepoint/warmup analysis; skipped")
            spike_frames.append(spike_table(x, label))
            plot_series(n, x, [], 0, 0, [], x, OUT / f"{label}.png")
            continue
        cps = pelt_changepoints(x, n)
        seg_frames.append(segments(x, cps).with_columns(series=pl.lit(label)))
        print(f"PELT changepoints (>= {DELTA_MIN:.0%} shifts): {cps}")
        print(segments(x, cps))
        for d in (0.01, 0.02, 0.05, 0.10):
            c = pelt_changepoints(x, n, d)
            sens_rows.append(dict(series=label, delta_min=d, n_changepoints=len(c),
                                  changepoints=str(c)))
        b = baseline(x, CFG[n]["base_w"])
        for tol in (0.02, 0.03, 0.05, 0.10):
            first, last = warmup_bounds(x, n, tol)
            warm_rows.append(dict(series=label, tol=tol, final_baseline=final_level(b),
                                  first_reach=first, last_exit=last,
                                  last_exit_discard_pct=100 * last / len(x)))
        first, last = warmup_bounds(x, n, STEADY_TOL)
        post = x[first:]
        eps = slow_episodes(x, n, first) if len(post) >= 200 else []
        in_ep = sum(b_ - a_ for a_, b_ in eps)
        episode_rows.append(dict(series=label, post_n=len(post), n_episodes=len(eps),
                                 pct_time_in_episodes=100 * in_ep / max(len(post), 1),
                                 longest=max([b_ - a_ for a_, b_ in eps], default=0),
                                 episodes=str(eps)))
        spike_frames.append(spike_table(post if len(post) >= 30 else x, label))
        plot_series(n, x, cps, first, last, eps, post, OUT / f"{label}.png")
        if len(post) >= 200:
            ess = ess_from_acf(post)
            ess_rows.append(dict(series=label, n_post=len(post), ess_mean=ess,
                                 ess_ratio=ess / len(post), lag1=float(acf(post, nlags=1)[1]),
                                 iid_se_mean=float(post.std(ddof=1) / np.sqrt(len(post))),
                                 ess_se_mean=float(post.std(ddof=1) / np.sqrt(ess))))
            boot_frames.append(bootstrap_table(post, f"{label}:post-steady"))
        if n == 10000:
            boot_frames.append(bootstrap_table(x, f"{label}:full"))

    boot = pl.concat(boot_frames)
    plot_bootstrap(boot, OUT / "bootstrap_se_vs_block.png")
    tables = {"segments": pl.concat(seg_frames), "spikes": pl.concat(spike_frames),
              "bootstrap": boot, "warmup": pl.DataFrame(warm_rows),
              "ess": pl.DataFrame(ess_rows), "episodes": pl.DataFrame(episode_rows),
              "changepoint_sensitivity": pl.DataFrame(sens_rows)}
    for name, df in tables.items():
        df.write_csv(OUT / f"{name}.csv")
    for name in ("changepoint_sensitivity", "warmup", "episodes", "spikes", "ess",
                 "bootstrap"):
        print(f"\n--- {name} ---\n{tables[name]}")


if __name__ == "__main__":
    main()
