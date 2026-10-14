"""Synthetic benchmark-series generator with known ground truth.

Nothing runs on import. You trigger generation yourself:

    # write synthetic series (+ truth sidecars) in the same one-int-per-line format as data/
    python sandbox/synth.py generate --preset data10000 --reps 5 --seed 1 --out sandbox/synthetic

    # compare synthetic summary statistics with a real file (uses sandbox/analyze.py)
    python sandbox/synth.py compare --preset data10000 --real data/data_10000.txt --reps 20

Generative model (times in the assumed microseconds), for iteration t:

    level(t) = base * process_mult * effect
               * (1 + drift_amp * exp(-t / drift_tau))                  slow baseline drift
               * jit(t)                                                  optional JIT warmup curve
    x(t)     = level(t)
               * (1 + episode(t))        slow episodes: sharp jump, exponential decay
               * (1 + spike(t))          one-sided spikes, in short runs
               * (1 + periodic(t))       optional weak periodic component
               * exp(jitter_sd * N(0,1)) small multiplicative noise
    then rounded to integers (the real data is quantised).

`process_mult = exp(process_sd * N(0,1))` is the Level-2 (between-process) effect and
`effect` is the true speedup ratio (new/old) used to test change detection. The
real data has one process per file, so `process_sd` is an assumption, not a measurement.

Defaults are starting values taken from visual/exploratory analysis of data_10000
(see docs/research.md Appendix A.2). They are NOT yet calibrated: run `compare` and adjust.
"""
import argparse
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Params:
    n: int = 10000
    base: float = 137.0  # asymptotic baseline level
    drift_amp: float = 0.07  # initial relative excess of the baseline
    drift_tau: float = 700.0  # iterations
    jit_warmup: bool = False
    jit_ratio: float = 13.0  # cold/warm slowdown (data_100: ~2400 / ~180)
    jit_mid: float = 35.0  # iteration where the JIT curve is halfway (log scale)
    jit_width: float = 8.0
    jitter_sd: float = 0.003  # relative sd of baseline jitter
    spike_rate: float = 0.10  # fraction of iterations in a spike
    spike_persist: float = 0.3  # P(spike continues to next iteration)
    spike_log_mean: float = float(np.log(0.25))  # excess ~ lognormal
    spike_log_sd: float = 0.7
    episode_rate: float = 0.0023  # per iteration (~21 per 9,300 in data_10000)
    episode_log_mean: float = float(np.log(0.9))  # peak excess ~ lognormal
    episode_log_sd: float = 0.35
    episode_tau: float = 30.0  # decay time constant (iterations)
    episode_tau_log_sd: float = 0.3
    period: float = 13.5
    period_prob: float = 0.0  # chance a periodic slot fires (0 = off)
    period_excess: float = 0.15
    process_sd: float = 0.0  # Level-2 log-sd of the process-level multiplier
    effect: float = 1.0  # true new/old ratio of long-run means
    quantise: bool = True


PRESETS = {
    "data10000": Params(n=10000, period_prob=0.3),
    "data1000": Params(n=1000, base=148.0, drift_amp=0.15, drift_tau=300.0,
                       spike_rate=0.15, episode_rate=0.004),
    "jit100": Params(n=100, base=180.0, drift_amp=0.0, jit_warmup=True, spike_rate=0.15,
                     episode_rate=0.0, jitter_sd=0.01),
}


@dataclass
class Series:
    x: np.ndarray  # observed (integers if quantised)
    level: np.ndarray  # true baseline level (drift/warmup/process/effect included)
    episode_excess: np.ndarray
    spike_mask: np.ndarray
    episode_mask: np.ndarray  # episode_excess > 0.10
    asymptote: float  # level the baseline converges to
    warmup_end: int  # first iteration after which level stays within 3% of asymptote
    params: Params

    def truth(self):
        edges = np.diff(np.r_[0, self.episode_mask.astype(int), 0])
        eps = list(zip(np.where(edges == 1)[0].tolist(), np.where(edges == -1)[0].tolist()))
        return dict(params=asdict(self.params), warmup_end=self.warmup_end,
                    asymptote=self.asymptote, episodes=eps,
                    spike_fraction=float(self.spike_mask.mean()))


def _runs_mask(n, starts, lengths):
    diff = np.zeros(n + 1)
    np.add.at(diff, starts, 1)
    np.add.at(diff, np.minimum(starts + lengths, n), -1)
    return np.cumsum(diff[:n]) > 0


def _episodes(p, n, rng):
    ep = np.zeros(n)
    k = rng.poisson(p.episode_rate * n)
    for s in rng.integers(0, n, size=k):
        amp = rng.lognormal(p.episode_log_mean, p.episode_log_sd)
        tau = p.episode_tau * rng.lognormal(0.0, p.episode_tau_log_sd)
        length = min(int(np.ceil(6 * tau)), n - s)
        ep[s:s + length] = np.maximum(ep[s:s + length], amp * np.exp(-np.arange(length) / tau))
    return ep


def _spikes(p, n, rng):
    mean_len = 1.0 / (1.0 - p.spike_persist)
    starts = np.where(rng.random(n) < p.spike_rate / mean_len)[0]
    lengths = rng.geometric(1.0 - p.spike_persist, size=len(starts))
    mask = _runs_mask(n, starts, lengths)
    exc = np.zeros(n)
    exc[mask] = rng.lognormal(p.spike_log_mean, p.spike_log_sd, size=int(mask.sum()))
    return mask, exc


def simulate(p: Params, seed=None, rng=None, tol=0.03) -> Series:
    rng = rng or np.random.default_rng(seed)
    n, t = p.n, np.arange(p.n)
    mult = np.exp(p.process_sd * rng.standard_normal()) * p.effect
    asym = p.base * mult
    level = asym * (1 + p.drift_amp * np.exp(-t / p.drift_tau))
    if p.jit_warmup:
        level = level * np.exp(np.log(p.jit_ratio) / (1 + np.exp((t - p.jit_mid) / p.jit_width)))
    ep = _episodes(p, n, rng)
    spike_mask, spike_exc = _spikes(p, n, rng)
    per = np.zeros(n)
    if p.period_prob > 0:
        slots = np.floor(rng.uniform(0, p.period) + np.arange(0, n, p.period)).astype(int)
        slots = slots[(slots < n) & (rng.random(len(slots)) < p.period_prob)]
        per[slots] = p.period_excess
    x = level * (1 + ep) * (1 + spike_exc) * (1 + per) * np.exp(p.jitter_sd * rng.standard_normal(n))
    if p.quantise:
        x = np.maximum(np.rint(x), 1.0)
    over = np.where(level > asym * (1 + tol))[0]
    warm_end = 0 if len(over) == 0 else int(over[-1] + 1)
    return Series(x=x, level=level, episode_excess=ep, spike_mask=spike_mask,
                  episode_mask=ep > 0.10, asymptote=float(asym), warmup_end=warm_end,
                  params=p)


def long_run_mean(p: Params, n_long=2_000_000, chunk=200_000, seed=0):
    """Estimand for coverage studies: long-run mean/median of the stationary process.

    Drift, JIT warmup and the process effect are switched off, `effect` is kept, so the
    result is the true per-iteration mean for a process whose level multiplier is 1.
    """
    rng = np.random.default_rng(seed)
    q = replace(p, drift_amp=0.0, jit_warmup=False, process_sd=0.0, n=chunk)
    xs = np.concatenate([simulate(q, rng=rng).x for _ in range(n_long // chunk)])
    return dict(mean=float(xs.mean()), median=float(np.median(xs)))


# ---------------------------------------------------------------- CLI
def _stats(x):
    """Summary statistics computed with the same pipeline used on the real data."""
    import analyze as A

    n = len(x)
    first, _ = A.warmup_bounds(x, n, A.STEADY_TOL)
    post = x[first:]
    med = float(np.median(post))
    eps = A.slow_episodes(x, n, first) if len(post) >= 200 else []
    return dict(
        warmup_end=first, median=med, mean=float(post.mean()),
        p90=float(np.percentile(post, 90)), p99=float(np.percentile(post, 99)),
        lag1=float(np.corrcoef(post[:-1], post[1:])[0, 1]),
        frac_gt_10pct=float((post > 1.10 * med).mean()),
        frac_gt_25pct=float((post > 1.25 * med).mean()),
        frac_gt_50pct=float((post > 1.50 * med).mean()),
        n_episodes=len(eps), pct_in_episodes=100 * sum(b - a for a, b in eps) / len(post),
        ess_ratio=A.ess_from_acf(post) / len(post) if len(post) >= 200 else float("nan"))


def cmd_generate(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    p = PRESETS[a.preset]
    over = {k: v for k, v in dict(n=a.n, process_sd=a.process_sd, effect=a.effect).items()
            if v is not None}
    p = replace(p, **over)
    for r in range(a.reps):
        s = simulate(p, seed=a.seed + r)
        stem = f"{a.preset}_n{p.n}_seed{a.seed + r}"
        np.savetxt(out / f"{stem}.txt", s.x, fmt="%d")
        (out / f"{stem}.truth.json").write_text(json.dumps(s.truth(), indent=1))
    print(f"wrote {a.reps} series + truth files to {out}")


def cmd_compare(a):
    import analyze as A

    p = PRESETS[a.preset]
    if p.n not in A.CFG:
        raise SystemExit(f"analysis config only exists for n in {sorted(A.CFG)}")
    real = _stats(np.loadtxt(a.real))
    syn = [_stats(simulate(p, seed=a.seed + r).x) for r in range(a.reps)]
    print(f"{'statistic':<16}{'real':>12}{'synthetic mean':>16}{'synthetic sd':>14}")
    for k, v in real.items():
        vals = np.array([s[k] for s in syn], dtype=float)
        print(f"{k:<16}{v:>12.3f}{np.nanmean(vals):>16.3f}{np.nanstd(vals):>14.3f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--preset", choices=PRESETS, default="data10000")
    g.add_argument("--reps", type=int, default=1)
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--n", type=int)
    g.add_argument("--process-sd", dest="process_sd", type=float)
    g.add_argument("--effect", type=float)
    g.add_argument("--out", default="sandbox/synthetic")
    g.set_defaults(fn=cmd_generate)
    c = sub.add_parser("compare")
    c.add_argument("--preset", choices=PRESETS, default="data10000")
    c.add_argument("--real", default="data/data_10000.txt")
    c.add_argument("--reps", type=int, default=20)
    c.add_argument("--seed", type=int, default=1)
    c.set_defaults(fn=cmd_compare)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
