import 'package:bench_press/bench_press.dart';
import 'package:bench_sandbox/workload.dart';

/// The controlled workload, plus [spinIterations] of spin cost.
///
/// Built without `-DBENCH_SPIN` it is the baseline for A/A runs. Built with
/// `-DBENCH_SPIN=<n>` it is the known-effect candidate.
final class WorkloadBenchmark extends Benchmark {
  WorkloadBenchmark() : super('workload');

  final SortWorkload _workload = SortWorkload();

  @override
  void run() {
    final value = _workload.run();
    Blackhole.consume(spin(spinIterations, value));
  }
}

final List<Object> benchmarks = [WorkloadBenchmark()];

void main(List<String> args) => mainBenchmarkSuite(benchmarks, args);
