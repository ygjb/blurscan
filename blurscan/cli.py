"""Command-line entry point for blurscan.

Wires the scan + report surface from DESIGN.md §6: select a detection method,
scan a directory, and either print a ranked summary (default), write a report,
or emit JSON. Quarantine/tag/review actions are layered on in later issues.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from blurscan.actions.report import write_report
from blurscan.detectors import available
from blurscan.models import BLURRY, BORDERLINE, SHARP, ImageResult, ScanConfig
from blurscan.pipeline import run_scan


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="blurscan",
        description="Scan a photo collection and flag blurry images.",
    )
    parser.add_argument("scan_path", nargs="?", help="Directory of images to scan.")

    detect = parser.add_argument_group("detection")
    detect.add_argument(
        "--method",
        choices=available(),
        default="laplacian",
        help="Detection method (default: laplacian).",
    )
    detect.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Absolute sharpness floor (default: method-specific).",
    )
    detect.add_argument(
        "--adaptive",
        nargs="?",
        type=float,
        const=10.0,
        default=None,
        metavar="PCT",
        help="Also flag the bottom PCT%% of the collection (default 10 when given).",
    )
    detect.add_argument("--grid", type=int, default=4, help="Tiles per side (default 4).")
    detect.add_argument(
        "--working-size",
        type=int,
        default=1000,
        help="Downscale longest edge before analysis (default 1000).",
    )

    out = parser.add_argument_group("output")
    out.add_argument("--report", metavar="PATH", help="Write CSV + HTML report to PATH.{csv,html}.")
    out.add_argument("--json", action="store_true", help="Emit results as JSON to stdout.")
    out.add_argument("-v", "--verbose", action="store_true", help="List every flagged image.")
    return parser


def _config_from_args(args: argparse.Namespace) -> ScanConfig:
    return ScanConfig(
        scan_path=Path(args.scan_path),
        method=args.method,
        threshold=args.threshold,
        adaptive_pct=args.adaptive,
        grid=args.grid,
        working_size=args.working_size,
    )


def _print_summary(results: list[ImageResult], verbose: bool) -> None:
    classes = (BLURRY, BORDERLINE, SHARP)
    counts = {c: sum(1 for r in results if r.classification == c) for c in classes}
    errors = sum(1 for r in results if r.error is not None)
    print(
        f"Scanned {len(results)} images — "
        f"blurry: {counts[BLURRY]}, borderline: {counts[BORDERLINE]}, "
        f"sharp: {counts[SHARP]}" + (f", errors: {errors}" if errors else "")
    )
    flagged = sorted(
        (r for r in results if r.classification in (BLURRY, BORDERLINE)),
        key=lambda r: r.score_max_tile,
    )
    shown = flagged if verbose else flagged[:10]
    for r in shown:
        note = f"  ({r.error})" if r.error else ""
        print(f"  {r.classification:10s} {r.score_max_tile:8.1f}  {r.path}{note}")
    if not verbose and len(flagged) > len(shown):
        print(f"  … and {len(flagged) - len(shown)} more (use -v to list all)")


def main(argv: list[str] | None = None) -> int:
    """Program entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.scan_path:
        parser.print_help()
        return 0

    scan_path = Path(args.scan_path)
    if not scan_path.is_dir():
        print(f"error: not a directory: {scan_path}", file=sys.stderr)
        return 2

    results = run_scan(_config_from_args(args))

    if args.json:
        json.dump([r.to_dict() for r in results], sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    _print_summary(results, args.verbose)
    if args.report:
        csv_path, html_path = write_report(results, args.report)
        print(f"Wrote {csv_path} and {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
