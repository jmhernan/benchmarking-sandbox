"""Synthetic bench_press-like runs with known truth (plan A4).

Every version is P processes × n trials. Trial times are multiplicative:

    x = mean · exp(a_p + drift · launch_p) · within_pj

- a_p: process effect, normal(0, σ₂) or bimodal ±σ₂ ("good" and "bad" layouts);
- launch_p: launch index. Interleaved runs follow bench_press's `ABBA BAAB` rounds; sequential runs
  launch every baseline process before any candidate process (like `--diff` against a stored run);
- within_pj: trial noise, normal on the log scale or Student t (ν = 3) on the relative scale, AR(1)
  across trials, times optional lognormal spikes and slow episodes (a sharp jump that decays over a
  few trials, the trial-level counterpart of sandbox/synth.py's iteration-level episodes).

Baseline and candidate share every distribution except the mean (candidate = baseline / θ), the
process-effect SD (`candidate_sigma2_scale`) and the process count (`candidate_missing`), so the
ratio of expected process means is known exactly: `Scenario.true_ratio(θ)`.
"""

import math
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

MEAN_NS = 100_000.0


@dataclass(frozen=True)
class Scenario:
    name: str = "normal"
    sigma1: float = 0.01
    sigma2: float = 0.01
    n: int = 16
    rho: float = 0.0
    noise: Literal["normal", "t3"] = "normal"
    spike_rate: float = 0.0
    spike_median: float = 0.3
    episode_rate: float = 0.0
    episode_median: float = 0.05
    episode_tau: float = 2.0
    process: Literal["normal", "bimodal"] = "normal"
    outlier: float = 0.0
    candidate_sigma2_scale: float = 1.0
    candidate_missing: int = 0
    drift: float = 0.0
    sessions: Literal["interleaved", "sequential"] = "interleaved"

    def _process_mean_factor(self, sigma2: float) -> float:
        return math.cosh(sigma2) if self.process == "bimodal" else math.exp(sigma2**2 / 2)

    def true_ratio(self, theta: float) -> float:
        """Ratio of expected process means, baseline / candidate (the Fieller estimand).

        Excludes contamination (`outlier`) and launch drift, which are departures from the model
        that the estimator should survive, not part of what it estimates.
        """
        s2c = self.sigma2 * self.candidate_sigma2_scale
        return theta * self._process_mean_factor(self.sigma2) / self._process_mean_factor(s2c)

    @property
    def process_sd(self) -> float:
        """SD of one process's log mean under the normal model (for scaling outliers)."""
        k = np.arange(1, self.n)
        f = 1 + 2 * np.sum((1 - k / self.n) * self.rho**k)
        return math.sqrt(self.sigma2**2 + f * self.sigma1**2 / self.n)


def _launch_indices(P_b: int, P_c: int, sessions: str) -> tuple[np.ndarray, np.ndarray]:
    if sessions == "sequential":
        return np.arange(P_b), P_b + np.arange(P_c)
    lb, lc, L = [], [], 0
    for p in range(max(P_b, P_c)):
        reverse = (p & 1) != ((p >> 1) & 1)
        for side in ("c", "b") if reverse else ("b", "c"):
            if side == "b" and p < P_b:
                lb.append(L)
                L += 1
            elif side == "c" and p < P_c:
                lc.append(L)
                L += 1
    return np.array(lb), np.array(lc)


def _within(rng: np.random.Generator, s: Scenario, P: int) -> np.ndarray:
    n = s.n
    e = rng.standard_t(3, (P, n)) / math.sqrt(3) if s.noise == "t3" else rng.standard_normal((P, n))
    if s.rho:
        z = np.empty_like(e)
        z[:, 0] = e[:, 0]
        innov = math.sqrt(1 - s.rho**2)
        for j in range(1, n):
            z[:, j] = s.rho * z[:, j - 1] + innov * e[:, j]
        e = z
    factor = np.exp(s.sigma1 * e) if s.noise == "normal" else np.clip(1 + s.sigma1 * e, 0.5, None)
    if s.spike_rate:
        hit = rng.random((P, n)) < s.spike_rate
        factor = factor * (1 + hit * rng.lognormal(math.log(s.spike_median), 0.5, (P, n)))
    if s.episode_rate:
        t = np.arange(n)
        excess = np.zeros((P, n))
        for p, j in zip(*np.nonzero(rng.random((P, n)) < s.episode_rate)):
            amp = rng.lognormal(math.log(s.episode_median), 0.35)
            bump = np.where(t >= j, amp * np.exp(-(t - j) / s.episode_tau), 0.0)
            excess[p] = np.maximum(excess[p], bump)
        factor = factor * (1 + excess)
    return factor


def _process_effects(rng: np.random.Generator, s: Scenario, P: int, sigma2: float) -> np.ndarray:
    if s.process == "bimodal":
        return sigma2 * rng.choice([-1.0, 1.0], P)
    return sigma2 * rng.standard_normal(P)


def simulate_pair(
    rng: np.random.Generator, s: Scenario, P: int, theta: float, mean: float = MEAN_NS
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Baseline and candidate per-process trial arrays (ns per operation)."""
    P_c = max(1, P - s.candidate_missing)
    lb, lc = _launch_indices(P, P_c, s.sessions)
    a_b = _process_effects(rng, s, P, s.sigma2) + s.drift * lb
    a_c = _process_effects(rng, s, P_c, s.sigma2 * s.candidate_sigma2_scale) + s.drift * lc
    if s.outlier:
        a_b[P // 2] += s.outlier
    base = mean * np.exp(a_b)[:, None] * _within(rng, s, P)
    cand = (mean / theta) * np.exp(a_c)[:, None] * _within(rng, s, P_c)
    return list(base), list(cand)


def simulate_version(rng: np.random.Generator, s: Scenario, P: int, mean: float = MEAN_NS) -> list[np.ndarray]:
    """One version on its own (a pilot run)."""
    a = _process_effects(rng, s, P, s.sigma2) + s.drift * np.arange(P)
    return list(mean * np.exp(a)[:, None] * _within(rng, s, P))


def simulate_group(
    rng: np.random.Generator, P: int, theta: float, sigma_shared: float, sigma_variant: float,
    sigma1: float = 0.01, n: int = 16, mean: float = MEAN_NS,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Group mode: both variants run inside the same P processes, so they share each process's
    offset (sigma_shared) and differ by a variant-specific one (sigma_variant)."""
    shared = sigma_shared * rng.standard_normal(P)
    s = Scenario(sigma1=sigma1, n=n)
    base = mean * np.exp(shared + sigma_variant * rng.standard_normal(P))[:, None] * _within(rng, s, P)
    cand = (mean / theta) * np.exp(shared + sigma_variant * rng.standard_normal(P))[:, None] * _within(rng, s, P)
    return list(base), list(cand)


NORMAL = Scenario()

ROBUSTNESS: dict[str, Scenario] = {
    s.name: s
    for s in [
        NORMAL,
        replace(NORMAL, name="t3 trial noise", noise="t3"),
        replace(NORMAL, name="lognormal spikes", spike_rate=0.05),
        replace(NORMAL, name="AR(1) trials, rho 0.6", rho=0.6),
        replace(NORMAL, name="slow episodes", episode_rate=0.04),
        replace(NORMAL, name="bimodal process effects", process="bimodal"),
        replace(NORMAL, name="one outlier process (+5%)", outlier=0.05),
        replace(NORMAL, name="unequal sigma2 (candidate 2x)", candidate_sigma2_scale=2.0),
        replace(NORMAL, name="one candidate process missing", candidate_missing=1),
        replace(NORMAL, name="launch drift, interleaved", drift=0.001),
        replace(NORMAL, name="launch drift, separate sessions", drift=0.001, sessions="sequential"),
    ]
}
"""Robustness scenarios at σ₁ = σ₂ = 1%, n = 16. Drift is 0.1% per launch, about the pilot's
2–4% over 40 launches; spikes hit 5% of trials (+30% median); episodes start in 4% of trials."""
