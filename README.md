# benchmarking-sandbox

Research toward a rigorous performance-benchmarking suite for a software engineering team (currently working in Dart). The goal is to tell, with quantified uncertainty, whether a code change made things faster or slower, by how much, and how sure we are.

**Status: implementation started (Part A: A0 setup, A0c pilot, A1 git-ref runner, A2 analysis core, A3 report and A4 simulation validation done).** The project builds on [kevmoo/bench_press](https://github.com/kevmoo/bench_press) as the Dart runner (AOT target), and the work here is the statistical layer. The implementation plan is kept locally (`docs/plan.md`, git-ignored). It has two parts. **Part A** closes the statistical gaps identified in [docs/bench_press/](docs/bench_press). Much of it has now landed upstream in bench_press v0.4.2 (`5fd6396`): multi-process runs (`--processes`), process-level and paired Fieller intervals, a threshold/TOST gate (`--threshold`) and a between-process variance share, all opt-in. What remains here is git-ref rebuilds for `--diff`, better variance diagnostics, a design recommendation, multiple-comparison control, and validation in simulation and on real hardware. **Part B** then adds a Bayesian hierarchical estimator on top.

## Background

The project started from Kalibera & Jones, *Rigorous Benchmarking in Reasonable Time*. Their approach decomposes variance across iterations, process executions and builds, picks repetition counts from the cost and variance of each level, and reports speedup as an effect-size confidence interval instead of a $p$-value. A more recent literature review adds findings that challenge parts of it, mainly that steady state is often not reached, plus reactive stopping rules and CI-noise handling.

## Usage

Run benchmarks with bench_press using several processes per version (5 or more), then analyse the JSON with `bench-stats` (installed by `pip install -e ".[dev]"` into the `perfBench` environment):

```bash
# Compare a candidate run with a baseline run (same benchmarks, separate process launches)
bench-stats analyze baseline.json candidate.json --threshold 0.03

# One run: compare Benchmark.compare variants with their group baseline (paired by process),
# and report variance diagnostics and a design hint for every benchmark
bench-stats analyze run.json

# Same content as JSON, for scripts or CI
bench-stats analyze baseline.json candidate.json --format json -o report.json
```

The Markdown report has three parts:
- **Comparisons:** for each benchmark, the speedup, its process-level interval, the δ-gate verdict (faster ≥ δ, slower ≥ δ, no meaningful change, inconclusive), whether it stays detectable after Benjamini–Hochberg, and what bench_press itself prints for the same data.
- **Variance diagnostics:** σ₁, σ₂, k, ρ and launch drift.
- **Design hint:** trials per process and processes per version for a target power.

`bench-stats analyze --help` lists the options: confidence level, per-process mean or median, FDR q, power and the effect to plan for.

### Comparing two git refs in one session

bench_press's `--diff` compares against a JSON stored in an earlier session, and drift between sessions makes that interval unreliable (A4). `bench-stats run` builds both refs and runs them interleaved in one session instead:

```bash
# Baseline main vs candidate feature, 10 processes each, in a seeded order balanced within pairs
bench-stats run bench/benchmark/workload_benchmark.dart --baseline main --candidate feature -P 10 -o data/runs/feature.jsonl
bench-stats analyze data/runs/feature.jsonl

# Same commit, candidate built with a compile-time define (bench_press can't interleave builds that differ only in -D)
bench-stats run bench/benchmark/workload_benchmark.dart --baseline HEAD --candidate HEAD \
  --candidate-flag=-DBENCH_SPIN=4800 -P 10 -o data/runs/spin.jsonl

# A/A: one binary launched under both labels
bench-stats run bench/benchmark/workload_benchmark.dart --baseline HEAD --aa -P 20 -o data/runs/aa.jsonl
```

The package is the nearest `pubspec.yaml` above the benchmark file. Each ref is checked out in its own git worktree (in a temporary directory, or under `--work-dir` to keep it), then built with `dart pub get` and `dart compile exe`, as bench_press does for `-t aot`. Relative path dependencies that leave the repository, such as `../../bench_press`, are pinned to where they point from the main checkout through a `pubspec_overrides.yaml` in the worktree. Only committed code is measured.

The output is JSONL with one header line, holding the refs, commits, compiler flags, binary hashes, launch order and machine environment, then one line per process. Each process line holds that process's bench_press JSON, launch timestamps, power source and macOS thermal limits. It keeps the per-process stability that bench_press loses when it merges processes. Failed processes are recorded and excluded by `analyze`. Other options: `--trials`, `--seed`, `--cooldown` between launches, `--timeout` per process, and `--compiler-flag` for both versions.

## Repository layout

| Path | Contents |
|---|---|
| `docs/plan.md` | **Local only (git-ignored).** Implementation plan, pinned to bench_press `5fd6396`. Part A: close the statistical gaps (what landed upstream, plus git-ref rebuilds, diagnostics, design, multiplicity, validation). Part B: Bayesian additions. Both have acceptance criteria fixed before running. |
| [docs/research.md](docs/research.md) | **Start here.** Current state of the research: problem, core concepts, source-quality notes, open questions, analysis of the sample data, and the synthetic-data method. |
| [docs/rigorous-benchmarking-in-reasonable-time.md](docs/rigorous-benchmarking-in-reasonable-time.md) | Summary of the original methodology. |
| [docs/literature-review-benchmarking.md](docs/literature-review-benchmarking.md) | Literature review of newer work. |
| [docs/bayesian-literature.md](docs/bayesian-literature.md) | Verified sources for the Bayesian additions (Part B), grouped by question and mapped to milestones, with notes on what the A0c pilot changes. |
| [docs/bench_press/](docs/bench_press) | Standalone statistical proposal for [kevmoo/bench_press](https://github.com/kevmoo/bench_press) (process-level intervals, threshold gate, validation, experiment design) and the reproducible simulation behind it (`simulate.py`). |
| `data/` | Sample per-iteration timing series (`data_10.txt` … `data_10000.txt`; one integer per line, **unit assumed to be microseconds**, unconfirmed). **Not in version control** (`data/.gitignore` excludes `*.txt` and `*.csv`), so a fresh clone needs the files supplied separately. |
| [sandbox/analyze.py](sandbox/analyze.py) | Exploratory analysis of the sample data: warmup detection, changepoints, slow episodes, spike fractions, block bootstrap. |
| [sandbox/synth.py](sandbox/synth.py) | Synthetic data generator with known ground truth, for validating detectors and estimators. |
| `sandbox/output/` | Tables (CSV), plots (PNG) and `results.txt` from `analyze.py`. |
| [sandbox/spikes/](sandbox/spikes) | Throwaway feasibility checks (e.g. the Bayesian grid estimator spike cited in the local plan, `docs/plan.md` §B.2a). |
| [pyproject.toml](pyproject.toml), [src/bench_stats/](src/bench_stats), [tests/](tests) | The `bench_stats` Python package (the statistical layer) and its pytest suite. Part A's analysis core (A2) is in place: it loads bench_press run JSON ([io.py](src/bench_stats/io.py)) and compares versions ([compare.py](src/bench_stats/compare.py)) with process-level Fieller, the δ gate, variance components that allow for autocorrelation and drift, design recommendations and Benjamini–Hochberg (all in [stats/](src/bench_stats/stats)), and reports the results as Markdown or JSON ([report.py](src/bench_stats/report.py), CLI `bench-stats analyze`). The git-ref runner (A1, [runner.py](src/bench_stats/runner.py), CLI `bench-stats run`) builds two refs in worktrees and runs them interleaved. It also holds exact ports of bench_press's own interval and verdict rules, checked against golden fixtures generated from bench_press `5fd6396` ([tests/fixtures/](tests/fixtures)). Install with `pip install -e ".[dev]"` (into the `perfBench` conda environment), run tests with `python -m pytest`; the end-to-end runner test builds Dart binaries and is opt-in with `python -m pytest -m dart`. |
| [src/bench_stats/validate/](src/bench_stats/validate) | The A4 simulation validation: a generator with known truth (normal model plus robustness scenarios), experiments run through the shipped estimators, and a summary that checks the plan's acceptance criteria. `python -m bench_stats.validate` (about 1 minute on 16 cores; `--quick` for a smoke test). Results: [sandbox/output/a4/summary.md](sandbox/output/a4/summary.md). |
| [bench/](bench) | Controlled Dart benchmarks (a fixed workload with an injectable, calibrated spin cost, plus a same-binary group) for pilots and real-hardware validation. Needs a bench_press clone next to this repository; see [bench/README.md](bench/README.md). |
| `data/runs/` | Raw bench_press run JSON and `bench-stats run` JSONL. Git-ignored. |

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
