"""Throwaway feasibility check for the grid posterior in docs/plan.md §B.2 (results in §B.2a; the plan is local, git-ignored).

A/A (theta = 1), sigma1 = sigma2 = 1%, n = 15, 500 reps per row.
Run: python sandbox/spikes/bayes_grid_spike.py   (perfBench env; ~1-2 min)
Superseded by src/bench_stats/bayes/grid.py once milestone B1 is built.
"""
import numpy as np
from scipy import stats
rng = np.random.default_rng(7)
s1, s2, n, reps = 0.01, 0.01, 15, 2000
g1 = np.exp(np.linspace(np.log(1e-3), np.log(0.2), 80))
g2 = np.exp(np.linspace(np.log(1e-4), np.log(0.2), 120))
S1, S2 = np.meshgrid(g1, g2, indexing="ij")
def posterior(y_b, y_c, logprior2):
    P = y_b.shape[0]
    mb, mc = y_b.mean(1), y_c.mean(1)
    W = ((y_b - mb[:, None])**2).sum() + ((y_c - mc[:, None])**2).sum()
    Sb = ((mb - mb.mean())**2).sum() + ((mc - mc.mean())**2).sum()
    dfw, dfb = 2*P*(n-1), 2*(P-1)
    tau2 = S2**2 + S1**2/n
    logw = (-dfw*np.log(S1) - W/(2*S1**2) - dfb/2*np.log(tau2) - Sb/(2*tau2)
            + logprior2(S2) - np.log(S1) * 0)  # flat in log s1 (grid is log-spaced)
    w = np.exp(logw - logw.max()); w /= w.sum()
    D = mc.mean() - mb.mean(); sd = np.sqrt(2*tau2/P)
    # mixture quantiles by bisection on CDF
    def cdf(x): return (w*stats.norm.cdf((x-D)/sd)).sum()
    def q(p):
        lo, hi = D-1, D+1
        for _ in range(60):
            mid = (lo+hi)/2
            lo, hi = (mid, hi) if cdf(mid) < p else (lo, mid)
        return mid
    return q(0.025), q(0.975)
priors = {
  "informative (correct)": lambda s: stats.norm.logpdf(np.log(s), np.log(0.01), 0.3),
  "informative (2x too small)": lambda s: stats.norm.logpdf(np.log(s), np.log(0.005), 0.3),
  "weak half-normal(5%)": lambda s: stats.halfnorm.logpdf(s, scale=0.05) + np.log(s),
}
for P in (3, 5):
    for name, pr in priors.items():
        cov, wid = 0, []
        for _ in range(reps // 4):
            def proc():
                a = s2*rng.standard_normal((P, 1))
                return a + np.log1p(s1*rng.standard_normal((P, n)))
            lo, hi = posterior(proc(), proc(), pr)
            cov += lo <= 0 <= hi; wid.append(hi - lo)
        print(f"P={P} {name:28s} cov={cov/(reps//4):.3f} median width={100*np.median(wid):.2f}%")
