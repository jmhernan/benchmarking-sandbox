"""Golden-file tests for the A3 report, in both formats, plus the CLI.

Regenerate the goldens after an intended change with:

    BENCH_STATS_UPDATE_GOLDEN=1 python -m pytest tests/test_report.py

and review the diff of tests/fixtures/golden/ before committing.
"""

import json
import math
import os

import pytest

from bench_stats.cli import main
from bench_stats.io import load_run
from bench_stats.report import SCHEMA, build_report, render_markdown

from .conftest import FIXTURES

GOLDEN = FIXTURES / "golden"
UPDATE = os.environ.get("BENCH_STATS_UPDATE_GOLDEN") == "1"
BASELINE = FIXTURES / "report_baseline.json"
CANDIDATE = FIXTURES / "report_candidate.json"


def _check_golden(name: str, text: str) -> None:
    path = GOLDEN / name
    if UPDATE:
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert path.exists(), f"missing golden {path}; run with BENCH_STATS_UPDATE_GOLDEN=1"
    expected = path.read_text(encoding="utf-8")
    if name.endswith(".json"):
        _assert_json_close(json.loads(text), json.loads(expected), name)
    else:
        assert text == expected


def _assert_json_close(actual, expected, where):
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys(), where
        for k in expected:
            _assert_json_close(actual[k], expected[k], f"{where}.{k}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), where
        for i, (a, e) in enumerate(zip(actual, expected)):
            _assert_json_close(a, e, f"{where}[{i}]")
    elif isinstance(expected, float) and not isinstance(expected, bool):
        assert actual == pytest.approx(expected, rel=1e-9, abs=1e-12), where
    else:
        assert actual == expected, where


@pytest.fixture(scope="module")
def runs_report():
    return build_report(load_run(BASELINE), load_run(CANDIDATE))


@pytest.fixture(scope="module")
def groups_report(suite_path):
    return build_report(load_run(suite_path))


def test_runs_report_golden(runs_report):
    _check_golden("report_runs.md", render_markdown(runs_report))
    _check_golden("report_runs.json", json.dumps(runs_report, indent=2, ensure_ascii=False) + "\n")


def test_groups_report_golden(groups_report):
    _check_golden("report_groups.md", render_markdown(groups_report))
    _check_golden("report_groups.json", json.dumps(groups_report, indent=2, ensure_ascii=False) + "\n")


def test_runs_report_content(runs_report):
    assert runs_report["schema"] == SCHEMA and runs_report["mode"] == "runs"
    verdicts = {c["name"]: c["gate"]["verdict"] for c in runs_report["comparisons"]}
    assert verdicts["faster"] == "faster"
    assert verdicts["slower"] == "slower"
    assert verdicts["same"] == "no meaningful change"
    assert verdicts["noisy"] == "inconclusive"
    assert verdicts["single"] == "inconclusive"
    small = next(c for c in runs_report["comparisons"] if c["name"] == "small")
    assert small["gate"]["verdict"] == "no meaningful change" and small["gate"]["detectable"]
    assert runs_report["summary"]["only_baseline"] == ["retired:aot"]
    assert runs_report["summary"]["only_candidate"] == ["new:aot"]
    single = [d for d in runs_report["diagnostics"] if d["name"] == "single"]
    assert all(d["components"] is None and d["design"] is None for d in single)
    drifting = [d for d in runs_report["diagnostics"] if d["name"] == "drifting"]
    assert all(d["components"]["drift"]["detected"] for d in drifting)
    for d in runs_report["diagnostics"]:
        if d["design"] is not None:
            assert d["design"]["processes_per_version"] >= 5
            assert d["design"]["trials_per_process"] % 4 == 0


def test_report_json_is_strict(runs_report, groups_report):
    for report in (runs_report, groups_report):
        json.dumps(report, allow_nan=False)


def test_group_baseline_diagnostics_are_consistent(groups_report):
    (c,) = groups_report["comparisons"]
    assert c["paired"] and c["key"] == "fast:aot:group=G" and c["baseline_key"] == "base:aot:group=G"


def test_cli_markdown_and_json(tmp_path, capsys):
    assert main(["analyze", str(BASELINE), str(CANDIDATE)]) == 0
    assert capsys.readouterr().out.startswith("# bench-stats report")

    out = tmp_path / "report.json"
    assert main(["analyze", str(BASELINE), str(CANDIDATE), "--format", "json", "-o", str(out), "--threshold", "0.05"]) == 0
    report = json.loads(out.read_text())
    assert report["settings"]["threshold"] == 0.05
    assert report["settings"]["detect"] == pytest.approx(0.10)


def test_cli_rejects_bad_input(tmp_path, capsys):
    assert main(["analyze", str(tmp_path / "missing.json")]) == 2
    assert "cannot read input" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        main(["analyze", str(BASELINE), "--threshold", "3"])
    assert e.value.code == 2


def test_markdown_handles_unbounded_and_missing_values(runs_report):
    md = render_markdown(runs_report)
    assert "unbounded" in md and "| `single:aot` | baseline | 1 |" in md
    assert not any(token in md for token in ("nan", "None", "inf"))
    assert math.isfinite(runs_report["summary"]["expected_false_flags"]["detectable (interval excludes 1)"])
