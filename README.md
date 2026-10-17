# benchmarking-sandbox

Research toward a rigorous performance-benchmarking suite for a software engineering team (currently working in Dart). The goal is to tell, with quantified uncertainty, whether a code change made things faster or slower, by how much, and how sure we are.

**Status: research phase.** There is no plan, no chosen implementation language and no production code yet. `src/` is empty on purpose. A `plan.md` comes after the research is reviewed.

## Background

The project started from Kalibera & Jones, *Rigorous Benchmarking in Reasonable Time*. Their approach decomposes variance across iterations, process executions and builds, picks repetition counts from the cost and variance of each level, and reports speedup as an effect-size confidence interval instead of a $p$-value. A more recent literature review adds findings that challenge parts of it, mainly that steady state is often not reached, plus reactive stopping rules and CI-noise handling.

## Repository layout

| Path | Contents |
|---|---|
| [docs/research.md](docs/research.md) | **Start here.** Current state of the research: problem, core concepts, source-quality notes, open questions, analysis of the sample data, and the synthetic-data method. |
| [docs/rigorous-benchmarking-in-reasonable-time.md](docs/rigorous-benchmarking-in-reasonable-time.md) | Summary of the original methodology. |
| [docs/literature-review-benchmarking.md](docs/literature-review-benchmarking.md) | Literature review of newer work. |
| [docs/bench_press/](docs/bench_press) | Standalone statistical proposal for [kevmoo/bench_press](https://github.com/kevmoo/bench_press) (process-level intervals, threshold gate, validation, experiment design) and the reproducible simulation behind it (`simulate.py`). |
| `data/` | Sample per-iteration timing series (`data_10.txt` … `data_10000.txt`; one integer per line, **unit assumed to be microseconds**, unconfirmed). **Not in version control** (`data/.gitignore` excludes `*.txt` and `*.csv`), so a fresh clone needs the files supplied separately. |
| [sandbox/analyze.py](sandbox/analyze.py) | Exploratory analysis of the sample data: warmup detection, changepoints, slow episodes, spike fractions, block bootstrap. |
| [sandbox/synth.py](sandbox/synth.py) | Synthetic data generator with known ground truth, for validating detectors and estimators. |
| `sandbox/output/` | Tables (CSV), plots (PNG) and `results.txt` from `analyze.py`. |
| `src/` | Reserved for the eventual implementation. Empty. |

## What the research has found so far

Details, caveats and sources are in [docs/research.md](docs/research.md). In brief, for the sample data:

- The series are **not i.i.d.** Each looks like a slowly drifting baseline interrupted by recurring slow episodes (about 14% of post-warmup time in the longest file), plus spikes. Resampling individual iterations understated the standard error of the mean by about 4×. A block bootstrap (block ≈ 100) gave an honest interval.
- Warmup-end detection depends on a tolerance, and a conservative rule can discard the whole series.
- With one process per file, between-process and between-build variance cannot be estimated, so no speedup confidence interval can be computed from this data yet.

These are exploratory results on one series per file, not validated conclusions.


## Open questions

The main ones, all listed in [docs/research.md](docs/research.md) §7:
- What is the unit of the sample data, what is being timed, and which Dart runtime mode (JIT, AOT or JS) produced it?
- Can replicate runs (several processes per code version) be collected, so between-process variance can be estimated?
- What practical threshold counts as a meaningful change for the team?
- Which estimators should be the default (Fieller, hierarchical bootstrap, Bayesian), and in which language should the suite be written?

## License

MIT. See [LICENSE](LICENSE).
