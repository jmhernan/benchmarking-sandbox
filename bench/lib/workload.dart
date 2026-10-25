/// Controlled workload and injectable spin cost for bench_stats experiments.
library;

import 'dart:math' as math;

/// Number of integers sorted per operation.
const int workloadSize = 1000;

/// Extra spin iterations per operation, fixed at compile time with
/// `-DBENCH_SPIN=<n>` (for example
/// `bench_press run --compiler-flag=-DBENCH_SPIN=<n>`). Defaults to 0, in which
/// case the compiler removes the spin loop and the binary is the plain workload.
const int spinIterations = int.fromEnvironment('BENCH_SPIN');

/// Spin iterations for the `spin` variant of the in-process group benchmark,
/// fixed at compile time with `-DBENCH_GROUP_SPIN=<n>`. The default adds about
/// +5% on an Apple-silicon Mac under AOT (calibrated 2026-10-24 with
/// `tool/calibrate_spin.dart`); recalibrate on other machines.
const int groupSpinIterations = int.fromEnvironment(
  'BENCH_GROUP_SPIN',
  defaultValue: 4800,
);

/// Sorts a fixed, seeded permutation of [workloadSize] integers.
///
/// The input is copied into a preallocated buffer, so an operation does not
/// allocate.
final class SortWorkload {
  SortWorkload()
    : _source = List<int>.generate(workloadSize, (i) => i)
        ..shuffle(math.Random(42)),
      _buffer = List<int>.filled(workloadSize, 0);

  final List<int> _source;
  final List<int> _buffer;

  /// Runs one operation and returns a data-dependent value to consume.
  int run() {
    _buffer.setRange(0, workloadSize, _source);
    _buffer.sort();
    return _buffer[workloadSize ~/ 2];
  }
}

/// A serial xorshift chain of [iterations] steps seeded from runtime data, so
/// the compiler can neither fold nor vectorise it.
int spin(int iterations, int seed) {
  var x = seed | 1;
  for (var i = 0; i < iterations; i++) {
    x ^= x << 13;
    x ^= x >>> 7;
    x ^= x << 17;
  }
  return x;
}
