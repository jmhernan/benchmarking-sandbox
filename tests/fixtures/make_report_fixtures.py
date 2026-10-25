"""Generate the two bench_press-shaped run files used by the report golden tests.

    python tests/fixtures/make_report_fixtures.py

The files mimic `bench_press run --processes 6 -o …` output (schema version 1) for a synthetic suite
with known effects. Only the fields bench_stats reads are filled in. Rerun only if the scenarios
change, then regenerate the goldens (see tests/test_report.py).
"""

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
MEAN_NS = 100_000.0
BATCH = 1000
WARMUP_S = 2.0

# name: (true speedup θ, processes, sigma1, sigma2, drift per launch, stable)
SCENARIOS = {
    "same": (1.00, 6, 0.01, 0.005, 0.0, True),
    "faster": (1.10, 6, 0.01, 0.005, 0.0, True),
    "slower": (0.93, 6, 0.01, 0.005, 0.0, True),
    "small": (1.015, 8, 0.004, 0.001, 0.0, True),
    "noisy": (1.00, 6, 0.01, 0.04, 0.0, True),
    "single": (1.00, 1, 0.01, 0.005, 0.0, True),
    "unstable": (1.00, 6, 0.01, 0.005, 0.0, False),
    "drifting": (1.00, 8, 0.01, 0.002, 0.004, True),
}


def _entry(rng, name, mean, P, s1, s2, drift, stable, n=12):
    offsets = s2 * rng.standard_normal(P) + drift * np.arange(P)
    trials = [mean * np.exp(o + s1 * rng.standard_normal(n)) for o in offsets]
    raw = [float(x) for t in trials for x in t]
    entry = {
        "name": name,
        "target": "aot",
        "mode": "sync",
        "samples": len(raw),
        "metrics": {
            "mean_ns": float(np.mean([t.mean() for t in trials])),
            "is_stable": stable,
        },
        "raw_trials_ns": raw,
        "warmup": {"is_stable": stable, "elapsed_seconds": WARMUP_S * P},
        "calibrated_batch_iterations": BATCH,
    }
    if P > 1:
        entry["processes"] = P
        entry["process_means_ns"] = [float(t.mean()) for t in trials]
        entry["process_trials_ns"] = [[float(x) for x in t] for t in trials]
    return entry


def _run(entries):
    return {
        "version": 1,
        "timestamp": "2026-10-25T00:00:00.000Z",
        "environment": {"dart_version": "3.13.7 (stable) (fixture)", "os": "macos", "arch": "arm64"},
        "benchmarks": entries,
    }


def main():
    rng = np.random.default_rng(2026)
    base, cand = [], []
    for name, (theta, P, s1, s2, drift, stable) in SCENARIOS.items():
        base.append(_entry(rng, name, MEAN_NS, P, s1, s2, drift, stable))
        cand.append(_entry(rng, name, MEAN_NS / theta, P, s1, s2, drift, True))
    base.append(_entry(rng, "retired", MEAN_NS, 6, 0.01, 0.005, 0.0, True))
    cand.append(_entry(rng, "new", MEAN_NS, 6, 0.01, 0.005, 0.0, True))
    for label, entries in (("baseline", base), ("candidate", cand)):
        (HERE / f"report_{label}.json").write_text(json.dumps(_run(entries), indent=1) + "\n")


if __name__ == "__main__":
    main()
