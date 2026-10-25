"""Load bench_press run JSON (`bench_press run -o …`, schema version 1, bench_press 5fd6396)."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

Reduce = Literal["mean", "median"]


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
