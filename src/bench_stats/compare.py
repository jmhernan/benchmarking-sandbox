"""Compare a baseline and a candidate benchmark the way the proposal recommends (plan A2).

The primary interval is process-level Fieller on per-process values (paired by process in group
mode, where variants share every process). Alongside it a `Comparison` carries a log-scale
cross-check, the δ gate, what bench_press itself would print (with and without `--threshold`), the
variance components of each side and warnings.
"""

import math
import zlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace

from .io import BenchmarkRecord, Reduce, Run
from .stats.components import VarianceComponents, variance_components
from .stats.current_rule import TodayVerdict, today_verdict
from .stats.design import gate_power, optimal_trials, processes_for_power
from .stats.fieller import fieller
from .stats.gate import GateResult, Verdict, gate_interval
from .stats.interval import RatioInterval
from .stats.multiplicity import benjamini_hochberg, expected_false_flags
from .stats.paired import paired_log_ratio
from .stats.welch_log import welch_log

RECOMMENDED_PROCESSES = 5

@dataclass(frozen=True)
class Comparison:
    key: str
    baseline: BenchmarkRecord
    candidate: BenchmarkRecord
    delta: float
    reduce: Reduce
    paired: bool
    interval: RatioInterval
    cross_check: RatioInterval
    gate: GateResult
    today: TodayVerdict
    today_threshold: TodayVerdict
    components_baseline: VarianceComponents | None
    components_candidate: VarianceComponents | None
    warnings: tuple[str, ...]
    bh_detectable: bool | None = None
    bh_adjusted_p: float = math.nan

    @property
    def name(self) -> str:
        return self.candidate.name


def components_for(record: BenchmarkRecord, seed: int = 0) -> VarianceComponents | None:
    """Variance components of one record, or None with fewer than 2 processes or no repeated trials.

    The bootstrap seed is derived from the record's key, so a record gets the same intervals
    wherever it appears (e.g. a group baseline compared with several variants).
    """
    if record.processes < 2 or max(len(t) for t in record.process_trials) < 2:
        return None
    return variance_components(record.process_trials, seed=seed + zlib.crc32(record.key.encode()))


def _side_warnings(label: str, record: BenchmarkRecord, vc: VarianceComponents | None) -> list[str]:
    out = []
    P = record.processes
    if P == 1:
        out.append(
            f"{label}: 1 process, so no process-level interval. bench_press's interval uses that "
            "process's trials and is too narrow whenever processes differ. Rerun with --processes 5 or more."
        )
    elif P < RECOMMENDED_PROCESSES:
        out.append(f"{label}: only {P} processes ({RECOMMENDED_PROCESSES}+ recommended).")
    if not record.is_stable:
        out.append(
            f"{label}: bench_press marked it unstable (a process failed warmup or the CV check); "
            "the JSON does not say which process."
        )
    if vc is not None:
        if vc.outlier_processes:
            out.append(f"{label}: outlier process(es) {list(vc.outlier_processes)} (generalized ESD test, α = 1%), kept.")
        if vc.drift_detected:
            out.append(
                f"{label}: process means drift with launch order (Spearman {vc.launch_spearman:+.2f}, "
                f"p = {vc.launch_spearman_p:.2g}); keep versions interleaved."
            )
    return out


def compare(
    baseline: BenchmarkRecord,
    candidate: BenchmarkRecord,
    delta: float = 0.03,
    conf: float = 0.95,
    reduce: Reduce = "mean",
    paired: bool = False,
    seed: int = 0,
) -> Comparison:
    """Speedup baseline/candidate (> 1 means the candidate is faster)."""
    a, b = baseline.process_values(reduce), candidate.process_values(reduce)
    if paired and a.size != b.size:
        raise ValueError(f"paired comparison needs equal process counts, got {a.size} and {b.size}")

    interval = fieller(a, b, conf, paired=paired)
    cross = paired_log_ratio(a, b, conf) if paired else welch_log(a, b, conf)
    verdict = gate_interval(interval, delta)

    bp_args = (baseline.bench_press_samples(), candidate.bench_press_samples())
    bp_kwargs = dict(baseline_stable=baseline.is_stable, current_stable=candidate.is_stable, paired=paired)
    today = today_verdict(*bp_args, 0.0, **bp_kwargs)
    today_threshold = today_verdict(*bp_args, delta, **bp_kwargs)

    vc_b, vc_c = components_for(baseline, seed), components_for(candidate, seed)
    warnings = _side_warnings("baseline", baseline, vc_b) + _side_warnings("candidate", candidate, vc_c)
    if a.size >= 2 and b.size >= 2 and not interval.bounded:
        warnings.append("Fieller interval is unbounded (g ≥ 1): too few or too noisy processes.")
    cross_verdict = gate_interval(cross, delta)
    if interval.bounded and cross.bounded and cross_verdict.verdict != verdict.verdict:
        warnings.append(f"cross-check ({cross.method}) gives a different verdict: {cross_verdict.label}.")

    return Comparison(
        key=candidate.key,
        baseline=baseline,
        candidate=candidate,
        delta=delta,
        reduce=reduce,
        paired=paired,
        interval=interval,
        cross_check=cross,
        gate=verdict,
        today=today,
        today_threshold=today_threshold,
        components_baseline=vc_b,
        components_candidate=vc_c,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class SuiteComparison:
    comparisons: tuple[Comparison, ...]
    only_baseline: tuple[str, ...]
    only_candidate: tuple[str, ...]
    q: float
    expected_false_flags: dict[str, float]

    def counts(self) -> dict[Verdict, int]:
        out = dict.fromkeys(Verdict, 0)
        for c in self.comparisons:
            out[c.gate.verdict] += 1
        return out


def _with_fdr(comparisons: list[Comparison], q: float) -> list[Comparison]:
    rejected, adjusted = benjamini_hochberg([c.interval.p_value for c in comparisons], q)
    return [
        replace(c, bh_detectable=bool(r), bh_adjusted_p=float(p))
        for c, r, p in zip(comparisons, rejected, adjusted)
    ]


def compare_runs(
    baseline: Run,
    candidate: Run,
    delta: float = 0.03,
    conf: float = 0.95,
    reduce: Reduce = "mean",
    q: float = 0.05,
    seed: int = 0,
) -> SuiteComparison:
    """Compare matching benchmarks of two runs (separate process launches, so unpaired)."""
    base, cand = baseline.by_key(), candidate.by_key()
    keys = [k for k in cand if k in base]
    comparisons = [compare(base[k], cand[k], delta, conf, reduce, False, seed) for k in keys]
    return SuiteComparison(
        comparisons=tuple(_with_fdr(comparisons, q)),
        only_baseline=tuple(k for k in base if k not in cand),
        only_candidate=tuple(k for k in cand if k not in base),
        q=q,
        expected_false_flags=expected_false_flags(len(comparisons), conf),
    )


def _group_cells(records: Iterable[BenchmarkRecord]) -> dict[tuple, list[BenchmarkRecord]]:
    cells: dict[tuple, list[BenchmarkRecord]] = defaultdict(list)
    for r in records:
        if r.group is None:
            continue
        others = tuple(sorted((k, v) for k, v in r.coordinates.items() if k != "group"))
        cells[(r.target, r.group, others)].append(r)
    return cells


def compare_groups(
    run: Run,
    delta: float = 0.03,
    conf: float = 0.95,
    reduce: Reduce = "mean",
    q: float = 0.05,
    seed: int = 0,
) -> SuiteComparison:
    """Compare each variant of a `Benchmark.compare` group with the group's baseline.

    Variants of a group share every process, so the comparison is paired by process whenever both
    have the same number of processes and more than one.
    """
    comparisons = []
    for records in _group_cells(run.records).values():
        base = next((r for r in records if r.is_baseline), records[0])
        for r in records:
            if r is base:
                continue
            paired = base.processes == r.processes > 1
            comparisons.append(compare(base, r, delta, conf, reduce, paired, seed))
    return SuiteComparison(
        comparisons=tuple(_with_fdr(comparisons, q)),
        only_baseline=(),
        only_candidate=(),
        q=q,
        expected_false_flags=expected_false_flags(len(comparisons), conf),
    )


@dataclass(frozen=True)
class DesignHint:
    trials_per_process: int
    processes_per_version: int | None
    power: float
    theta: float
    c1: float
    c2: float
    sigma2_used: float


def recommend_design(
    record: BenchmarkRecord,
    components: VarianceComponents,
    delta: float = 0.03,
    theta: float | None = None,
    power: float = 0.8,
    max_trials: int = 200,
    min_processes: int = RECOMMENDED_PROCESSES,
    conservative: bool = False,
) -> DesignHint | None:
    """Trials per process (n*, rounded up to a multiple of 4) and processes per version to detect a speedup θ (default 1 + 2δ) as
    "faster ≥ δ" with the given power, from one record's costs and its variance components.

    Uses the σ₂ estimate and recommends at least `min_processes` processes (fewer leave intervals
    and outlier checks fragile, and a σ₂ estimate near 0 would otherwise suggest very few, very long
    processes). In A4 this reached 87–100% power for an 80% target at 1.15–1.27× the machine time of
    the bare formula. `conservative=True` uses the upper end of σ₂'s interval instead: 95–100% power
    at 1.3–1.5× the time.
    """
    c1, c2 = record.trial_seconds(), record.process_overhead_seconds()
    if c1 is None or c2 is None:
        return None
    theta = theta if theta is not None else 1.0 + 2.0 * delta
    s1, f = components.sigma1, components.inflation
    s2 = components.sigma2_ci[1] if conservative and math.isfinite(components.sigma2_ci[1]) else components.sigma2
    n_star = optimal_trials(c1, c2, s1, s2, f)
    # sigma2 = 0 makes n* infinite: with no process-to-process spread, longer processes are cheapest.
    n = max_trials if not math.isfinite(n_star) else int(min(max(round(n_star), 1), max_trials))
    # bench_press splits trials into four ABBA BAAB visits; a multiple of 4 keeps them balanced.
    n = 4 * math.ceil(n / 4)
    P = processes_for_power(theta, delta, n, s1, s2, power, f=f)
    if P is not None:
        P = max(P, min_processes)
    achieved = gate_power(P, n, s1, s2, theta, delta, f=f) if P else math.nan
    return DesignHint(n, P, achieved, theta, c1, c2, s2)
