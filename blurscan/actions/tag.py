"""Metadata tagging action via exiftool.

See DESIGN.md §5. Writes an XMP keyword (``blurscan:<class>``) and a low star
rating onto flagged images so photo managers can filter on them. RAW files get
an XMP **sidecar** by default (original never touched); other formats are tagged
in place (pixels untouched — XMP only).

Security posture (this action shells out to an external binary):
- exiftool is always invoked with an **argv list** via ``subprocess`` with
  ``shell=False`` — no string interpolation into a shell, so filenames cannot
  inject commands.
- Target paths are rejected if they contain newline/CR/NUL, which are the only
  characters that could confuse argument handling or the (unused) stay-open
  protocol.
- ``ensure_exiftool`` resolves the binary on PATH up front with a clear error.
- Command construction is a pure function (``build_commands``) so it is unit
  tested without invoking exiftool; ``--dry-run`` returns the plan unexecuted.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from blurscan.loader import RAW_EXTENSIONS
from blurscan.models import BLURRY, BORDERLINE, ImageResult

KEYWORD_PREFIX = "blurscan"
# Star rating written per class (blurry lowest).
RATINGS = {BLURRY: 1, BORDERLINE: 2}
# Max file targets per exiftool invocation (keep argv well under ARG_MAX).
CHUNK_SIZE = 400


class ExiftoolNotFound(RuntimeError):
    """Raised when the exiftool binary is not on PATH."""


@dataclass
class ExiftoolCommand:
    """A single exiftool invocation: tag args applied to a chunk of targets."""

    args: list[str]
    targets: list[Path] = field(default_factory=list)

    def argv(self, exiftool: str = "exiftool") -> list[str]:
        return [exiftool, *self.args, *(_as_filename_arg(t) for t in self.targets)]


def _as_filename_arg(path: Path) -> str:
    """Render a path so exiftool can't mistake it for an option.

    exiftool treats any argument beginning with ``-`` as a flag, so a file named
    e.g. ``-delete_original.jpg`` would inject an option. Prefixing relative paths
    that start with ``-`` with ``./`` neutralizes that (absolute paths start with
    ``/`` and are already safe).
    """
    s = str(path)
    return f"./{s}" if s.startswith("-") else s


def ensure_exiftool(exe: str = "exiftool") -> str:
    """Resolve the exiftool binary on PATH or raise :class:`ExiftoolNotFound`."""
    resolved = shutil.which(exe)
    if resolved is None:
        raise ExiftoolNotFound(
            "exiftool not found on PATH — install it (e.g. `apt install libimage-exiftool-perl`)"
        )
    return resolved


def _keyword(classification: str) -> str:
    return f"{KEYWORD_PREFIX}:{classification}"


def _path_is_safe(path: Path) -> bool:
    s = str(path)
    return not any(ch in s for ch in ("\n", "\r", "\x00"))


def _chunks(items: list[Path], size: int) -> Iterator[list[Path]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def build_commands(
    results: Iterable[ImageResult],
    *,
    include_borderline: bool = False,
    raw_inplace: bool = False,
) -> list[ExiftoolCommand]:
    """Build the exiftool commands to tag flagged results (pure, no execution).

    Raises ``ValueError`` if a target path contains characters (newline/NUL) that
    are unsafe for argument handling.
    """
    classes = {BLURRY} | ({BORDERLINE} if include_borderline else set())
    # Group by (classification, write-to-sidecar) so each group shares tag args.
    groups: dict[tuple[str, bool], list[Path]] = {}
    for r in results:
        if r.error is not None or r.classification not in classes:
            continue
        if not _path_is_safe(r.path):
            raise ValueError(f"unsafe characters in path, refusing to tag: {r.path!r}")
        is_raw = r.path.suffix.lower() in RAW_EXTENSIONS
        sidecar = is_raw and not raw_inplace
        groups.setdefault((r.classification, sidecar), []).append(r.path)

    commands: list[ExiftoolCommand] = []
    for (classification, sidecar), paths in sorted(groups.items()):
        args = ["-srcfile", "%d%f.xmp"] if sidecar else ["-overwrite_original"]
        args += [
            f"-XMP:Subject+={_keyword(classification)}",
            f"-XMP:Rating={RATINGS[classification]}",
        ]
        for chunk in _chunks(paths, CHUNK_SIZE):
            commands.append(ExiftoolCommand(args=list(args), targets=chunk))
    return commands


def tag(
    results: Iterable[ImageResult],
    *,
    dry_run: bool = False,
    include_borderline: bool = False,
    raw_inplace: bool = False,
    exe: str = "exiftool",
) -> list[ExiftoolCommand]:
    """Tag flagged images via exiftool. Returns the commands (planned if dry-run)."""
    commands = build_commands(
        results, include_borderline=include_borderline, raw_inplace=raw_inplace
    )
    if dry_run or not commands:
        return commands
    exiftool = ensure_exiftool(exe)
    for command in commands:
        proc = subprocess.run(  # noqa: S603 - argv list, shell=False, paths guarded above
            command.argv(exiftool),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"exiftool failed ({proc.returncode}): {proc.stderr.strip()}")
    return commands
