"""Persistence for staged review decisions (DESIGN.md §4.2).

Decisions are keyed by image path in a small SQLite table (in the same
``.blurscan_cache`` location as the result cache), so a review session is
resumable — closing and reopening restores prior Keep/Quarantine/Tag choices.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    path     TEXT PRIMARY KEY,
    decision TEXT NOT NULL
)
"""


class DecisionStore:
    """SQLite-backed map of image path -> staged decision."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    def load(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT path, decision FROM decisions").fetchall()
        return {path: decision for path, decision in rows}

    def set(self, path: str, decision: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO decisions (path, decision) VALUES (?, ?)",
            (path, decision),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> DecisionStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
