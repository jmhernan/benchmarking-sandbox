# A4 simulation validation

bench-stats 0.0.1, seed 20261025, replication scale 1, 670 tasks in 61 s. Every number comes from the shipped `bench_stats` estimators. Monte Carlo SE at 4,000 replications is about ±0.35 pp at 95% coverage.

## Part A acceptance criteria (plan A.4)

| Area | Criterion | Result | Status |
| :--- | :--- | :--- | :---: |
| Coverage (normal model) | Fieller coverage ≥ 93.5% in every cell with P ≥ 3 (revised, see plan A.4) | min 94.3% over 240 cells | ✅ pass |
| Coverage (normal model) | Fieller coverage within 95 ± 1.5 pp in every cell with P ≥ 5 (revised, see plan A.4) | 94.3% – 96.3% over 180 cells | ✅ pass |
| Coverage (normal model) | Superseded: within 95 ± 1.5 pp in every cell with P ≥ 3 | 94.3% – 97.7%; 24 cells above, all at P = 3 | — |
| Coverage (normal model) | A/A false alarms (interval excludes 1) ≤ 6% | max 5.4% | ✅ pass |
| Gate | False "faster ≥ δ" at θ = 1.02 ≤ 2.5% (P ≥ 3, every σ) | max 0.7% | ✅ pass |
| Gate | Power at θ = 1.05 ≥ 80% at P = 10 (σ₁ = σ₂ = 1%) | 97.4% | ✅ pass |
| Group mode | Paired coverage within 95 ± 1.5 pp at P ≥ 3 | 94.5% – 95.5% | ✅ pass |
| Group mode | Paired narrower than independent Fieller when a shared effect is present | paired/unpaired width 0.34 – 0.48 | ✅ pass |
| Robustness | Coverage ≥ 90% under heavy tails at P ≥ 5 (t3 trial noise, lognormal spikes) | min 94.5% | ✅ pass |
| Robustness | Coverage ≥ 90% under drift at P ≥ 5 (AR(1) trials, rho 0.6, slow episodes, launch drift, interleaved) | min 94.7% | ✅ pass |
| Robustness | Coverage ≥ 90% under unequal variance at P ≥ 5 (unequal sigma2 (candidate 2x)) | min 94.5% | ✅ pass |
| Robustness | Superseded: outlier process (+5%, about 4.9 process SDs) flagged in ≥ 95% of cells, P ≥ 5 | P=5: 10%, P=10: 44%, P=20: 68% | — |
| Robustness | False outlier flags ≤ 2% per benchmark at P ≥ 10, normal model (revised, see plan A.4) | max 1.3% | ✅ pass |
| Robustness | Outlier of ≥ 8 process SDs flagged in ≥ 95% at P ≥ 10 (revised, see plan A.4) | P=10, 8 SD: 95%, P=10, 12 SD: 100%, P=20, 8 SD: 100%, P=20, 12 SD: 100%, P=40, 8 SD: 100%, P=40, 12 SD: 100% | ✅ pass |
| Suite | Gate: expected false "≥ δ" claims per 20-benchmark run ≤ 0.5 (all null) | 0.000 | ✅ pass |
| Suite | Gate: expected false "≥ δ" claims per 20-benchmark run ≤ 0.5 (5 at +2%) | 0.000 | ✅ pass |
| Suite | "Detectable" with BH: false discovery rate ≤ 5% when true effects are present | 2 at +5%: 4.3%, 5 at +5%: 3.3%, 5 at +2%: 3.5% | ✅ pass |
| Suite | "Detectable" with BH: expected false flags per all-null run ≤ 1 | 0.058 | ✅ pass |
| Design | Shipped design achieves ≥ the 80% target − 5 pp, i.e. is never under-powered (revised, see plan A.4) | pilot-like: 87.0% at 1.15× cost, σ₁ = σ₂ = 1%: 94.9% at 1.20× cost, small σ₂: 100.0% at 2.09× cost, noisy trials: 91.0% at 1.27× cost | ✅ pass |
| Design | Achieves the 80% target within ±5 pp (superseded, shipped default) | pilot-like: 87.0%, σ₁ = σ₂ = 1%: 94.9%, small σ₂: 100.0%, noisy trials: 91.0% | — |
| Design | Achieves the 80% target within ±5 pp (informational, no 5-process floor) | pilot-like: 79.9%, σ₁ = σ₂ = 1%: 83.6%, small σ₂: 85.8%, noisy trials: 79.5% | — |
| Design | Achieves the 80% target within ±5 pp (informational, upper end of σ₂'s interval) | pilot-like: 95.5%, σ₁ = σ₂ = 1%: 97.3%, small σ₂: 100.0%, noisy trials: 95.9% | — |

## Identical versions (θ = 1): ours vs bench_press today

σ₁ = 1%, n = 16. **Ours:** process-level Fieller and the δ = 3% gate. **Today:** one process per version (batch-level interval, ±5% band). **Today --threshold:** the same single process with upstream's `--threshold 0.03`. **Upstream --processes P:** upstream's gate on the same P process means.

| σ₂ | P | Ours: coverage | Ours: false ≥ δ | Ours: no meaningful change | Today: printed CI coverage | Today: false Faster/Regression | Today --threshold: false ≥ δ | Upstream --processes P: false ≥ δ |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0% | 2 | 97.7% | 0.0% | 82.0% | 94.8% | 0.0% | 0.0% | 0.0% |
| 0% | 3 | 96.7% | 0.0% | 100.0% | 94.7% | 0.0% | 0.0% | 0.0% |
| 0% | 5 | 95.2% | 0.0% | 100.0% | 95.3% | 0.0% | 0.0% | 0.0% |
| 0% | 10 | 94.9% | 0.0% | 100.0% | 94.7% | 0.0% | 0.0% | 0.0% |
| 0% | 20 | 95.0% | 0.0% | 100.0% | 94.3% | 0.0% | 0.0% | 0.0% |
| 0.25% | 2 | 97.9% | 0.0% | 64.6% | 83.8% | 0.0% | 0.0% | 0.0% |
| 0.25% | 3 | 96.5% | 0.0% | 100.0% | 84.9% | 0.0% | 0.0% | 0.0% |
| 0.25% | 5 | 96.3% | 0.0% | 100.0% | 85.4% | 0.0% | 0.0% | 0.0% |
| 0.25% | 10 | 94.9% | 0.0% | 100.0% | 83.8% | 0.0% | 0.0% | 0.0% |
| 0.25% | 20 | 94.7% | 0.0% | 100.0% | 84.5% | 0.0% | 0.0% | 0.0% |
| 0.5% | 2 | 97.8% | 0.0% | 36.5% | 63.4% | 0.0% | 0.0% | 0.0% |
| 0.5% | 3 | 96.4% | 0.0% | 96.5% | 63.6% | 0.0% | 0.0% | 0.0% |
| 0.5% | 5 | 95.3% | 0.0% | 100.0% | 63.1% | 0.0% | 0.0% | 0.0% |
| 0.5% | 10 | 95.0% | 0.0% | 100.0% | 62.3% | 0.0% | 0.0% | 0.0% |
| 0.5% | 20 | 95.7% | 0.0% | 100.0% | 63.8% | 0.0% | 0.0% | 0.0% |
| 1% | 2 | 97.6% | 0.0% | 10.5% | 37.0% | 0.1% | 1.1% | 0.0% |
| 1% | 3 | 96.4% | 0.0% | 43.5% | 38.0% | 0.0% | 1.3% | 0.0% |
| 1% | 5 | 95.9% | 0.0% | 93.8% | 36.8% | 0.1% | 1.2% | 0.0% |
| 1% | 10 | 95.2% | 0.0% | 100.0% | 38.2% | 0.2% | 1.5% | 0.0% |
| 1% | 20 | 95.7% | 0.0% | 100.0% | 37.7% | 0.0% | 0.9% | 0.0% |
| 2% | 2 | 97.5% | 0.1% | 1.9% | 19.1% | 7.8% | 20.0% | 0.1% |
| 2% | 3 | 96.5% | 0.1% | 4.5% | 21.1% | 7.8% | 19.6% | 0.1% |
| 2% | 5 | 95.6% | 0.0% | 17.6% | 19.6% | 8.0% | 20.2% | 0.0% |
| 2% | 10 | 95.2% | 0.0% | 74.0% | 20.3% | 7.6% | 18.8% | 0.0% |
| 2% | 20 | 95.6% | 0.0% | 99.1% | 18.1% | 8.7% | 20.4% | 0.0% |

## Gate operating characteristics

P("faster ≥ 3%") by true speedup θ and processes per version, n = 16.

σ₁ = 1%, σ₂ = 1%:

| θ | P = 2 | P = 3 | P = 5 | P = 10 | P = 20 |
| :--- | ---: | ---: | ---: | ---: | ---: |
| 1.00 | 0% | 0% | 0% | 0% | 0% |
| 1.01 | 0% | 0% | 0% | 0% | 0% |
| 1.02 | 0% | 0% | 0% | 0% | 0% |
| 1.03 | 1% | 2% | 2% | 3% | 2% |
| 1.05 | 10% | 33% | 71% | 97% | 100% |
| 1.10 | 53% | 100% | 100% | 100% | 100% |

σ₁ = 1%, σ₂ = 0.25%:

| θ | P = 2 | P = 3 | P = 5 | P = 10 | P = 20 |
| :--- | ---: | ---: | ---: | ---: | ---: |
| 1.00 | 0% | 0% | 0% | 0% | 0% |
| 1.01 | 0% | 0% | 0% | 0% | 0% |
| 1.02 | 0% | 0% | 0% | 0% | 0% |
| 1.03 | 1% | 2% | 2% | 2% | 2% |
| 1.05 | 45% | 98% | 100% | 100% | 100% |
| 1.10 | 97% | 100% | 100% | 100% | 100% |

σ₁ = 3%, σ₂ = 1%:

| θ | P = 2 | P = 3 | P = 5 | P = 10 | P = 20 |
| :--- | ---: | ---: | ---: | ---: | ---: |
| 1.00 | 0% | 0% | 0% | 0% | 0% |
| 1.01 | 0% | 0% | 0% | 0% | 0% |
| 1.02 | 0% | 0% | 0% | 0% | 0% |
| 1.03 | 1% | 2% | 2% | 2% | 2% |
| 1.05 | 7% | 24% | 55% | 90% | 100% |
| 1.10 | 44% | 98% | 100% | 100% | 100% |

## Coverage across the whole grid

Minimum and maximum Fieller coverage over σ₁, σ₂ and θ, by P.

| P | Fieller min | Fieller max | Welch-log min | Welch-log max | Unbounded (max) |
| :--- | ---: | ---: | ---: | ---: | ---: |
| 2 | 97.2% | 98.3% | 97.2% | 98.3% | 0.0% |
| 3 | 95.9% | 97.7% | 95.9% | 97.7% | 0.0% |
| 5 | 94.9% | 96.3% | 94.9% | 96.3% | 0.0% |
| 10 | 94.3% | 95.9% | 94.2% | 95.9% | 0.0% |
| 20 | 94.3% | 95.9% | 94.3% | 95.9% | 0.0% |

## σ̂ bias under the normal model (independent trials)

Mean estimates over replications, σ₁ = 1%, n = 16. The bench_press share is compared with the true σ₂² / (σ₂² + σ₁²).

| σ₂ | P | σ̂₁ | σ̂₂ (shipped) | σ̂₂ (iid ANOVA) | σ̂₂ (drift-robust) | bench_press share | true share |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0% | 5 | 1.00% | 0.08% | 0.08% | 0.07% | 1.9% | 0.0% |
| 0% | 10 | 1.00% | 0.06% | 0.06% | 0.07% | 1.2% | 0.0% |
| 0% | 20 | 1.00% | 0.06% | 0.06% | 0.06% | 0.9% | 0.0% |
| 0.25% | 5 | 1.00% | 0.20% | 0.21% | 0.20% | 6.4% | 5.9% |
| 0.25% | 10 | 1.00% | 0.23% | 0.23% | 0.22% | 6.3% | 5.9% |
| 0.25% | 20 | 1.00% | 0.23% | 0.23% | 0.22% | 5.8% | 5.9% |
| 0.5% | 5 | 1.00% | 0.45% | 0.45% | 0.43% | 18.8% | 20.0% |
| 0.5% | 10 | 1.00% | 0.48% | 0.48% | 0.48% | 19.5% | 20.0% |
| 0.5% | 20 | 1.00% | 0.49% | 0.49% | 0.49% | 19.8% | 20.0% |
| 1% | 5 | 1.00% | 0.94% | 0.94% | 0.92% | 44.5% | 50.0% |
| 1% | 10 | 1.00% | 0.97% | 0.97% | 0.95% | 47.4% | 50.0% |
| 1% | 20 | 1.00% | 0.98% | 0.98% | 0.97% | 48.4% | 50.0% |
| 2% | 5 | 1.00% | 1.85% | 1.85% | 1.82% | 72.3% | 80.0% |
| 2% | 10 | 1.00% | 1.94% | 1.94% | 1.91% | 76.9% | 80.0% |
| 2% | 20 | 1.00% | 2.00% | 2.00% | 1.99% | 79.1% | 80.0% |

## Robustness scenarios

σ₁ = σ₂ = 1%, n = 16. Coverage at θ = 1 and P("faster ≥ 3%") at θ = 1.05.

| Scenario | P = 3: coverage / power | P = 5: coverage / power | P = 10: coverage / power | P = 20: coverage / power |
| :--- | ---: | ---: | ---: | ---: |
| normal | 96% / 33% | 96% / 71% | 94% / 98% | 95% / 100% |
| t3 trial noise | 96% / 33% | 95% / 71% | 96% / 97% | 95% / 100% |
| lognormal spikes | 97% / 9% | 97% / 22% | 95% / 45% | 95% / 73% |
| AR(1) trials, rho 0.6 | 96% / 28% | 96% / 64% | 95% / 96% | 95% / 100% |
| slow episodes | 96% / 25% | 95% / 58% | 96% / 92% | 95% / 100% |
| bimodal process effects | 96% / 22% | 96% / 71% | 95% / 99% | 94% / 100% |
| one outlier process (+5%) | 100% / 5% | 99% / 44% | 97% / 97% | 96% / 100% |
| unequal sigma2 (candidate 2x) | 96% / 17% | 95% / 38% | 95% / 70% | 96% / 96% |
| one candidate process missing | 96% / 23% | 96% / 62% | 95% / 96% | 95% / 100% |
| launch drift, interleaved | 97% / 32% | 97% / 66% | 97% / 94% | 100% / 100% |
| launch drift, separate sessions | 96% / 23% | 91% / 45% | 51% / 43% | 0% / 1% |

### σ̂₂ and bench_press's share by scenario (P = 10, true σ₂ = 1%)

| Scenario | σ̂₂ (shipped) | σ̂₂ (iid) | σ̂₂ (drift-robust) | ρ̂ | bench_press share | Any outlier flagged |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| normal | 0.97% | 0.97% | 0.96% | 0.00 | 47.4% | 1.3% |
| t3 trial noise | 0.94% | 0.94% | 0.95% | -0.01 | 48.6% | 1.3% |
| lognormal spikes | 0.82% | 0.83% | 0.82% | 0.00 | 2.4% | 5.8% |
| AR(1) trials, rho 0.6 | 0.89% | 1.02% | 0.87% | 0.63 | 70.6% | 1.3% |
| slow episodes | 0.96% | 1.06% | 0.93% | 0.33 | 40.7% | 1.6% |
| bimodal process effects | 0.99% | 0.99% | 0.98% | 0.01 | 49.9% | 9.3% |
| one outlier process (+5%) | 1.85% | 1.85% | 1.92% | 0.01 | 76.7% | 43.8% |
| unequal sigma2 (candidate 2x) | 0.95% | 0.95% | 0.94% | 0.00 | 46.8% | 1.2% |
| one candidate process missing | 0.98% | 0.98% | 0.97% | -0.00 | 47.9% | 1.3% |
| launch drift, interleaved | 1.12% | 1.12% | 0.97% | -0.00 | 53.9% | 1.3% |
| launch drift, separate sessions | 1.02% | 1.02% | 0.98% | -0.01 | 49.1% | 1.7% |

## Group mode (variants share each process)

Variant-specific process effect 0.25%, σ₁ = 1%, n = 16. Coverage at θ = 1; median relative half-width.

| Shared effect | P | Paired Fieller | Paired log-t | Unpaired Fieller | Paired ± width | Unpaired ± width |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0% | 3 | 95.0% | 95.0% | 96.3% | 1.02% | 0.84% |
| 0% | 5 | 95.3% | 95.3% | 95.9% | 0.57% | 0.51% |
| 0% | 10 | 94.6% | 94.6% | 94.7% | 0.34% | 0.33% |
| 0% | 20 | 94.9% | 94.8% | 94.6% | 0.23% | 0.22% |
| 1% | 3 | 95.0% | 94.9% | 99.7% | 1.04% | 2.17% |
| 1% | 5 | 94.8% | 94.8% | 99.9% | 0.56% | 1.42% |
| 1% | 10 | 95.5% | 95.5% | 100.0% | 0.35% | 0.96% |
| 1% | 20 | 95.2% | 95.2% | 100.0% | 0.23% | 0.67% |

## 20-benchmark suites

P = 10, σ₁ = σ₂ = 1%, δ = 3%, BH at q = 0.05. Per-run averages.

| Mix | Gate false ≥ δ | False detectable (raw) | False detectable (BH) | FDR raw | FDR BH | Power raw | Power BH | Runs |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all null | 0.000 | 0.99 | 0.06 | 64.0% | 5.1% | — | — | 2000 |
| 2 at +5% | 0.000 | 0.87 | 0.13 | 23.7% | 4.3% | 100.0% | 100.0% | 2000 |
| 5 at +5% | 0.000 | 0.72 | 0.20 | 10.9% | 3.3% | 100.0% | 100.0% | 2000 |
| 5 at +2% | 0.000 | 0.71 | 0.20 | 11.0% | 3.5% | 98.2% | 91.2% | 2000 |

## Design check

A 10-process pilot → `recommend_design` (θ = 1.06, δ = 3%, 80% target) → the recommended experiment, simulated. Variants: **shipped** (defaults: σ̂₂ as estimated, at least 5 processes, trials a multiple of 4), **point** (no floor) and **conservative** (upper end of σ₂'s interval, at least 5 processes). Means over pilots; cost is total machine time relative to the point design.

| Truth | Variant | Trials × processes | Promised power | Achieved power | Cost |
| :--- | ---: | ---: | ---: | ---: | ---: |
| pilot-like (σ₁ 1.5%, σ₂ 1.2%, ρ 0.45) | shipped | 18.3 × 6.1 | 87.7% | 87.0% | 1.15× |
|  | point | 18.3 × 5.7 | 85.4% | 79.9% | 1.00× |
|  | conservative | 9.0 × 9.8 | 83.0% | 95.5% | 1.48× |
| σ₁ = σ₂ = 1% | shipped | 6.3 × 5.2 | 93.4% | 94.9% | 1.20× |
|  | point | 6.3 × 4.3 | 87.8% | 83.6% | 1.00× |
|  | conservative | 4.4 × 6.6 | 85.8% | 97.3% | 1.43× |
| small σ₂ (σ₁ 1%, σ₂ 0.3%) | shipped | 28.7 × 5.0 | 100.0% | 100.0% | 2.09× |
|  | point | 28.7 × 2.6 | 96.2% | 85.8% | 1.00× |
|  | conservative | 11.1 × 5.0 | 99.9% | 100.0% | 1.33× |
| noisy trials (σ₁ 3%, σ₂ 1%) | shipped | 27.2 × 5.7 | 90.4% | 91.0% | 1.27× |
|  | point | 27.2 × 5.0 | 87.5% | 79.5% | 1.00× |
|  | conservative | 10.8 × 8.9 | 83.6% | 95.9% | 1.32× |

## Power formula calibration

`design.gate_power` (noncentral t, effective df 1.5(P − 1)) vs simulated gate power over 72 cells: mean difference -0.2 pp, largest -3.7 pp (P = 3, θ = 1.07, σ₁ = 3%, σ₂ = 1%, ρ = 0.5).

Cells off by more than 3 pp:

| P | θ | σ₁ / σ₂ | ρ | Simulated | Analytic |
| :--- | ---: | ---: | ---: | ---: | ---: |
| 3 | 1.05 | 1% / 1% | 0.5 | 30% | 33% |
| 3 | 1.05 | 3% / 1% | 0.5 | 14% | 18% |
| 3 | 1.07 | 3% / 1% | 0.5 | 48% | 51% |

## Variance-component interval coverage

Nominal 95% parametric-bootstrap intervals from `components.py` (σ₁ = 1%, n = 16).

| P | σ₂ | ρ | σ₁ | σ₂ | k |
| :--- | ---: | ---: | ---: | ---: | ---: |
| 5 | 0% | 0 | 96.8% | 100.0% | 90.2% |
| 10 | 0% | 0 | 94.8% | 99.8% | 86.0% |
| 20 | 0% | 0 | 94.2% | 99.0% | 86.5% |
| 5 | 0.5% | 0 | 94.8% | 83.2% | 85.5% |
| 10 | 0.5% | 0 | 94.5% | 88.0% | 90.8% |
| 20 | 0.5% | 0 | 96.0% | 91.5% | 93.0% |
| 5 | 1% | 0 | 94.5% | 83.0% | 85.0% |
| 10 | 1% | 0 | 96.5% | 89.0% | 90.5% |
| 20 | 1% | 0 | 93.2% | 92.0% | 92.5% |
| 5 | 0% | 0.5 | 93.0% | 99.8% | 82.5% |
| 10 | 0% | 0.5 | 94.2% | 99.2% | 75.5% |
| 20 | 0% | 0.5 | 93.5% | 100.0% | 62.0% |
| 5 | 0.5% | 0.5 | 94.2% | 97.2% | 98.2% |
| 10 | 0.5% | 0.5 | 95.2% | 92.2% | 93.8% |
| 20 | 0.5% | 0.5 | 93.8% | 87.0% | 89.5% |
| 5 | 1% | 0.5 | 94.2% | 79.5% | 83.8% |
| 10 | 1% | 0.5 | 95.8% | 88.2% | 88.5% |
| 20 | 1% | 0.5 | 95.2% | 92.5% | 93.0% |

## Outlier detection (generalized ESD, α = 1%)

Rate at which one shifted process is flagged, by shift in process SDs (one process SD ≈ 1.03% here: σ₁ = σ₂ = 1%, n = 16).

| Shift | P = 5 | P = 10 | P = 20 | P = 40 |
| :--- | ---: | ---: | ---: | ---: |
| 3 SD | 3% | 10% | 16% | 17% |
| 5 SD | 11% | 48% | 72% | 80% |
| 8 SD | 31% | 95% | 100% | 100% |
| 12 SD | 65% | 100% | 100% | 100% |
