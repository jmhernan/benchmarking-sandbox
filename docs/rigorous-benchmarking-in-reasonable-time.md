# Rigorous Benchmarking in Reasonable Time: Core Methodology & Principles

> **Reference:** Tomas Kalibera and Richard Jones. *"Rigorous Benchmarking in Reasonable Time"* (ISMM / ACM SIGPLAN) & *"Quantifying Performance Changes with Effect Size Confidence Intervals"*.

---

## 1. Executive Summary & Core Diagnosis

Experimental evaluation is central to software engineering and systems research, yet the vast majority of performance evaluations suffer from severe methodological shortcomings:
* **Pervasive Unquantified Uncertainty:** A survey of 122 top-tier systems papers (PLDI, ASPLOS, ISMM, TOPLAS, TACO) revealed that 90 evaluated execution time, but **71 of those papers failed to provide any measure of variation** (such as standard deviation, variance, or confidence intervals).
* **Unrepeatable Ratios:** 65 of those papers quantified performance changes using ratios of execution times (speedup), yet virtually none provided error bounds for those speedup ratios.
* **Flawed Heuristics:** Standard continuous integration tools and developer practices rely on arbitrary iteration counts, single process runs, or automated "on-the-fly" heuristics (e.g., waiting for relative standard deviation to fall below 3%) that frequently fail to reach steady state or oversample unnecessarily.

**The Solution:** Kalibera and Jones establish a mathematically sound, cost-optimal benchmarking framework. Instead of arbitrary repetition or flawed significance testing, their methodology decomposes system non-determinism across a multi-level hierarchy, mathematically dimensions experiments to maximize precision per unit of time, and summarizes speedup using **effect size confidence intervals**.

---

## 2. Theoretical Foundations & Methodological Principles

### 2.1 The Failure of $p$-Values & Overlapping Confidence Intervals
Modern performance evaluations often misapply Null Hypothesis Statistical Testing ($p$-values) or look for non-overlapping standard deviation error bars:
1. **The Sample Size Trap of $p$-Values:** With a large enough sample size (common in software execution), even an infinitesimally small performance shift (e.g., $0.05\%$) becomes "statistically significant" ($p < 0.05$). A $p$-value tells us *whether* a difference is unlikely to be pure chance, but says nothing about *how large* or *practically meaningful* the difference is.
2. **The Overlap Fallacy:** Assessing whether two $95\%$ confidence intervals overlap is an improper test for ratios; two overlapping intervals do not necessarily mean there is no statistically significant difference between execution time means.

### 2.2 Execution States: Initialised vs. Independent
When running benchmarks (especially on managed runtimes like JVM, Julia, Python, or .NET), execution passes through distinct phases:
* **Initialised State (Lower Bar):** The point at which major setup overheads (dynamic linking, I/O buffer allocation, initial JIT compilation) have completed.
* **Independent State (Steady State):** The point where iteration execution times become **independently and identically distributed ($i.i.d.$)**. Autocorrelation drops toward zero, meaning an iteration's runtime is no longer influenced by previous iterations.

> **Key Rule:** Repeating measurements before reaching an $i.i.d.$ independent state introduces strong serial correlation, biasing variance and confidence interval calculations.

---

## 3. The Multi-Level Hierarchical Variance Model

Non-determinism enters software systems at multiple operational levels:
* **Level 1 (Iterations):** Loop repetitions within a single running process instance (e.g., GC pauses, CPU scheduling).
* **Level 2 (Executions):** Fresh process launches (capturing OS memory layout randomization, ASLR, environment size, and VM startup variance).
* **Level 3 (Compilations / Builds):** Fresh binary builds (capturing compiler optimization non-determinism, symbol order, and code layout effects).

### 3.1 Unbiased Variance Decomposition
To model an $n$-level experiment without statistical bias, the total variance is decomposed into unbiased level-specific variance estimators ($T^2_i$):

1. **Biased Level Sample Variance ($S^2_i$):**
   $$S^2_i = \frac{1}{\prod_{k=i+1}^{n} r_k} \frac{1}{r_i - 1} \sum_{j_n=1}^{r_n} \dots \sum_{j_i=1}^{r_i} \left( \bar{Y}_{j_n \dots j_i \bullet \dots \bullet} - \bar{Y}_{j_n \dots j_{i+1} \bullet \dots \bullet} \right)^2$$

2. **Unbiased Level Variance Estimator ($T^2_i$):**
   $$T^2_1 = S^2_1$$
   $$T^2_i = S^2_i - \frac{S^2_{i-1}}{r_{i-1}} \quad \text{for } i > 1$$

*If $T^2_i \le 0$, that specific level induces negligible variance and can be eliminated from future experiments to save build time.*

---

## 4. Experiment Dimensioning: Optimal Repetition Counts

Given a fixed time budget $C$, repeating experiments at the highest level (e.g., rebuilding binaries) is extremely expensive, whereas adding loop iterations within a warm process is very cheap.

Kalibera and Jones derive the **cost-optimal repetition counts ($r_i$)** for every non-top level:

$$r_i = \left\lceil \sqrt{ \frac{c_{i+1}}{c_i} \cdot \frac{T^2_i}{T^2_{i+1}} } \right\rceil$$

Where:
* $c_i$ = The execution time cost added exclusively by level $i$ (e.g., $c_1$ is iteration duration, $c_2$ is warmup + execution startup time, $c_3$ is build time).
* $T^2_i / T^2_{i+1}$ = The ratio of unbiased variance at level $i$ relative to level $i+1$.

### Practical Implication
* If execution-level variance ($T^2_2$) is huge compared to iteration variance ($T^2_1$), the formula dictates $r_1 = 1$ — meaning developer time is far better spent launching fresh process instances rather than accumulating iterations in a single process.
* This one-off dimensioning step per platform/benchmark eliminates guesswork and prevents under- or over-sampling.

---

## 5. Effect Size Confidence Intervals for Speedup Ratios

To compare a Baseline system ($O$, Old) against a Feature branch ($N$, New), performance change is expressed as the execution ratio $\theta = \frac{\mu_{\text{New}}}{\mu_{\text{Old}}}$.

### 5.1 Asymptotic Parametric Interval via Fieller's Theorem
Using **Fieller's Theorem**, the exact $(1 - \alpha)$ confidence interval for the execution time ratio $\frac{\bar{Y}_{\text{New}}}{\bar{Y}_{\text{Old}}}$ is:

$$\text{Ratio CI} = \frac{\bar{Y}_{\text{Old}} \cdot \bar{Y}_{\text{New}} \mp \sqrt{ \left( \bar{Y}_{\text{Old}} \cdot \bar{Y}_{\text{New}} \right)^2 - \left( \bar{Y}_{\text{Old}}^2 - h_{\text{Old}}^2 \right) \left( \bar{Y}_{\text{New}}^2 - h_{\text{New}}^2 \right) }}{\bar{Y}_{\text{Old}}^2 - h_{\text{Old}}^2}$$

Where:
* $h_{\text{Old}} = \sqrt{ t_{\alpha/2, \nu}^2 \cdot \frac{S^2_{n, \text{Old}}}{r_{n, \text{Old}}} }$ is the single-system confidence interval half-width.
* $t_{\alpha/2, \nu}$ is the critical quantile of Student's $t$-distribution with $\nu = r_n - 1$ degrees of freedom.

### 5.2 Approximating Speedup Ratio Width
If individual baseline and new system measurements have relative error half-widths $e_{\text{Old}}$ and $e_{\text{New}}$ (e.g., $\pm 2\%$), the speedup ratio uncertainty half-width $e_{\text{ratio}}$ is approximately:

$$e_{\text{ratio}} \approx \frac{\bar{Y}_{\text{New}}}{\bar{Y}_{\text{Old}}} \sqrt{ e_{\text{Old}}^2 + e_{\text{New}}^2 }$$

Comparing a system against itself yields a ratio error bound that is $\sqrt{2} \approx 1.414\times$ wider than the single system's error bound.

---

## 6. Step-by-Step Practitioner's Cookbook

To build a testing suite grounded in this methodology, follow these steps:

1. **Identify Operational Levels:** Decide on the hierarchy (e.g., Level 1 = Iterations, Level 2 = Process Executions, Level 3 = Code Builds).
2. **One-Off Calibration Experiment:**
   * Run an initial dimensioning experiment with $r_1 = 30, r_2 = 30, r_3 = 30$.
   * Measure execution costs $c_1, c_2, c_3$.
   * Calculate $S^2_i$ and unbiased variance components $T^2_i$.
   * Compute optimal repetition counts $r_1, r_2$ using the dimensioning formula.
3. **Configure the Suite / Harness:** Set the calculated $r_1, r_2$ for subsequent benchmark runs.
4. **Execute Parallel & Interleaved Runs:** Execute baseline ($O$) and candidate ($N$) commits side-by-side in randomized/interleaved fashion to cancel out system-level environmental drift.
5. **Report Human-Understandable Results:** Avoid reporting raw $p$-values. Report the effect size confidence interval:
   > *"Feature Branch is **5.5% ± 2.5% faster** than Baseline Branch at 95% confidence."*
6. **Apply Practical Decision Thresholds:** Declare a true performance change only if the full confidence interval sits beyond a meaningful engineering threshold (e.g., speedup ratio $< 0.97$ or $> 1.03$ for a $3\%$ threshold).
