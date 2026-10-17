# Making bench_press verdicts statistically valid: a proposal

**Audience:** the bench_press maintainer(s).
**Scope:** statistics only: what the verdicts claim, when the claim holds, and how to make it hold.
**Basis:** bench_press at commit [`e21db31`](https://github.com/kevmoo/bench_press/tree/e21db31). Every number in §6 comes from [simulate.py](simulate.py) (seeded; runs in seconds with numpy and scipy).

---

## 1. Summary

bench_press already handles the hard engineering parts: dead-code-elimination barriers, adaptive warmup, ~100 ms batches, ABBA/BAAB interleaving and a Fieller ratio interval. This proposal adds four statistical pieces on top:

| # | Contribution | Problem it solves | Headline evidence |
|---|---|---|---|
| 1 | **Use the process as the unit of analysis** | The current 95% interval comes from batches inside one process. It ignores variation *between* processes, so it is too narrow. | With 1% batch noise and 0.5–1% process-to-process variation, the "95%" interval covers the truth only 39–65% of the time. Identical binaries are flagged as faster or slower 35–61% of the time. With 5–10 processes per version, the interval covers 95%. |
| 2 | **A practical-significance gate** | "The interval excludes 1.00×" means *any* detectable difference. With enough data, a 1% change looks like a win. | At a true +2%, today's rule says "faster" 98% of the time. The gate says "faster ≥3%" 0% of the time and can positively report "no meaningful change". |
| 3 | **Validation of the method itself** | A "95%" label is a claim, and no test currently checks it. | A simulation harness plus an A/A protocol on real hardware report coverage, false-alarm rate and power. |
| 4 | **Experiment design** | How many processes, and how many batches each? | Per-level variance estimates give the cost-optimal split (Kalibera & Jones) and the processes needed for a target precision or power. |

The fix reuses `FiellerInterval.compute` unchanged. Only its inputs change: per-process means instead of per-batch means.

---

## 2. What bench_press does today (statistically)

- Each benchmark × target × matrix coordinate runs in **one process** (`run_command.dart`, `_executeFileCoordinates`).
- Within that process it records `trials` batch means (default 15; each batch is ~100 ms of calls).
- The delta verdict (`markdown_reporter.dart`, `_computeFiellerVerdict`) calls `FiellerInterval.compute(sampleA: base.rawTrialsNs, sampleB: cur.rawTrialsNs)`. Its inputs are the batch means of one baseline process and one candidate process. It uses Welch–Satterthwaite df and estimates $R=\bar x_A/\bar x_B$, so values above 1 mean the candidate is faster.
- The verdict is *unresolved* if either side fails `isStable` or Fieller's $g\ge1$. Otherwise it is *faster* or *slower* if the 95% interval excludes 1.00×, and *neutral* if it contains 1.00×.
- `--diff <git-ref>` loads a **previously saved** results JSON from that ref and compares it with a fresh run. The two sides come from different sessions.

Fieller's formula is implemented correctly. The issue is the **sampling unit** it is applied to.

---

## 3. Contribution 1: the process as the unit of analysis

### 3.1 Model

Timing variation is nested (Kalibera & Jones 2013). For version $v$, process $p$ and batch $j$:

$$
x_{vpj} = \mu_v \,\alpha_{vp}\,(1+\varepsilon_{vpj}),\qquad
\log\alpha_{vp}\sim N(0,\sigma_2^2),\quad \varepsilon_{vpj}\sim N(0,\sigma_1^2)
$$

- $\sigma_1$ is **within-process** batch-to-batch noise: GC, scheduling, frequency changes.
- $\sigma_2$ is the **between-process** effect. Each fresh process gets its own memory layout (ASLR), initial heap, code placement and so on, and stays at that level for its whole life.

A third level, between builds or sessions, sits above these. It matters for `--diff` against a stored JSON (§3.5).

### 3.2 Why the current interval is too narrow

For one process with $n$ batches, the true variance of the version mean is $\mu_v^2(\sigma_2^2 + \sigma_1^2/n)$, but bench_press estimates only $\mu_v^2\,\sigma_1^2/n$.

The between-process term $\sigma_2^2$ is invisible from inside one process and doesn't shrink with $n$. The reported standard error is too small by the factor

$$
k=\sqrt{1+n\,\sigma_2^2/\sigma_1^2}
$$

(the *design effect* of survey sampling; $\sigma_2^2/(\sigma_1^2+\sigma_2^2)$ is the intraclass correlation). So the nominal 95% interval actually covers about

$$
\text{coverage}\approx 2\,\Phi(1.96/k)-1 .
$$

Two consequences run against intuition:
- **Better batching makes it worse.** bench_press's long 100 ms batches make $\sigma_1$ small, which makes $k$ large.
- **More trials make it worse.** $k$ grows with $n$, so the interval narrows around the process's own offset $\alpha_p$ rather than the true $\mu$ (§6, E2).

### 3.3 The fix

1. Run $P$ fresh processes per version, interleaving baseline and candidate launches in random order.
2. Reduce each process to its mean, $\bar x_{vp}$.
3. Apply the existing `FiellerInterval.compute` to the $P$ baseline means against the $P$ candidate means.

Process means are independent, and each one's variance already includes both $\sigma_2^2$ and $\sigma_1^2/n$, so the interval is valid **without estimating either component**. The analysis assumes only that processes are independent. Autocorrelation, drift or non-normal noise *within* a process does not bias it, because none of that crosses process boundaries.

Required: $P\ge2$ per version. Recommended: $P\ge5$, and $P\ge10$ when using the bootstrap (§6, E5).

### 3.4 Variance components as a diagnostic

The same data gives per-level estimates through a one-way random-effects ANOVA on $y=\log x$ (log scale, because effects are multiplicative):

$$
\hat\sigma_1^2=\text{MS}_\text{within},\qquad
\hat\sigma_2^2=\max\!\Big(0,\ \tfrac{\text{MS}_\text{between}-\text{MS}_\text{within}}{n}\Big),\qquad
\hat k=\sqrt{1+n\hat\sigma_2^2/\hat\sigma_1^2}.
$$

Reporting $\hat\sigma_1$, $\hat\sigma_2$ and $\hat k$ per benchmark shows how much a single-process interval would have been overconfident. These estimates also drive experiment design (§5).

### 3.5 Same-binary comparisons and `--diff`

- **`Benchmark.compare` / groups (variants in one binary).** A process effect *shared* by all variants cancels in the ratio, which is a real advantage of in-binary interleaving. Effects *specific* to a variant (where its code lands, and how its allocation pattern interacts with the layout) do not cancel. How much remains is an empirical question, and the A/A protocol in §4.3 measures it directly.
- **Comparing two builds or git refs.** Different binaries get independent layouts, so the full $\sigma_2$ applies.
- **`--diff` against a stored JSON.** This adds a between-session term on top: machine state, thermal conditions, background load, possibly a different host. One process on each side cannot separate any of that from the code change. The statistically sound version builds both refs and runs their processes interleaved in the same session.

---

## 4. Contribution 2: the practical-significance gate

### 4.1 Rule

Given the ratio interval $[L,U]$ ($>1$ = faster) and a threshold $\delta$ (e.g. 3%), using a band that is symmetric on the log scale:

| Verdict | Condition | Meaning |
|---|---|---|
| **Faster ≥ δ** | $L > 1+\delta$ | Confidently at least δ faster |
| **Slower ≥ δ** | $U < 1/(1+\delta)$ | Confidently at least δ slower |
| **No meaningful change** | $1/(1+\delta) < L$ and $U < 1+\delta$ | Any change is confidently smaller than δ. Optional sub-label: "detectable but < δ" when the interval excludes 1. |
| **Inconclusive** | otherwise | Not enough precision to decide relative to δ |

### 4.2 Why it matters statistically

- **It separates statistical from practical significance.** Any nonzero effect eventually excludes 1.00× as data grows. The gate asks whether the change is big enough to act on.
- **It can positively confirm that nothing meaningful changed.** "The interval contains 1.00×" is only *absence of evidence*. "The interval lies inside ±δ" is *evidence of absence*. This is the two one-sided tests (TOST) equivalence logic. A 95% interval inside the band corresponds to TOST at α = 2.5% per side; a 90% interval would give the conventional α = 5%.
- **"Inconclusive" is informative.** It says precisely that more processes are needed, and §5 says how many.
- **It needs valid intervals underneath.** A gate on top of the one-process interval inherits its overconfidence, which is why contributions 1 and 2 go together.

### 4.3 Many benchmarks at once

With $m$ benchmarks in a suite or matrix, each tested at 5%, about $0.05m$ false flags are expected per run even with correct intervals: one per run for $m=20$. With today's overconfident intervals it is about 7–12 (§6, E7). Options to discuss:
- report the expected number of false flags alongside the results;
- control the false discovery rate (Benjamini–Hochberg) across the table;
- automatically rerun flagged rows as a confirmation step.

---

## 5. Contributions 3 and 4: validation and experiment design

### 5.1 Validating the method (simulation)

The operating characteristics of the procedure, measured the way a clinical trial reports its error rates:

| Metric | Definition | Target |
|---|---|---|
| Coverage | P(interval contains the true θ) | ≈ 95% (Monte Carlo SE ±0.3 pp at 4,000 reps) |
| False-alarm rate | P(faster or slower verdict \| θ = 1) | ≈ 5% |
| False "meaningful" rate | P(faster ≥ δ \| 1 < θ < 1+δ) | ≤ 2.5% |
| Power | P(faster ≥ δ \| θ ≥ 1+δ+margin) | e.g. ≥ 80% at the planned P |
| Width | median interval width | reported, to compare estimators |

**Scenarios.** The baseline sweep is in [simulate.py](simulate.py). Robustness scenarios worth adding:
- heavy-tailed batch noise (Student t, lognormal spikes);
- within-process drift and autocorrelation;
- unequal variance between versions;
- a single outlier process;
- bimodal process effects ("good" and "bad" layouts).

**Estimators to compare:** current single-process Fieller; process-level Fieller; process-level bootstrap (percentile and BCa); a log-ratio Welch interval; and later a Bayesian hierarchical model.

### 5.2 Validating on real hardware: the A/A protocol

This is the most convincing test because it needs no model.

1. Build **one** AOT binary.
2. Launch it $2P$ times ($P$ = 15–20), randomly labelling each launch "A" or "B". Record every process's batch means.
3. **Empirical false-alarm rate:** pair A and B processes and apply today's single-process verdict to each pair. A correct procedure says faster or slower about 5% of the time. Anything well above that reproduces E1 on real hardware. With 15–20 pairs, 5% vs 35% is easy to tell apart.
4. **Variance components:** compute $\hat\sigma_1,\hat\sigma_2,\hat k$ (§3.4) on that machine for that benchmark.
5. **Same-binary variant:** repeat with a `Benchmark.compare` group whose candidate is an identical copy of the baseline. This measures how much of $\sigma_2$ cancels when variants share a binary (§3.5).
6. **Known-effect check:** add a calibrated extra cost to the candidate, such as a fixed spin loop worth ~5% of the iteration time. Then check that the interval contains the injected θ and that the gate fires.

The estimates from steps 4 and 6 also calibrate the simulation, closing the loop between §5.1 and real data.

### 5.3 Experiment design: how many processes, how many batches

On the log-ratio scale, with $P$ processes per version and $n$ batches per process:

$$
\operatorname{Var}(\log\hat\theta)\approx 2\left(\frac{\sigma_2^2}{P}+\frac{\sigma_1^2}{P\,n}\right).
$$

With $c_1$ the cost of a batch (~0.1 s) and $c_2$ the per-process overhead (startup, warmup, calibration), the total cost is $2P(c_2+n\,c_1)$. Minimising the variance for a fixed budget gives the Kalibera & Jones (2013) optimum:

$$
n^{\ast} = \sqrt{\frac{c_2}{c_1}\cdot\frac{\sigma_1^2}{\sigma_2^2}} .
$$

For a target 95% half-width $h$ on the log scale:

$$
P \approx \frac{2\cdot1.96^2\,(\sigma_2^2+\sigma_1^2/n)}{h^2}.
$$

The rule of thumb that follows: **when processes differ more than batches do, run more short processes rather than one long one.** $c_1$ is fixed by design (~100 ms), $c_2$ is easy to time from the runner, and §3.4 supplies $\sigma_1,\sigma_2$. So the tool could recommend $(P, n)$ itself after a pilot run. It could also stop adaptively once the interval is decisive relative to δ.

---

## 6. Simulation results

Model as in §3.1, with σ values in relative terms. "Current" is one process per version with Fieller on batch means and Welch df, as bench_press does today. "P = 5/10" is process-level Fieller. 4,000 replications (2,000 for E5), seed `20261017`. Reproduce with `python docs/bench_press/simulate.py`.

### E1. Identical versions (θ = 1): coverage and false alarms, n = 15 batches

| σ₁ | σ₂ | k | predicted cov. | current cov. | current false alarm | P=5 cov. | P=5 false alarm | P=10 cov. | P=10 false alarm |
|---|---|---|---|---|---|---|---|---|---|
| 1% | 0% | 1.00 | 95% | 95% | 5% | 95% | 5% | 95% | 5% |
| 1% | 0.25% | 1.39 | 84% | 85% | 15% | 95% | 5% | 95% | 5% |
| 1% | 0.5% | 2.18 | 63% | 65% | 35% | 96% | 4% | 95% | 5% |
| 1% | 1% | 4.00 | 38% | 39% | 61% | 96% | 4% | 95% | 5% |
| 1% | 2% | 7.81 | 20% | 20% | 80% | 95% | 5% | 95% | 5% |
| 3% | 0% | 1.00 | 95% | 95% | 5% | 96% | 4% | 95% | 5% |
| 3% | 0.25% | 1.05 | 94% | 94% | 6% | 96% | 4% | 96% | 4% |
| 3% | 0.5% | 1.19 | 90% | 90% | 10% | 95% | 5% | 95% | 5% |
| 3% | 1% | 1.63 | 77% | 78% | 22% | 96% | 4% | 95% | 5% |
| 3% | 2% | 2.77 | 52% | 53% | 47% | 95% | 5% | 95% | 5% |

The closed-form prediction (§3.2) matches the simulated coverage to within about 2 points. When σ₂ = 0, today's method is correct. The process-level interval holds 95% in every row.

### E2. More trials do not fix it (σ₁ = σ₂ = 1%, θ = 1)

| trials n | k | current cov. | current false alarm | P=5 cov. |
|---|---|---|---|---|
| 5 | 2.45 | 64% | 36% | 95% |
| 15 | 4.00 | 40% | 60% | 96% |
| 30 | 5.57 | 28% | 72% | 95% |
| 60 | 7.81 | 20% | 80% | 96% |
| 120 | 11.00 | 14% | 86% | 95% |

This bears directly on adaptive `--max-trials` scaling: adding trials inside one process makes the overconfidence worse.

### E3. The gate (process-level, P = 10, n = 15, σ₁ = σ₂ = 1%, δ = 3%)

| true θ | "interval excludes 1" (today's rule) | gate: faster ≥3% | gate: no meaningful change (contains 1) | gate: detectable but <3% | gate: inconclusive | gate: slower ≥3% |
|---|---|---|---|---|---|---|
| 1.00 | 5% | 0% | 95% | 5% | 0% | 0% |
| 1.01 | 53% | 0% | 47% | 51% | 2% | 0% |
| 1.02 | 98% | 0% | 2% | 50% | 49% | 0% |
| 1.03 | 100% | 3% | 0% | 2% | 95% | 0% |
| 1.05 | 100% | 98% | 0% | 0% | 2% | 0% |
| 1.10 | 100% | 100% | 0% | 0% | 0% | 0% |

- **Below δ (θ = 1.01–1.02):** the gate never claims a meaningful speedup.
- **At δ (θ = 1.03):** it is honestly inconclusive, and the 3% "faster" rate is the designed error rate at the boundary.
- **Above δ (θ = 1.05):** it detects the speedup 98% of the time.

### E4. Power: P(gate says "faster ≥3%") vs processes per version (n = 15, σ₁ = σ₂ = 1%)

| P per version | θ=1.00 | θ=1.03 | θ=1.05 | θ=1.07 | θ=1.10 |
|---|---|---|---|---|---|
| 3 | 0% | 2% | 33% | 84% | 100% |
| 5 | 0% | 2% | 69% | 100% | 100% |
| 10 | 0% | 3% | 98% | 100% | 100% |
| 20 | 0% | 3% | 100% | 100% | 100% |

### E5. Choice of estimator: process-level Fieller vs percentile bootstrap (θ = 1)

| P per version | Fieller cov. | bootstrap cov. | Fieller median width | bootstrap median width |
|---|---|---|---|---|
| 3 | 96% | 80% | 4.85% | 2.38% |
| 5 | 96% | 88% | 3.02% | 2.16% |
| 10 | 96% | 92% | 1.94% | 1.69% |
| 20 | 95% | 94% | 1.31% | 1.23% |

With few processes the percentile bootstrap is overconfident, because it cannot see variability beyond the handful of processes it resamples. Fieller's *t*-based interval is the safer default at small P. The bootstrap becomes competitive at P ≈ 20, where it is useful for skewed or outlier-prone process means.

### E6. Budget allocation (analytic; c₁ = 0.1 s, c₂ = 2 s, 120 s total, σ₁ = σ₂ = 1%)

Optimum $n^{\ast}=\sqrt{(c_2/c_1)(\sigma_1^2/\sigma_2^2)}\approx 4.5$.

| batches per process n | processes per version P | ≈95% half-width |
|---|---|---|
| 1 | 28.6 | ±0.73% |
| 2 | 27.3 | ±0.65% |
| 5 | 24.0 | ±0.62% |
| 15 | 17.1 | ±0.69% |
| 50 | 8.6 | ±0.96% |
| 200 | 2.7 | ±1.68% |

The same two minutes give an interval about 2.7× tighter when spent on many short processes instead of a few long ones. The costs here are illustrative; the real $c_2$, which includes AOT startup and adaptive warmup, should come from the A/A run.

### E7. A 20-benchmark suite with no real changes

| per-benchmark false-alarm rate | expected false flags per run | P(at least one) |
|---|---|---|
| correct 5% per benchmark | 1.0 | 64% |
| current, σ₂ = 0.5% (from E1) | 7.0 | 100% |
| current, σ₂ = 1% (from E1) | 12.1 | 100% |

---

## 7. Suggested changes to bench_press

These are listed in order of statistical value and are open for discussion; none is required in a particular form.

1. **`--processes N`**: run each benchmark × target × coordinate in N fresh processes. When comparing versions, interleave their launches in random order. Store per-process results in the JSON schema (for example, a list of runs, each with its `raw_trials_ns`). With N = 1, behaviour is unchanged, but the report notes that between-process variance was not measured.
2. **Process-level Fieller** in `_computeFiellerVerdict`, with per-process means as inputs. The existing `FiellerInterval.compute` is reused as-is.
3. **`--threshold δ`** to switch on the four-way verdict of §4.1.
4. **Diagnostics:** report $\hat\sigma_1$, $\hat\sigma_2$ and $\hat k$ per benchmark, plus a warning when $\hat k$ is large.
5. **`--diff <git-ref>` that rebuilds** the reference and runs both versions interleaved in the same session, instead of only reading a stored JSON.
6. **Later:** $(P, n)$ recommendations from a pilot run (§5.3), multiple-comparison control (§4.3), and adaptive stopping relative to δ.

---

## 8. Assumptions and limitations

- **The σ₂ values are scenarios, not measurements.** How large process-to-process variation is for Dart AOT on a given machine is the key unknown, and the A/A protocol in §5.2 is designed to measure it. If σ₂ turns out to be ≈ 0 for a benchmark, today's interval is already fine for it, and the diagnostic in §3.4 would show that.
- **The simulation model is simple:** normal, independent batches and a lognormal process effect. The robustness scenarios in §5.1 are there to test that.
- **Interval semantics:** Fieller here targets the **ratio of mean** batch times. Whether mean or median time is the right target depends on whether occasional pauses (GC, deoptimisation) count as part of the cost. That is a product decision, not a statistical one.
- **Small P:** with P < 5 the intervals are valid but wide (E4, E5). That is the honest price of not knowing σ₂.

---

## References

1. Kalibera, T. & Jones, R. (2013). *Rigorous Benchmarking in Reasonable Time.* ISMM.
2. Kalibera, T. & Jones, R. (2020). *Quantifying Performance Changes with Effect Size Confidence Intervals.* arXiv:2007.10899.
3. Fieller, E. C. (1954). *Some Problems in Interval Estimation.* JRSS B 16(2).
4. Schuirmann, D. J. (1987). *A comparison of the two one-sided tests procedure and the power approach for assessing the equivalence of average bioavailability.* J. Pharmacokinetics and Biopharmaceutics 15(6).
5. Benjamini, Y. & Hochberg, Y. (1995). *Controlling the False Discovery Rate.* JRSS B 57(1).
6. Kish, L. (1965). *Survey Sampling.* Wiley. (Design effect.)
7. Barrett, E. et al. (2017). *Virtual Machine Warmup Blows Hot and Cold.* OOPSLA.
