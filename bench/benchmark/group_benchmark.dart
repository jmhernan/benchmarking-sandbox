import 'package:bench_press/bench_press.dart';
import 'package:bench_sandbox/workload.dart';

final SortWorkload _workload = SortWorkload();

/// In-process (group mode) comparison: every variant runs in the same process.
///
/// - `identical_copy` runs exactly the baseline code, for a same-binary A/A.
/// - `spin` adds [groupSpinIterations] of spin cost, for a known effect.
final BenchmarkGroup workloadGroup = BenchmarkGroup('Workload', [
  BenchmarkVariant('baseline', () {
    Blackhole.consume(_workload.run());
  }, isBaseline: true),
  BenchmarkVariant('identical_copy', () {
    Blackhole.consume(_workload.run());
  }),
  BenchmarkVariant('spin', () {
    final value = _workload.run();
    Blackhole.consume(spin(groupSpinIterations, value));
  }),
]);

final List<Object> benchmarks = [workloadGroup];

void main(List<String> args) => mainBenchmarkSuite(benchmarks, args);
