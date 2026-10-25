/// Writes golden fixtures from bench_press itself, for the Python ports in
/// `bench_stats` (plan A2 unit tests).
///
/// Run from `bench/`:
///
///     dart run tool/golden_bench_press.dart ../tests/fixtures
///
/// Every input is generated from a fixed seed and stored next to bench_press's
/// output, so the Python tests read both from the fixture and never need Dart.
/// Regenerate (and re-pin) whenever the bench_press commit changes.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:bench_press/bench_press.dart';
// Implementation imports: the quantile functions and the reporter are not
// exported, and this tool exists to pin their exact behaviour.
// ignore: implementation_imports
import 'package:bench_press/src/stats/fieller.dart'
    show normalQuantile, studentTQuantile;
// ignore: implementation_imports
import 'package:bench_press/src/telemetry/markdown_reporter.dart';
// ignore: implementation_imports
import 'package:bench_press/src/telemetry/schema.dart';

const String benchPressCommit = '5fd6396';

final math.Random _rng = math.Random(20261025);

double _gauss() {
  final u1 = 1.0 - _rng.nextDouble();
  final u2 = _rng.nextDouble();
  return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2);
}

List<double> _sample(int n, double mean, double cv) => [
  for (var i = 0; i < n; i++) mean * (1.0 + cv * _gauss()),
];

/// JSON cannot hold non-finite doubles, so encode them as strings.
Object _enc(double x) => x.isFinite ? x : x.toString();

Map<String, Object?> _fiellerCase(
  List<double> a,
  List<double> b, {
  double conf = 0.95,
  bool paired = false,
}) {
  final f = FiellerInterval.compute(
    sampleA: a,
    sampleB: b,
    confidenceLevel: conf,
    paired: paired,
  );
  return {
    'a': a,
    'b': b,
    'conf': conf,
    'paired_requested': paired,
    'ratio': _enc(f.ratio),
    'lower': _enc(f.lowerBound),
    'upper': _enc(f.upperBound),
    'g': _enc(f.g),
    'is_valid': f.isValid,
    'paired': f.paired,
  };
}

List<Map<String, Object?>> _fiellerCases() {
  final cases = <Map<String, Object?>>[
    // Cases from bench_press test/fieller_test.dart.
    _fiellerCase([50, 50, 50], [100, 100, 100]),
    _fiellerCase(
      [49, 51, 50, 48, 52, 50, 49.5, 50.5],
      [98, 102, 99, 101, 100, 97, 103, 100],
    ),
    _fiellerCase([10, 11, 9, 10.5, 9.5], [1, 30, -20, 25, -15, 2]),
    _fiellerCase([], [100, 100]),
    _fiellerCase([50], [100, 100]),
    _fiellerCase([50, 50], [100]),
    _fiellerCase([50, 50], [0, 0]),
    _fiellerCase(
      [48.2, 48.4, 49.1, 49.4, 50.6, 50.9, 51.6, 51.8],
      [96, 97, 98, 99, 101, 102, 103, 104],
      paired: true,
    ),
    _fiellerCase(
      [51.8, 51.6, 50.9, 50.6, 49.4, 49.1, 48.4, 48.2],
      [96, 97, 98, 99, 101, 102, 103, 104],
      paired: true,
    ),
    _fiellerCase([50, 51, 52, 53, 54], [100, 102, 104, 106, 108], paired: true),
    _fiellerCase(
      [50, 51, 52, 53, 54, 55],
      [100, 102, 104, 106, 108],
      paired: true,
    ),
    // Unequal sizes, unpaired.
    _fiellerCase(_sample(3, 100, 0.02), _sample(7, 101, 0.01)),
    _fiellerCase(_sample(12, 99, 0.05), _sample(4, 100, 0.03)),
  ];
  for (final n in [2, 3, 5, 8, 16, 40]) {
    for (final cv in [0.005, 0.02, 0.1, 0.4]) {
      for (final ratio in [0.5, 0.97, 1.0, 1.04, 2.0]) {
        for (final paired in [false, true]) {
          for (final conf in [0.95, 0.90]) {
            final shared = [for (var i = 0; i < n; i++) _gauss()];
            List<double> draw(double mean) => [
              for (var i = 0; i < n; i++)
                mean *
                    (1.0 +
                        cv *
                            (paired
                                ? 0.8 * shared[i] + 0.6 * _gauss()
                                : _gauss())),
            ];
            cases.add(
              _fiellerCase(
                draw(1000.0 * ratio),
                draw(1000.0),
                conf: conf,
                paired: paired,
              ),
            );
          }
        }
      }
    }
  }
  return cases;
}

Map<String, Object?> _quantiles() => {
  'student_t': [
    for (final p in [0.9, 0.95, 0.975, 0.99, 0.995])
      for (final df in [
        0.5,
        1.0,
        1.2,
        1.5,
        1.9,
        2.0,
        2.5,
        3.0,
        4.0,
        4.7,
        5.0,
        7.3,
        10.0,
        15.0,
        30.0,
        100.0,
        1000.0,
      ])
        {'p': p, 'df': df, 'value': studentTQuantile(p, df)},
  ],
  'normal': [
    for (final p in [
      0.0001,
      0.001,
      0.01,
      0.02,
      0.02425,
      0.025,
      0.05,
      0.1,
      0.3,
      0.5,
      0.7,
      0.9,
      0.95,
      0.975,
      0.97575,
      0.98,
      0.99,
      0.999,
      0.9999,
    ])
      {'p': p, 'value': normalQuantile(p)},
  ],
};

final EnvironmentInfo _env = const EnvironmentInfo(
  os: 'golden',
  arch: 'golden',
  dartVersion: 'golden',
);

BenchmarkEntry _entry(String name, List<double> samples) => BenchmarkEntry(
  name: name,
  target: 'aot',
  mode: 'sync',
  samples: samples.length,
  metrics: BenchmarkMetrics.fromSamples(samples),
  rawTrialsNs: samples,
);

BenchmarkSuiteResult _suite(List<BenchmarkEntry> entries) =>
    BenchmarkSuiteResult(
      timestamp: DateTime.utc(2026, 10, 25),
      environment: _env,
      benchmarks: entries,
    );

/// Status and CI cells of every `case_*` row in a rendered delta table.
Map<String, (String, String)> _parseDeltaRows(String markdown) {
  final rows = <String, (String, String)>{};
  for (final line in const LineSplitter().convert(markdown)) {
    if (!line.startsWith('| case_')) continue;
    final cells = line.split('|').map((c) => c.trim()).toList();
    rows[cells[1]] = (cells[cells.length - 2], cells[cells.length - 3]);
  }
  return rows;
}

Map<String, Object?> _verdicts() {
  final base = <BenchmarkEntry>[];
  final cur = <BenchmarkEntry>[];
  final inputs = <Map<String, Object?>>[];
  var i = 0;
  for (final n in [3, 16]) {
    for (final cv in [0.002, 0.01, 0.03, 0.08]) {
      for (final ratio in [
        0.85,
        0.93,
        0.95,
        0.96,
        0.97,
        0.98,
        0.99,
        1.0,
        1.005,
        1.01,
        1.02,
        1.03,
        1.04,
        1.05,
        1.06,
        1.08,
        1.2,
      ]) {
        final name = 'case_${(i++).toString().padLeft(3, '0')}';
        final b = _sample(n, 1000.0, cv);
        final c = _sample(n, 1000.0 / ratio, cv);
        final eb = _entry(name, b);
        final ec = _entry(name, c);
        base.add(eb);
        cur.add(ec);
        inputs.add({
          'name': name,
          'baseline': b,
          'current': c,
          'baseline_stable': eb.metrics.isStable,
          'current_stable': ec.metrics.isStable,
        });
      }
    }
  }
  final out = <String, Object?>{'cases': inputs};
  for (final threshold in [0.0, 0.03, 0.05]) {
    final md = MarkdownReporter.renderDeltaTable(
      baseline: _suite(base),
      current: _suite(cur),
      threshold: threshold,
    );
    final rows = _parseDeltaRows(md);
    out['threshold_$threshold'] = {
      for (final e in rows.entries)
        e.key: {'status': e.value.$1, 'ci': e.value.$2},
    };
  }
  return out;
}

List<Map<String, Object?>> _components() {
  final cases = <Map<String, Object?>>[];
  for (final p in [1, 2, 3, 5, 10]) {
    for (final balanced in [true, false]) {
      for (final s2 in [0.0, 0.01, 0.05]) {
        final trials = <List<double>>[];
        for (var j = 0; j < p; j++) {
          final n = balanced ? 8 : 1 + _rng.nextInt(12);
          final offset = 1000.0 * (1.0 + s2 * _gauss());
          trials.add(_sample(n, offset, 0.01));
        }
        final c = ProcessVarianceComponents.compute(trials);
        cases.add({'process_trials_ns': trials, 'result': c?.toJson()});
      }
    }
  }
  cases.add({
    'process_trials_ns': [
      [1000.0],
      [1001.0],
    ],
    'result': ProcessVarianceComponents.compute([
      [1000.0],
      [1001.0],
    ])?.toJson(),
  });
  return cases;
}

/// A suite as bench_press writes it, mixing P = 1 and P > 1 entries.
BenchmarkSuiteResult _sampleSuite() {
  BenchmarkEntry processEntry(
    String name,
    List<double> trials, {
    Map<String, String> coords = const {},
    bool stable = true,
  }) => BenchmarkEntry(
    name: name,
    target: 'aot',
    mode: 'sync',
    samples: trials.length,
    metrics: BenchmarkMetrics.fromSamples(trials),
    rawTrialsNs: trials,
    warmup: {'is_stable': stable, 'total_iterations': 100},
    coordinates: BenchmarkCoordinates(coords),
  );

  final multi = BenchmarkEntry.fromProcesses([
    for (var j = 0; j < 4; j++)
      processEntry('multi', _sample(6, 1000 * (1 + 0.01 * _gauss()), 0.01)),
  ]);
  final unstable = BenchmarkEntry.fromProcesses([
    for (var j = 0; j < 3; j++)
      processEntry('unstable', _sample(5, 500, 0.01), stable: j != 1),
  ]);
  final grouped = [
    for (final variant in ['base', 'fast'])
      BenchmarkEntry.fromProcesses([
        for (var j = 0; j < 3; j++)
          processEntry(
            variant,
            _sample(4, variant == 'base' ? 200 : 180, 0.01),
            coords: {'group': 'G'},
          ),
      ]),
  ];
  return _suite([
    _entry('single', _sample(16, 1000, 0.01)),
    multi,
    unstable,
    ...grouped,
  ]);
}

void main(List<String> args) {
  final outDir = Directory(args.isEmpty ? '../tests/fixtures' : args.first)
    ..createSync(recursive: true);
  final golden = {
    'bench_press_commit': benchPressCommit,
    'quantiles': _quantiles(),
    'fieller': _fiellerCases(),
    'verdicts': _verdicts(),
    'components': _components(),
  };
  final encoder = const JsonEncoder.withIndent(' ');
  File('${outDir.path}/bench_press_golden_$benchPressCommit.json')
      .writeAsStringSync(encoder.convert(golden));
  File('${outDir.path}/bench_press_suite_$benchPressCommit.json')
      .writeAsStringSync(encoder.convert(_sampleSuite().toJson()));
  stdout.writeln('wrote golden fixtures to ${outDir.path}');
}
