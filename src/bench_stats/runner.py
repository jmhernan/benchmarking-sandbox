"""Git-ref runner (plan A1): build two refs of a Dart package and launch their AOT binaries interleaved.

bench_press's `--diff` compares against a stored JSON from an earlier session, and A4 showed that drift between
sessions breaks the interval. This builds both refs in git worktrees, then launches 2P processes in one session,
in a seeded order balanced within consecutive pairs, and writes one JSONL record per process.
"""

import datetime as dt
import hashlib
import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .io import RUNNER_LABELS, RUNNER_SCHEMA, RUNNER_SCHEMA_VERSION

JSON_START = "<<<BENCH_PRESS_JSON_START>>>"
JSON_END = "<<<BENCH_PRESS_JSON_END>>>"
_DEP_SECTIONS = ("dependencies", "dev_dependencies", "dependency_overrides")

Log = Callable[[str], None]


class RunnerError(Exception):
    """A setup or build step failed; nothing was measured."""


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def launch_order(processes: int, seed: int) -> list[tuple[str, int]]:
    """2P launches: pair i holds baseline i and candidate i, in a seeded random order within the pair."""
    rng = random.Random(seed)
    order: list[tuple[str, int]] = []
    for i in range(processes):
        pair = [(RUNNER_LABELS[0], i), (RUNNER_LABELS[1], i)]
        if rng.random() < 0.5:
            pair.reverse()
        order += pair
    return order


def parse_process_output(stdout: str) -> dict[str, Any]:
    """The bench_press suite JSON a compiled benchmark prints between its stream markers."""
    start = stdout.find(JSON_START)
    if start == -1:
        raise ValueError("no bench_press JSON markers in the process output")
    end = stdout.find(JSON_END, start)
    if end == -1:
        raise ValueError("bench_press JSON start marker without an end marker")
    suite = json.loads(stdout[start + len(JSON_START) : end])
    if not isinstance(suite, dict) or suite.get("version") != 1 or not isinstance(suite.get("benchmarks"), list):
        raise ValueError("unexpected bench_press JSON (expected schema version 1 with a benchmarks list)")
    return suite


# --- project, git and pub -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Project:
    repo_root: Path
    package_rel: Path
    benchmark_rel: Path


def _check(cmd: Sequence[str], cwd: Path, what: str) -> str:
    try:
        r = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True)
    except OSError as e:
        raise RunnerError(f"{what}: {e}") from None
    if r.returncode != 0:
        detail = (r.stderr.strip() or r.stdout.strip())[-2000:]
        raise RunnerError(f"{what} failed (exit {r.returncode}):\n{detail}")
    return r.stdout.strip()


def _git(cwd: Path, *args: str) -> str:
    return _check(["git", *args], cwd, f"git {' '.join(args)}")


def resolve_project(benchmark: Path) -> Project:
    """The Dart package (nearest pubspec.yaml above the benchmark) and the git repository that holds it."""
    bench = benchmark.resolve()
    if not bench.is_file():
        raise RunnerError(f"benchmark file not found: {benchmark}")
    package = next((d for d in bench.parents if (d / "pubspec.yaml").is_file()), None)
    if package is None:
        raise RunnerError(f"no pubspec.yaml above {benchmark}")
    root = Path(_git(package, "rev-parse", "--show-toplevel")).resolve()
    if not package.is_relative_to(root):
        raise RunnerError(f"{package} is outside the git repository {root}")
    return Project(root, package.relative_to(root), bench.relative_to(package))


def _path_deps(pubspec: Path) -> dict[str, str]:
    data = yaml.safe_load(pubspec.read_text(encoding="utf-8")) or {}
    out: dict[str, str] = {}
    for section in _DEP_SECTIONS:
        for name, spec in (data.get(section) or {}).items():
            if isinstance(spec, dict) and isinstance(spec.get("path"), str):
                out[name] = spec["path"]
    return out


def external_path_overrides(worktree: Path, project: Project) -> dict[str, str]:
    """Relative path dependencies that leave the repository, pinned to where they point from the main checkout.

    A worktree lives elsewhere, so `../../bench_press` would point at nothing. Paths inside the repository resolve
    inside the worktree (they are part of the ref) and are followed transitively."""
    overrides: dict[str, str] = {}
    seen: set[Path] = set()
    stack = [project.package_rel]
    while stack:
        rel = stack.pop()
        if rel in seen:
            continue
        seen.add(rel)
        for filename in ("pubspec.yaml", "pubspec_overrides.yaml"):
            pubspec = worktree / rel / filename
            if not pubspec.is_file():
                continue
            for name, dep in _path_deps(pubspec).items():
                if os.path.isabs(dep):
                    continue
                target = Path(os.path.normpath(project.repo_root / rel / dep))
                if target.is_relative_to(project.repo_root):
                    stack.append(target.relative_to(project.repo_root))
                else:
                    overrides.setdefault(name, str(target))
    return overrides


def write_overrides(package_dir: Path, overrides: dict[str, str]) -> None:
    """Add `overrides` to the package's pubspec_overrides.yaml.

    That file's `dependency_overrides` replaces the one in pubspec.yaml, so the existing overrides are carried over."""
    if not overrides:
        return
    path = package_dir / "pubspec_overrides.yaml"
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        pubspec = yaml.safe_load((package_dir / "pubspec.yaml").read_text(encoding="utf-8")) or {}
        data = {"dependency_overrides": pubspec.get("dependency_overrides") or {}}
    merged = dict(data.get("dependency_overrides") or {})
    merged.update({name: {"path": p} for name, p in overrides.items()})
    data["dependency_overrides"] = merged
    path.write_text("# Written by bench-stats run\n" + yaml.safe_dump(data, sort_keys=True), encoding="utf-8")


@dataclass
class Build:
    label: str
    ref: str
    commit: str
    worktree: Path
    package_dir: Path
    binary: Path
    compiler_flags: list[str]
    sha256: str = ""
    build_seconds: float = 0.0
    overrides: dict[str, str] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "commit": self.commit,
            "compiler_flags": self.compiler_flags,
            "binary_sha256": self.sha256,
            "build_seconds": round(self.build_seconds, 3),
            "pubspec_overrides": self.overrides,
        }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_ref(project: Project, ref: str, label: str, work_dir: Path, compiler_flags: Sequence[str], log: Log) -> Build:
    """Check out `ref` in a worktree, `dart pub get`, then `dart compile exe` the benchmark (as bench_press does)."""
    try:
        commit = _git(project.repo_root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except RunnerError:
        raise RunnerError(f"unknown git ref: {ref}") from None
    worktree = work_dir / "worktrees" / label
    _git(project.repo_root, "worktree", "add", "--detach", str(worktree), commit)
    package_dir = worktree / project.package_rel
    binary = work_dir / "bin" / f"{label}{'.exe' if os.name == 'nt' else ''}"
    binary.parent.mkdir(parents=True, exist_ok=True)
    b = Build(label, ref, commit, worktree, package_dir, binary, list(compiler_flags))
    if not (package_dir / project.benchmark_rel).is_file():
        raise RunnerError(f"{project.package_rel / project.benchmark_rel} does not exist at {ref} ({commit[:12]})")

    b.overrides = external_path_overrides(worktree, project)
    write_overrides(package_dir, b.overrides)
    log(f"building {label}: {ref} ({commit[:12]})" + (f" with {' '.join(compiler_flags)}" if compiler_flags else ""))
    t0 = time.monotonic()
    _check(["dart", "pub", "get"], package_dir, f"dart pub get for {label} ({ref})")
    _check(
        ["dart", "compile", "exe", *compiler_flags, str(project.benchmark_rel), "-o", str(binary)],
        package_dir,
        f"dart compile exe for {label} ({ref})",
    )
    b.build_seconds = time.monotonic() - t0
    b.sha256 = _sha256(binary)
    return b


# --- environment probes ---------------------------------------------------------------------------------------


def _probe(cmd: Sequence[str]) -> str | None:
    try:
        r = subprocess.run(list(cmd), capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _cpu_model() -> str | None:
    if sys.platform == "darwin":
        return _probe(["sysctl", "-n", "machdep.cpu.brand_string"])
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def power_source() -> str | None:
    if sys.platform == "darwin":
        m = re.search(r"drawing from '([^']+)'", _probe(["pmset", "-g", "batt"]) or "")
        return m.group(1) if m else None
    for supply in Path("/sys/class/power_supply").glob("*"):
        try:
            if (supply / "type").read_text().strip() == "Mains":
                return "AC Power" if (supply / "online").read_text().strip() == "1" else "Battery Power"
        except OSError:
            continue
    return None


def thermal_state() -> dict[str, str] | None:
    """macOS `pmset -g therm` limits (e.g. CPU_Speed_Limit); empty when nothing has been recorded."""
    if sys.platform != "darwin":
        return None
    out = _probe(["pmset", "-g", "therm"])
    if out is None:
        return None
    return {k.strip(): v.strip() for k, v in (line.split("=", 1) for line in out.splitlines() if "=" in line)}


def machine_environment() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "cpu_model": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "power_source": power_source(),
        "dart_version": _probe(["dart", "--version"]),
        "python_version": platform.python_version(),
        "bench_stats_version": __version__,
    }


# --- execution ------------------------------------------------------------------------------------------------


def run_process(binary: Path, cwd: Path, trials: int | None, timeout: float | None) -> dict[str, Any]:
    """Launch one benchmark process; the result holds the suite JSON, or an error and no suite."""
    cmd = [str(binary), "--target", "aot"] + (["--trials", str(trials)] if trials else [])
    rec: dict[str, Any] = {"power_source": power_source(), "thermal": thermal_state(), "start": _now()}
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        rec.update(end=_now(), exit_code=None, error=f"timed out after {timeout:g} s", suite=None)
        return rec
    rec.update(end=_now(), exit_code=r.returncode, error=None, suite=None)
    if r.returncode != 0:
        rec["error"] = f"exit code {r.returncode}: {(r.stderr.strip() or r.stdout.strip())[-1000:]}"
        return rec
    try:
        rec["suite"] = parse_process_output(r.stdout)
    except ValueError as e:
        rec["error"] = str(e)
    return rec


def run(
    benchmark: Path,
    baseline: str,
    candidate: str | None,
    processes: int,
    output: Path,
    *,
    trials: int | None = None,
    seed: int = 0,
    cooldown: float = 0.0,
    compiler_flags: Sequence[str] = (),
    baseline_flags: Sequence[str] = (),
    candidate_flags: Sequence[str] = (),
    work_dir: Path | None = None,
    timeout: float | None = None,
    log: Log = _stderr,
) -> int:
    """Build, launch and record. `candidate=None` is an A/A run: one binary under both labels.

    Returns the number of failed processes; raises RunnerError if nothing could be measured."""
    if processes < 1:
        raise RunnerError("--processes must be at least 1")
    if candidate is None and candidate_flags:
        raise RunnerError("candidate flags need --candidate; an A/A run launches the baseline binary under both labels")
    if output.exists():
        raise RunnerError(f"{output} already exists; choose another path or delete it")
    project = resolve_project(benchmark)
    if _git(project.repo_root, "status", "--porcelain", "--", str(project.package_rel) or "."):
        log(f"note: {project.package_rel} has uncommitted changes; only committed refs are measured")

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    keep = work_dir is not None
    base_dir = (work_dir / run_id) if keep else Path(tempfile.mkdtemp(prefix="bench-stats-"))
    base_dir.mkdir(parents=True, exist_ok=True)
    base_dir = base_dir.resolve()

    builds: list[Build] = []
    try:
        builds.append(build_ref(project, baseline, "baseline", base_dir, [*compiler_flags, *baseline_flags], log))
        if candidate is None:
            versions = {"baseline": builds[0], "candidate": builds[0]}
        else:
            builds.append(build_ref(project, candidate, "candidate", base_dir, [*compiler_flags, *candidate_flags], log))
            versions = {"baseline": builds[0], "candidate": builds[1]}
            if builds[0].sha256 == builds[1].sha256:
                log("note: both refs produced identical binaries")

        order = launch_order(processes, seed)
        header = {
            "type": "header",
            "schema": RUNNER_SCHEMA,
            "schema_version": RUNNER_SCHEMA_VERSION,
            "run_id": run_id,
            "created": _now(),
            "benchmark": str(project.benchmark_rel),
            "package": str(project.package_rel),
            "aa": candidate is None,
            "processes": processes,
            "trials": trials,
            "seed": seed,
            "cooldown_seconds": cooldown,
            "timeout_seconds": timeout,
            "order": [[label, i] for label, i in order],
            "versions": {label: b.describe() for label, b in versions.items()},
            "environment": machine_environment(),
        }
        if header["environment"]["power_source"] not in (None, "AC Power"):
            log(f"warning: running on {header['environment']['power_source']}; plug in for stable timings")

        failed = 0
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")
            f.flush()
            for n, (label, i) in enumerate(order):
                if n and cooldown > 0:
                    time.sleep(cooldown)
                b = versions[label]
                rec = run_process(b.binary, b.package_dir, trials, timeout)
                record = {
                    "type": "process",
                    "run_id": run_id,
                    "version": label,
                    "ref": b.ref,
                    "commit": b.commit,
                    "process_index": i,
                    "launch_order": n,
                    **rec,
                }
                f.write(json.dumps(record) + "\n")
                f.flush()
                status = "ok" if rec["error"] is None else f"FAILED: {rec['error'].splitlines()[0]}"
                failed += rec["error"] is not None
                log(f"[{n + 1:>{len(str(len(order)))}}/{len(order)}] {label} #{i}: {status}")
        return failed
    finally:
        if keep:
            log(f"builds kept in {base_dir} (remove with `git worktree remove`)")
        else:
            shutil.rmtree(base_dir, ignore_errors=True)
            try:
                _git(project.repo_root, "worktree", "prune")
            except RunnerError as e:
                log(f"warning: {e}")
