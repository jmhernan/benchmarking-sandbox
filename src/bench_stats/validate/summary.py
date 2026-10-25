"""Render the A4 results as Markdown, checking the plan's A.4 acceptance criteria."""

import math
from collections import defaultdict
from typing import Any

Rows = list[dict[str, Any]]

HEAVY_TAILS = ("t3 trial noise", "lognormal spikes")
DRIFT = ("AR(1) trials, rho 0.6", "slow episodes", "launch drift, interleaved")
UNEQUAL = ("unequal sigma2 (candidate 2x)",)


def _pct(x: float | None, digits: int = 1) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{digits}f}%"


def _mark(ok: bool | None) -> str:
    return {True: "✅ pass", False: "❌ fail", None: "—"}[ok]


def _table(header: list[str], rows: list[list[str]], align: str | None = None) -> list[str]:
    align = align or "| " + " | ".join(":---" if i == 0 else "---:" for i in range(len(header))) + " |"
    return ["| " + " | ".join(header) + " |", align] + ["| " + " | ".join(r) + " |" for r in rows] + [""]


def _acceptance(r: dict[str, Rows]) -> list[tuple[str, str, str, bool | None]]:
    out = []
    grid = [g for g in r.get("grid", []) if g["P"] >= 3]
    if grid:
        cov = [g["covers"] for g in grid]
        low = [g for g in grid if g["covers"] < 0.935]
        band = [g["covers"] for g in grid if g["P"] >= 5]
        out.append(("Coverage (normal model)", "Fieller coverage ≥ 93.5% in every cell with P ≥ 3 (revised, see plan A.4)",
                    f"min {_pct(min(cov))} over {len(cov)} cells", not low))
        out.append(("Coverage (normal model)", "Fieller coverage within 95 ± 1.5 pp in every cell with P ≥ 5 (revised, see plan A.4)",
                    f"{_pct(min(band))} – {_pct(max(band))} over {len(band)} cells", 0.935 <= min(band) and max(band) <= 0.965))
        high = [g for g in grid if g["covers"] > 0.965]
        out.append(("Coverage (normal model)", "Superseded: within 95 ± 1.5 pp in every cell with P ≥ 3",
                    f"{_pct(min(cov))} – {_pct(max(cov))}; {len(high)} cells above, all at P = "
                    + ", ".join(str(P) for P in sorted({g['P'] for g in high})) if high else f"{_pct(min(cov))} – {_pct(max(cov))}",
                    None))
        aa = [g["excludes_1"] for g in grid if g["theta"] == 1.0]
        out.append(("Coverage (normal model)", "A/A false alarms (interval excludes 1) ≤ 6%",
                    f"max {_pct(max(aa))}", max(aa) <= 0.06))
        f102 = [g["gate_faster"] for g in grid if g["theta"] == 1.02]
        out.append(("Gate", "False \"faster ≥ δ\" at θ = 1.02 ≤ 2.5% (P ≥ 3, every σ)", f"max {_pct(max(f102))}",
                    max(f102) <= 0.025))
        pw = [g["gate_faster"] for g in grid if g["P"] == 10 and g["theta"] == 1.05 and g["sigma1"] == 0.01 and g["sigma2"] == 0.01]
        if pw:
            out.append(("Gate", "Power at θ = 1.05 ≥ 80% at P = 10 (σ₁ = σ₂ = 1%)", _pct(pw[0]), pw[0] >= 0.80))
    group = [g for g in r.get("group", []) if g["P"] >= 3]
    if group:
        cov = [g["paired_covers"] for g in group]
        out.append(("Group mode", "Paired coverage within 95 ± 1.5 pp at P ≥ 3", f"{_pct(min(cov))} – {_pct(max(cov))}",
                    0.935 <= min(cov) and max(cov) <= 0.965))
        shared = [g for g in group if g["sigma_shared"] > 0]
        ratio = [g["paired_median_half_width"] / g["unpaired_median_half_width"] for g in shared]
        out.append(("Group mode", "Paired narrower than independent Fieller when a shared effect is present",
                    f"paired/unpaired width {min(ratio):.2f} – {max(ratio):.2f}", max(ratio) < 1))
    robust = [g for g in r.get("robust", []) if g["P"] >= 5]
    if robust:
        for label, names in (("heavy tails", HEAVY_TAILS), ("drift", DRIFT), ("unequal variance", UNEQUAL)):
            cov = [g["covers"] for g in robust if g["scenario"] in names]
            out.append(("Robustness", f"Coverage ≥ 90% under {label} at P ≥ 5 ({', '.join(names)})",
                        f"min {_pct(min(cov))}", min(cov) >= 0.90))
        det = [g for g in robust if g["scenario"].startswith("one outlier") and g["theta"] == 1.0]
        out.append(("Robustness", "Superseded: outlier process (+5%, about 4.9 process SDs) flagged in ≥ 95% of cells, P ≥ 5",
                    ", ".join(f"P={g['P']}: {_pct(g['outlier_flag_true'], 0)}" for g in det), None))
        clean = [g for g in robust if g["scenario"] == "normal" and g["P"] >= 10]
        if clean:
            fp = max(g["outlier_flag_any"] for g in clean)
            out.append(("Robustness", "False outlier flags ≤ 2% per benchmark at P ≥ 10, normal model (revised, see plan A.4)",
                        f"max {_pct(fp)}", fp <= 0.02))
    outl = [g for g in r.get("outlier", []) if g["P"] >= 10 and g["shift_process_sd"] >= 8]
    if outl:
        out.append(("Robustness", "Outlier of ≥ 8 process SDs flagged in ≥ 95% at P ≥ 10 (revised, see plan A.4)",
                    ", ".join(f"P={g['P']}, {g['shift_process_sd']:g} SD: {_pct(g['detected'], 0)}" for g in outl),
                    all(g["detected"] >= 0.95 for g in outl)))
    suite = _suite_totals(r.get("suite", []))
    if suite:
        for mix in ("all null", "5 at +2%"):
            if mix in suite:
                v = suite[mix]["gate_false_claims"] / suite[mix]["reps"]
                out.append(("Suite", f"Gate: expected false \"≥ δ\" claims per 20-benchmark run ≤ 0.5 ({mix})", f"{v:.3f}", v <= 0.5))
        fdr = {m: s["bh_fdp"] / s["reps"] for m, s in suite.items() if s["effects"]}
        out.append(("Suite", "\"Detectable\" with BH: false discovery rate ≤ 5% when true effects are present",
                    ", ".join(f"{m}: {_pct(v)}" for m, v in fdr.items()), max(fdr.values()) <= 0.05))
        if "all null" in suite:
            v = suite["all null"]["bh_false"] / suite["all null"]["reps"]
            out.append(("Suite", "\"Detectable\" with BH: expected false flags per all-null run ≤ 1", f"{v:.3f}", v <= 1))
    design = _design_means(r.get("design", []))
    if design:
        ship = {t: (d["shipped_achieved"], d["shipped_cost_s"] / d["point_cost_s"]) for t, d in design.items()}
        out.append(("Design", "Shipped design achieves ≥ the 80% target − 5 pp, i.e. is never under-powered (revised, see plan A.4)",
                    ", ".join(f"{t.split(' (')[0]}: {_pct(v)} at {c:.2f}× cost" for t, (v, c) in ship.items()),
                    all(v >= DESIGN_TARGET - 0.05 for v, _ in ship.values())))
        for variant, note in (("shipped", "superseded, shipped default"), ("point", "informational, no 5-process floor"),
                              ("conservative", "informational, upper end of σ₂'s interval")):
            got = {t: d[f"{variant}_achieved"] for t, d in design.items()}
            out.append(("Design", f"Achieves the 80% target within ±5 pp ({note})",
                        ", ".join(f"{t.split(' (')[0]}: {_pct(v)}" for t, v in got.items()), None))
    return out


def _suite_totals(rows: Rows) -> dict[str, dict[str, float]]:
    tot: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        t = tot[row["mix"]]
        for k, v in row.items():
            if k == "effects":
                t[k] = v
            elif k != "mix":
                t[k] += v
    return {m: dict(v) for m, v in tot.items()}


def _design_means(rows: Rows) -> dict[str, dict[str, float]]:
    by: dict[str, Rows] = defaultdict(list)
    for row in rows:
        by[row["truth"]].append(row)
    keys = [k for k in rows[0] if k not in ("truth", "pilot")] if rows else []
    return {t: {k: sum(x[k] for x in rs) / len(rs) for k in keys} | {"pilots": len(rs)} for t, rs in by.items()}


DESIGN_TARGET = 0.80


def _grid_md(rows: Rows, out: list[str]) -> None:
    out += ["## Identical versions (θ = 1): ours vs bench_press today", "",
            "σ₁ = 1%, n = 16. **Ours:** process-level Fieller and the δ = 3% gate. **Today:** one process per version "
            "(batch-level interval, ±5% band). **Today --threshold:** the same single process with upstream's "
            "`--threshold 0.03`. **Upstream --processes P:** upstream's gate on the same P process means.", ""]
    body = []
    for g in sorted((g for g in rows if g["theta"] == 1.0 and g["sigma1"] == 0.01), key=lambda g: (g["sigma2"], g["P"])):
        body.append([f"{100 * g['sigma2']:g}%", str(g["P"]), _pct(g["covers"]), _pct(g["gate_faster"] + g["gate_slower"]),
                     _pct(g["gate_no_change"]), _pct(g["today_covers"]), _pct(g["today_faster"] + g["today_slower"]),
                     _pct(g["today_threshold_faster"] + g["today_threshold_slower"]),
                     _pct(g["upstream_P_faster"] + g["upstream_P_slower"]) if g["P"] > 1 else "—"])
    out += _table(["σ₂", "P", "Ours: coverage", "Ours: false ≥ δ", "Ours: no meaningful change", "Today: printed CI coverage",
                   "Today: false Faster/Regression", "Today --threshold: false ≥ δ", "Upstream --processes P: false ≥ δ"], body)

    out += ["## Gate operating characteristics", "", "P(\"faster ≥ 3%\") by true speedup θ and processes per version, n = 16.", ""]
    for s1, s2 in ((0.01, 0.01), (0.01, 0.0025), (0.03, 0.01)):
        sel = [g for g in rows if g["sigma1"] == s1 and g["sigma2"] == s2]
        if not sel:
            continue
        Ps = sorted({g["P"] for g in sel})
        thetas = sorted({g["theta"] for g in sel})
        by = {(g["P"], g["theta"]): g for g in sel}
        out += [f"σ₁ = {100 * s1:g}%, σ₂ = {100 * s2:g}%:", ""]
        out += _table(["θ"] + [f"P = {P}" for P in Ps],
                      [[f"{t:.2f}"] + [_pct(by[(P, t)]["gate_faster"], 0) for P in Ps] for t in thetas])

    out += ["## Coverage across the whole grid", "", "Minimum and maximum Fieller coverage over σ₁, σ₂ and θ, by P.", ""]
    body = []
    for P in sorted({g["P"] for g in rows}):
        cov = [g["covers"] for g in rows if g["P"] == P]
        wl = [g["welch_log_covers"] for g in rows if g["P"] == P]
        ub = [1 - g["bounded"] for g in rows if g["P"] == P]
        body.append([str(P), _pct(min(cov)), _pct(max(cov)), _pct(min(wl)), _pct(max(wl)), _pct(max(ub))])
    out += _table(["P", "Fieller min", "Fieller max", "Welch-log min", "Welch-log max", "Unbounded (max)"], body)

    comp = [g for g in rows if g["theta"] == 1.0 and g["sigma1"] == 0.01 and g.get("components_reps")]
    if comp:
        out += ["## σ̂ bias under the normal model (independent trials)", "",
                "Mean estimates over replications, σ₁ = 1%, n = 16. The bench_press share is compared with the true "
                "σ₂² / (σ₂² + σ₁²).", ""]
        body = [[f"{100 * g['sigma2']:g}%", str(g["P"]), _pct(g["sigma1_hat"], 2), _pct(g["sigma2_hat"], 2),
                 _pct(g["sigma2_iid_hat"], 2), _pct(g["sigma2_drift_hat"], 2), _pct(g["upstream_share_hat"]),
                 _pct(g["sigma2"] ** 2 / (g["sigma2"] ** 2 + 0.01**2))]
                for g in sorted(comp, key=lambda g: (g["sigma2"], g["P"])) if g["P"] in (5, 10, 20)]
        out += _table(["σ₂", "P", "σ̂₁", "σ̂₂ (shipped)", "σ̂₂ (iid ANOVA)", "σ̂₂ (drift-robust)", "bench_press share", "true share"], body)


def _robust_md(rows: Rows, out: list[str]) -> None:
    out += ["## Robustness scenarios", "", "σ₁ = σ₂ = 1%, n = 16. Coverage at θ = 1 and P(\"faster ≥ 3%\") at θ = 1.05.", ""]
    names = list(dict.fromkeys(g["scenario"] for g in rows))
    Ps = sorted({g["P"] for g in rows})
    by = {(g["scenario"], g["P"], g["theta"]): g for g in rows}
    body = []
    for name in names:
        cells = []
        for P in Ps:
            a, b = by.get((name, P, 1.0)), by.get((name, P, 1.05))
            cells.append(f"{_pct(a['covers'], 0)} / {_pct(b['gate_faster'], 0)}" if a and b else "—")
        body.append([name] + cells)
    out += _table(["Scenario"] + [f"P = {P}: coverage / power" for P in Ps], body)

    out += ["### σ̂₂ and bench_press's share by scenario (P = 10, true σ₂ = 1%)", ""]
    body = []
    for name in names:
        g = by.get((name, 10, 1.0))
        if g and g.get("components_reps"):
            body.append([name, _pct(g["sigma2_hat"], 2), _pct(g["sigma2_iid_hat"], 2), _pct(g["sigma2_drift_hat"], 2),
                         f"{g['rho_hat']:.2f}", _pct(g["upstream_share_hat"]), _pct(g["outlier_flag_any"])])
    out += _table(["Scenario", "σ̂₂ (shipped)", "σ̂₂ (iid)", "σ̂₂ (drift-robust)", "ρ̂", "bench_press share",
                   "Any outlier flagged"], body)


def _group_md(rows: Rows, out: list[str]) -> None:
    out += ["## Group mode (variants share each process)", "",
            "Variant-specific process effect 0.25%, σ₁ = 1%, n = 16. Coverage at θ = 1; median relative half-width.", ""]
    body = []
    for g in sorted((g for g in rows if g["theta"] == 1.0), key=lambda g: (g["sigma_shared"], g["P"])):
        body.append([f"{100 * g['sigma_shared']:g}%", str(g["P"]), _pct(g["paired_covers"]), _pct(g["paired_log_covers"]),
                     _pct(g["unpaired_covers"]), _pct(g["paired_median_half_width"], 2), _pct(g["unpaired_median_half_width"], 2)])
    out += _table(["Shared effect", "P", "Paired Fieller", "Paired log-t", "Unpaired Fieller", "Paired ± width",
                   "Unpaired ± width"], body)


def _suite_md(rows: Rows, out: list[str]) -> None:
    tot = _suite_totals(rows)
    out += ["## 20-benchmark suites", "", "P = 10, σ₁ = σ₂ = 1%, δ = 3%, BH at q = 0.05. Per-run averages.", ""]
    body = []
    for mix, t in tot.items():
        n = t["reps"]
        body.append([mix, f"{t['gate_false_claims'] / n:.3f}", f"{t['raw_false'] / n:.2f}", f"{t['bh_false'] / n:.2f}",
                     _pct(t["raw_fdp"] / n), _pct(t["bh_fdp"] / n),
                     _pct(t["raw_true"] / (n * t["effects"])) if t["effects"] else "—",
                     _pct(t["bh_true"] / (n * t["effects"])) if t["effects"] else "—", str(int(n))])
    out += _table(["Mix", "Gate false ≥ δ", "False detectable (raw)", "False detectable (BH)", "FDR raw", "FDR BH",
                   "Power raw", "Power BH", "Runs"], body)


def _design_md(rows: Rows, out: list[str]) -> None:
    means = _design_means(rows)
    out += ["## Design check", "",
            "A 10-process pilot → `recommend_design` (θ = 1.06, δ = 3%, 80% target) → the recommended experiment, "
            "simulated. Variants: **shipped** (defaults: σ̂₂ as estimated, at least 5 processes, trials a multiple "
            "of 4), **point** (no floor) and **conservative** (upper end of σ₂'s interval, at least 5 processes). "
            "Means over pilots; cost is total machine time relative to the point design.", ""]
    body = []
    for t, d in means.items():
        for v in ("shipped", "point", "conservative"):
            body.append([t if v == "shipped" else "", v, f"{d[f'{v}_n']:.1f} × {d[f'{v}_P']:.1f}", _pct(d[f"{v}_promised"]),
                         _pct(d[f"{v}_achieved"]), f"{d[f'{v}_cost_s'] / d['point_cost_s']:.2f}×"])
    out += _table(["Truth", "Variant", "Trials × processes", "Promised power", "Achieved power", "Cost"], body)


def _power_md(rows: Rows, out: list[str]) -> None:
    diffs = [g["simulated"] - g["analytic"] for g in rows]
    worst = max(rows, key=lambda g: abs(g["simulated"] - g["analytic"]))
    out += ["## Power formula calibration", "",
            f"`design.gate_power` (noncentral t, effective df 1.5(P − 1)) vs simulated gate power over {len(rows)} cells: "
            f"mean difference {100 * sum(diffs) / len(diffs):+.1f} pp, largest {100 * (worst['simulated'] - worst['analytic']):+.1f} pp "
            f"(P = {worst['P']}, θ = {worst['theta']}, σ₁ = {100 * worst['sigma1']:g}%, σ₂ = {100 * worst['sigma2']:g}%, ρ = {worst['rho']}).", ""]
    body = [[str(g["P"]), f"{g['theta']:.2f}", f"{100 * g['sigma1']:g}% / {100 * g['sigma2']:g}%", f"{g['rho']:g}",
             _pct(g["simulated"], 0), _pct(g["analytic"], 0)]
            for g in sorted(rows, key=lambda g: (g["sigma1"], g["sigma2"], g["rho"], g["theta"], g["P"]))
            if abs(g["simulated"] - g["analytic"]) > 0.03]
    if body:
        out += ["Cells off by more than 3 pp:", ""]
        out += _table(["P", "θ", "σ₁ / σ₂", "ρ", "Simulated", "Analytic"], body)


def _ci_md(rows: Rows, out: list[str]) -> None:
    out += ["## Variance-component interval coverage", "",
            "Nominal 95% parametric-bootstrap intervals from `components.py` (σ₁ = 1%, n = 16).", ""]
    body = [[str(g["P"]), f"{100 * g['sigma2']:g}%", f"{g['rho']:g}", _pct(g["covers_s1"]), _pct(g["covers_s2"]), _pct(g["covers_k"])]
            for g in sorted(rows, key=lambda g: (g["rho"], g["sigma2"], g["P"]))]
    out += _table(["P", "σ₂", "ρ", "σ₁", "σ₂", "k"], body)


def _outlier_md(rows: Rows, out: list[str]) -> None:
    Ps = sorted({g["P"] for g in rows})
    shifts = sorted({g["shift_process_sd"] for g in rows})
    by = {(g["P"], g["shift_process_sd"]): g for g in rows}
    out += ["## Outlier detection (generalized ESD, α = 1%)", "",
            "Rate at which one shifted process is flagged, by shift in process SDs (one process SD ≈ 1.03% here: σ₁ = σ₂ = 1%, n = 16).", ""]
    out += _table(["Shift"] + [f"P = {P}" for P in Ps],
                  [[f"{s:g} SD"] + [_pct(by[(P, s)]["detected"], 0) for P in Ps] for s in shifts])


def render_summary(results: dict[str, Rows], info: dict[str, Any]) -> str:
    out = ["# A4 simulation validation", "",
           f"bench-stats {info['bench_stats_version']}, seed {info['seed']}, replication scale {info['scale']:g}, "
           f"{info['tasks']} tasks in {info['seconds']:g} s. Every number comes from the shipped `bench_stats` estimators. "
           "Monte Carlo SE at 4,000 replications is about ±0.35 pp at 95% coverage.", ""]
    acc = _acceptance(results)
    if acc:
        out += ["## Part A acceptance criteria (plan A.4)", ""]
        out += _table(["Area", "Criterion", "Result", "Status"], [[a, c, r, _mark(ok)] for a, c, r, ok in acc],
                      "| :--- | :--- | :--- | :---: |")
    sections = (("grid", _grid_md), ("robust", _robust_md), ("group", _group_md), ("suite", _suite_md),
                ("design", _design_md), ("power", _power_md), ("ci", _ci_md), ("outlier", _outlier_md))
    for key, fn in sections:
        if results.get(key):
            fn(results[key], out)
    return "\n".join(out)
