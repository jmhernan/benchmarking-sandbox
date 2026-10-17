"""Monte Carlo simulations behind docs/bench_press/statistical-proposal.md.

Run:  python docs/bench_press/simulate.py      (numpy + scipy; a few seconds)

Model, per version v in {baseline, candidate}, process p, batch j:

    x_vpj = mu_v * alpha_vp * (1 + sigma1 * eps_vpj)
    alpha_vp = exp(sigma2 * Z_vp),  Z, eps ~ N(0, 1) independent

sigma1 = within-process batch-to-batch noise (relative SD).
sigma2 = between-process effect (layout, ASLR, initial heap), relative SD.
theta  = mu_baseline / mu_candidate (bench_press's orientation: > 1 = faster).

"Current" = bench_press today (e21db31): one process per version, Fieller on
that process's batch means (Welch-Satterthwaite df, lib/src/stats/fieller.dart).
Its *verdict* (markdown_reporter.dart, _classifyMovement) is Faster only if the
interval excludes 1 AND the point speedup >= 1.05, Regression only if it
excludes 1 AND the speedup <= 0.95, otherwise Neutral. Tables report both the
printed interval ("interval excludes 1") and that verdict ("bench_press verdict").
The isStable gate is not modelled (CV is well under 5% at these sigma1 values).
"Process-level" = P processes per version, Fieller on the P per-process means.
"""

import numpy as np
from scipy import stats

SEED = 20261017
REPS = 4000
BOOT_REPS = 2000
B = 1000
GATE = 0.03
BAND_UP, BAND_DOWN = 1.05, 0.95   # bench_press _classifyMovement thresholds

rng = np.random.default_rng(SEED)


def fieller(a, b, level=0.95):
    """Fieller CI for mean(a)/mean(b), Welch df; mirrors bench_press."""
    na, nb = a.shape[-1], b.shape[-1]
    ma, mb = a.mean(-1), b.mean(-1)
    va, vb = a.var(-1, ddof=1) / na, b.var(-1, ddof=1) / nb
    df = np.clip((va + vb) ** 2 / (va**2 / (na - 1) + vb**2 / (nb - 1)), 1, 1e4)
    t = stats.t.ppf(0.5 + level / 2, df)
    g = t * t * vb / mb**2
    r = ma / mb
    disc = va * (1 - g) + r * r * vb
    m = t / np.abs(mb) * np.sqrt(np.maximum(disc, 0))
    lo, hi = (r - m) / (1 - g), (r + m) / (1 - g)
    bad = g >= 1
    return np.where(bad, -np.inf, lo), np.where(bad, np.inf, hi)


def simulate(mu, s1, s2, P, n, reps, gen=None):
    """Batch means, shape (reps, P, n)."""
    g = rng if gen is None else gen
    alpha = np.exp(s2 * g.standard_normal((reps, P, 1)))
    return mu * alpha * (1 + s1 * g.standard_normal((reps, P, n)))


def current_full(theta, s1, s2, n, reps=REPS, gen=None):
    A = simulate(theta, s1, s2, 1, n, reps, gen)[:, 0, :]
    Bv = simulate(1.0, s1, s2, 1, n, reps, gen)[:, 0, :]
    lo, hi = fieller(A, Bv)
    return lo, hi, A.mean(-1) / Bv.mean(-1)


def current(theta, s1, s2, n, reps=REPS):
    lo, hi, _ = current_full(theta, s1, s2, n, reps)
    return lo, hi


def bench_press_verdict(lo, hi, r):
    """Real bench_press rule: interval excludes 1 AND point past the 5% band."""
    excl = ~((lo <= 1) & (1 <= hi))
    return excl & (r >= BAND_UP), excl & (r <= BAND_DOWN)


def verdict_flag_rate(lo, hi, r):
    faster, slower = bench_press_verdict(lo, hi, r)
    return np.mean(faster | slower)


def process_level(theta, s1, s2, P, n, reps=REPS):
    A = simulate(theta, s1, s2, P, n, reps).mean(-1)
    Bv = simulate(1.0, s1, s2, P, n, reps).mean(-1)
    return fieller(A, Bv)


def bootstrap_process(theta, s1, s2, P, n, reps=BOOT_REPS):
    A = simulate(theta, s1, s2, P, n, reps).mean(-1)
    Bv = simulate(1.0, s1, s2, P, n, reps).mean(-1)
    lo, hi = np.empty(reps), np.empty(reps)
    for s in range(0, reps, 100):
        a, b = A[s:s + 100], Bv[s:s + 100]
        rows = np.arange(len(a))[:, None, None]
        ra = a[rows, rng.integers(0, P, (len(a), B, P))].mean(-1)
        rb = b[rows, rng.integers(0, P, (len(b), B, P))].mean(-1)
        lo[s:s + 100], hi[s:s + 100] = np.percentile(ra / rb, [2.5, 97.5], axis=1)
    return lo, hi


def coverage(lo, hi, theta):
    return np.mean((lo <= theta) & (theta <= hi))


def false_alarm(lo, hi):
    return np.mean(~((lo <= 1) & (1 <= hi)))


def predicted_coverage(s1, s2, n):
    k = np.sqrt(1 + n * s2**2 / s1**2)
    return k, 2 * stats.norm.cdf(1.96 / k) - 1


def verdicts(lo, hi, d=GATE):
    up, down = 1 + d, 1 / (1 + d)
    faster = lo > up
    slower = hi < down
    inside = (lo > down) & (hi < up)
    contains1 = (lo <= 1) & (1 <= hi)
    equivalent = inside & contains1
    small_real = inside & ~contains1
    inconclusive = ~(faster | slower | inside)
    return {
        "faster": faster.mean(),
        "slower": slower.mean(),
        "equivalent": equivalent.mean(),
        "small_real": small_real.mean(),
        "inconclusive": inconclusive.mean(),
        "excl1": (~contains1).mean(),
    }


def table(header, rows):
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join("---" for _ in header) + "|")
    for r in rows:
        print("| " + " | ".join(r) + " |")
    print()


def pct(x):
    return f"{100 * x:.0f}%"


def main():
    n = 15
    print(f"seed={SEED}, reps={REPS} (bootstrap {BOOT_REPS}x{B}); "
          f"Monte Carlo SE at 95% coverage = {100*np.sqrt(.95*.05/REPS):.1f} pp\n")

    print("### E1. A/A test: coverage and false alarms vs process effect (n = 15)\n")
    rows = []
    for s1 in (0.01, 0.03):
        for s2 in (0.0, 0.0025, 0.005, 0.01, 0.02):
            k, pred = predicted_coverage(s1, s2, n)
            lo, hi, r = current_full(1.0, s1, s2, n)
            lo5, hi5 = process_level(1.0, s1, s2, 5, n)
            lo10, hi10 = process_level(1.0, s1, s2, 10, n)
            rows.append([f"{100*s1:g}%", f"{100*s2:g}%", f"{k:.2f}", pct(pred),
                         pct(coverage(lo, hi, 1.0)), pct(false_alarm(lo, hi)),
                         pct(verdict_flag_rate(lo, hi, r)),
                         pct(coverage(lo5, hi5, 1.0)), pct(false_alarm(lo5, hi5)),
                         pct(coverage(lo10, hi10, 1.0)), pct(false_alarm(lo10, hi10))])
    table(["σ₁", "σ₂", "k", "predicted cov.", "current cov.", "current: interval excludes 1",
           "current: bench_press verdict flags", "P=5 cov.", "P=5 false alarm",
           "P=10 cov.", "P=10 false alarm"], rows)

    print("### E2. More trials do not fix it (σ₁ = 1%, σ₂ = 1%, A/A)\n")
    rows = []
    for nn in (5, 15, 30, 60, 120):
        k, pred = predicted_coverage(0.01, 0.01, nn)
        lo, hi, r = current_full(1.0, 0.01, 0.01, nn)
        lo5, hi5 = process_level(1.0, 0.01, 0.01, 5, nn)
        rows.append([str(nn), f"{k:.2f}", pct(coverage(lo, hi, 1.0)),
                     pct(false_alarm(lo, hi)), pct(verdict_flag_rate(lo, hi, r)),
                     pct(coverage(lo5, hi5, 1.0))])
    table(["trials n", "k", "current cov.", "current: interval excludes 1",
           "current: bench_press verdict flags", "P=5 cov."], rows)

    print("### E3. Threshold gate (process-level, P = 10, n = 15, σ₁ = σ₂ = 1%, gate 3%)\n")
    rng_e3 = np.random.default_rng(SEED + 3)   # separate stream: E4-E6 unchanged
    rows = []
    for th in (1.00, 1.01, 1.02, 1.03, 1.05, 1.10):
        v = verdicts(*process_level(th, 0.01, 0.01, 10, n))
        lo1, hi1, r1 = current_full(th, 0.01, 0.01, n, gen=rng_e3)
        today_faster, _ = bench_press_verdict(lo1, hi1, r1)
        rows.append([f"{th:.2f}", pct(today_faster.mean()), pct(v["excl1"]), pct(v["faster"]),
                     pct(v["equivalent"]), pct(v["small_real"]), pct(v["inconclusive"]),
                     pct(v["slower"])])
    table(["true θ", "today: 1 process, verdict 'Faster'", "P=10: interval excludes 1",
           "gate: faster ≥3%", "gate: equivalent", "gate: real but <3%",
           "gate: inconclusive", "gate: slower ≥3%"], rows)

    print("### E4. Power: P(gate says 'faster ≥3%') vs processes (n = 15, σ₁ = σ₂ = 1%)\n")
    rows = []
    for P in (3, 5, 10, 20):
        r = [str(P)]
        for th in (1.00, 1.03, 1.05, 1.07, 1.10):
            r.append(pct(verdicts(*process_level(th, 0.01, 0.01, P, n))["faster"]))
        rows.append(r)
    table(["P per version", "θ=1.00", "θ=1.03", "θ=1.05", "θ=1.07", "θ=1.10"], rows)

    print("### E5. Estimator check: Fieller vs percentile bootstrap on process means (A/A)\n")
    rows = []
    for P in (3, 5, 10, 20):
        lo, hi = process_level(1.0, 0.01, 0.01, P, n, reps=BOOT_REPS)
        blo, bhi = bootstrap_process(1.0, 0.01, 0.01, P, n)
        rows.append([str(P), pct(coverage(lo, hi, 1.0)), pct(coverage(blo, bhi, 1.0)),
                     f"{100*np.median(hi-lo):.2f}%", f"{100*np.median(bhi-blo):.2f}%"])
    table(["P per version", "Fieller cov.", "bootstrap cov.", "Fieller median width",
           "bootstrap median width"], rows)

    print("### E6. Budget allocation (analytic): Var(log ratio) = 2(σ₂²/P + σ₁²/(P n)), "
          "budget P(c₂ + n c₁) = C\n")
    c1, c2, C = 0.1, 2.0, 120.0
    s1, s2 = 0.01, 0.01
    n_star = np.sqrt((c2 / c1) * (s1**2 / s2**2))
    rows = []
    for nn in (1, 2, 5, 15, 50, 200):
        P = C / 2 / (c2 + nn * c1)
        se = np.sqrt(2 * (s2**2 / P + s1**2 / (P * nn)))
        rows.append([str(nn), f"{P:.1f}", f"±{100*1.96*se:.2f}%"])
    print(f"c₁ = {c1} s/batch, c₂ = {c2} s/process start+warmup, "
          f"C = {C:.0f} s total (both versions), σ₁ = σ₂ = 1% → n* = {n_star:.1f}\n")
    table(["trials per process n", "processes per version P", "≈95% half-width"], rows)

    print("### E7. Many benchmarks at once (A/A, 20 independent benchmarks)\n")
    m = 20
    rows = [["correct 5% per benchmark", "5%", f"{m*0.05:.1f}", pct(1 - 0.95**m)]]
    for s2 in (0.005, 0.01, 0.02):
        lo, hi, r = current_full(1.0, 0.01, s2, n)
        for label, fa in ((f"today, σ₂ = {100*s2:g}%: interval excludes 1", false_alarm(lo, hi)),
                          (f"today, σ₂ = {100*s2:g}%: bench_press verdict", verdict_flag_rate(lo, hi, r))):
            rows.append([label, pct(fa), f"{m*fa:.1f}", pct(1 - (1 - fa) ** m)])
    table(["per benchmark", "rate", "expected false flags / run", "P(at least one)"], rows)


if __name__ == "__main__":
    main()
