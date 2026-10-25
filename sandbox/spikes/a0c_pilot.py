"""A0c A/A pilot analysis (plan A0c; the plan is local, git-ignored).

Input: one bench_press run of a single binary with --processes P, e.g.
    cd bench && dart run bench_press run -t aot --processes 40 \
        -o ../data/runs/pilot/aa_workload.json benchmark/workload_benchmark.dart
Run:  python sandbox/spikes/a0c_pilot.py [path/to/run.json]   (perfBench env)

Every process ran the same binary, so the true speedup between any two is 1.
Throwaway: superseded by bench_stats.stats once A2 is built.
"""
import json
import sys
from itertools import combinations
from pathlib import Path

import matplotlib
import numpy as np
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/runs/pilot/aa_workload.json"
PLOT = ROOT / "sandbox/output/a0c_pilot.png"
DELTA = 0.03
rng = np.random.default_rng(20261024)


def fieller(a, b, conf=0.95):
    """Port of bench_press FiellerInterval.compute, unpaired (Welch df). Ratio mean(a)/mean(b)."""
    ma, mb = a.mean(), b.mean()
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    df = (va + vb) ** 2 / (va**2 / (len(a) - 1) + vb**2 / (len(b) - 1))
    t = stats.t.ppf(1 - (1 - conf) / 2, df)
    r, g = ma / mb, t * t * vb / mb**2
    if g >= 1:
        return r, -np.inf, np.inf
    m = t / abs(mb) * np.sqrt(va * (1 - g) + r * r * vb)
    return r, (r - m) / (1 - g), (r + m) / (1 - g)


def verdict_today(r, lo, hi):
    """bench_press _classifyMovement with --threshold 0 (the ±5% point band)."""
    if lo <= 1 <= hi:
        return "neutral"
    return "faster" if r >= 1.05 else "slower" if r <= 0.95 else "neutral"


def verdict_threshold(lo, hi, lo90, hi90, d=DELTA):
    """bench_press _classifyThresholdMovement (--threshold d)."""
    up, down = 1 + d, 1 / (1 + d)
    if lo >= up:
        return "faster"
    if hi <= down:
        return "slower"
    return "equivalent" if (lo90 >= down and hi90 <= up) else "inconclusive"


def ar1_factor(rho, n):
    """n * Var(mean) / sigma^2 for a stationary AR(1) series of length n."""
    k = np.arange(1, n)
    return 1 + 2 * np.sum((1 - k / n) * rho**k)


def components(Y):
    """One-way random-effects ANOVA on log trials Y (P x n), proposal §3.4."""
    P, n = Y.shape
    m = Y.mean(1)
    msb = n * m.var(ddof=1)
    msw = Y.var(axis=1, ddof=1).mean()
    s2 = max(0.0, (msb - msw) / n)
    return dict(s1=np.sqrt(msw), s2=np.sqrt(s2), k=np.sqrt(1 + n * s2 / msw))


def upstream_share(X):
    """bench_press ProcessVarianceComponents.compute (balanced case), on raw ns."""
    n = X.shape[1]
    msb = n * X.mean(1).var(ddof=1)
    msw = 0.5 * (np.diff(X, axis=1) ** 2).mean()
    vb = max(0.0, (msb - msw) / n)
    return vb / (vb + msw)


def ar_corrected(Y):
    """sigma2 after allowing for AR(1) autocorrelation within processes."""
    P, n = Y.shape
    R = Y - Y.mean(1, keepdims=True)
    rho = np.sum(R[:, 1:] * R[:, :-1]) / np.sum(R**2)
    f = ar1_factor(rho, n)
    sig2 = Y.var(axis=1, ddof=1).mean() * (n - 1) / (n - f)
    within_var_of_mean = sig2 * f / n
    s2 = max(0.0, Y.mean(1).var(ddof=1) - within_var_of_mean)
    return rho, f, np.sqrt(sig2), np.sqrt(s2)


run = json.loads(RUN.read_text())
b = run["benchmarks"][0]
X = np.array(b["process_trials_ns"], dtype=float)
Y = np.log(X)
P, n = X.shape
print(f"{RUN.name}: {b['name']} ({b['target']}), P={P} processes x n={n} trials, "
      f"batch={b['calibrated_batch_iterations']} ops, mean={X.mean() / 1e3:.2f} us/op")
print(f"bench_press: is_stable={b['metrics']['is_stable']}, "
      f"between_process_share={b['metrics']['variance_components']['between_process_share']:.1%}")

print("\n1. Variance components (log scale; 95% intervals from resampling processes)")
c = components(Y)
boot = np.array([[*components(Y[idx]).values(), upstream_share(X[idx])]
                 for idx in rng.integers(0, P, (4000, P))])
ci = lambda j: np.percentile(boot[:, j], [2.5, 97.5])  # noqa: E731
print(f"   sigma1 (within, per trial)   {100 * c['s1']:.3f}%   [{100 * ci(0)[0]:.3f}, {100 * ci(0)[1]:.3f}]")
print(f"   sigma2 (between processes)   {100 * c['s2']:.3f}%   [{100 * ci(1)[0]:.3f}, {100 * ci(1)[1]:.3f}]")
print(f"   k-hat                        {c['k']:.2f}      [{ci(2)[0]:.2f}, {ci(2)[1]:.2f}]"
      "   (single-process SE understated by this factor)")
print(f"   upstream share (recomputed)  {upstream_share(X):.1%}    [{ci(3)[0]:.1%}, {ci(3)[1]:.1%}]")
anova_share = c["s2"] ** 2 / (c["s2"] ** 2 + c["s1"] ** 2)
print(f"   ANOVA share for comparison   {anova_share:.1%}")

print("\n2. Autocorrelation within processes")
R = Y - Y.mean(1, keepdims=True)
r1 = np.array([np.corrcoef(y[:-1], y[1:])[0, 1] for y in Y])
rho, f, s1_ar, s2_ar = ar_corrected(Y)
print(f"   lag-1 per process: median {np.median(r1):.2f}, IQR [{np.percentile(r1, 25):.2f}, "
      f"{np.percentile(r1, 75):.2f}], {np.mean(r1 > 0.3):.0%} of processes above 0.3")
print(f"   pooled lag-1 rho={rho:.2f} (biased low at n={n}); variance inflation of a process mean f={f:.2f}")
print(f"   sigma2 allowing for AR(1): {100 * s2_ar:.3f}%  (vs {100 * c['s2']:.3f}% assuming independent trials)")
profile = R.mean(0)
print(f"   mean profile by trial index (common to all processes): first 3 "
      f"{np.round(100 * profile[:3], 3)}%, last 3 {np.round(100 * profile[-3:], 3)}%")

print("\n3. Drift across launch order (processes ran one after another)")
m = Y.mean(1)
rs, pv = stats.spearmanr(np.arange(P), m)
von_neumann = np.mean(np.diff(m) ** 2) / (2 * m.var(ddof=1))
print(f"   Spearman(process mean, launch index) = {rs:.2f} (p={pv:.3f})")
print(f"   von Neumann ratio = {von_neumann:.2f} (about 1 if process means are independent, < 1 if they drift)")
s2_diff = np.sqrt(max(0.0, 0.5 * np.mean(np.diff(m) ** 2) - (c["s1"] ** 2) * f / n))
print(f"   sigma2 from successive process means (drift-robust, AR-adjusted): {100 * s2_diff:.3f}%")

print("\n4. Verdicts between processes of the same binary (true ratio = 1)")
pairs = list(combinations(range(P), 2))
today, gate, excl = {}, {}, 0
for i, j in pairs:
    r, lo, hi = fieller(X[i], X[j])
    _, lo90, hi90 = fieller(X[i], X[j], 0.90)
    excl += not (lo <= 1 <= hi)
    v = verdict_today(r, lo, hi)
    today[v] = today.get(v, 0) + 1
    v = verdict_threshold(lo, hi, lo90, hi90)
    gate[v] = gate.get(v, 0) + 1
N = len(pairs)
print(f"   single process vs single process, {N} pairs (not independent):")
print(f"     printed 95% interval excludes 1:          {excl / N:.0%}   (nominal 5%)")
print(f"     today's verdict (--threshold 0) flags:    {(N - today.get('neutral', 0)) / N:.0%}   {today}")
print(f"     --threshold {DELTA} gate: " + ", ".join(f"{k} {v / N:.0%}" for k, v in sorted(gate.items())))
for p in (5, 10):
    hits, flags, eq, reps = 0, 0, 0, 2000
    for _ in range(reps):
        idx = rng.permutation(P)[: 2 * p]
        a, bb = X[idx[:p]].mean(1), X[idx[p:]].mean(1)
        r, lo, hi = fieller(a, bb)
        _, lo90, hi90 = fieller(a, bb, 0.90)
        hits += not (lo <= 1 <= hi)
        v = verdict_threshold(lo, hi, lo90, hi90)
        flags += v in ("faster", "slower")
        eq += v == "equivalent"
    print(f"   process-level Fieller, P={p} vs {p} (random splits): excludes 1 {hits / reps:.1%} (nominal 5%), "
          f"gate false >= {DELTA:.0%} {flags / reps:.1%}, equivalent {eq / reps:.0%}")

print("\n5. Go/no-go (plan A0c): sigma2 is material if its interval excludes ~0 and k-hat is well above 1.")

fig, ax = plt.subplots(1, 3, figsize=(15, 4))
se = Y.std(axis=1, ddof=1) / np.sqrt(n)
ax[0].errorbar(np.arange(P), 100 * (m - m.mean()), yerr=200 * se, fmt="o", ms=3, capsize=2)
ax[0].set(title="Process means vs launch order (±2 single-process SE)",
          xlabel="launch index", ylabel="% from grand mean")
ax[1].plot(np.arange(n), 100 * R.T, color="0.8", lw=0.6)
ax[1].plot(np.arange(n), 100 * profile, color="C3", lw=2, label="mean over processes")
ax[1].set(title="Within-process trials (centred per process)", xlabel="trial index", ylabel="%")
ax[1].legend()
ax[2].hist(r1, bins=15)
ax[2].axvline(0, color="k", lw=0.8)
ax[2].set(title="Lag-1 autocorrelation per process", xlabel="rho", ylabel="processes")
fig.tight_layout()
fig.savefig(PLOT, dpi=120)
print(f"\nplot: {PLOT.relative_to(ROOT)}")
