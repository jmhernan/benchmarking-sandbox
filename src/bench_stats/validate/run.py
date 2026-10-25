"""Run the A4 simulation validation.

    python -m bench_stats.validate                 # full run, ~1 min on 16 cores
    python -m bench_stats.validate --quick         # 1/20 of the replications, for a smoke test
    python -m bench_stats.validate --only grid suite --out /tmp/a4

Writes one CSV per experiment, `run_info.json`, and `summary.md` (the plan's A.4 acceptance
criteria checked against the results) to `--out` (default sandbox/output/a4).
"""

import argparse
import csv
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .. import __version__
from . import experiments as ex
from .generator import ROBUSTNESS
from .summary import render_summary

BASE_SEED = 20261025


def _tasks(scale: float) -> dict[str, list[tuple]]:
    def reps(n: int) -> int:
        return max(20, round(n * scale))

    t: dict[str, list[tuple]] = {k: [] for k in ("grid", "robust", "group", "suite", "design", "power", "ci", "outlier")}
    for P in (2, 3, 5, 10, 20):
        for s2 in (0.0, 0.0025, 0.005, 0.01, 0.02):
            for s1 in (0.01, 0.03):
                for theta in (1.00, 1.01, 1.02, 1.03, 1.05, 1.10):
                    t["grid"].append((ex.grid_cell, dict(P=P, sigma1=s1, sigma2=s2, theta=theta, reps=reps(4000),
                                                         components_reps=reps(1000))))
    for name in ROBUSTNESS:
        for P in (3, 5, 10, 20):
            for theta in (1.00, 1.05):
                t["robust"].append((ex.robust_cell, dict(scenario=name, P=P, theta=theta, reps=reps(4000),
                                                         components_reps=reps(500))))
    for P in (3, 5, 10, 20):
        for theta in (1.00, 1.05):
            for shared in (0.0, 0.01):
                t["group"].append((ex.group_cell, dict(P=P, theta=theta, sigma_shared=shared, reps=reps(4000))))
    for mix in ex.SUITE_MIXES:
        for _ in range(20):
            t["suite"].append((ex.suite_chunk, dict(mix=mix, reps=reps(100))))
    for truth in ex.DESIGN_TRUTHS:
        for _ in range(20):
            t["design"].append((ex.design_chunk, dict(truth=truth, pilots=max(1, round(10 * scale)),
                                                      exp_reps=reps(400))))
    for P in (3, 5, 10, 20):
        for theta in (1.04, 1.05, 1.07):
            for s1, s2 in ((0.01, 0.01), (0.01, 0.0025), (0.03, 0.01)):
                for rho in (0.0, 0.5):
                    t["power"].append((ex.power_cell, dict(P=P, theta=theta, sigma1=s1, sigma2=s2, rho=rho,
                                                           reps=reps(4000))))
    for P in (5, 10, 20):
        for s2 in (0.0, 0.005, 0.01):
            for rho in (0.0, 0.5):
                t["ci"].append((ex.ci_cell, dict(P=P, sigma2=s2, rho=rho, reps=reps(400))))
    for P in (5, 10, 20, 40):
        for shift in (3, 5, 8, 12):
            t["outlier"].append((ex.outlier_cell, dict(P=P, shift_sd=shift, reps=reps(20000))))
    return t


def _run_one(job: tuple) -> list[dict]:
    fn, kwargs, seed = job
    out = fn(seed=seed, **kwargs)
    return out if isinstance(out, list) else [out]


def _write_csv(path: Path, rows: list[dict]) -> None:
    keys: list[str] = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def run(out: Path, scale: float = 1.0, only: list[str] | None = None, workers: int | None = None,
        seed: int = BASE_SEED) -> dict[str, list[dict]]:
    tasks = _tasks(scale)
    names = [k for k in tasks if not only or k in only]
    jobs, owners = [], []
    for e_idx, name in enumerate(tasks):
        if name not in names:
            continue
        for t_idx, (fn, kwargs) in enumerate(tasks[name]):
            jobs.append((fn, kwargs, (seed, e_idx, t_idx)))
            owners.append(name)
    results: dict[str, list[dict]] = {k: [] for k in names}
    start = time.time()
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
        for name, rows in zip(owners, pool.map(_run_one, jobs, chunksize=1)):
            results[name] += rows
    elapsed = time.time() - start

    out.mkdir(parents=True, exist_ok=True)
    for name, rows in results.items():
        _write_csv(out / f"{name}.csv", rows)
    info = {"bench_stats_version": __version__, "seed": seed, "scale": scale, "experiments": names,
            "tasks": len(jobs), "seconds": round(elapsed, 1)}
    (out / "run_info.json").write_text(json.dumps(info, indent=2) + "\n")
    (out / "summary.md").write_text(render_summary(results, info), encoding="utf-8")
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m bench_stats.validate", description=__doc__.split("\n\n")[0])
    p.add_argument("--out", type=Path, default=Path("sandbox/output/a4"))
    p.add_argument("--quick", action="store_true", help="1/20 of the replications (smoke test)")
    p.add_argument("--scale", type=float, default=None, help="multiply all replication counts")
    p.add_argument("--only", nargs="+", choices=["grid", "robust", "group", "suite", "design", "power", "ci", "outlier"])
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--seed", type=int, default=BASE_SEED)
    args = p.parse_args(argv)
    scale = args.scale if args.scale is not None else (0.05 if args.quick else 1.0)
    run(args.out, scale, args.only, args.workers, args.seed)
    print(f"wrote {args.out}/summary.md")
    return 0
