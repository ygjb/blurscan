"""Command-line entry point for blurscan.

Scaffolding only at this stage: parses a scan path and prints usage. Detection
and action flags are wired in later issues (see DESIGN.md §6).
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="blurscan",
        description="Scan a photo collection and flag blurry images.",
    )
    parser.add_argument(
        "scan_path",
        nargs="?",
        help="Directory of images to scan.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.scan_path:
        parser.print_help()
        return 0
    print(f"blurscan: scaffolding only; would scan {args.scan_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
