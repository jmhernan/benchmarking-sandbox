# benchmarking-sandbox

Research toward a rigorous performance-benchmarking suite for a software engineering team (currently working in Dart). The goal is to tell, with quantified uncertainty, whether a code change made things faster or slower, by how much, and how sure we are.

**Status: implementation started (Part A, step A0 done).** The project builds on [kevmoo/bench_press](https://github.com/kevmoo/bench_press) as the Dart runner (AOT target), and the work here is the statistical layer. The implementation plan is kept locally (`docs/plan.md`, git-ignored). It has two parts. **Part A** closes the statistical gaps identified in [docs/bench_press/](docs/bench_press). Much of it has now landed upstream in bench_press v0.4.2 (`5fd6396`): multi-process runs (`--processes`), process-level and paired Fieller intervals, a threshold/TOST gate (`--threshold`) and a between-process variance share, all opt-in. What remains here is git-ref rebuilds for `--diff`, better variance diagnostics, a design recommendation, multiple-comparison control, and validation in simulation and on real hardware. **Part B** then adds a Bayesian hierarchical estimator on top.

## Background

The project started from Kalibera & Jones, *Rigorous Benchmarking in Reasonable Time*. Their approach decomposes variance across iterations, process executions and builds, picks repetition counts from the cost and variance of each level, and reports speedup as an effect-size confidence interval instead of a $p$-value. A more recent literature review adds findings that challenge parts of it, mainly that steady state is often not reached, plus reactive stopping rules and CI-noise handling.

## Repository layout

| Path | Contents |
|---|---|
| `docs/plan.md` | **Local only (git-ignored).** Implementation plan, pinned to bench_press `5fd6396`. Part A: close the statistical gaps (what landed upstream, plus git-ref rebuilds, diagnostics, design, multiplicity, validation). Part B: Bayesian additions. Both have acceptance criteria fixed before running. |
| [docs/research.md](docs/research.md) | **Start here.** Current state of the research: problem, core concepts, source-quality notes, open questions, analysis of the sample data, and the synthetic-data method. |
| [docs/rigorous-benchmarking-in-reasonable-time.md](docs/rigorous-benchmarking-in-reasonable-time.md) | Summary of the original methodology. |
| [docs/literature-review-benchmarking.md](docs/literature-review-benchmarking.md) | Literature review of newer work. |
| [docs/bench_press/](docs/bench_press) | Standalone statistical proposal for [kevmoo/bench_press](https://github.com/kevmoo/bench_press) (process-level intervals, threshold gate, validation, experiment design) and the reproducible simulation behind it (`simulate.py`). |
| `data/` | Sample per-iteration timing series (`data_10.txt` … `data_10000.txt`; one integer per line, **unit assumed to be microseconds**, unconfirmed). **Not in version control** (`data/.gitignore` excludes `*.txt` and `*.csv`), so a fresh clone needs the files supplied separately. |
| [sandbox/analyze.py](sandbox/analyze.py) | Exploratory analysis of the sample data: warmup detection, changepoints, slow episodes, spike fractions, block bootstrap. |
| [sandbox/synth.py](sandbox/synth.py) | Synthetic data generator with known ground truth, for validating detectors and estimators. |
| `sandbox/output/` | Tables (CSV), plots (PNG) and `results.txt` from `analyze.py`. |
| [sandbox/spikes/](sandbox/spikes) | Throwaway feasibility checks (e.g. the Bayesian grid estimator spike cited in the local plan, `docs/plan.md` §B.2a). |
| [pyproject.toml](pyproject.toml), [src/bench_stats/](src/bench_stats), [tests/](tests) | The `bench_stats` Python package (the statistical layer) and its pytest suite. Scaffolding only so far. Install with `pip install -e ".[dev]"` (into the `perfBench` conda environment), run tests with `python -m pytest`. |
| [bench/](bench) | Controlled Dart benchmarks (a fixed workload with an injectable, calibrated spin cost, plus a same-binary group) for pilots and real-hardware validation. Needs a bench_press clone next to this repository; see [bench/README.md](bench/README.md). |
| `data/runs/` | Raw bench_press run JSON. Git-ignored. |

## What the research has found so far

Details, caveats and sources are in [docs/research.md](docs/research.md). In brief, for the sample data:

- The series are **not i.i.d.** Each looks like a slowly drifting baseline interrupted by recurring slow episodes (about 14% of post-warmup time in the longest file), plus spikes. Resampling individual iterations understated the standard error of the mean by about 4×. A block bootstrap (block ≈ 100) gave an honest interval.
- Warmup-end detection depends on a tolerance, and a conservative rule can discard the whole series.
- With one process per file, between-process and between-build variance cannot be estimated, so no speedup confidence interval can be computed from this data yet.

These are exploratory results on one series per file, not validated conclusions.


## Open questions

The main ones, all listed in [docs/research.md](docs/research.md) §7:
- What is the unit of the sample data, what is being timed, and which Dart runtime mode (JIT, AOT or JS) produced it?
- How large is between-process variance on Dart AOT? A first A/A pilot (one benchmark, 40 processes, this Mac) puts it at about 0.8–1.3% per process, comparable to within-process noise, with part of it being drift over the session ([sandbox/output/a0c_pilot.txt](sandbox/output/a0c_pilot.txt)). More benchmarks and machines are needed.
- What practical threshold counts as a meaningful change for the team?
- Which estimators should be the default (Fieller, hierarchical bootstrap, Bayesian), and in which language should the suite be written?

## License

MIT. See [LICENSE](LICENSE).
