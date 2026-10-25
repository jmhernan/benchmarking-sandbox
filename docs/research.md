# Research: Rigorous Benchmarking for Software Performance Changes

**Status:** Research / current-state capture. No plan, language, or design decisions made yet.
**Sources:** [rigorous-benchmarking-in-reasonable-time.md](rigorous-benchmarking-in-reasonable-time.md) (original methodology) and [literature-review-benchmarking.md](literature-review-benchmarking.md) (updated literature review).
**Provenance tags:** statements are from the docs unless tagged **[Background]** (my own general knowledge, not in the docs, so verify) or **[Unverified]** (claim from a source I have not checked).

---

## 1. Problem Statement

A software engineering team (currently working in **Dart**) wants to judge whether their performance "improvements" are real. They need a **robust, reusable testing suite** that answers, with quantified uncertainty: *"Is the new code faster or slower than the baseline, by how much, and how sure are we?"*

This project began from Kalibera & Jones, *Rigorous Benchmarking in Reasonable Time*. That work is several years old, and the literature review has since updated the picture, mainly on steady-state assumptions, dynamic stopping criteria, and CI noise.

### Constraints so far
- Target codebase is Dart.
- The implementation language is **undecided**. Python is a candidate but may not suit a benchmarking tool. Julia and others are open, and a Dart implementation is possible later.
- Output of this phase: this document. `plan.md` follows.

---

## 2. Why Naive Benchmarking Fails

| Failure mode | Evidence / source |
|---|---|
| No variation reported | Of 122 top systems papers surveyed, 90 measured execution time and **71 gave no measure of variation**. |
| Speedup ratios without error bounds | 65 papers reported ratios; virtually none gave error bounds. |
| Fixed iteration counts / single process | Misses process-level and build-level variance. |
| "Stop when RSD < 3%" heuristics | Stop on temporary plateaus. They distort steady-state estimates by 9–10% (Traini 2023). |
| Hardcoded warmup (e.g. JMH) | Median warmup estimation error of 28–90 s per run (Traini 2023). |
| $p$-values | With enough samples, a 0.05% change is "significant". They say nothing about magnitude. |
| Overlapping-CI eyeballing | Not a valid test for ratios. |
| Dead-code elimination / constant folding | The compiler removes the work being measured (see §3.6). |
| Noisy shared CI runners | "Noisy neighbour" and VM-migration variance (Bencher, Japke 2026). |

---

## 3. Core Concepts

### 3.1 Hierarchical variance (Kalibera & Jones 2013, 2020)
Non-determinism enters at several levels:

| Level | What varies | Typical sources |
|---|---|---|
| 1. Iterations | Loop repetitions inside one process | GC pauses, cache state, CPU scheduling, frequency scaling |
| 2. Executions | Fresh process launches | ASLR, environment/stack layout, VM startup, initial heap |
| 3. Builds | Fresh compiled binaries | Link order, code layout, optimisation non-determinism |

Variance is decomposed into unbiased per-level components $T_i^2$:
- $T_1^2 = S_1^2$
- $T_i^2 = S_i^2 - S_{i-1}^2 / r_{i-1}$ for $i > 1$
- If $T_i^2 \le 0$, that level adds negligible variance and can be dropped, which saves build time.

### 3.2 Experiment dimensioning
Given per-level costs $c_i$, the cost-optimal repetition counts are:

$$r_i = \left\lceil \sqrt{\frac{c_{i+1}}{c_i}\cdot\frac{T_i^2}{T_{i+1}^2}} \right\rceil$$

If execution-level variance dominates iteration variance, then $r_1 = 1$. In that case it is better to launch more fresh processes than to loop longer. This is a **one-off calibration per platform/benchmark**. The cookbook suggests a pilot of $r_1=r_2=r_3=30$.

### 3.3 Effect-size confidence intervals (not $p$-values)
Performance change is the ratio $\theta = \mu_{new}/\mu_{old}$, reported with a CI. Two ways to compute it:
- **Parametric:** Fieller's theorem. Assumes approximately normal data, and the CI accounts for hierarchy-level variance.
- **Non-parametric:** hierarchical bootstrap. Resample with replacement at each level (build → execution → iteration) and take percentile bounds. This needs no Gaussian assumption.

Rule of thumb: a ratio CI from two systems is ~$\sqrt{2}$ wider than a single-system CI.

**Reporting form:** "Feature is 5.5% ± 2.5% faster than baseline at 95% confidence."
**Decision form:** flag a change only if the *entire* CI lies beyond a practical threshold (e.g. ratio < 0.97 or > 1.03).

### 3.4 Steady state is not guaranteed (newer literature)
The 2013 framework assumes runs reach an i.i.d. "independent state" after warmup. Newer work challenges that:
- About **11% of executions never reach steady state**, and over **43% of runs behave inconsistently across forks** (Antoch 2026, Traini 2023; Renaissance suite and 586 JMH benchmarks across 30 systems). **[Unverified: figures come from the lit review]**
- Performance can shift hours into a run (GC clearing soft references, metaspace growth, JIT re-optimisation).
- Antoch et al. model runs as **segments separated by changepoints**, detected with PELT. Variance is decomposed across runs, segments and baseline iteration performance. They report >20% fewer CI misses.
- Barrett et al. (2017) is cited, but the lit review does not discuss it in the body. It is the foundational "warmup blows hot and cold" result and worth reading directly.

**Implication:** the original model's "iterations become i.i.d." assumption needs a check, not a presumption.

### 3.5 Reactive / dynamic sampling (Junge 2022)
- RSD alone cannot detect active warmup. Use **lag-1 autocorrelation** $r_1$ as well: ~0.5–0.9 means warmup or trend, ~0–0.2 means roughly i.i.d.
- Two-phase protocol:
  1. Short probe (~0.5 s).
  2. Purge the cold batch if $r_1$ or RSE is too high, keeping the warmed runtime.
  3. Grow $n \to n\sqrt{2}$ until RSE < target (e.g. 1%) and $r_1 \approx 0$.
- Reported 5.5× faster convergence than conservative fixed counts (4m16s vs 23m44s). It was demonstrated in the Futhark compiler, a bachelor's thesis.

### 3.6 Harness hazards
Optimisers delete unobserved work. A harness needs a **sink/barrier** primitive: JMH `Blackhole.consume`, Google Benchmark `DoNotOptimize`/`ClobberMemory`, Rust `black_box`, Haskell `whnf`/`nf`. Dart's equivalent is not covered in the docs (see §6).

### 3.7 Warmup protocol depends on runtime (Schulle 2026)
- Julia is highly sensitive to warmup protocol: excluding first-use JIT hides cold-start cost.
- Haskell is low-sensitivity because of lazy evaluation.
- Python depends on the IPC/data transport.
- **Takeaway:** decide explicitly whether cold-start cost is part of what the team cares about. **[Unverified: preprint]**

### 3.8 CI/CD context
- **Statistical continuous benchmarking:** historical baselines on dedicated testbeds.
- **Relative continuous benchmarking:** run baseline and candidate **back-to-back/interleaved in the same job**, so host noise cancels. This also matches the 2013 cookbook's "interleaved runs".
- **Changepoint detection (PELT)** over commit streams: flags persistent step changes and ignores transient spikes.

### 3.9 Estimator options: hierarchical bootstrap vs Bayesian **[Background: not in the docs; verify]**
Treat these as competing estimators to compare empirically, not a choice to make now.

**Hierarchical bootstrap**
- Needs no distributional assumption. It is easy to implement in any language and easy to explain.
- *Resampling level matters.* Resampling with replacement at every level tends to overstate variance. A common recommendation is to resample the top level with replacement and lower levels without, but test this by simulation.
- *Few top-level units* (3–5 builds or a handful of runs) make percentile intervals undercover. Consider BCa or bootstrap-t, and work on the log-ratio scale.
- *Autocorrelated iterations* make i.i.d. resampling invalid (see Appendix A). Resample whole runs or segments, or use a block bootstrap.

**Bayesian hierarchical model** (e.g. log-time with build, run and iteration effects, giving a posterior on the speedup ratio)
- Partial pooling handles few builds/runs better than the bootstrap.
- It fits the decision rule directly: P(faster by more than the threshold), P(practically equivalent) and P(slower) against a ROPE (region of practical equivalence), including a real "no meaningful change" outcome.
- It can use history as priors and fits sequential stopping ("stop when the posterior is decisive against the ROPE").
- The likelihood is flexible: Student-t, mixtures, AR(1) errors, changepoint models.
- Costs: prior sensitivity, MCMC runtime and diagnostics, risk of confident wrong answers under misspecification, and the need to explain credible vs confidence intervals.
- Tooling: mature in Python (PyMC, cmdstanpy), Julia (Turing.jl) and R (brms); essentially absent in Dart. That reinforces a Dart runner that emits raw measurements, with analysis in another language.

**Suggested approach:** keep the estimator pluggable (the runner-to-analysis data format is the contract). Use the hierarchical bootstrap as the baseline and Bayesian as a comparison. Decide with a simulation study on synthetic data with known effects (hierarchical variance, segment shifts, bimodality, autocorrelation, small run counts), comparing coverage, false-positive rate and power for Fieller, bootstrap and Bayesian.

Related work, now verified: Furia, Feldt & Torkar (TSE 2021) on Bayesian data analysis in software engineering and Bulej et al. (ICPE 2020) on duet/paired benchmarking are in [bayesian-literature.md](bayesian-literature.md) §8, which collects all sources for the Bayesian option (plan Part B). Davison & Hinkley, *Bootstrap Methods and their Application* (Cambridge University Press, 1997), is the reference for the bootstrap estimator.

---

## 4. Reference Pipeline (from the literature review)

```
1. Calibration & dimensioning   -> measure c_i, T_i^2; derive r_1, r_2
2. Isolated runner & warmup     -> fresh process forks, sink primitives, r_1/RSE monitoring, purge cold batches
3. Changepoint / segment-aware  -> PELT segments, segment-aware means and variance
4. Effect-size reporting + CI   -> interleaved baseline vs candidate, 95% ratio CI (Fieller / bootstrap), threshold gate
```

### Where the two documents agree and differ

| Topic | 2013 methodology doc | Literature review (newer) |
|---|---|---|
| Variance hierarchy | 3 levels, core model | Same, extended with segments |
| Steady state | Assumed reachable (i.i.d.) | Frequently not reached; must be tested |
| Number of iterations | Calibrated once via $r_i$ | Also adaptive at runtime (RSE + $r_1$) |
| Comparison statistic | Fieller CI on ratio | Fieller **or** hierarchical bootstrap |
| Environment | Interleaved runs | Same-job relative runs in CI; PELT over history |
| Tooling hazards | Not covered | Compiler barriers / blackholes |

The two approaches are **not mutually exclusive**. Static dimensioning picks a budget up front, and reactive checks validate that the assumptions held. How to combine them is an open design question (§7).

---

## 5. Source Quality Notes (read before relying on this)

- **Primary, peer-reviewed / established:** Kalibera & Jones 2013 and 2020; Barrett et al. 2017; Traini et al. 2023.
- **Weaker or less verified:** Schulle (2026, Research Square preprint); Junge (2022, bachelor's thesis); and the secondary sources "JVM Tools Guide", "Good GitHub Report" and Bencher docs. The Antoch (2026) and Japke (2026) papers are recent and I have not independently verified them. **Action:** confirm key numbers (11%, 43%, >20%, 5.5×) against the originals before they appear in any plan or team-facing document.
- **Small inconsistencies in the docs:** the time budget is called $C$ in one and $T$ in the other (clashing with $T_i^2$). The lit review states Kalibera & Jones "prove" optimality, which holds under the model's assumptions. The 30×30×30 pilot size is given as a recipe and is not derived.
- **Evidence is JVM/systems-heavy.** Little of it studies Dart, so Dart-specific behaviour is currently an **assumption** (see §6).

---

## 6. Dart-Specific Considerations **[Background: not in the docs; verify]**

- Dart can run as a **JIT VM** (e.g. `dart run`), as **AOT native** (`dart compile exe`), or compile to **JavaScript** (`dart compile js`). Each has a different warmup and variance profile. JIT has warmup and possibly non-steady behaviour. AOT largely removes JIT warmup but still has GC, layout and OS variance.
- **Level-3 (build) variance** may be small for AOT/JS builds, but this is an empirical question that the calibration experiment should answer. It determines whether rebuilds are worth their cost.
- Dart has a `benchmark_harness` package, which is a simple loop timer. It likely lacks multi-process, hierarchical and CI-ratio support and has no sink primitive documented here. Whether it handles dead-code elimination needs checking.
- If the team ships **Flutter** apps, the relevant metrics may be frame times or startup rather than function runtime. That affects what "a benchmark" means.
- **Metrics beyond wall-clock** (memory/RSS, allocation, binary size, throughput) may matter. The literature here focuses on execution time.

---

## 7. Open Questions

### About the team and target
1. What are the benchmark targets: pure Dart libraries, server code, CLI tools, Flutter apps? Which runtime mode (JIT / AOT / JS) matters in production?
2. What is the metric: wall-clock time, memory, throughput, startup time, frame time?
3. What practical threshold counts as meaningful (3%? 5%)?
4. How long can a benchmark run take, and is there a CI time budget?
5. Does the team have dedicated hardware, or only shared CI runners?
6. What do their current "improvement" claims and measurements look like? Collecting 2–3 real examples would ground everything else.

### About the sample data (see Appendix A)
- Confirm the **unit** (assumed microseconds, from the engineer's recollection) and what was timed.
- What are the four files: different benchmarks, or different runs of the same one? Which runtime mode (JIT/AOT/JS) and which code version (baseline, new, or mixed)?
- Is the first line the true first iteration, with no discarded warmup?
- Is there a replicate set (multiple processes per version) so Level-2 variance can be estimated?

### About methodology
7. Should the suite include **both** static dimensioning and reactive stopping, or just one?
8. Fieller vs hierarchical bootstrap as the default, or both for cross-checking?
9. Is cold-start/first-use cost in scope (Schulle) or only steady-state?
10. How should non-steady-state runs be handled: exclude, flag, or segment-analyse (PELT)?
11. Is a build level (Level 3) practical for this team, or will it be skipped when $T_3^2$ is negligible?
12. How should we validate the suite itself? One option is synthetic benchmarks with *known injected* slowdowns, to measure false-positive and false-negative rates. This is not covered in either doc and is likely essential.

### About implementation (deferred)
13. **Language:** decide after requirements are clear. Possible separation: the *harness/runner* must run Dart code in fresh processes, while the *analysis/statistics* can live in any language. Candidates for the analysis side (Python, Julia, R) have mature bootstrap, changepoint (e.g. `ruptures`, `changepoint`) and stats libraries. A Dart implementation would lower friction for the team but has fewer statistics libraries. **[Background]**
14. Should the harness target Dart only, or be language-agnostic (launch any command, parse output)?

---

## 8. Candidate Capability List (inputs for `plan.md`, not commitments)

- Multi-process runner with randomised/interleaved baseline vs candidate execution
- Calibration experiment: estimate $c_i$, $T_i^2$, and output $r_i$
- Warmup / steady-state diagnostics: lag-1 autocorrelation, RSE, changepoint segmentation
- Ratio CI engine (Fieller and hierarchical bootstrap)
- Threshold-based decision gate and human-readable report
- Environment capture (CPU, OS, Dart SDK version, flags, runtime mode) for reproducibility
- CI integration (same-job relative comparison)
- Self-validation harness with synthetic, known-effect workloads
- Dead-code-elimination protection primitives

---

## 9. References

1. Kalibera, T. & Jones, R. (2013). *Rigorous Benchmarking in Reasonable Time.* ISMM.
2. Kalibera, T. & Jones, R. (2020). *Quantifying Performance Changes with Effect Size Confidence Intervals.* arXiv:2007.10899.
3. Antoch, J. et al. (2026). *Experimental Evaluation Methodology for the Era of No Steady Performance.* OOPSLA / PACMPL.
4. Traini, L. et al. (2023). *Towards effective assessment of steady state performance in Java software: are we there yet?* Empirical Software Engineering 28:13.
5. Schulle, A. (2026). *The Warmup Protocol Problem: JIT, GC, and Lazy Evaluation Effects on WRSS in Julia, Haskell, and Python.* Research Square preprint.
6. Junge, A. (2022). *Reactive Benchmarking: Benchmarking in the Futhark Compiler.* BSc thesis, University of Copenhagen.
7. Japke, N. et al. (2026). *Towards an Optimized Benchmarking Platform for CI/CD Pipelines.* arXiv.
8. Bencher (2023/2026). *How to Track Benchmarks in CI with Bencher.* Documentation.
9. JVM Tools Guide (2026). *JMH tutorial: microbenchmark Java code without JIT pitfalls.*
10. Good GitHub Report (2026). *Load testing and performance benchmarking tools: A field guide.*
11. Barrett, E. et al. (2017). *Virtual Machine Warmup Blows Hot and Cold.* OOPSLA / PACMPL.

---

## Appendix A. Initial Sample Data ([data/](../data))

**Provenance (unconfirmed):** four single-column text files of integers, one per line, in run order: `data_10.txt`, `data_100.txt`, `data_1000.txt`, `data_10000.txt` (line counts in the names). Unit is **assumed to be microseconds**, from a colleague's recollection. The process, benchmark and Dart runtime mode are unknown. They look like per-iteration timings from a single process each (Level 1 only).

**The files are independent series, not truncations of one run.** None is a prefix of another, and each starts at a different level. Do not treat them as one experiment at different lengths.

| File | n | min | median | mean | p90 | p99 | max | sd | lag-1 autocorr |
|---|---|---|---|---|---|---|---|---|---|
| data_10 | 10 | 2318 | 2494 | 5628 | 32728 | 32728 | 32728 | 9529 | 0.03 |
| data_100 | 100 | 177 | 381 | 1189 | 2407 | 15464 | 15464 | 2007 | 0.52 |
| data_1000 | 1000 | 147 | 171 | 198 | 257 | 558 | 1401 | 88 | 0.24 |
| data_10000 | 10000 | 136 | 139 | 154 | 194 | 281 | 585 | 32 | 0.46 |

(Computed with plain Python over the raw files. Values in the assumed µs.)

### Observations
- **data_10:** entirely inside a ~2,300–2,800 plateau after a 32,728 first value. Never reaches the fast code, so it is useless for steady-state estimation. It is useful only as a "too few iterations" example.
- **data_100:** a classic JIT warmup curve. It starts at 9,528, sits on a ~2,300–2,400 plateau, spikes to 15,464 (likely a compile event), then decays through ~1,000 and ~400 to ~180. Roughly the first 65 of 100 iterations are warmup, and the median (381) and mean (1,189) are meaningless without discarding it. This is the best fixture for warmup detection.
- **data_1000:** starts already warm (~200) and drifts down to ~150 (block medians: 202 → 182 → 181 → 186 → 165 → 170 → 161 → 153 → 192 → 158). It has heavy upward outliers (max 1,401, p99 558).
- **data_10000:** settles near 138–139 after a slow descent. Block-of-1000 medians: 145, 145, 140, 138, 138, 138, 138, 138, 138, 139. That is about a 5% drift over the first ~3,000 iterations. The baseline is extremely tight: in the second half, 138 appears in ~38% of values and 137–139 in ~65%. Integer quantisation is therefore visible (~0.7% resolution). Roughly 15–27% of iterations in each block exceed 1.15× the block median. The final ~40 iterations show a brief excursion (286, 238, 455, then 157–169) before the trailing window returns to ~142, so it is a transient bump, not a confirmed new segment.

### Implications
1. **i.i.d. fails.** Plateaus of near-identical values give high lag-1 autocorrelation (0.46 for data_10000, 0.52 for data_100). An iteration-level bootstrap or a plain standard error would badly understate uncertainty. Use run-level or block resampling, or a segment/changepoint model.
2. **Mean vs median is a requirement question.** Spikes pull the mean ~11% above the median in data_10000 (154 vs 139). Is the target typical time or total time including pauses?
3. **Right-skewed, heavy-tailed.** Work on the log scale, and consider Student-t or mixture models in the Bayesian option.
4. **Warmup purging needs automation** (lag-1 + RSE, or changepoints). In data_100 most of the run is warmup.
5. **Limits of this data.** One series per file means no $T_2^2$ or $T_3^2$ can be estimated, and there is no baseline-vs-candidate pair. It supports Level-1 behaviour, warmup detection and changepoint/estimator stress tests, but not the dimensioning formula or a speedup CI.
6. **Fixture value.** The four files cover distinct regimes (never warmed, full warmup, drifting, long-run spiky). Together they make a useful initial test set for the warmup detector and as realistic noise for the simulation study in §3.9.

### A.2 Exploratory analysis results

Code: [sandbox/analyze.py](../sandbox/analyze.py) (Python 3.14 in conda env `perfBench`; numpy, scipy, polars, matplotlib, ruptures, statsmodels). Tables and plots: [sandbox/output/](../sandbox/output) (`results.txt`, CSVs, `data_*.png`, `bootstrap_se_vs_block.png`). Seeded, 2,000 bootstrap resamples. These are **exploratory** numbers on one series per file. The method choices are mine and are listed under "Method notes" below.

**Model used.** Each series is treated as a slowly drifting *baseline* (fast mode, tracked by a rolling 10th percentile) plus *one-sided* slowdowns. Slowdowns are either isolated spikes or multi-iteration "slow episodes". Warmup is the period before the baseline reaches within 3% of its final level.

#### Warmup / steady-state start (baseline within tolerance of final level)
| Series | final baseline | start @2% | @3% (used) | @5% | @10% |
|---|---|---|---|---|---|
| data_100 | 180 | 67 | 65 | 64 | 62 |
| data_1000 | 150 | 673 | 670 | 628 | 136 |
| data_10000 | 137 | 2114 | 704 | 252 | 0 |

- **data_100:** warmup ends at iteration ~65 whatever the tolerance, which is robust. Only 35 post-warmup points remain, so statistics on this file are weak.
- **data_10000:** the start is sensitive to the tolerance (704 at 3%, 2,114 at 2%), because the baseline drifts slowly from ~147 to ~137 over the first ~2,000 iterations. Any warmup rule needs a tolerance, and the tolerance is a modelling choice, not a fact.
- A conservative "last time above tolerance" rule is useless on data_10000. The final transient excursion (iterations ~9,800–9,900) makes it flag the end of the series, which argues for the first-reach definition plus separate episode handling.

#### Changepoints (PELT, l2 on log block-medians, BIC-style penalty, shifts < 2% merged)
- **data_100:** 16 changepoints. PELT represents the decay as a staircase, so the boundary of interest is the end of the staircase (~63), which agrees with the table above.
- **data_1000:** 23 changepoints. Most are short (20–60 iteration) slow segments with medians 20–100% above the ~150–170 baseline.
- **data_10000:** 40 changepoints, forming alternating "baseline" and "slow" segments. Slow segments have median 160–190 against a baseline p10 of ~137–141.
- The count depends on the penalty and minimum segment size: 26 to 43 changepoints for data_10000 as the minimum shift goes from 10% to 1%. Many data_10000 segments are exactly 100 iterations long, which is the minimum segment size I set (5 blocks × 20). Treat boundaries as approximate.

#### Slow episodes are real, recurrent and have a signature
A finer look (10-iteration medians) shows that each slow episode in data_10000 starts with a sharp jump (~280) and decays in **steps** back to baseline over ~70 iterations: roughly 217 → 192 → 171 → 155 → 140. The same staircase recurs (around iterations 1570, 1750, 1970, 6010 and 6190). That is consistent with repeated deoptimise/re-optimise cycles. **[Hypothesis, not verified; needs the engineer or VM logs.]**
- Episodes (rolling median > 1.10× long-window baseline for ≥ 20 iterations): data_10000 has 21 episodes covering ~14% of post-warmup time, the longest being 113 iterations. data_1000 has one (iterations ~848–914), covering 20% of its post-warmup 330 iterations.
- This is the "non-steady performance" behaviour from §3.4. The data is not warmup then steady. It is a stable baseline repeatedly interrupted by multi-iteration slow regimes.
- A weak periodic component also exists: gaps of 13 and 14 iterations are the most common non-adjacent spacings between spikes, and the ACF has peaks near lags 14, 27, 41 and 55. **[Suggestive only.]**

#### Spike fraction (post-warmup; depends heavily on the rule)
| Rule | data_1000 | data_10000 |
|---|---|---|
| > median +10% | 31.8% | 25.1% |
| > median +25% | 23.9% | 16.1% |
| > median +50% | 11.2% | 7.5% |
| > median + 5×(normalised MAD) | 19.7% | 30.3% |
| > Q3 + 3×IQR (Tukey) | 4.8% | 9.9% |

The answer ranges 7–30% for data_10000, so "spike fraction" has no rule-free value. The MAD rule is unusable on this data: the baseline is so tight (MAD ≈ 1.5 µs after quantisation) that normal fast-mode jitter gets flagged. A relative threshold tied to the practical-significance threshold is easier to defend.

#### Uncertainty: block bootstrap vs naive (data_10000, post-warmup n = 9,296)
Circular block bootstrap, 95% percentile intervals:

| Statistic | point | iid (block 1) SE | block 100 SE | block 100 95% CI | block 250 SE |
|---|---|---|---|---|---|
| mean | 153.4 | 0.33 | 1.33 | 150.9 – 156.1 (±1.7%) | 1.36 |
| median | 138 | 0.49 | 0.62 | 138 – 140 | 0.78 |
| 10% trimmed mean | 145.8 | 0.25 | 1.06 | 143.8 – 147.9 (±1.4%) | 1.07 |

- The naive iid bootstrap understates the SE of the mean by about **4×** (0.33 vs ~1.35), so its intervals (±0.4%) are badly overconfident. The SE stops growing at block lengths of ~100–250, matching the ~70–110-iteration episode length, so ~100 is a defensible block length here.
- **Effective sample size** (ACF-based): ~474 of 9,296 iterations (5%). The ESS-based SE of the mean is 1.47, which is the same order as the bootstrap plateau (~1.35).
- The median is far less affected, but note quantisation: with integer values near 138, the iid interval collapses to [138, 139], which is false precision.
- **data_1000 (post-warmup n = 330) is too short to be reliable.** The SE keeps growing with block length (mean: 5.5 → 11.4) and never plateaus, because one big episode dominates. Intervals are wide (mean ±10%) and block lengths above ~50 are not trustworthy. About 330 iterations containing one episode cannot represent the variation.
- data_100 post-warmup (n = 35) was not bootstrapped (too small). data_10 was skipped entirely.

#### Method notes and caveats
- Warmup tolerance (3%), episode threshold (+10%, ≥ 20 iterations), changepoint penalty and minimum shift (2%), and baseline quantile (p10) are my choices for exploration, not established parameters. They need their own validation, ideally on synthetic data with known structure.
- My first attempt (PELT on a smoothed series with a fixed penalty) over-segmented, and my first steady-state rule was fooled by the end-of-series excursion. Both were replaced. This shows that these detectors are sensitive and need testing before anyone trusts them.
- Percentile bootstrap intervals are used. BCa or bootstrap-t were not compared. No coverage study has been done, so the CIs above are indicative only.
- The data is **one process per file**. The block bootstrap here captures Level-1 (iteration) dependence only. Between-process (Level 2) and between-build (Level 3) variance remain unmeasured, so none of these intervals are a full speedup CI.

### A.3 What this changes for the design
1. **Resample in blocks (or by segment/run), never by iteration.** The 4× SE understatement is concrete evidence for the earlier concern. Block length should be chosen from the data (e.g. the SE plateau), not fixed.
2. **Handle slow episodes explicitly** (detect, report their share of time, and decide whether they belong in the metric). They are 14–20% of post-warmup time in these samples, so the mean and median could give different verdicts on a code change.
3. **Warmup detection needs a documented tolerance and sensitivity check.** The same series can lose 0% to 21% of its iterations depending on a 10% vs 2% tolerance.
4. **Run length matters.** 330 post-warmup iterations containing one episode were not enough, while ~9,000 iterations gave a usable interval for the mean (±1.7%). A required-length or reactive stopping rule should consider episodes, not just RSE.
5. **Validate the detectors on synthetic data** with known baselines, drift, episodes and spikes before using them to judge real changes (see §7, Q12). The method for that is Appendix B.

---

## Appendix B. Synthetic Data Method (design only; not yet run)

**Purpose:** give the detectors and estimators from Appendix A a ground truth they can be scored against. The real data cannot do this, because it has no known answer and only one process per file.

**Code:** [sandbox/synth.py](../sandbox/synth.py). Nothing runs on import. Generation and calibration are triggered manually (commands in the file's docstring). The file passed a syntax check only. **It has not been run, and its default parameters are uncalibrated starting values.**

### B.1 Generative model
Per iteration $t$, in the assumed µs:

$$x_t = \text{round}\Big(\underbrace{b\cdot m\cdot\theta\,(1+a\,e^{-t/\tau})\,J(t)}_{\text{true baseline level}}\;(1+E_t)(1+S_t)(1+P_t)\,e^{\sigma\varepsilon_t}\Big)$$

| Component | Model | Initial setting and basis |
|---|---|---|
| Baseline $b$, drift $a, \tau$ | asymptote plus exponentially decaying excess | 137; +7% decaying over ~700 iterations (data_10000) |
| JIT warmup $J(t)$ (optional) | logistic in log-space: ratio $r$ at the start, 1 later | $r{=}13$, midpoint 35 (data_100: ~2,400 → ~180) |
| Slow episodes $E_t$ | Poisson arrivals; jump of lognormal size, exponential decay (random $\tau$); overlaps take the max | rate 0.0023/iteration, peak ~+90%, $\tau\approx30$ (the stepwise decay in A.2) |
| Spikes $S_t$ | short runs (persistence 0.3), lognormal excess | ~10% of iterations, median excess +25% (**guess**, to calibrate) |
| Periodic $P_t$ (optional) | slot every ~13.5 iterations, fires with some probability | off by default; +15% when on (weak signal in A.2) |
| Jitter $\sigma$ | multiplicative Gaussian | 0.3% |
| Quantisation | round to integers | real data is integer-valued |
| Process effect $m$ | $e^{\sigma_{L2}Z}$, one draw per process | **assumption**: no replicate data exists |
| Speedup $\theta$ | multiplies the whole level | the known truth for change-detection tests |

Each `Series` object also returns the **ground truth**: the true baseline level, the episode mask (excess > 10%), the spike mask, the true warmup end (last iteration the baseline is more than 3% above its asymptote), and the asymptote. `long_run_mean()` gives the estimand (long-run mean and median) for coverage studies by simulating 2M stationary iterations.

Presets: `data10000`, `data1000` (drift, more episodes) and `jit100` (JIT warmup curve).

### B.2 Calibration (to do before trusting any result)
`compare` runs the *same* analysis pipeline as Appendix A on a real file and on N synthetic series, printing: warmup end, median, mean, p90, p99, lag-1 autocorrelation, fraction above +10/25/50%, episode count and share, and ESS ratio. Parameters (especially spike rate/size and episode decay) should be adjusted until the real value sits inside the synthetic spread. Targets from data_10000: median ~138, mean ~153, p90 194, p99 281, lag-1 ~0.49, ESS ratio ~0.05, ~21 episodes covering ~14% of time. Agreement on summary statistics does not prove the model is right. Check the plots too.

### B.3 Planned validation experiments (design; to be built after the generator is calibrated)
1. **Warmup detector:** detected start vs `warmup_end`. Report the error distribution across tolerances (2/3/5/10%) and series lengths.
2. **Episode detector:** iteration-level precision/recall against the episode mask, plus episode-count error.
3. **Single-series coverage:** 95% CIs for the long-run mean and median from iid bootstrap, circular block bootstrap (block $n^{1/3}$, 100, 250) and the ESS-based normal interval. Measure empirical coverage and width, with detected and oracle warmup discard separately, to isolate detector error from estimator error.
4. **Baseline-vs-candidate ratio** with $P$ processes per version (e.g. 5 and 10), $\sigma_{L2}\in\{1\%, 3\%\}$, and true $\theta\in\{1.00, 1.02, 1.05, 1.10\}$. Compare ratio CIs from:
   - a naive pooled iid bootstrap over all iterations,
   - a process-level bootstrap on per-process means,
   - Fieller's theorem on per-process means,
   - a log-ratio Welch interval.

   Metrics: coverage of true $\theta$, false-positive rate at $\theta=1.00$ and at $\theta=1.02$ (below a 3% gate), power at $\theta\ge1.05$, and how often a $p<0.05$ test fires at the tiny effect (the $p$-value trap from §2.1).
5. **Bayesian hierarchical model:** deferred. It needs PyMC or Stan, which means installing packages (to be approved first). It would join experiment 4 as a fifth estimator.

### B.4 Limits of this approach (stated up front)
- The generator encodes **my reading of one process's data**. Any estimator tuned to it may be overfit to it. The between-process effect $\sigma_{L2}$ and any build-level effect are pure assumptions until replicate runs exist, so experiment 4 results depend directly on them (hence the sweep).
- The synthetic episodes decay smoothly, while the real ones decay in steps. The hypothesised JIT cause of episodes is unverified.
- Coverage results are conditional on the model. They say how methods behave when the data looks like this, not how they behave on the team's real code.
