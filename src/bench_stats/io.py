"""Load bench_press run JSON (`bench_press run -o …`, schema version 1, bench_press 5fd6396) and
`bench-stats run` files (JSONL: a header, then one record per process holding that process's bench_press JSON)."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

Reduce = Literal["mean", "median"]

RUNNER_SCHEMA = "bench-stats-run"
RUNNER_SCHEMA_VERSION = 1
RUNNER_LABELS = ("baseline", "candidate")


@dataclass(frozen=True)
class BenchmarkRecord:
    """One benchmark cell (name × target × coordinates) from a bench_press run."""

    name: str
    target: str
    coordinates: dict[str, str]
    is_baseline: bool
    process_trials: tuple[np.ndarray, ...]
    process_means_ns: tuple[float, ...]
    raw_trials_ns: tuple[float, ...]
    is_stable: bool
    warmup_stable: bool | None
    mean_ns: float
    calibrated_batch_iterations: int | None
    warmup: dict[str, Any] = field(default_factory=dict)
    upstream_components: dict[str, Any] | None = None

    @property
    def processes(self) -> int:
        return len(self.process_trials)

    @property
    def key(self) -> str:
        """bench_press's `BenchmarkEntry.key`."""
        if not self.coordinates:
            return f"{self.name}:{self.target}"
        coords = ",".join(f"{k}={v}" for k, v in sorted(self.coordinates.items()))
        return f"{self.name}:{self.target}:{coords}"

    @property
    def group(self) -> str | None:
        return self.coordinates.get("group")

    @property
    def mean_trials(self) -> float:
        return float(np.mean([len(t) for t in self.process_trials]))

    def process_values(self, reduce: Reduce = "mean") -> np.ndarray:
        """One value per process: the mean (default) or median of its trials, in ns per operation."""
        fn = np.mean if reduce == "mean" else np.median
        return np.array([fn(t) for t in self.process_trials])

    def bench_press_samples(self) -> list[float]:
        """What bench_press feeds into Fieller: process means when P > 1, raw trials when P = 1."""
        if self.processes > 1:
            return list(self.process_means_ns)
        return list(self.raw_trials_ns)

    def trial_seconds(self) -> float | None:
        """Approximate cost of one trial (a calibrated batch), c1 in the design formulas."""
        if not self.calibrated_batch_iterations:
            return None
        return self.calibrated_batch_iterations * self.mean_ns * 1e-9

    def process_overhead_seconds(self) -> float | None:
        """Warmup and calibration time per process, a lower bound on c2 (process startup is not recorded)."""
        elapsed = self.warmup.get("elapsed_seconds")
        if not elapsed:
            return None
        return float(elapsed) / self.processes


@dataclass(frozen=True)
class Run:
    path: Path
    version: int
    timestamp: str
    environment: dict[str, Any]
    records: tuple[BenchmarkRecord, ...]
    meta: dict[str, Any] = field(default_factory=dict)

    def by_key(self) -> dict[str, BenchmarkRecord]:
        return {r.key: r for r in self.records}


def _record(b: dict[str, Any]) -> BenchmarkRecord:
    raw = tuple(float(x) for x in b.get("raw_trials_ns", ()))
    processes = int(b.get("processes", 1))
    if processes > 1 and b.get("process_trials_ns"):
        trials = tuple(np.asarray(p, float) for p in b["process_trials_ns"])
    elif processes > 1 and b.get("process_means_ns"):
        trials = tuple(np.array([float(m)]) for m in b["process_means_ns"])
    else:
        trials = (np.asarray(raw, float),)
    means = tuple(float(x) for x in b.get("process_means_ns", ())) or tuple(float(t.mean()) for t in trials)
    warmup = b.get("warmup") or {}
    metrics = b["metrics"]
    return BenchmarkRecord(
        name=b["name"],
        target=b["target"],
        coordinates=dict(b.get("coordinates") or {}),
        is_baseline=bool(b.get("is_baseline", False)),
        process_trials=trials,
        process_means_ns=means,
        raw_trials_ns=raw,
        is_stable=bool(metrics.get("is_stable", True)),
        warmup_stable=warmup.get("is_stable"),
        mean_ns=float(metrics["mean_ns"]),
        calibrated_batch_iterations=b.get("calibrated_batch_iterations"),
        warmup=dict(warmup),
        upstream_components=metrics.get("variance_components"),
    )


def load_run(path: str | Path) -> Run:
    path = Path(path)
    data = json.loads(path.read_text())
    version = int(data.get("version", 0))
    if version != 1:
        raise ValueError(f"{path}: unsupported bench_press schema version {version} (expected 1)")
    return Run(
        path=path,
        version=version,
        timestamp=data.get("timestamp", ""),
        environment=dict(data.get("environment") or {}),
        records=tuple(_record(b) for b in data["benchmarks"]),
    )


def is_runner_file(path: str | Path) -> bool:
    """True if `path` starts with a `bench-stats run` header line."""
    with Path(path).open(encoding="utf-8") as f:
        first = f.readline()
    try:
        header = json.loads(first)
    except ValueError:
        return False
    return isinstance(header, dict) and header.get("schema") == RUNNER_SCHEMA


def _process_stable(entry: dict[str, Any]) -> bool:
    warmup = entry.get("warmup") or {}
    return bool(entry["metrics"].get("is_stable", True)) and bool(warmup.get("is_stable", True))


def _record_from_processes(entries: list[dict[str, Any]]) -> BenchmarkRecord:
    """Merge one benchmark's per-process entries, as bench_press's `BenchmarkEntry.fromProcesses` does,
    but keep which processes were unstable."""
    first = entries[0]
    trials = tuple(
        np.asarray(e["raw_trials_ns"], float) if e.get("raw_trials_ns") else np.array([float(e["metrics"]["mean_ns"])])
        for e in entries
    )
    P = len(trials)
    means = tuple(float(t.mean()) for t in trials)
    warmups = [e.get("warmup") for e in entries]
    present = [w for w in warmups if w]
    warmup_stable = all(bool(w.get("is_stable", True)) for w in present) if present else None
    unstable = [i for i, e in enumerate(entries) if not _process_stable(e)]
    warmup: dict[str, Any] = {"unstable_processes": unstable}
    if present:
        warmup.update(
            is_stable=warmup_stable,
            total_iterations=sum(int(w.get("total_iterations", 0)) for w in present),
            elapsed_seconds=sum(float(w.get("elapsed_seconds", 0.0)) for w in present),
        )
    return BenchmarkRecord(
        name=first["name"],
        target=first["target"],
        coordinates=dict(first.get("coordinates") or {}),
        is_baseline=bool(first.get("is_baseline", False)),
        process_trials=trials,
        process_means_ns=means if P > 1 else (),
        raw_trials_ns=tuple(float(x) for t in trials for x in t),
        is_stable=not unstable,
        warmup_stable=warmup_stable,
        mean_ns=float(np.mean(means)) if P > 1 else float(first["metrics"]["mean_ns"]),
        calibrated_batch_iterations=first.get("calibrated_batch_iterations"),
        warmup=warmup,
    )


def load_runner_file(path: str | Path) -> tuple[Run, Run]:
    """Read a `bench-stats run` JSONL file into (baseline, candidate) runs.

    Failed processes are skipped (their count is in `Run.meta["failed_processes"]`), the rest are taken in
    launch order. A file cut short by an interrupted run loads with the processes it has."""
    path = Path(path)
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or lines[0].get("schema") != RUNNER_SCHEMA:
        raise ValueError(f"{path}: not a bench-stats run file")
    header = lines[0]
    if header.get("schema_version") != RUNNER_SCHEMA_VERSION:
        raise ValueError(f"{path}: unsupported bench-stats run schema version {header.get('schema_version')}")
    processes = sorted((r for r in lines[1:] if r.get("type") == "process"), key=lambda r: r["launch_order"])

    runs = []
    for label in RUNNER_LABELS:
        mine = [r for r in processes if r["version"] == label]
        ok = [r for r in mine if r.get("suite") is not None and r.get("error") is None]
        if not ok:
            raise ValueError(f"{path}: no successful {label} processes")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for r in ok:
            for b in r["suite"]["benchmarks"]:
                coords = b.get("coordinates") or {}
                key = ":".join([b["name"], b["target"]] + ([",".join(f"{k}={v}" for k, v in sorted(coords.items()))] if coords else []))
                grouped.setdefault(key, []).append(b)
        version = header["versions"][label]
        runs.append(
            Run(
                path=path,
                version=int(ok[0]["suite"].get("version", 1)),
                timestamp=header.get("created", ""),
                environment=dict(ok[0]["suite"].get("environment") or {}),
                records=tuple(_record_from_processes(entries) for entries in grouped.values()),
                meta={
                    "label": label,
                    "ref": version.get("ref"),
                    "commit": version.get("commit"),
                    "compiler_flags": list(version.get("compiler_flags") or []),
                    "aa": bool(header.get("aa")),
                    "run_id": header.get("run_id"),
                    "failed_processes": len(mine) - len(ok),
                },
            )
        )
    return runs[0], runs[1]
