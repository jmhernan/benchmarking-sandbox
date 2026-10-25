import numpy as np

from bench_stats.io import BenchmarkRecord


def ar1_trials(rng, P, n, sigma1, rho=0.0, sigma2=0.0, mean=1000.0, drift=0.0):
    """P processes × n trials, log-normal: process offset sigma2, AR(1) trials with SD sigma1, optional linear drift."""
    e = np.empty((P, n))
    e[:, 0] = rng.standard_normal(P)
    for j in range(1, n):
        e[:, j] = rho * e[:, j - 1] + np.sqrt(1 - rho**2) * rng.standard_normal(P)
    offsets = sigma2 * rng.standard_normal((P, 1)) + drift * np.arange(P)[:, None]
    return mean * np.exp(offsets + sigma1 * e)


def make_record(trials, name="bench", stable=True, coordinates=None, is_baseline=False, batch=100, warmup_seconds=None):
    trials = tuple(np.asarray(t, float) for t in trials)
    means = tuple(float(t.mean()) for t in trials)
    raw = tuple(float(x) for t in trials for x in t)
    P = len(trials)
    mean_ns = float(np.mean(means)) if P > 1 else float(np.mean(raw))
    warmup = {"is_stable": stable}
    if warmup_seconds is not None:
        warmup["elapsed_seconds"] = warmup_seconds * P
    return BenchmarkRecord(
        name=name,
        target="aot",
        coordinates=dict(coordinates or {}),
        is_baseline=is_baseline,
        process_trials=trials,
        process_means_ns=means if P > 1 else (),
        raw_trials_ns=raw,
        is_stable=stable,
        warmup_stable=stable,
        mean_ns=mean_ns,
        calibrated_batch_iterations=batch,
        warmup=warmup,
    )
