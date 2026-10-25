/// Estimates the spin iterations that add a target fraction to the workload.
///
/// Only the spin cost is timed here. The workload time must come from
/// bench_press (`mean_ns` of a `-DBENCH_SPIN=0` build): AOT whole-program
/// optimisation makes the same sort about 1.6x faster in a small standalone
/// program than inside the bench_press harness, so timing it here is wrong.
///
///     dart compile exe tool/calibrate_spin.dart -o /tmp/calibrate_spin
///     /tmp/calibrate_spin <workload_mean_ns> [target_fraction]   # default 0.05
///
/// The result is a starting value. The realised effect is measured separately
/// with bench_press (plan A5 step 2).
library;

import 'dart:io';

import 'package:bench_sandbox/workload.dart';

const Duration _window = Duration(seconds: 2);
const int _spinProbe = 100000;

int _sink = 1;

void main(List<String> args) {
  if (args.isEmpty) {
    stderr.writeln(
      'usage: calibrate_spin <workload_mean_ns> [target_fraction]',
    );
    exit(64);
  }
  final workloadNs = double.parse(args[0]);
  final target = args.length > 1 ? double.parse(args[1]) : 0.05;

  for (var i = 0; i < 100; i++) {
    _sink ^= spin(_spinProbe, _sink);
  }
  final sw = Stopwatch()..start();
  var calls = 0;
  while (sw.elapsed < _window) {
    _sink ^= spin(_spinProbe, _sink);
    calls++;
  }
  final spinNs = sw.elapsedMicroseconds * 1000 / (calls * _spinProbe);
  final iterations = (target * workloadNs / spinNs).round();

  print('workload (given): ${workloadNs.toStringAsFixed(1)} ns/op');
  print('spin:             ${spinNs.toStringAsFixed(4)} ns/iteration');
  print('target:           +${(target * 100).toStringAsFixed(1)}%');
  print('BENCH_SPIN:       $iterations');
  print('(sink: ${_sink & 1})');
}
