# bench-stats report

**Input:** `report_baseline.json` (baseline) vs `report_candidate.json` (candidate). **Environment:** Dart 3.13.7 on macos/arm64.

**Settings:** δ = 3%, 95% intervals, per-process mean, FDR q = 0.05. Speedup = baseline time / candidate time, so > 1 means the candidate is faster.

## Baseline vs candidate

| Benchmark | Speedup | 95% CI | Verdict (δ = 3%) | Detectable after BH | P (base / cand) | bench_press | bench_press `--threshold 0.03` |
| :--- | ---: | :---: | :--- | :---: | :---: | :--- | :--- |
| `same:aot` | 0.999× | [0.990, 1.008] | ✅ no meaningful change | no | 6 / 6 | ➖ ⚪ Neutral | ✅ Equivalent |
| `faster:aot` | 1.097× | [1.086, 1.108] | 🚀 faster ≥ 3% | yes | 6 / 6 | 🚀 Faster | 🚀 Faster |
| `slower:aot` | 0.928× | [0.921, 0.934] | ⚠️ slower ≥ 3% | yes | 6 / 6 | ⚠️ Regression | ⚠️ Regression |
| `small:aot` | 1.016× | [1.014, 1.018] | ✅ no meaningful change (detectable but < 3%) | yes | 8 / 8 | ➖ ⚪ Neutral | ✅ Equivalent |
| `noisy:aot` | 1.004× | [0.961, 1.048] | ➖ inconclusive (interval crosses the ±δ band) | no | 6 / 6 | ➖ ⚪ Neutral | ➖ ⚪ Inconclusive |
| `single:aot` | — | unbounded | ➖ inconclusive (unbounded interval) | no | 1 / 1 | ➖ ⚪ Neutral | ✅ Equivalent |
| `unstable:aot` | 1.005× | [0.998, 1.012] | ✅ no meaningful change | no | 6 / 6 | ❓ Unresolved | ❓ Unresolved |
| `drifting:aot` | 0.999× | [0.987, 1.011] | ✅ no meaningful change | no | 8 / 8 | ➖ ⚪ Neutral | ✅ Equivalent |

> **Summary:** 🚀 1 faster ≥ 3% · ⚠️ 1 slower ≥ 3% · ✅ 4 no meaningful change · ➖ 2 inconclusive.
> **Detectable** (interval excludes 1): 3 of 8; 3 after Benjamini–Hochberg at q = 0.05. If nothing had changed, about 0.4 of 8 would be flagged detectable by chance without FDR control.

> **Not compared** (in one run only): `retired:aot` (baseline), `new:aot` (candidate)

### Warnings

- `single:aot`: baseline: 1 process, so no process-level interval. bench_press's interval uses that process's trials and is too narrow whenever processes differ. Rerun with --processes 5 or more.
- `single:aot`: candidate: 1 process, so no process-level interval. bench_press's interval uses that process's trials and is too narrow whenever processes differ. Rerun with --processes 5 or more.
- `unstable:aot`: baseline: bench_press marked it unstable (a process failed warmup or the CV check); the JSON does not say which process.
- `drifting:aot`: baseline: process means drift with launch order (Spearman +0.93, p = 0.00086); keep versions interleaved.
- `drifting:aot`: candidate: process means drift with launch order (Spearman +0.98, p = 3.3e-05); keep versions interleaved.

## Variance diagnostics

σ₁: trial-to-trial noise inside a process. σ₂: process-to-process spread, allowing for autocorrelated trials (ρ). k: how many times too narrow a single-process interval would be. Intervals are 95% parametric-bootstrap intervals.

| Benchmark | Run | P | n | σ₁ | σ₂ | k | ρ | σ₂ drift-robust | Launch drift | bench_press share |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | ---: |
| `same:aot` | baseline | 6 | 12 | 0.95% | 0.81% [0.21, 1.34] | 3.1 [1.3, 5.2] | -0.03 | 0.97% | no (p = 0.7) | 41.1% |
| `faster:aot` | baseline | 6 | 12 | 0.99% | 0.74% [0.08, 1.27] | 2.8 [1.2, 4.7] | 0.01 | 0.70% | no (p = 0.4) | 35.7% |
| `slower:aot` | baseline | 6 | 12 | 0.98% | 0.20% [0.00, 0.48] | 1.3 [0.9, 2.1] | 0.09 | 0.20% | no (p = 0.21) | 6.5% |
| `small:aot` | baseline | 8 | 12 | 0.44% | 0.13% [0.00, 0.25] | 1.5 [1.0, 2.3] | 0.06 | 0.14% | no (p = 0.65) | 10.3% |
| `noisy:aot` | baseline | 6 | 12 | 1.06% | 3.26% [1.31, 5.19] | 10.7 [4.4, 17.3] | 0.09 | 3.37% | no (p = 0.7) | 91.1% |
| `single:aot` | baseline | 1 | 12 | — | — | — | — | — | — | — |
| `unstable:aot` | baseline | 6 | 12 | 1.06% | 0.41% [0.00, 0.74] | 1.6 [0.8, 2.7] | -0.15 | 0.54% | no (p = 0.7) | 8.9% |
| `drifting:aot` | baseline | 8 | 12 | 0.89% | 0.82% [0.35, 1.31] | 3.3 [1.6, 5.3] | -0.15 | 0.24% | yes (p = 0.00086) | 41.4% |
| `retired:aot` | baseline | 6 | 12 | 0.97% | 0.00% [0.00, 0.37] | 1.0 [0.9, 1.7] | 0.05 | 0.00% | no (p = 0.16) | 1.0% |
| `same:aot` | candidate | 6 | 12 | 1.17% | 0.01% [0.00, 0.53] | 1.2 [1.0, 2.1] | 0.21 | 0.34% | no (p = 0.7) | 6.6% |
| `faster:aot` | candidate | 6 | 12 | 1.10% | 0.60% [0.00, 1.07] | 2.3 [1.3, 3.8] | 0.26 | 0.62% | no (p = 0.87) | 31.5% |
| `slower:aot` | candidate | 6 | 12 | 1.09% | 0.47% [0.00, 0.89] | 2.0 [1.2, 3.3] | 0.25 | 0.55% | no (p = 0.96) | 25.4% |
| `small:aot` | candidate | 8 | 12 | 0.36% | 0.11% [0.00, 0.20] | 1.4 [0.8, 2.1] | -0.16 | 0.14% | no (p = 0.29) | 6.1% |
| `noisy:aot` | candidate | 6 | 12 | 0.91% | 3.41% [1.37, 5.41] | 13.0 [5.3, 21.1] | 0.10 | 3.23% | no (p = 0.87) | 93.8% |
| `single:aot` | candidate | 1 | 12 | — | — | — | — | — | — | — |
| `unstable:aot` | candidate | 6 | 12 | 0.93% | 0.53% [0.00, 0.92] | 2.2 [1.0, 3.7] | -0.03 | 0.58% | no (p = 0.87) | 23.7% |
| `drifting:aot` | candidate | 8 | 12 | 0.94% | 1.29% [0.57, 2.03] | 4.9 [2.3, 7.8] | 0.04 | 0.30% | yes (p = 3.3e-05) | 65.6% |
| `new:aot` | candidate | 6 | 12 | 1.09% | 0.00% [0.00, 0.41] | 1.1 [0.9, 1.7] | 0.08 | 0.00% | no (p = 0.21) | 0.0% |

Rows with — had a single process (or one trial per process): no between-process estimate.

## Design hint

Trials per process (n*, the cost-optimal split, rounded up to a multiple of 4 for bench_press's `ABBA BAAB` visits) and processes per version needed to report a +6% speedup as "faster ≥ 3%" with 80% power. Computed from each benchmark's own costs and variance components, using the upper end of σ₂'s interval and at least 5 processes, from whichever run needs more processes.

| Benchmark | From run | Trials per process | Processes per version | Power | σ₂ used | Trial cost c₁ | Process overhead c₂ |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `same:aot` | baseline | 4 | 6 | 86% | 1.34% | 0.100 s | ≥ 2.00 s |
| `faster:aot` | baseline | 4 | 6 | 89% | 1.27% | 0.100 s | ≥ 2.00 s |
| `slower:aot` | baseline | 12 | 5 | 100% | 0.48% | 0.100 s | ≥ 2.00 s |
| `small:aot` | baseline | 8 | 5 | 100% | 0.25% | 0.100 s | ≥ 2.00 s |
| `noisy:aot` | candidate | 4 | 58 | 80% | 5.41% | 0.102 s | ≥ 2.00 s |
| `unstable:aot` | baseline | 8 | 5 | 100% | 0.74% | 0.100 s | ≥ 2.00 s |
| `drifting:aot` | candidate | 4 | 10 | 81% | 2.03% | 0.101 s | ≥ 2.00 s |
| `retired:aot` | baseline | 12 | 5 | 100% | 0.37% | 0.100 s | ≥ 2.00 s |
| `new:aot` | candidate | 16 | 5 | 100% | 0.41% | 0.100 s | ≥ 2.00 s |

c₂ is bench_press's warmup and calibration time per process; process startup is not recorded, so it is a lower bound and the suggested n* may be slightly low.

---

Intervals are process-level Fieller intervals on per-process values (paired by process for group variants); they estimate the ratio of arithmetic means. Verdicts use the proposal's gate: the whole interval must clear ±δ (symmetric on the log scale) to call a change, or lie inside it to call no meaningful change. The bench_press columns show what bench_press 5fd6396 prints for the same data. Generated by bench-stats 0.0.1.
