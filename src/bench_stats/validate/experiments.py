"""A4 experiments: each function runs one cell through the shipped bench_stats estimators and
returns a flat dict (one CSV row). Seeds are explicit, so every cell is reproducible on its own.
"""

import math
from collections import Counter
from dataclasses import replace

import numpy as np

from ..io import BenchmarkRecord
from ..compare import recommend_design
from ..stats.components import ar1_inflation, outlier_processes, variance_components
from ..stats.current_rule import EQUIVALENT, FASTER, INCONCLUSIVE, REGRESSION, today_verdict
from ..stats.design import gate_power
from ..stats.fieller import fieller
from ..stats.gate import Verdict, gate_interval
from ..stats.multiplicity import benjamini_hochberg
from ..stats.paired import paired_log_ratio
from ..stats.welch_log import welch_log
from .generator import MEAN_NS, ROBUSTNESS, Scenario, simulate_group, simulate_pair, simulate_version

DELTA = 0.03

_UPSTREAM = {FASTER: "faster", REGRESSION: "slower", EQUIVALENT: "equivalent", INCONCLUSIVE: "inconclusive"}


def _rng(seed: tuple[int, ...]) -> np.random.Generator:
    return np.random.default_rng(list(seed))


def _means(trials: list[np.ndarray]) -> list[float]:
    return [float(t.mean()) for t in trials]


def _covers(lower: float, upper: float, truth: float) -> bool:
    return lower <= truth <= upper


class _Acc:
    """Counts and samples for one cell."""

    def __init__(self) -> None:
        self.c: Counter[str] = Counter()
        self.v: dict[str, list[float]] = {}

    def hit(self, key: str, flag: bool = True) -> None:
        self.c[key] += bool(flag)

    def add(self, key: str, value: float) -> None:
        self.v.setdefault(key, []).append(value)

    def rate(self, key: str, n: int) -> float:
        return self.c[key] / n if n else math.nan

    def mean(self, key: str) -> float:
        xs = self.v.get(key)
        return float(np.mean(xs)) if xs else math.nan

    def median(self, key: str) -> float:
        xs = self.v.get(key)
        return float(np.median(xs)) if xs else math.nan


def _score_interval(acc: _Acc, iv, truth: float, delta: float, prefix: str = "") -> None:
    acc.hit(prefix + "bounded", iv.bounded)
    acc.hit(prefix + "covers", iv.bounded and _covers(iv.lower, iv.upper, truth))
    acc.hit(prefix + "excludes_1", iv.excludes_one)
    if iv.bounded:
        acc.add(prefix + "half_width", iv.relative_half_width)
    g = gate_interval(iv, delta)
    acc.hit(prefix + "gate_" + g.verdict.name.lower())
    acc.hit(prefix + "gate_no_change_detectable", g.verdict == Verdict.NO_CHANGE and g.detectable)


def _interval_columns(acc: _Acc, reps: int, prefix: str = "") -> dict[str, float]:
    keys = ["bounded", "covers", "excludes_1", "gate_faster", "gate_slower", "gate_no_change",
            "gate_no_change_detectable", "gate_inconclusive"]
    row = {prefix + k: acc.rate(prefix + k, reps) for k in keys}
    row[prefix + "median_half_width"] = acc.median(prefix + "half_width")
    return row


def _components_columns(acc: _Acc) -> dict[str, float]:
    return {
        "sigma1_hat": acc.mean("s1"),
        "sigma2_hat": acc.mean("s2"),
        "sigma2_iid_hat": acc.mean("s2_iid"),
        "sigma2_drift_hat": acc.mean("s2_drift"),
        "upstream_share_hat": acc.mean("share"),
        "rho_hat": acc.mean("rho"),
        "components_reps": len(acc.v.get("s2", [])),
    }


def _score_components(acc: _Acc, trials: list[np.ndarray]) -> None:
    vc = variance_components(trials, n_boot=0)
    acc.add("s1", vc.sigma1)
    acc.add("s2", vc.sigma2)
    acc.add("s2_iid", vc.sigma2_iid)
    acc.add("s2_drift", vc.sigma2_drift)
    acc.add("share", vc.upstream_share)
    acc.add("rho", vc.rho)


def grid_cell(P, sigma1, sigma2, theta, reps, seed, n=16, delta=DELTA, components_reps=1000) -> dict:
    """The normal model: our interval and gate, a log-scale cross-check, and bench_press's rules."""
    rng = _rng(seed)
    s = Scenario(sigma1=sigma1, sigma2=sigma2, n=n)
    truth = s.true_ratio(theta)
    acc = _Acc()
    for r in range(reps):
        b, c = simulate_pair(rng, s, P, theta)
        mb, mc = _means(b), _means(c)
        _score_interval(acc, fieller(mb, mc), truth, delta)
        wl = welch_log(mb, mc)
        acc.hit("welch_log_covers", wl.bounded and _covers(wl.lower, wl.upper, theta))

        # bench_press today: one process per version, batch-level samples.
        t0 = today_verdict(list(b[0]), list(c[0]), 0.0)
        acc.hit("today_covers", t0.resolved and _covers(t0.lower, t0.upper, truth))
        acc.hit("today_excludes_1", t0.resolved and not _covers(t0.lower, t0.upper, 1.0))
        acc.hit("today_faster", t0.direction == 1)
        acc.hit("today_slower", t0.direction == -1)
        t1 = today_verdict(list(b[0]), list(c[0]), delta)
        acc.hit("today_threshold_" + _UPSTREAM.get(t1.status, "unresolved"))
        if P > 1:
            up = today_verdict(mb, mc, delta)
            acc.hit("upstream_P_" + _UPSTREAM.get(up.status, "unresolved"))
        if theta == 1.0 and P >= 2 and r < components_reps:
            _score_components(acc, b)

    row = {"P": P, "sigma1": sigma1, "sigma2": sigma2, "theta": theta, "n": n, "reps": reps, "truth": truth}
    row |= _interval_columns(acc, reps)
    row["welch_log_covers"] = acc.rate("welch_log_covers", reps)
    for k in ("today_covers", "today_excludes_1", "today_faster", "today_slower"):
        row[k] = acc.rate(k, reps)
    for label in ("faster", "slower", "equivalent", "inconclusive"):
        row[f"today_threshold_{label}"] = acc.rate(f"today_threshold_{label}", reps)
        row[f"upstream_P_{label}"] = acc.rate(f"upstream_P_{label}", reps) if P > 1 else math.nan
    if theta == 1.0 and P >= 2:
        row |= _components_columns(acc)
    return row


def robust_cell(scenario, P, theta, reps, seed, delta=DELTA, components_reps=500) -> dict:
    """A robustness scenario: our interval and gate, outlier flags, and σ̂ bias."""
    rng = _rng(seed)
    s = ROBUSTNESS[scenario]
    truth = s.true_ratio(theta)
    acc = _Acc()
    for r in range(reps):
        b, c = simulate_pair(rng, s, P, theta)
        mb, mc = _means(b), _means(c)
        _score_interval(acc, fieller(mb, mc), truth, delta)
        flagged = outlier_processes(mb)
        acc.hit("outlier_flag_any", len(flagged) > 0)
        acc.hit("outlier_flag_true", s.outlier != 0 and (P // 2) in flagged)
        if r < components_reps and P >= 2:
            _score_components(acc, b)
    row = {"scenario": scenario, "P": P, "theta": theta, "reps": reps, "truth": truth, "sigma2_true": s.sigma2}
    row |= _interval_columns(acc, reps)
    row["outlier_flag_any"] = acc.rate("outlier_flag_any", reps)
    row["outlier_flag_true"] = acc.rate("outlier_flag_true", reps) if s.outlier else math.nan
    row |= _components_columns(acc)
    return row


def group_cell(P, theta, sigma_shared, reps, seed, sigma_variant=0.0025, delta=DELTA) -> dict:
    """Group mode: paired Fieller (shipped default), paired log-ratio t, and unpaired Fieller."""
    rng = _rng(seed)
    acc = _Acc()
    for _ in range(reps):
        b, c = simulate_group(rng, P, theta, sigma_shared, sigma_variant)
        mb, mc = _means(b), _means(c)
        _score_interval(acc, fieller(mb, mc, paired=True), theta, delta, "paired_")
        _score_interval(acc, fieller(mb, mc), theta, delta, "unpaired_")
        pl = paired_log_ratio(mb, mc)
        acc.hit("paired_log_covers", pl.bounded and _covers(pl.lower, pl.upper, theta))
    row = {"P": P, "theta": theta, "sigma_shared": sigma_shared, "sigma_variant": sigma_variant, "reps": reps}
    row |= _interval_columns(acc, reps, "paired_") | _interval_columns(acc, reps, "unpaired_")
    row["paired_log_covers"] = acc.rate("paired_log_covers", reps)
    return row


SUITE_MIXES: dict[str, list[float]] = {
    "all null": [1.0] * 20,
    "2 at +5%": [1.05] * 2 + [1.0] * 18,
    "5 at +5%": [1.05] * 5 + [1.0] * 15,
    "5 at +2%": [1.02] * 5 + [1.0] * 15,
}


def suite_chunk(mix, reps, seed, P=10, q=0.05, delta=DELTA) -> dict:
    """20-benchmark suites: false "≥ δ" gate claims, and the "detectable" label with and without BH."""
    rng = _rng(seed)
    thetas = np.array(SUITE_MIXES[mix])
    null = thetas == 1.0
    s = Scenario()
    acc = Counter()
    for _ in range(reps):
        p_values, false_claims, detect = [], 0, []
        for theta in thetas:
            b, c = simulate_pair(rng, s, P, float(theta))
            iv = fieller(_means(b), _means(c))
            p_values.append(iv.p_value)
            detect.append(iv.excludes_one)
            v = gate_interval(iv, delta).verdict
            false_claims += (v == Verdict.FASTER and theta < 1 + delta) or (v == Verdict.SLOWER and theta > 1 / (1 + delta))
        detect = np.array(detect)
        bh, _ = benjamini_hochberg(p_values, q)
        for label, flags in (("raw", detect), ("bh", bh)):
            false = int((flags & null).sum())
            true = int((flags & ~null).sum())
            acc[f"{label}_false"] += false
            acc[f"{label}_true"] += true
            acc[f"{label}_fdp"] += false / max(1, false + true)
            acc[f"{label}_any_false"] += false > 0
        acc["gate_false_claims"] += false_claims
    return {"mix": mix, "reps": reps, "effects": int((~null).sum())} | dict(acc)


DESIGN_TRUTHS: dict[str, tuple[Scenario, float, float]] = {
    "pilot-like (σ₁ 1.5%, σ₂ 1.2%, ρ 0.45)": (Scenario(sigma1=0.015, sigma2=0.012, rho=0.45), 0.10, 2.4),
    "σ₁ = σ₂ = 1%": (Scenario(sigma1=0.01, sigma2=0.01), 0.10, 2.0),
    "small σ₂ (σ₁ 1%, σ₂ 0.3%)": (Scenario(sigma1=0.01, sigma2=0.003), 0.10, 2.0),
    "noisy trials (σ₁ 3%, σ₂ 1%)": (Scenario(sigma1=0.03, sigma2=0.01), 0.10, 2.0),
}


DESIGN_VARIANTS: dict[str, dict] = {
    "shipped": {},
    "point": {"min_processes": 2},
    "conservative": {"conservative": True},
}
"""shipped: recommend_design defaults (σ̂₂ as estimated, ≥ 5 processes). point: no floor (tests the
formula alone). conservative: upper end of σ₂'s interval, ≥ 5 processes (the A3 default)."""


def _record(trials: list[np.ndarray], c1: float, c2: float) -> BenchmarkRecord:
    trials = tuple(np.asarray(t) for t in trials)
    means = tuple(float(t.mean()) for t in trials)
    return BenchmarkRecord(
        name="pilot", target="aot", coordinates={}, is_baseline=False, process_trials=trials,
        process_means_ns=means, raw_trials_ns=tuple(float(x) for t in trials for x in t), is_stable=True,
        warmup_stable=True, mean_ns=float(np.mean(means)),
        calibrated_batch_iterations=max(1, round(c1 / (MEAN_NS * 1e-9))),
        warmup={"is_stable": True, "elapsed_seconds": c2 * len(trials)},
    )


def design_chunk(truth, pilots, seed, theta=1.06, delta=DELTA, power=0.8, pilot_P=10, exp_reps=400) -> list[dict]:
    """Pilot → recommend_design → run the recommended experiment → achieved gate power."""
    rng = _rng(seed)
    s, c1, c2 = DESIGN_TRUTHS[truth]
    rows = []
    for i in range(pilots):
        trials = simulate_version(rng, s, pilot_P)
        vc = variance_components(trials, n_boot=300, seed=int(rng.integers(2**31)))
        rec = _record(trials, c1, c2)
        row = {"truth": truth, "pilot": i}
        for label, kwargs in DESIGN_VARIANTS.items():
            hint = recommend_design(rec, vc, delta, theta=theta, power=power, **kwargs)
            P = min(hint.processes_per_version or 200, 200)
            exp = replace(s, n=hint.trials_per_process)
            faster = 0
            for _ in range(exp_reps):
                b, c = simulate_pair(rng, exp, P, theta)
                faster += gate_interval(fieller(_means(b), _means(c)), delta).verdict == Verdict.FASTER
            row |= {
                f"{label}_n": hint.trials_per_process,
                f"{label}_P": P,
                f"{label}_promised": hint.power,
                f"{label}_achieved": faster / exp_reps,
                f"{label}_cost_s": 2 * P * (c2 + hint.trials_per_process * c1),
            }
        rows.append(row)
    return rows


def power_cell(P, theta, sigma1, sigma2, rho, reps, seed, n=16, delta=DELTA) -> dict:
    """Simulated gate power vs design.gate_power (calibration of the 1.5(P - 1) effective df)."""
    rng = _rng(seed)
    s = Scenario(sigma1=sigma1, sigma2=sigma2, rho=rho, n=n)
    faster = 0
    for _ in range(reps):
        b, c = simulate_pair(rng, s, P, theta)
        faster += gate_interval(fieller(_means(b), _means(c)), delta).verdict == Verdict.FASTER
    f = float(ar1_inflation(rho, n))
    return {
        "P": P, "theta": theta, "sigma1": sigma1, "sigma2": sigma2, "rho": rho, "reps": reps,
        "simulated": faster / reps, "analytic": gate_power(P, n, sigma1, sigma2, theta, delta, f=f),
    }


def ci_cell(P, sigma2, rho, reps, seed, sigma1=0.01, n=16, n_boot=400) -> dict:
    """Coverage of components.py's parametric-bootstrap intervals for σ₁, σ₂ and k."""
    rng = _rng(seed)
    s = Scenario(sigma1=sigma1, sigma2=sigma2, rho=rho, n=n)
    f = float(ar1_inflation(rho, n))
    k_true = math.sqrt(f + n * sigma2**2 / sigma1**2)
    acc = Counter()
    for _ in range(reps):
        vc = variance_components(simulate_version(rng, s, P), n_boot=n_boot, seed=int(rng.integers(2**31)))
        acc["s1"] += _covers(*vc.sigma1_ci, sigma1)
        acc["s2"] += _covers(*vc.sigma2_ci, sigma2)
        acc["k"] += _covers(*vc.k_ci, k_true)
    return {"P": P, "sigma2": sigma2, "rho": rho, "reps": reps} | {f"covers_{k}": v / reps for k, v in acc.items()}


def outlier_cell(P, shift_sd, reps, seed) -> dict:
    """Detection of one outlier process by the generalized ESD test, by size in process SDs."""
    rng = _rng(seed)
    base = Scenario()
    s = replace(base, outlier=shift_sd * base.process_sd)
    hit = false = 0
    for _ in range(reps):
        b, _ = simulate_pair(rng, s, P, 1.0)
        flagged = outlier_processes(_means(b))
        hit += (P // 2) in flagged
        false += any(i != P // 2 for i in flagged)
    return {"P": P, "shift_process_sd": shift_sd, "reps": reps, "detected": hit / reps, "other_flagged": false / reps}
