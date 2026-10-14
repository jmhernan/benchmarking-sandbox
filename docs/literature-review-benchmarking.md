# Literature Review: Modern Methodologies and Frameworks for Software Performance Benchmarking

## Executive Summary

Software performance benchmarking is fundamentally challenged by non-deterministic execution, dynamic runtime optimizations, memory layout variations, and cloud environment noise. Naive timing approaches—such as running a single benchmark loop locally or calculating simple arithmetic averages—frequently lead to misleading conclusions, false regression alarms, or excessive execution times. 

This literature review synthesizes 11 foundational research papers, industry guides, and open-source tool analyses. Together, they establish a statistically rigorous foundation for building an automated, reliable software performance benchmarking suite. The literature is structured around four main pillars:

1. **Hierarchical Random Effects & Experiment Dimensioning:** Accounting for multi-level variance (iterations, process executions, and binary builds) and computing effect size confidence intervals for speedup ratios rather than relying on flawed $p$-values.
2. **Steady-State Realities & Warmup Dynamics:** Addressing JIT, GC, and memory layout behavior where workloads frequently fail to reach a true steady state, requiring segment-aware statistical models and standardized warmup protocols.
3. **Reactive Convergence & Dynamic Sampling:** Replacing fixed iteration counts with automated stopping criteria based on Relative Standard Error (RSE) and lag-1 autocorrelation monitoring.
4. **Continuous Benchmarking in CI/CD:** Mitigating cloud runner noise through side-by-side relative benchmarking, change point detection (PELT), and compiler optimization barriers.

---

## 1. Hierarchical Random Effects & Experiment Dimensioning

### 1.1 Multi-Level Variance Decomposition
* **Core Papers:** Kalibera & Jones (2013) (*Rigorous Benchmarking in Reasonable Time*); Kalibera & Jones (2020) (*Quantifying Performance Changes with Effect Size Confidence Intervals*).
* **Key Insights:** Computer systems exhibit non-determinism across multiple distinct hierarchical levels:
  * **Iteration Level:** In-process loop repetitions affected by transient cache behavior and CPU frequency scaling.
  * **Execution Level:** Fresh process invocations affected by OS virtual-to-physical memory page mapping (ASLR), stack/environment layout, and initial heap allocations.
  * **Compilation/Build Level:** Compiler optimization choices, link orders, and code layout alignment shifts across separate binary compilations.
* **Optimal Experiment Dimensioning:** Instead of running arbitrary loop iterations, Kalibera & Jones prove that an experimenter can mathematically calculate the optimal number of repetitions $r_i$ at each lower level $i$ to achieve maximum statistical precision within a fixed time budget $T$:
  $$r_i = \left\lceil \sqrt{\frac{c_{i+1}}{c_i} \cdot \frac{T_i^2}{T_{i+1}^2}} \right\rceil$$
  where $c_i$ represents the execution cost (time) at level $i$, and $T_i^2$ represents the estimated variance component at level $i$.

### 1.2 Effect Size Confidence Intervals vs. $p$-Value Traps
* **Core Papers:** Kalibera & Jones (2020).
* **Key Insights:** Standard null-hypothesis significance testing ($p$-values) and visual checks of overlapping standard deviation error bars are systematically flawed for software benchmarking:
  * Large sample sizes make infinitesimal, practically meaningless performance differences (e.g., 0.05%) appear "statistically significant" ($p < 0.05$).
  * Traditional testing fails to quantify *how much* faster or slower a change is, nor does it provide a margin of error for the speedup ratio.
* **Mathematical Solution:** Performance comparisons should be expressed as **effect size confidence intervals for speedup ratios** ($\theta = \mu_{\text{new}} / \mu_{\text{old}}$) calculated via **Fieller’s Theorem** or **hierarchical bootstrap resampling**:
  * *Parametric (Fieller's Theorem):* Constructs exact confidence bounds for ratios of normal distributions accounting for variance across hierarchy levels.
  * *Non-Parametric (Hierarchical Bootstrap):* Resamples measurements with replacement at each structural level (build $\rightarrow$ execution $\rightarrow$ iteration) to build percentile confidence bounds without assuming Gaussian distributions.
* **Practical Thresholds:** Enables teams to enforce a practical threshold (e.g., $\pm 3\%$). A feature branch is flagged as a regression only if the upper/lower confidence bound crosses the practical threshold, eliminating false alarms driven by sample size over-sampling.

---

## 2. VM Warmup Dynamics & The "Era of No Steady Performance"

### 2.1 Demystifying the Steady-State Assumption
* **Core Papers:** Antoch et al. (2026) (*Experimental Evaluation Methodology for the Era of No Steady Performance*); Traini et al. (2023) (*Towards Effective Assessment of Steady State Performance in Java Software*).
* **Key Insights:** Traditional performance methodology assumes a simple two-phase model: an initial warmup phase followed by a stable, constant "steady state." Empirical evaluation across massive benchmark corpora (e.g., Renaissance suite and 586 JMH benchmarks across 30 systems) proves this assumption is invalid:
  * Approximately **11% of benchmark executions never reach a steady state**, exhibiting continuous variance shifts or bimodal performance states.
  * Over **43% of benchmark runs involve inconsistent behavior** across process forks.
  * Sudden performance shifts occur hours into execution due to long-period background activity (e.g., GC clearing soft references, metaspace expansion, or JIT re-optimization).
* **Segment-Aware Statistical Model:** Antoch et al. model performance as a random process transitioning between discrete steady-state segments separated by changepoints. Grand mean variance is decomposed as:
  $$\text{Var}(\bar{X}) = \frac{\text{Var}(R)}{N_R} + \frac{\text{Var}(S)}{N_R \cdot N_{SR}} + \frac{\text{Var}(B)}{N_R \cdot N_{SR} \cdot N_{MSR}}$$
  where $R$ represents run effects, $S$ represents segment effects, and $B$ represents baseline iteration performance. Utilizing Pruned Exact Linear Time (**PELT**) changepoint analysis to calculate segment-aware confidence intervals reduces confidence interval miss rates by over 20%.

### 2.2 The Warmup Protocol Problem & Language Runtimes
* **Core Papers:** Schulle (2026) (*The Warmup Protocol Problem: JIT, GC, and Lazy Evaluation Effects*).
* **Key Insights:** Excluding warmup and first-execution overheads hides real-world operational performance:
  * **Julia (JIT Specialization):** Exhibits high sensitivity to warmup protocols. Excluding first-use JIT compilation masks substantial cold-start overheads and alters the location of Bottleneck Transition Points (BTPs) in parallel workloads.
  * **Haskell (Lazy Evaluation):** Demonstrates low sensitivity to warmup timing because lazy thunk forcing distributes initialization throughout execution rather than concentrating it at startup.
  * **Python (Process Models):** Warmup sensitivity depends heavily on data IPC transport mechanisms (e.g., pickle serialization vs. shared memory mapping).

### 2.3 Limitations of Static Developer Configurations and Dynamic Heuristics
* **Core Papers:** Traini et al. (2023).
* **Key Insights:** Developers routinely miscalculate warmup requirements. Static configurations (e.g., hardcoded iteration counts in JMH) lead to a median estimation error of 28 to 90 seconds per run. Dynamic reconfiguration heuristics based on sliding-window Coefficient of Variation (CV) or Relative Confidence Interval Width (RCIW) frequently stop benchmarking prematurely during temporary plateaus, distorting steady-state estimates by 9%–10%.

---

## 3. Reactive Benchmarking & Dynamic Sampling

### 3.1 Autocorrelation at Lag-1 ($r_1$) and Serial Dependencies
* **Core Papers:** Junge (2022) (*Reactive Benchmarking in the Futhark Compiler*).
* **Key Insights:** Measuring sample variance alone (such as Relative Standard Deviation, RSD) fails to detect active warmup phases because consecutive iterations in a warmup phase exhibit strong serial dependencies.
* **Autocorrelation Metric:** Serial autocorrelation at lag-1 ($r_1$) measures the linear dependency between execution time $x_i$ and the immediately preceding sample $x_{i-1}$:
  $$r_1 = \frac{\sum_{i=1}^{n-1} (x_i - \bar{x})(x_{i+1} - \bar{x})}{\sum_{i=1}^n (x_i - \bar{x})^2}$$
  * A high $r_1$ value ($\sim 0.5 - 0.9$) indicates active warmup plateaus or time-dependent state trends.
  * A low $r_1$ value ($\sim 0.0 - 0.2$) confirms that samples are independent and identically distributed (i.i.d.).

### 3.2 Two-Phase Reactive Benchmarking Protocol
* **Core Papers:** Junge (2022).
* **Workflow:**
  1. **Phase 1 (Initial Probe):** Run the benchmark for a brief fixed window (e.g., 0.5 seconds).
  2. **Warmup Purge:** Calculate $r_1$ and Relative Standard Error ($\text{RSE} = s / (\bar{x}\sqrt{n})$). If $r_1$ or RSE exceeds target thresholds, discard the initial sample batch (purging the cold-start phase) while preserving the warmed runtime state.
  3. **Phase 2 (Dynamic Extension):** Exponentially step iteration counts ($n \rightarrow n \cdot \sqrt{2}$) until RSE drops below target precision (e.g., $< 1\%$) and lag-1 autocorrelation settles near zero.
* **Results:** Reaches reliable statistical convergence 5.5$\times$ faster than conservative static iteration counts (e.g., 4 min 16 sec vs. 23 min 44 sec) while eliminating manual configuration.

---

## 4. Continuous Benchmarking in CI/CD Pipelines

### 4.1 Mitigating Cloud Runner Variance
* **Core Papers:** Bencher Documentation (2023/2026); Japke et al. (2026) (*Towards an Optimized Benchmarking Platform for CI/CD Pipelines*).
* **Key Insights:** Shared cloud CI runners (GitHub Actions, GitLab CI) suffer from severe "noisy neighbor" interference and virtual machine migration variance.
* **Comparison Strategies:**
  1. **Statistical Continuous Benchmarking:** Tracks historical baselines over time on dedicated testbeds using Student's $t$-tests or moving boundaries.
  2. **Relative Continuous Benchmarking:** Executes the baseline commit and feature branch commit back-to-back within the exact same CI runner container job. Relative percentage comparison cancels out physical host environment noise.
  3. **Change Point Detection:** Monitored over continuous commit streams using PELT to flag persistent step-function performance drops while ignoring transient spikes.

### 4.2 Compiler Optimization Hazards & Blackholes
* **Core Papers:** JVM Tools JMH Guide (2026); Good GitHub Load Testing Report (2026); Google Benchmark Guide (2026).
* **Key Insights:** Optimizing compilers (JIT or AOT) aggressively eliminate code whose return values are unobserved (dead code elimination) or fold static loops (constant folding).
* **Scaffolding Primitives:** Benchmarking harnesses must force return values into explicit compiler barriers:
  * **Java (JMH):** `Blackhole.consume(val)` forces CPU register/memory observation.
  * **C++ (Google Benchmark):** `benchmark::DoNotOptimize(val)` and `benchmark::ClobberMemory()`.
  * **Rust:** `std::hint::black_box(val)`.
  * **Haskell:** Weak Head Normal Form (`whnf`) or Normal Form (`nf`) evaluation forcing to prevent lazy thunk accumulation.

---

## 5. Architectural Recommendations for a Custom Benchmarking Suite

Synthesizing these findings, a modern, production-grade benchmarking suite should implement the following pipeline architecture:

```
+-----------------------------------------------------------------------------------+
| 1. CALIBRATION & DIMENSIONING                                                     |
|    - Measure multi-level variance across process forks and iteration loops.       |
|    - Calculate optimal process execution (r_2) vs. iteration loop (r_1) ratios.   |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 2. ISOLATED RUNNER & WARMUP DETECTOR                                             |
|    - Execute fresh process forks to isolate OS memory layout & GC state.          |
|    - Scaffold benchmarks with explicit Blackhole primitives.                      |
|    - Monitor lag-1 autocorrelation (r_1) & RSE; discard cold warmup batches.     |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 3. CHANGEPOINT & SEGMENT-AWARE STATISTICAL ANALYSIS                               |
|    - Apply PELT changepoint detection to identify discrete performance segments. |
|    - Compute segment-aware grand means and variance bounds.                       |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 4. EFFECT SIZE REPORTING & CI INTEGRATION                                         |
|    - Run side-by-side relative comparisons (Branch vs. Baseline) in same CI job.   |
|    - Compute 95% speedup ratio confidence intervals (Fieller's / Bootstrap).     |
|    - Apply practical threshold gate (e.g., flag only if speedup <= 0.97 or >= 1.03). |
+-----------------------------------------------------------------------------------+
```

---

## 6. Primary Sources & Citations

1. **Kalibera, T., & Jones, R. (2013).** *Rigorous Benchmarking in Reasonable Time.* ACM ISMM.
2. **Kalibera, T., & Jones, R. (2020).** *Quantifying Performance Changes with Effect Size Confidence Intervals.* arXiv:2007.10899 / School of Computing, University of Kent.
3. **Antoch, J., Binder, W., Bulej, L., Farquet, F., Horký, V., Prokopec, A., Rosà, A., & Tůma, P. (2026).** *Experimental Evaluation Methodology for the Era of No Steady Performance.* Proc. ACM Program. Lang. (OOPSLA).
4. **Traini, L., Cortellessa, V., Di Pompeo, D., & Tucci, M. (2023).** *Towards effective assessment of steady state performance in Java software: are we there yet?* Empirical Software Engineering, 28:13.
5. **Schulle, A. (2026).** *The Warmup Protocol Problem: JIT, GC, and Lazy Evaluation Effects on WRSS in Julia, Haskell, and Python.* Research Square Preprint.
6. **Junge, A. (2022).** *Reactive Benchmarking: Benchmarking in the Futhark Compiler.* Bachelor's Thesis, University of Copenhagen.
7. **Japke, N., Koch, S., Lukasczyk, H., & Bermbach, D. (2026).** *Towards an Optimized Benchmarking Platform for CI/CD Pipelines.* arXiv.
8. **Bencher Engineering (2023/2026).** *How to Track Benchmarks in CI with Bencher.* Bencher Documentation.
9. **JVM Tools Guide (2026).** *JMH tutorial: microbenchmark Java code without JIT pitfalls.*
10. **Good GitHub Report (2026).** *Load testing and performance benchmarking tools: A field guide.*
11. **Barrett, E., Bolz-Tereick, C. F., Killick, R., Mount, S., & Tratt, L. (2017).** *Virtual Machine Warmup Blows Hot and Cold.* Proc. ACM Program. Lang. (OOPSLA).
