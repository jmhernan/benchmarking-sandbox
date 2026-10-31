# bench/

Controlled Dart benchmarks for validating the `bench_stats` statistics layer (plan A0, used in A0c and A5). It depends on a local clone of [kevmoo/bench_press](https://github.com/kevmoo/bench_press) checked out next to this repository (`../../bench_press` from here).

## Toolchain (recorded 2026-10-24)

| Tool | Version |
|---|---|
| Dart SDK | 3.13.7 (stable), `macos_arm64` |
| bench_press | `5fd6396` (v0.4.2) |
| Machine | Apple-silicon Mac, macOS |

## Benchmarks

| File | What it measures | Used for |
|---|---|---|
| [benchmark/workload_benchmark.dart](benchmark/workload_benchmark.dart) | `workload`: sort a fixed, seeded permutation of 1,000 ints (no allocation per operation), plus `BENCH_SPIN` iterations of spin cost | A/A runs (`BENCH_SPIN` unset), known-effect candidate (`-DBENCH_SPIN=<n>`) |
| [benchmark/group_benchmark.dart](benchmark/group_benchmark.dart) | Group mode: `baseline`, `identical_copy` (same code) and `spin` (+`BENCH_GROUP_SPIN` iterations, default 4,800 ≈ +5%) in one process | Same-binary A/A and paired known effect (A5 step 3) |

The spin cost is a serial xorshift chain seeded from the workload's result, so the compiler can neither fold nor vectorise it. Because it's a compile-time constant, a build without `-DBENCH_SPIN` contains no spin loop at all.

## Running

```bash
cd bench
dart pub get

# A/A, several processes (A0c pilot: --processes 40)
dart run bench_press run -t aot --processes 3 -o ../data/runs/<name>.json benchmark/workload_benchmark.dart

# Known-effect candidate
dart run bench_press run -t aot --processes 3 --compiler-flag=-DBENCH_SPIN=4800 \
  -o ../data/runs/<name>.json benchmark/workload_benchmark.dart

# Group mode with the threshold gate
dart run bench_press run -t aot --processes 3 --threshold 0.03 --no-save benchmark/group_benchmark.dart

# Analyse a run (from the repository root, perfBench environment)
bench-stats analyze data/runs/<name>.json
```

Builds with different `-D` values write to the same artifact path (`.dart_tool/bench_press/build/aot/`), so with bench_press run them one after another, not in one interleaved session. `bench-stats run` builds each version into its own directory and can interleave them; see the "Comparing two git refs" section of the [top-level README](../README.md):

```bash
# From the repository root: baseline vs known-effect candidate, interleaved in one session
bench-stats run bench/benchmark/workload_benchmark.dart --baseline HEAD --candidate HEAD \
  --candidate-flag=-DBENCH_SPIN=4800 -P 10 -o data/runs/<name>.jsonl
```

## Calibrating the spin cost

```bash
dart compile exe tool/calibrate_spin.dart -o /tmp/calibrate_spin
/tmp/calibrate_spin <workload_mean_ns> [target_fraction]
```

`<workload_mean_ns>` is the bench_press `mean_ns` of a build without `BENCH_SPIN`. The tool times only the spin, because the workload's speed depends on the whole binary. On 2026-10-24 the same sort took about 70 µs/op in a standalone program, about 115 µs/op once an unrelated `List<double>.sort` was added to that program, and about 135–138 µs/op inside the bench_press harness. AOT whole-program optimisation specialises `List.sort` only when a single element type is sorted anywhere in the program.

Measured that day: workload ≈ 138 µs/op, spin ≈ 1.43 ns/iteration, so ≈ 4,800 iterations for +5%. A group run (AOT, 3 processes, `--threshold 0.03`) gave `identical_copy` 1.00× [1.00, 1.01] ✅ Equivalent and `spin` 0.95× [0.95, 0.95] ⚠️ Slow.

## Golden fixtures for the Python ports

[tool/golden_bench_press.dart](tool/golden_bench_press.dart) runs bench_press's own code (Fieller intervals, t and normal quantiles, the delta-table verdicts at several thresholds, `ProcessVarianceComponents`) on fixed, seeded inputs. It writes both the inputs and the outputs to `../tests/fixtures/`, so the `bench_stats` tests can check the Python ports to 1e-9 without Dart:

```bash
dart run tool/golden_bench_press.dart ../tests/fixtures
```

Regenerate the fixtures, and update the commit in the file names and in `tests/conftest.py`, whenever the bench_press pin changes.
