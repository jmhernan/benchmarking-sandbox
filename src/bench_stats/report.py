"""The A3 report: one JSON-serialisable dict, rendered to Markdown from the same data.

Two modes:
- **runs** (baseline and candidate run files): every benchmark in both runs is compared, unpaired,
  with Benjamini–Hochberg across the suite;
- **groups** (one run file): every `Benchmark.compare` variant is compared with its group's
  baseline, paired by process.

Both modes add variance diagnostics and a design hint for every benchmark in the input.
"""

import math
from typing import Any

from . import __version__
from .compare import Comparison, components_for, compare_groups, compare_runs, recommend_design
from .io import BenchmarkRecord, Reduce, Run
from .stats.components import VarianceComponents
from .stats.current_rule import TodayVerdict
from .stats.gate import GateResult, Verdict
from .stats.interval import RatioInterval

SCHEMA = "bench-stats/report"
SCHEMA_VERSION = 1

_VERDICT_ICON = {
    Verdict.FASTER: "🚀",
    Verdict.SLOWER: "⚠️",
    Verdict.NO_CHANGE: "✅",
    Verdict.INCONCLUSIVE: "➖",
}


def _num(x: float | None) -> float | None:
    """JSON has no NaN or infinity; report those as null."""
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def _pair(xs: tuple[float, float]) -> list[float | None]:
    return [_num(xs[0]), _num(xs[1])]


def _interval(i: RatioInterval) -> dict[str, Any]:
    return {
        "method": i.method,
        "estimand": i.estimand,
        "ratio": _num(i.ratio),
        "lower": _num(i.lower),
        "upper": _num(i.upper),
        "conf": i.conf,
        "df": _num(i.df),
        "p_value": _num(i.p_value),
        "bounded": i.bounded,
    }


def _gate(g: GateResult) -> dict[str, Any]:
    return {"verdict": g.verdict.value, "label": g.label, "detectable": g.detectable, "reason": g.reason}


def _today(t: TodayVerdict) -> dict[str, Any]:
    return {
        "status": t.status,
        "speedup": _num(t.speedup),
        "lower": _num(t.lower),
        "upper": _num(t.upper),
        "reasons": list(t.reasons),
    }


def _comparison(c: Comparison) -> dict[str, Any]:
    return {
        "key": c.key,
        "name": c.name,
        "baseline_key": c.baseline.key,
        "paired": c.paired,
        "speedup": _interval(c.interval),
        "cross_check": _interval(c.cross_check),
        "gate": _gate(c.gate),
        "detectable_bh": bool(c.bh_detectable),
        "p_adjusted": _num(c.bh_adjusted_p),
        "bench_press": {"default": _today(c.today), "threshold": _today(c.today_threshold)},
        "processes": {"baseline": c.baseline.processes, "candidate": c.candidate.processes},
        "trials_per_process": {"baseline": c.baseline.mean_trials, "candidate": c.candidate.mean_trials},
        "warnings": list(c.warnings),
    }


def _components(vc: VarianceComponents, record: BenchmarkRecord) -> dict[str, Any]:
    upstream_json = (record.upstream_components or {}).get("between_process_share")
    return {
        "sigma1": _num(vc.sigma1),
        "sigma1_ci": _pair(vc.sigma1_ci),
        "sigma2": _num(vc.sigma2),
        "sigma2_ci": _pair(vc.sigma2_ci),
        "sigma2_iid": _num(vc.sigma2_iid),
        "sigma2_drift": _num(vc.sigma2_drift),
        "k": _num(vc.k),
        "k_ci": _pair(vc.k_ci),
        "icc": _num(vc.icc),
        "rho": _num(vc.rho),
        "rho_estimated": vc.rho_estimated,
        "inflation": _num(vc.inflation),
        "upstream_share": _num(vc.upstream_share),
        "upstream_share_reported": _num(upstream_json),
        "drift": {
            "spearman": _num(vc.launch_spearman),
            "p_value": _num(vc.launch_spearman_p),
            "von_neumann": _num(vc.von_neumann),
            "detected": vc.drift_detected,
        },
        "outlier_processes": list(vc.outlier_processes),
    }


def _diagnostic(
    record: BenchmarkRecord, side: str | None, delta: float, power: float, detect: float, seed: int
) -> dict[str, Any]:
    vc = components_for(record, seed)
    design = None
    if vc is not None:
        hint = recommend_design(record, vc, delta, theta=1.0 + detect, power=power)
        if hint is not None:
            design = {
                "trials_per_process": hint.trials_per_process,
                "processes_per_version": hint.processes_per_version,
                "power": _num(hint.power),
                "detect": detect,
                "c1_seconds": _num(hint.c1),
                "c2_seconds_min": _num(hint.c2),
                "sigma2_used": _num(hint.sigma2_used),
            }
    return {
        "key": record.key,
        "name": record.name,
        "side": side,
        "processes": record.processes,
        "trials_per_process": record.mean_trials,
        "is_stable": record.is_stable,
        "components": _components(vc, record) if vc is not None else None,
        "design": design,
    }


def _input(run: Run) -> dict[str, Any]:
    env = run.environment
    return {
        "file": run.path.name if run.path is not None else None,
        "timestamp": run.timestamp,
        "dart_version": env.get("dart_version") or env.get("dartVersion"),
        "os": env.get("os"),
        "arch": env.get("arch"),
        "benchmarks": len(run.records),
    }


def build_report(
    baseline: Run,
    candidate: Run | None = None,
    delta: float = 0.03,
    conf: float = 0.95,
    reduce: Reduce = "mean",
    q: float = 0.05,
    power: float = 0.8,
    detect: float | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    """Compare and diagnose; `detect` is the speedup to plan for (default 2 × delta)."""
    detect = 2.0 * delta if detect is None else detect
    if candidate is not None:
        mode = "runs"
        suite = compare_runs(baseline, candidate, delta, conf, reduce, q, seed)
        sides = [(r, "baseline") for r in baseline.records] + [(r, "candidate") for r in candidate.records]
    else:
        mode = "groups"
        suite = compare_groups(baseline, delta, conf, reduce, q, seed)
        sides = [(r, None) for r in baseline.records]

    comparisons = [_comparison(c) for c in suite.comparisons]
    counts = suite.counts()
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "bench_stats_version": __version__,
        "mode": mode,
        "inputs": {
            "baseline": _input(baseline),
            "candidate": _input(candidate) if candidate is not None else None,
        },
        "settings": {
            "threshold": delta,
            "conf": conf,
            "reduce": reduce,
            "fdr_q": q,
            "power": power,
            "detect": detect,
            "seed": seed,
        },
        "summary": {
            "comparisons": len(comparisons),
            "verdicts": {v.value: counts[v] for v in Verdict},
            "detectable": sum(1 for c in suite.comparisons if c.interval.excludes_one),
            "detectable_bh": sum(1 for c in suite.comparisons if c.bh_detectable),
            "expected_false_flags": suite.expected_false_flags,
            "only_baseline": list(suite.only_baseline),
            "only_candidate": list(suite.only_candidate),
        },
        "comparisons": comparisons,
        "diagnostics": [_diagnostic(r, side, delta, power, detect, seed) for r, side in sides],
    }


# --- Markdown -------------------------------------------------------------------------------


def _pct(x: float | None, digits: int = 2) -> str:
    return "—" if x is None else f"{100 * x:.{digits}f}%"


def _pct_ci(x: float | None, ci: list[float | None], digits: int = 2) -> str:
    if x is None:
        return "—"
    if ci[0] is None or ci[1] is None:
        return _pct(x, digits)
    return f"{100 * x:.{digits}f}% [{100 * ci[0]:.{digits}f}, {100 * ci[1]:.{digits}f}]"


def _ratio(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}×"


def _ci(i: dict[str, Any]) -> str:
    if not i["bounded"]:
        return "unbounded"
    return f"[{i['lower']:.3f}, {i['upper']:.3f}]"


def _verdict_cell(gate: dict[str, Any]) -> str:
    return f"{_VERDICT_ICON[Verdict(gate['verdict'])]} {gate['label']}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _comparisons_md(report: dict[str, Any], out: list[str]) -> None:
    s = report["settings"]
    comps = report["comparisons"]
    if not comps and report["mode"] == "groups":
        out += ["No `Benchmark.compare` groups in this run, so there is nothing to compare inside it. "
                "Pass a second run file to compare a baseline with a candidate.", ""]
        return
    title = "Baseline vs candidate" if report["mode"] == "runs" else "Group variants vs group baseline (paired by process)"
    out += [f"## {title}", ""]
    if not comps:
        out += ["No benchmark appears in both runs.", ""]
        return
    conf = f"{100 * s['conf']:g}%"
    delta = f"{100 * s['threshold']:g}%"
    out += [
        f"| Benchmark | Speedup | {conf} CI | Verdict (δ = {delta}) | Detectable after BH | P (base / cand) | bench_press | bench_press `--threshold {s['threshold']:g}` |",
        "| :--- | ---: | :---: | :--- | :---: | :---: | :--- | :--- |",
    ]
    for c in comps:
        name = f"`{c['key']}`" if report["mode"] == "runs" else f"`{c['key']}` vs `{c['baseline_key']}`"
        bh = "yes" if c["detectable_bh"] else "no"
        P = f"{c['processes']['baseline']} / {c['processes']['candidate']}"
        out.append(
            f"| {name} | {_ratio(c['speedup']['ratio'])} | {_ci(c['speedup'])} | {_cell(_verdict_cell(c['gate']))} "
            f"| {bh} | {P} | {c['bench_press']['default']['status']} | {c['bench_press']['threshold']['status']} |"
        )
    out.append("")

    sm = report["summary"]
    v = sm["verdicts"]
    n = sm["comparisons"]
    flags = sm["expected_false_flags"]["detectable (interval excludes 1)"]
    out += [
        f"> **Summary:** 🚀 {v['faster']} faster ≥ {delta} · ⚠️ {v['slower']} slower ≥ {delta} · "
        f"✅ {v['no meaningful change']} no meaningful change · ➖ {v['inconclusive']} inconclusive.",
        f"> **Detectable** (interval excludes 1): {sm['detectable']} of {n}; {sm['detectable_bh']} after "
        f"Benjamini–Hochberg at q = {s['fdr_q']:g}. If nothing had changed, about {flags:.1f} of {n} would be "
        "flagged detectable by chance without FDR control.",
        "",
    ]
    if sm["only_baseline"] or sm["only_candidate"]:
        out.append("> **Not compared** (in one run only): " + ", ".join(
            [f"`{k}` (baseline)" for k in sm["only_baseline"]] + [f"`{k}` (candidate)" for k in sm["only_candidate"]]
        ))
        out.append("")

    warned = [c for c in comps if c["warnings"]]
    if warned:
        out += ["### Warnings", ""]
        for c in warned:
            for w in c["warnings"]:
                out.append(f"- `{c['key']}`: {w}")
        out.append("")


def _diagnostics_md(report: dict[str, Any], out: list[str]) -> None:
    rows = report["diagnostics"]
    out += [
        "## Variance diagnostics",
        "",
        "σ₁: trial-to-trial noise inside a process. σ₂: process-to-process spread, allowing for "
        "autocorrelated trials (ρ). k: how many times too narrow a single-process interval would be. "
        "Intervals are 95% parametric-bootstrap intervals.",
        "",
    ]
    side = report["mode"] == "runs"
    out += [
        "| Benchmark |" + (" Run |" if side else "") + " P | n | σ₁ | σ₂ | k | ρ | σ₂ drift-robust | Launch drift | bench_press share |",
        "| :--- |" + (" :--- |" if side else "") + " ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | ---: |",
    ]
    for d in rows:
        lead = f"| `{d['key']}` |" + (f" {d['side']} |" if side else "")
        c = d["components"]
        if c is None:
            out.append(lead + f" {d['processes']} | {d['trials_per_process']:.3g} | — | — | — | — | — | — | — |")
            continue
        drift = "—"
        if c["drift"]["p_value"] is not None:
            drift = f"{'yes' if c['drift']['detected'] else 'no'} (p = {c['drift']['p_value']:.2g})"
        k = "—" if c["k"] is None else f"{c['k']:.1f} [{c['k_ci'][0]:.1f}, {c['k_ci'][1]:.1f}]"
        out.append(
            lead
            + f" {d['processes']} | {d['trials_per_process']:.3g} | {_pct(c['sigma1'])} | {_pct_ci(c['sigma2'], c['sigma2_ci'])} "
            f"| {k} | {c['rho']:.2f}{'' if c['rho_estimated'] else '*'} | {_pct(c['sigma2_drift'])} | {drift} | {_pct(c['upstream_share'], 1)} |"
        )
    out.append("")
    if any(d["components"] is None for d in rows):
        out += ["Rows with — had a single process (or one trial per process): no between-process estimate.", ""]
    if any(d["components"] is not None and not d["components"]["rho_estimated"] for d in rows):
        out += ["ρ marked * was not estimated (fewer than 8 trials per process) and is assumed 0, so σ₂ may "
                "include within-process drift.", ""]
    if any(d["components"] is not None and d["components"]["drift"]["p_value"] is None for d in rows):
        out += ["Launch drift — : fewer than 5 processes, too few to test.", ""]


def _design_md(report: dict[str, Any], out: list[str]) -> None:
    s = report["settings"]
    best: dict[str, dict[str, Any]] = {}
    for d in report["diagnostics"]:
        g = d["design"]
        if g is None:
            continue
        need = g["processes_per_version"] if g["processes_per_version"] is not None else math.inf
        prev = best.get(d["key"])
        prev_need = math.inf if prev is None or prev["design"]["processes_per_version"] is None else prev["design"]["processes_per_version"]
        if prev is None or need > prev_need:
            best[d["key"]] = d
    if not best:
        return
    side = report["mode"] == "runs"
    detect = f"+{100 * s['detect']:g}%"
    out += [
        "## Design hint",
        "",
        f"Trials per process (n*, the cost-optimal split, rounded up to a multiple of 4 for bench_press's "
        f"`ABBA BAAB` visits) and processes per version needed to report a "
        f"{detect} speedup as \"faster ≥ {100 * s['threshold']:g}%\" with {100 * s['power']:g}% power. "
        "Computed from each benchmark's own costs and variance components, with at least 5 processes"
        + (", from whichever run needs more processes." if side else "."),
        "",
        "| Benchmark |" + (" From run |" if side else "") + " Trials per process | Processes per version | Power | σ₂ used | Trial cost c₁ | Process overhead c₂ |",
        "| :--- |" + (" :--- |" if side else "") + " ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for d in best.values():
        g = d["design"]
        P = "> 1000" if g["processes_per_version"] is None else str(g["processes_per_version"])
        power = "—" if g["power"] is None else f"{100 * g['power']:.0f}%"
        out.append(
            f"| `{d['key']}` |" + (f" {d['side']} |" if side else "")
            + f" {g['trials_per_process']} | {P} | {power} | {_pct(g['sigma2_used'])} | {g['c1_seconds']:.3f} s | ≥ {g['c2_seconds_min']:.2f} s |"
        )
    out += [
        "",
        "c₂ is bench_press's warmup and calibration time per process; process startup is not recorded, so it is a "
        "lower bound and the suggested n* may be slightly low.",
        "",
    ]


def render_markdown(report: dict[str, Any]) -> str:
    s = report["settings"]
    inputs = report["inputs"]
    out = ["# bench-stats report", ""]
    files = f"`{inputs['baseline']['file']}`"
    if inputs["candidate"] is not None:
        files += f" (baseline) vs `{inputs['candidate']['file']}` (candidate)"
    env = inputs["baseline"]
    dart = f"Dart {env['dart_version'].split()[0]}" if env["dart_version"] else "unknown Dart version"
    out += [
        f"**Input:** {files}. **Environment:** {dart} on {env['os'] or '?'}/{env['arch'] or '?'}.",
        "",
        f"**Settings:** δ = {100 * s['threshold']:g}%, {100 * s['conf']:g}% intervals, per-process {s['reduce']}, "
        f"FDR q = {s['fdr_q']:g}. Speedup = baseline time / candidate time, so > 1 means the candidate is faster.",
        "",
    ]
    _comparisons_md(report, out)
    _diagnostics_md(report, out)
    _design_md(report, out)
    out += [
        "---",
        "",
        "Intervals are process-level Fieller intervals on per-process values (paired by process for group variants); "
        "they estimate the ratio of arithmetic means. Verdicts use the proposal's gate: the whole interval must clear "
        "±δ (symmetric on the log scale) to call a change, or lie inside it to call no meaningful change. The bench_press "
        f"columns show what bench_press 5fd6396 prints for the same data. Generated by bench-stats {report['bench_stats_version']}.",
        "",
    ]
    return "\n".join(out)
