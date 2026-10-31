import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from bench_stats.cli import main
from bench_stats.io import is_runner_file, load_runner_file
from bench_stats.runner import (
    RunnerError,
    external_path_overrides,
    launch_order,
    parse_process_output,
    resolve_project,
    run,
    write_overrides,
)

from .conftest import BENCH_PRESS_COMMIT, FIXTURES

REPO = Path(__file__).resolve().parents[1]
BENCH_PRESS = REPO.parent / "bench_press"


def _stdout(kind):
    return (FIXTURES / f"runner_stdout_{kind}_{BENCH_PRESS_COMMIT}.txt").read_text()


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True, capture_output=True)


# --- parsing and ordering ------------------------------------------------------------------------------------


def test_parse_recorded_output():
    suite = parse_process_output(_stdout("workload"))
    (b,) = suite["benchmarks"]
    assert (b["name"], b["target"]) == ("workload", "aot")
    assert len(b["raw_trials_ns"]) == 4 and "processes" not in b

    group = parse_process_output(_stdout("group"))["benchmarks"]
    assert [b["name"] for b in group] == ["baseline", "identical_copy", "spin"]
    assert all(b["coordinates"] == {"group": "Workload"} for b in group)
    assert [bool(b.get("is_baseline")) for b in group] == [True, False, False]


@pytest.mark.parametrize(
    "text, match",
    [
        ("no markers here\n", "no bench_press JSON markers"),
        ("<<<BENCH_PRESS_JSON_START>>>\n{}\n", "without an end marker"),
        ('<<<BENCH_PRESS_JSON_START>>>\n{"version": 2, "benchmarks": []}\n<<<BENCH_PRESS_JSON_END>>>', "schema version 1"),
        ("<<<BENCH_PRESS_JSON_START>>>\n{not json\n<<<BENCH_PRESS_JSON_END>>>", "Expecting property name"),
    ],
)
def test_parse_rejects_bad_output(text, match):
    with pytest.raises(ValueError, match=match):
        parse_process_output(text)


def test_launch_order_balanced_and_seeded():
    order = launch_order(20, seed=7)
    assert len(order) == 40
    for k in range(20):
        pair = order[2 * k : 2 * k + 2]
        assert {label for label, _ in pair} == {"baseline", "candidate"}
        assert {i for _, i in pair} == {k}
    assert order == launch_order(20, seed=7)
    assert order != launch_order(20, seed=8)
    firsts = [order[2 * k][0] for k in range(20)]
    assert 0 < firsts.count("baseline") < 20


# --- loading runner files ------------------------------------------------------------------------------------


def _write_runner_file(path, P=4, fail=("baseline", 1), unstable=("candidate", 2), aa=False):
    suite = parse_process_output(_stdout("workload"))
    order = launch_order(P, seed=3)
    header = {
        "type": "header",
        "schema": "bench-stats-run",
        "schema_version": 1,
        "run_id": "r1",
        "created": "2026-10-31T00:00:00+00:00",
        "aa": aa,
        "processes": P,
        "order": order,
        "versions": {
            "baseline": {"ref": "main", "commit": "a" * 40},
            "candidate": {"ref": "main" if aa else "feature", "commit": ("a" if aa else "b") * 40},
        },
    }
    lines = [header]
    for n, (label, i) in enumerate(order):
        s = json.loads(json.dumps(suite))
        b = s["benchmarks"][0]
        scale = (1 + 0.01 * i) * (0.95 if label == "candidate" else 1.0)
        b["raw_trials_ns"] = [x * scale for x in b["raw_trials_ns"]]
        if (label, i) == unstable:
            b["metrics"]["is_stable"] = False
        failed = (label, i) == fail
        lines.append(
            {
                "type": "process",
                "run_id": "r1",
                "version": label,
                "ref": header["versions"][label]["ref"],
                "commit": header["versions"][label]["commit"],
                "process_index": i,
                "launch_order": n,
                "exit_code": 255 if failed else 0,
                "error": "exit code 255: boom" if failed else None,
                "suite": None if failed else s,
            }
        )
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))
    return path


def test_load_runner_file(tmp_path):
    path = _write_runner_file(tmp_path / "run.jsonl")
    assert is_runner_file(path)
    base, cand = load_runner_file(path)
    (b,) = base.records
    (c,) = cand.records
    assert b.key == "workload:aot"
    assert (b.processes, c.processes) == (3, 4)
    assert base.meta["failed_processes"] == 1 and cand.meta["failed_processes"] == 0
    assert (base.meta["ref"], cand.meta["ref"]) == ("main", "feature")
    assert b.is_stable and not c.is_stable
    assert c.warmup["unstable_processes"] == [2]
    raw = parse_process_output(_stdout("workload"))["benchmarks"][0]["raw_trials_ns"]
    expected = [sum(raw) / len(raw) * (1 + 0.01 * i) * 0.95 for i in range(4)]
    assert c.process_means_ns == pytest.approx(expected, rel=1e-12)
    assert c.mean_ns == pytest.approx(sum(expected) / 4, rel=1e-12)
    assert base.environment["os"] == "macos"


def test_load_runner_file_group_keys(tmp_path):
    suite = parse_process_output(_stdout("group"))
    order = launch_order(2, 0)
    header = {"schema": "bench-stats-run", "schema_version": 1, "versions": {"baseline": {}, "candidate": {}}}
    recs = [header] + [
        {"type": "process", "version": label, "process_index": i, "launch_order": n, "error": None, "suite": suite}
        for n, (label, i) in enumerate(order)
    ]
    path = tmp_path / "g.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in recs))
    base, _ = load_runner_file(path)
    assert len(base.records) == 3 and all(r.group and r.processes == 2 for r in base.records)


def test_load_runner_file_needs_both_versions(tmp_path):
    path = _write_runner_file(tmp_path / "run.jsonl", P=1, fail=("candidate", 0))
    with pytest.raises(ValueError, match="no successful candidate"):
        load_runner_file(path)


def test_bench_press_json_is_not_a_runner_file(suite_path):
    assert not is_runner_file(suite_path)


def test_analyze_runner_file(tmp_path, capsys):
    path = _write_runner_file(tmp_path / "run.jsonl")
    out = tmp_path / "report.json"
    assert main(["analyze", str(path), "--format", "json", "-o", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["mode"] == "runs"
    assert report["inputs"]["candidate"]["ref"] == "feature"
    (comp,) = report["comparisons"]
    assert comp["speedup"]["ratio"] > 1.04
    assert comp["processes"] == {"baseline": 3, "candidate": 4}

    assert main(["analyze", str(path)]) == 0
    md = capsys.readouterr().out
    assert "baseline `main` (aaaaaaaaaaaa) vs candidate `feature` (bbbbbbbbbbbb); 1 failed processes excluded" in md

    assert main(["analyze", str(path), str(path)]) == 2
    assert "already holds both versions" in capsys.readouterr().err


# --- git worktrees and path dependencies ---------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path):
    """repo/pkg depends on ../lib2 (inside the repo) and ../../external (outside); lib2 depends on ../../external2."""
    root = tmp_path / "repo"
    (root / "pkg" / "benchmark").mkdir(parents=True)
    (root / "lib2").mkdir()
    (root / "pkg" / "pubspec.yaml").write_text(
        "name: pkg\n"
        "dependencies:\n  lib2:\n    path: ../lib2\n  args: ^2.0.0\n"
        "dev_dependencies:\n  ext:\n    path: ../../external\n"
        "dependency_overrides:\n  meta: 1.0.0\n"
    )
    (root / "lib2" / "pubspec.yaml").write_text("name: lib2\ndependencies:\n  ext2:\n    path: ../../external2\n")
    (root / "pkg" / "benchmark" / "b.dart").write_text("void main() {}\n")
    _git(tmp_path, "init", "-q", "-b", "main", str(root))
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_external_path_overrides(repo, tmp_path):
    project = resolve_project(repo / "pkg" / "benchmark" / "b.dart")
    assert project.repo_root == repo.resolve()
    assert (project.package_rel, project.benchmark_rel) == (Path("pkg"), Path("benchmark/b.dart"))

    wt = tmp_path / "elsewhere" / "wt"
    _git(repo, "worktree", "add", "-q", "--detach", str(wt), "HEAD")
    overrides = external_path_overrides(wt, project)
    parent = repo.resolve().parent
    assert overrides == {"ext": str(parent / "external"), "ext2": str(parent / "external2")}

    write_overrides(wt / "pkg", overrides)
    data = yaml.safe_load((wt / "pkg" / "pubspec_overrides.yaml").read_text())
    assert data["dependency_overrides"] == {
        "meta": "1.0.0",
        "ext": {"path": str(parent / "external")},
        "ext2": {"path": str(parent / "external2")},
    }


def test_run_setup_errors(repo, tmp_path):
    bench = repo / "pkg" / "benchmark" / "b.dart"
    with pytest.raises(RunnerError, match="unknown git ref: nope"):
        run(bench, "nope", None, 2, tmp_path / "out.jsonl", log=lambda _: None)
    assert not (tmp_path / "out.jsonl").exists()
    worktrees = subprocess.run(["git", "worktree", "list"], cwd=repo, capture_output=True, text=True).stdout
    assert len(worktrees.splitlines()) == 1

    existing = tmp_path / "exists.jsonl"
    existing.write_text("")
    with pytest.raises(RunnerError, match="already exists"):
        run(bench, "main", None, 2, existing, log=lambda _: None)

    with pytest.raises(RunnerError, match="candidate flags need --candidate"):
        run(bench, "main", None, 2, tmp_path / "x.jsonl", candidate_flags=["-DX=1"], log=lambda _: None)


# --- end to end with Dart (opt-in: python -m pytest -m dart) -------------------------------------------------

_BENCH = """\
import 'package:bench_press/bench_press.dart';

const int spinIterations = {spin};

final class SumBenchmark extends Benchmark {{
  SumBenchmark() : super('sum');

  final List<int> _data = List<int>.generate(2000, (i) => (i * 7919) % 1000);

  @override
  void run() {{
    var s = 0;
    for (final x in _data) {{
      s += x;
    }}
    for (var i = 0; i < spinIterations; i++) {{
      s = (s * 1103515245 + 12345) & 0x7fffffff;
    }}
    Blackhole.consume(s);
  }}
}}

void main(List<String> args) => mainBenchmarkSuite([SumBenchmark()], args);
"""


@pytest.mark.dart
@pytest.mark.skipif(shutil.which("dart") is None or not BENCH_PRESS.is_dir(), reason="needs dart and ../bench_press")
def test_run_end_to_end(tmp_path):
    root = tmp_path / "repo"
    pkg = root / "pkg"
    (pkg / "benchmark").mkdir(parents=True)
    rel = os.path.relpath(BENCH_PRESS, pkg)
    (pkg / "pubspec.yaml").write_text(
        f"name: e2e\nenvironment:\n  sdk: ^3.13.0\ndev_dependencies:\n  bench_press:\n    path: {rel}\n"
    )
    bench = pkg / "benchmark" / "sum_benchmark.dart"
    bench.write_text(_BENCH.format(spin=0))
    _git(tmp_path, "init", "-q", "-b", "main", str(root))
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "baseline")
    bench.write_text(_BENCH.format(spin=2000))
    _git(root, "commit", "-q", "-am", "slower")
    bench.write_text(_BENCH.format(spin=0))

    out = tmp_path / "run.jsonl"
    logs = []
    failed = run(bench, "main~1", "main", 2, out, trials=4, seed=1, log=logs.append)
    assert failed == 0
    assert any("uncommitted changes" in line for line in logs)

    header = json.loads(out.read_text().splitlines()[0])
    v = header["versions"]
    assert v["baseline"]["commit"] != v["candidate"]["commit"]
    assert v["baseline"]["binary_sha256"] != v["candidate"]["binary_sha256"]
    assert v["baseline"]["pubspec_overrides"] == {"bench_press": str(BENCH_PRESS.resolve())}

    base, cand = load_runner_file(out)
    (b,), (c,) = base.records, cand.records
    assert (b.key, b.processes, len(b.process_trials[0])) == ("sum:aot", 2, 4)
    assert c.mean_ns > b.mean_ns

    worktrees = subprocess.run(["git", "worktree", "list"], cwd=root, capture_output=True, text=True).stdout
    assert len(worktrees.splitlines()) == 1
