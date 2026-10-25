"""Command line: `bench-stats analyze`."""

import argparse
import json
import sys
from pathlib import Path

from .io import load_run
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


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bench-stats", description="Statistical analysis of bench_press runs.")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser(
        "analyze",
        help="compare two runs, or the groups inside one run, and report variance diagnostics",
        description=(
            "With two files, compares every benchmark of the candidate run with the same benchmark in the "
            "baseline run. With one file, compares each Benchmark.compare variant with its group's baseline "
            "(paired by process). Both report variance diagnostics and a design hint for every benchmark. "
            "Run bench_press with --processes 5 or more for meaningful intervals."
        ),
    )
    a.add_argument("baseline", type=Path, help="bench_press run JSON: the baseline, or the only run")
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
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
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
