# Bayesian literature for Part B

**Purpose:** the sources behind Part B of [plan.md](plan.md) (Bayesian additions), grouped by the question each one answers and mapped to milestones B0–B6.
**Status:** every citation below was checked against the publisher, arXiv or the author's page on 2026-10-25. Smyth 2004, Gelman, Hill & Yajima 2012, Johari et al. 2017 and Howard et al. 2021 were added after a review against the plan; Howard et al.'s volume and pages were confirmed on arXiv (a search summary had them wrong). 📁 = in the claude.ai project files.
**Companion to:** [research.md](research.md) §3.9, which this resolves (see §9).

---

## 0. What the A0c pilot changes for Part B

The pilot (commit `4318c48`) measured, on Dart AOT on this Mac: σ₁ ≈ 1.51%, σ₂ ≈ 1.34%, or **0.82% drift-robust**, with $\hat k$ ≈ 2.4–3.7. Two consequences for the reading:

- **H1 is alive.** σ₂ is material, so a prior on σ₂ has something to buy at small P.
- **The prior must handle drift.** The gap between 1.34% and 0.82% means within-session drift inflates a naive σ₂ estimate. A prior fitted to the naive number is the "misspecified-high" case in §B.2; one fitted to the drift-robust number risks "misspecified-low" if drift shows up in real runs. This is the strongest argument for the hierarchical and robustified priors (§3 below) over a single fixed empirical prior. Drift is also a model problem: plan §B.2 adds a round-paired variant that cancels it by design.
- **The trials are autocorrelated.** A2's `components.py` estimates a bias-corrected lag-1 correlation of ρ ≈ 0.46 within processes, which inflates the variance of a process mean by f ≈ 2.5. The plan's original likelihood assumed independent trials, so plan §B.2 now defaults to a means-only likelihood, with an AR-aware variant. None of the sources below addresses this directly (§8, gaps).

---

## 1. Milestone map

| Milestone | Question | Core sources |
|---|---|---|
| B.1 framing | How do we justify a Bayesian method to a frequentist maintainer? | Little 2006; Berkes & Fiser 2011 📁 |
| B1 grid estimator | How do we compute the posterior without MCMC? | Gelman et al. BDA3 (ch. 3, 5); Kalibera & Jones 2013 |
| B.2 priors | What prior on σ₂, and how do we pool it? | Gelman 2006; Polson & Scott 2012; BDA3 ch. 5 |
| H1 comparator | What is the frequentist way to borrow σ₂? | Smyth 2004 |
| B.2 gate (H2) | ROPE, Bayes factors or expected loss? | Kruschke 2018; Kruschke 2013; Rouder et al. 2009 📁; Clyde 2021 📁; Stucchio 2015 |
| B2 validation | How do we prove the code is right? | Talts et al. 2018; Modrák et al. 2023 |
| B3 sequential (H3) | Is "peeking is fine" true, and what is the fair baseline? | Rouder 2014; de Heide & Grünwald 2021; Deng, Lu & Chen 2016; Johari et al. 2017; Howard et al. 2021 |
| B4 pooling (H4) | Pooling effects across a suite | BDA3 ch. 5; Gelman 2006; Gelman, Hill & Yajima 2012 |
| B5 robustness | Student-t likelihood; autocorrelated trials | Kruschke 2013; (gap, §8) |
| B6 / context | Bayes in software engineering and benchmarking | Furia, Feldt & Torkar 2021; Bulej et al. 2020 |

---

## 2. Framing: calibrated Bayes

**Little, R. J. (2006). Calibrated Bayes: a Bayes/frequentist roadmap.** *The American Statistician* 60(3), 213–223. [PDF](https://errorstatistics.com/wp-content/uploads/2015/11/little_calibrated-bayes.pdf)
- Argues for Bayesian inference for the model, judged by frequentist calibration of its long-run properties.
- **Use:** the name and citation for the stance in §B.1 "Framing for the maintainer". Every Part B acceptance criterion is a frequentist operating characteristic.

**Berkes, P. & Fiser, J. (2011). A frequentist two-sample test based on Bayesian model selection.** arXiv:1104.2826. 📁 [arXiv](https://arxiv.org/abs/1104.2826)
- Builds a two-sample test from Bayesian model selection, then calibrates its threshold to a fixed Type I error. Reports up to 25% more power than the t-test at small samples, and at most 1% less when t-test assumptions hold exactly.
- **Use:** a worked example of the same move Part B makes: a Bayesian statistic with frequentist error control. The small-sample power claim is the analogue of H1. Note the gain comes from the prior over alternatives, just as H1's comes from the prior on σ₂.

**Michaeli, I. Frequentist vs Bayesian approach in A/B testing.** Dynamic Yield / Mastercard learning path. [Link](https://www.mastercard.com/us/en/business/consumer-acquisition-and-engagement/personalization/dynamic-yield/learning-paths/a-b-testing-optimization/frequentist-vs-bayesian-approach-in-a-b-testing.html)
- Accessible overview of probability-to-be-best, expected loss and HPD intervals.
- **Caveats:** vendor content. Its "peeking is allowed" claim is the weakest point; see §7. Useful for explaining outputs, not as a methods reference.

---

## 3. Model and computation (B1)

**Gelman, A., Carlin, J. B., Stern, H. S., Dunson, D. B., Vehtari, A. & Rubin, D. B. (2013). *Bayesian Data Analysis*, 3rd ed.** CRC Press. [Author page](https://sites.stat.columbia.edu/gelman/book/)
- **Ch. 3** (normal model with unknown mean and variance): the conjugate-given-σ structure that makes Δ | σ normal.
- **Ch. 5** (hierarchical models, the eight-schools example): computes the marginal posterior of the group-level SD τ **on a grid**, then draws the rest conditionally. That is exactly the B1 algorithm, with σ₂ in the role of τ. Read this first.
- Also the reference for the B4 effect-pooling model $\Delta_b\sim N(0,\omega^2)$.

**Kalibera, T. & Jones, R. (2013). Rigorous benchmarking in reasonable time.** ISMM. (Already in research.md, ref 1.)
- The nested variance model (σ₁ within, σ₂ between processes) that §B.2 puts priors on. Part B is a Bayesian treatment of their random-effects model.

---

## 4. Priors on σ₂ and pooling (B.2, B4)

**Gelman, A. (2006). Prior distributions for variance parameters in hierarchical models.** *Bayesian Analysis* 1(3), 515–534. [Project Euclid](https://projecteuclid.org/euclid.ba/1354024466)
- Shows the inverse-gamma(ε, ε) "noninformative" prior is badly behaved when the group SD is near zero, which σ₂ can be. Recommends uniform or half-t (half-Cauchy) priors on the SD.
- **Use:** justifies the "weak" half-normal row in §B.2 and the requirement that the σ₂ grid includes values near 0 (unit test (e)). Also warns that with few groups (2P processes) the prior on σ₂ matters, which is H1's premise and its main risk.

**Polson, N. G. & Scott, J. G. (2012). On the half-Cauchy prior for a global scale parameter.** *Bayesian Analysis* 7(4), 887–902. [arXiv](https://arxiv.org/abs/1104.4937)
- Frequentist risk analysis supporting half-Cauchy as a default scale prior.
- **Use:** a candidate for the "weak" or "robustified" σ₂ prior. A heavy-tailed prior lets the data override history when σ₂ really differs, which is what the 80/20 mixture in §B.2 approximates.

**Smyth, G. K. (2004). Linear models and empirical Bayes methods for assessing differential expression in microarray experiments.** *Statistical Applications in Genetics and Molecular Biology* 3(1), Article 3. doi:10.2202/1544-6115.1027
- The **moderated t**, the method behind the limma package: each test's variance is shrunk towards a prior fitted across thousands of tests (genes), with the prior's degrees of freedom $d_0$ estimated from the data, giving a t statistic with $d_0+d_g$ df. Built for small replicate counts.
- **Use:** the H1 comparator (plan §B.1). Benchmarks in a suite play the role of genes, and the variance of process means plays the role of the gene variance. It is the frequentist-calibrated, closed-form version of H1's hierarchical prior on σ₂, so Bayes earns H1 only by beating it.

**Gelman, A., Hill, J. & Yajima, M. (2012). Why we (usually) don't have to worry about multiple comparisons.** *Journal of Research on Educational Effectiveness* 5(2), 189–211. doi:10.1080/19345747.2011.618213
- Argues that multilevel models with partial pooling address multiple comparisons by shrinking estimates, instead of widening intervals as FDR or FWER corrections do.
- **Use:** the core argument for H4 (effect pooling vs Benjamini–Hochberg), and for H4's "less exaggeration of the largest effects" metric.

---

## 5. Decision rules: ROPE vs Bayes factors vs expected loss (H2)

**Kruschke, J. K. (2018). Rejecting or accepting parameter values in Bayesian estimation.** *Advances in Methods and Practices in Psychological Science* 1(2), 270–280. doi:10.1177/2515245918771304. [IU ScholarWorks](https://scholarworks.iu.edu/dspace/items/bada026d-fe1b-4f53-ad5b-db6e8bf99711)
- The HDI + ROPE decision rule: accept "practically equivalent" when the credible interval sits inside the region of practical equivalence, reject when it sits outside.
- **Use:** the primary reference for the §B.2 gate. Our ±δ band is the ROPE. Plan §B.2 now uses the 95% **equal-tailed** credible interval inside the ROPE, stated as two one-sided tail probabilities. Here it equals the HDI because the posterior is symmetric and unimodal, and with a flat prior it reproduces the Part A gate exactly. The posterior mass $P(\lvert\Delta\rvert<\ell)$ is reported but does not decide anything.

**Kruschke, J. K. (2013). Bayesian estimation supersedes the t test.** *Journal of Experimental Psychology: General* 142(2), 573–603. [Author's BEST page](https://jkkweb.sitehost.iu.edu/BEST)
- Two-group estimation with a **Student-t likelihood** and ROPE-based decisions ("BEST").
- **Use:** the reference model for B5's Student-t variant, and a PyMC implementation to cross-check against (`best` package, PyMC BEST notebook).

**Rouder, J. N., Speckman, P. L., Sun, D., Morey, R. D. & Iverson, G. (2009). Bayesian t tests for accepting and rejecting the null hypothesis.** *Psychonomic Bulletin & Review* 16(2), 225–237. doi:10.3758/PBR.16.2.225. 📁
- The JZS Bayes factor: a Cauchy prior on effect size, with discussion of the Lindley paradox and the unit-information prior.
- **Use:** why the plan does *not* make Bayes factors primary. They test a point null θ = 1, and two code versions are never exactly equal. Keep as an optional extra for the A/A same-binary case only. Its prior-sensitivity discussion (Cauchy scale) carries over to our choice of ω in B4.

**Clyde, M. (2021). Lecture 5: Basics of Bayesian hypothesis testing.** Course handout, 9 Sep 2021. 📁
- Compact contrast of credible-interval "tests", tail probabilities ("Bayesian p-values") and formal Bayes factors with prior model probabilities. Notes that a tail probability is not $P(H_0\mid y)$.
- **Use:** a primer for collaborators and for the B6 write-up; the clearest short statement of why our gate probabilities are not posterior probabilities of a null.

**Stucchio, C. (2015). Bayesian A/B testing at VWO.** VWO SmartStats technical whitepaper. [PDF](https://www.chrisstucchio.com/pubs/VWO_SmartStats_technical_whitepaper.pdf) · [blog post on the decision rule](https://www.chrisstucchio.com/blog/2014/bayesian_ab_decision_rule.html)
- The expected-loss stopping rule with a "threshold of caring".
- **Use:** the source for the expected-loss rule reported alongside the gate in §B.2 (the same rule Dynamic Yield describes).

---

## 6. Validating the estimator (B2)

**Talts, S., Betancourt, M., Simpson, D., Vehtari, A. & Gelman, A. (2018). Validating Bayesian inference algorithms with simulation-based calibration.** arXiv:1804.06788. [arXiv](https://arxiv.org/abs/1804.06788)
- Simulation-based calibration (SBC): draw parameters from the prior, simulate data, fit, and check that the rank of the true value among posterior draws is uniform.
- **Use:** B2 step 1. Note the grid gives a posterior CDF directly, so ranks can be replaced by the posterior CDF evaluated at the true value (the probability integral transform); it should be Uniform(0, 1).

**Modrák, M., Moon, A. H., Kim, S., Bürkner, P., Huurre, N., Faltejsková, K., Gelman, A. & Vehtari, A. (2023). Simulation-based calibration checking for Bayesian computation: the choice of test quantities shapes sensitivity.** *Bayesian Analysis*, advance publication. doi:10.1214/23-BA1404. [Project Euclid](https://projecteuclid.org/journals/bayesian-analysis/advance-publication/Simulation-Based-Calibration-Checking-for-Bayesian-Computation--The-Choice/10.1214/23-BA1404.full)
- Shows SBC on raw parameters can miss errors; checking derived quantities (e.g. the likelihood, or functions of several parameters) is more sensitive.
- **Use:** add SBC on the **gate probabilities** and on $\tau^2=\sigma_2^2+\sigma_1^2/n$, not only on Δ, σ₁ and σ₂. Those are what the tool actually reports.

---

## 7. Sequential stopping (H3)

The three papers below disagree in an instructive way. Read them together before designing B3.

**Rouder, J. N. (2014). Optional stopping: no problem for Bayesians.** *Psychonomic Bulletin & Review* 21(2), 301–308.
- Shows the posterior remains a correct statement of belief under optional stopping **when the analysis prior matches the data-generating prior**.

**de Heide, R. & Grünwald, P. D. (2021). Why optional stopping can be a problem for Bayesians.** *Psychonomic Bulletin & Review* 28, 795–812. [PMC open access](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8219595/)
- Shows Rouder's guarantee depends on the prior being correct (or "subjective") and fails for default or pragmatic priors, and for frequentist error rates generally.
- **Use:** the direct justification for B3's check of false alarms under early stopping with a **misspecified** prior. Our empirical prior is pragmatic, so we are in their regime, not Rouder's.

**Deng, A., Lu, J. & Chen, S. (2016). Continuous monitoring of A/B tests without pain: optional stopping in Bayesian testing.** arXiv:1602.05549. [arXiv](https://arxiv.org/abs/1602.05549)
- From Microsoft's experimentation platform: proves Bayesian testing stays valid under continuous monitoring for **proper** stopping rules, and identifies common improper ones.
- **Use:** the closest industrial precedent for B3's "launch processes until the posterior is decisive". Check that our rule (stop at $c$, cap at $P_\max=20$) is proper in their sense.

**Johari, R., Koomen, P., Pekelis, L. & Walsh, D. (2017). Peeking at A/B tests: why it matters, and what to do about it.** KDD '17, 1517–1525.
- **Always-valid p-values and confidence intervals** that keep their guarantees under continuous monitoring. Deployed at Optimizely.
- **Use:** with Howard et al., the frequentist alternative for H3. It controls error under any stopping rule by construction, which de Heide & Grünwald show a Bayesian rule with a pragmatic prior does not.

**Howard, S. R., Ramdas, A., McAuliffe, J. & Sekhon, J. (2021). Time-uniform, nonparametric, nonasymptotic confidence sequences.** *Annals of Statistics* 49(2), 1055–1080. doi:10.1214/20-AOS1991. [arXiv](https://arxiv.org/abs/1810.08240)
- **Confidence sequences:** intervals valid uniformly over time, so any data-dependent stopping time keeps the coverage guarantee.
- **Use:** the anytime-valid comparator in B3 (a confidence sequence for the log ratio of process means). H3 must beat it on average processes at equal error rates.

---

## 8. Bayes in software engineering and benchmarking (context, B6)

**Furia, C. A., Feldt, R. & Torkar, R. (2021). Bayesian data analysis in empirical software engineering research.** *IEEE Transactions on Software Engineering* 47(9), 1786–1810. doi:10.1109/TSE.2019.2935974. [arXiv](https://arxiv.org/abs/1811.05422)
- Reanalyses of published software engineering studies showing what Bayesian analysis adds (effect sizes, practical significance, multilevel models). Data and scripts are public.
- **Use:** the software engineering precedent to cite in B6, and a template for presenting posteriors to engineers. The same group's follow-up on *practical significance* in software engineering ([Chalmers record](https://research.chalmers.se/en/publication/521996)) bears on choosing δ (plan open question 2).

**Bulej, L., Horký, V., Tůma, P., Farquet, F. & Prokopec, A. (2020). Duet benchmarking: improving measurement accuracy in the cloud.** ICPE '20, 100–107. doi:10.1145/3358960.3379132. [arXiv](https://arxiv.org/abs/2001.05811)
- Runs the two versions **in parallel on the same machine** so they share interference, then compares them jointly. Reports accuracy gains of 2.3×–12.5× (5.03× average) on ScalaBench and DaCapo, and 23.8×–82.4× (37.4× average) on SPEC CPU 2017.
- **Use:** not Bayesian, but the precedent for pairing. Duet shares *machine* noise the way `Benchmark.compare` shares *process* noise, and the way plan §B.2's round-paired variant shares session drift. Cite it for the paired estimator (A2 `paired.py`) and the paired versions of the B.2 model.

**Gaps found:**
- No paper was found applying a Bayesian hierarchical model specifically to *between-process variance in benchmark comparisons*. Part B would be novel in that narrow sense; worth a sentence in B6, after a final search.
- No source here models **autocorrelated trials inside a process** together with process effects (§0). Plan §B.2 handles it by design (a means-only likelihood, with an AR-aware variant), and B5 fits an AR(1) model in PyMC as a check. A targeted search (time-series random-effects models; batch-means variance estimation in simulation output analysis) is still to do.

---

## 9. Resolving the leads in research.md §3.9

| Lead in research.md | Status |
|---|---|
| Furia, Feldt & Torkar on Bayesian data analysis in SE | Verified; §8 above (TSE 2021) |
| Bulej et al. on duet / paired benchmarking | Verified; §8 above (ICPE 2020) |
| Davison & Hinkley on bootstrap methods | *Bootstrap Methods and their Application*, Cambridge University Press, 1997. Not Bayesian; belongs in research.md for the bootstrap estimator |

Done 2026-10-25: research.md §3.9's "Related work to look up (unverified)" line now points to this file.

---

## 10. Suggested reading order

1. BDA3 ch. 5 (the grid-over-τ method), then ch. 3.
2. Gelman 2006 (priors on σ₂), then Smyth 2004 (the moderated-t comparator H1 must beat).
3. Kruschke 2018 (the gate).
4. Talts et al. 2018, then Modrák et al. 2023 (validation).
5. Rouder 2014 and de Heide & Grünwald 2021 together, then Johari et al. 2017 or Howard et al. 2021 (before B3).
6. Gelman, Hill & Yajima 2012 (before B4).
7. Little 2006 and Berkes & Fiser 2011 (framing, before B6).
