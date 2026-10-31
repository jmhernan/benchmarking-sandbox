"""Command line: `bench-stats analyze` and `bench-stats run`."""

import argparse
import json
import sys
from pathlib import Path

from .io import is_runner_file, load_run, load_runner_file
from .report import build_report, render_markdown


def _fraction(lo: float, hi: float, name: str):
    def parse(text: str) -> float:
        try:
            value = float(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{name} must be a number, got {text!r}") from None
        if not lo < value < hi:
            raise argparse.ArgumentTypeError(f"{name} must be between {lo:g} and {hi:g} (exclusive), got {value:g}")
        return value

    return parse


def _positive(kind: type, name: str):
    def parse(text: str):
        try:
            value = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{name} must be a {kind.__name__}, got {text!r}") from None
        if value <= 0:
            raise argparse.ArgumentTypeError(f"{name} must be positive, got {text}")
        return value

    return parse


def _add_run_parser(sub) -> None:
    r = sub.add_parser(
        "run",
        help="build two git refs of a Dart package and run their benchmarks interleaved",
        description=(
            "Builds the benchmark at two git refs (each in its own worktree, with dart compile exe), then launches "
            "P processes per ref in one session, in a seeded order that is balanced within consecutive pairs. "
            "Writes a JSONL file with one record per process; analyse it with `bench-stats analyze FILE`. "
            "Only committed code is measured."
        ),
    )
    r.add_argument("benchmark", type=Path, help="benchmark file in the current checkout; its package is the nearest pubspec.yaml above it")
    r.add_argument("--baseline", required=True, help="git ref for the baseline")
    which = r.add_mutually_exclusive_group(required=True)
    which.add_argument("--candidate", help="git ref for the candidate")
    which.add_argument("--aa", action="store_true", help="A/A run: build the baseline once and launch it under both labels")
    r.add_argument("-P", "--processes", type=_positive(int, "--processes"), required=True, help="processes per version (5 or more for meaningful intervals)")
    r.add_argument("-o", "--output", type=Path, required=True, help="JSONL file to write (must not exist)")
    r.add_argument("--trials", type=_positive(int, "--trials"), help="trials per process (default: the benchmark's own, 16 in bench_press 0.4.2)")
    r.add_argument("--seed", type=int, default=0, help="seed for the launch order (default 0)")
    r.add_argument("--cooldown", type=float, default=0.0, help="seconds to wait between launches (default 0)")
    r.add_argument("--timeout", type=_positive(float, "--timeout"), help="seconds before a process is killed and recorded as failed")
    r.add_argument("--compiler-flag", action="append", default=[], metavar="FLAG", help="passed to dart compile exe for both refs; repeatable")
    r.add_argument("--baseline-flag", action="append", default=[], metavar="FLAG", help="compiler flag for the baseline only; repeatable")
    r.add_argument("--candidate-flag", action="append", default=[], metavar="FLAG", help="compiler flag for the candidate only; repeatable")
    r.add_argument("--work-dir", type=Path, help="keep worktrees and binaries under this directory (default: a temporary directory, removed afterwards)")

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bench-stats", description="Statistical analysis of bench_press runs.")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser(
        "analyze",
        help="compare two runs, or the groups inside one run, and report variance diagnostics",
        description=(
            "With two files, compares every benchmark of the candidate run with the same benchmark in the "
            "baseline run. With one file, compares each Benchmark.compare variant with its group's baseline "
            "(paired by process); a `bench-stats run` file is compared baseline against candidate instead. All modes "
            "report variance diagnostics and a design hint for every benchmark. "
            "Run bench_press with --processes 5 or more for meaningful intervals."
        ),
    )
    a.add_argument("baseline", type=Path, help="bench_press run JSON (the baseline, or the only run), or a `bench-stats run` file")
    a.add_argument("candidate", type=Path, nargs="?", help="bench_press run JSON for the candidate")
    a.add_argument("--threshold", type=_fraction(0, 1, "--threshold"), default=0.03,
                   help="practical-significance threshold δ as a fraction (default 0.03 = 3%%)")
    a.add_argument("--conf", type=_fraction(0.5, 1, "--conf"), default=0.95, help="interval confidence level (default 0.95)")
    a.add_argument("--reduce", choices=["mean", "median"], default="mean", help="per-process reduction (default mean)")
    a.add_argument("--fdr", type=_fraction(0, 1, "--fdr"), default=0.05, help="Benjamini–Hochberg q (default 0.05)")
    a.add_argument("--power", type=_fraction(0, 1, "--power"), default=0.8, help="target power for the design hint (default 0.8)")
    a.add_argument("--detect", type=_fraction(0, 10, "--detect"), default=None,
                   help="speedup to plan for in the design hint, as a fraction (default 2 × threshold)")
    a.add_argument("--seed", type=int, default=0, help="seed for the bootstrap intervals (default 0)")
    a.add_argument("--format", choices=["markdown", "json"], default="markdown", help="output format (default markdown)")
    a.add_argument("-o", "--output", type=Path, help="write to this file instead of stdout")
    _add_run_parser(sub)
    return p


def _run(args: argparse.Namespace) -> int:
    from .runner import RunnerError, run

    try:
        failed = run(
            args.benchmark,
            args.baseline,
            None if args.aa else args.candidate,
            args.processes,
            args.output,
            trials=args.trials,
            seed=args.seed,
            cooldown=args.cooldown,
            compiler_flags=args.compiler_flag,
            baseline_flags=args.baseline_flag,
            candidate_flags=args.candidate_flag,
            work_dir=args.work_dir,
            timeout=args.timeout,
        )
    except RunnerError as e:
        print(f"bench-stats: {e}", file=sys.stderr)
        return 2
    print(f"wrote {args.output}" + (f" ({failed} failed processes)" if failed else ""), file=sys.stderr)
    print(f"next: bench-stats analyze {args.output}", file=sys.stderr)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        return _run(args)
    try:
        if is_runner_file(args.baseline):
            if args.candidate is not None:
                raise ValueError(f"{args.baseline} is a bench-stats run file; it already holds both versions")
            baseline, candidate = load_runner_file(args.baseline)
        else:
            baseline = load_run(args.baseline)
            candidate = load_run(args.candidate) if args.candidate is not None else None
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"bench-stats: cannot read input: {e}", file=sys.stderr)
        return 2

    report = build_report(
        baseline,
        candidate,
        delta=args.threshold,
        conf=args.conf,
        reduce=args.reduce,
        q=args.fdr,
        power=args.power,
        detect=args.detect,
        seed=args.seed,
    )
    if args.format == "json":
        text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    else:
        text = render_markdown(report)

    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
