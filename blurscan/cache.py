"""SQLite result cache keyed on path + mtime + size.

See DESIGN.md §3.3. Caches the expensive part of a scan (decode + score) so
reruns skip unchanged files. Classification is **not** cached — it is recomputed
each run because it depends on the whole-run distribution (adaptive mode) and on
the active threshold. A cache entry is keyed on ``(path, method)`` and considered
fresh only if the file's mtime and size still match.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import TracebackType

from blurscan.models import ImageResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    path   TEXT NOT NULL,
    method TEXT NOT NULL,
    mtime  REAL NOT NULL,
    size   INTEGER NOT NULL,
    data   TEXT NOT NULL,
    PRIMARY KEY (path, method)
)
"""


class ResultCache:
    """A SQLite-backed cache of per-image scoring results."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    def get(self, path: Path, method: str) -> ImageResult | None:
        """Return the cached result for ``path`` under ``method`` if still fresh."""
        try:
            stat = path.stat()
        except OSError:
            return None
        row = self.conn.execute(
            "SELECT mtime, size, data FROM results WHERE path = ? AND method = ?",
            (str(path), method),
        ).fetchone()
        if row is None:
            return None
        mtime, size, data = row
        if mtime != stat.st_mtime or size != stat.st_size:
            return None  # file changed since cached
        return ImageResult.from_dict(json.loads(data))

    def put(self, result: ImageResult) -> None:
        """Store ``result`` keyed on its current path/method/mtime/size."""
        try:
            stat = result.path.stat()
        except OSError:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO results (path, method, mtime, size, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(result.path),
                result.method,
                stat.st_mtime,
                stat.st_size,
                json.dumps(result.to_dict()),
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> ResultCache:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def default_cache_path(scan_path: Path) -> Path:
    """Default on-disk cache location for a scan root."""
    return scan_path / ".blurscan_cache" / "cache.sqlite"
