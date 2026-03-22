"""SQLite-backed storage for checkpoints and handoffs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterator

from .models import Checkpoint, Handoff


def _default_db_path() -> Path:
    """~/.threadline/threadline.db — shared across all projects."""
    path = Path.home() / ".threadline" / "threadline.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class Store:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _default_db_path()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id          TEXT PRIMARY KEY,
                project     TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                data        TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_checkpoints_project
                ON checkpoints(project, timestamp DESC);

            CREATE TABLE IF NOT EXISTS handoffs (
                id              TEXT PRIMARY KEY,
                checkpoint_id   TEXT NOT NULL,
                project         TEXT NOT NULL,
                generated_at    TEXT NOT NULL,
                data            TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_handoffs_project
                ON handoffs(project, generated_at DESC);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def save_checkpoint(self, cp: Checkpoint) -> Checkpoint:
        self._conn.execute(
            "INSERT OR REPLACE INTO checkpoints(id, project, timestamp, data) VALUES (?,?,?,?)",
            (cp.id, cp.project, cp.timestamp.isoformat(), cp.model_dump_json()),
        )
        self._conn.commit()
        return cp

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        row = self._conn.execute(
            "SELECT data FROM checkpoints WHERE id = ?", (checkpoint_id,)
        ).fetchone()
        return Checkpoint.model_validate_json(row["data"]) if row else None

    def latest_checkpoint(self, project: str) -> Checkpoint | None:
        row = self._conn.execute(
            "SELECT data FROM checkpoints WHERE project = ? ORDER BY timestamp DESC LIMIT 1",
            (project,),
        ).fetchone()
        return Checkpoint.model_validate_json(row["data"]) if row else None

    def list_checkpoints(
        self, project: str | None = None, limit: int = 20
    ) -> list[Checkpoint]:
        if project:
            rows = self._conn.execute(
                "SELECT data FROM checkpoints WHERE project = ? ORDER BY timestamp DESC LIMIT ?",
                (project, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT data FROM checkpoints ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [Checkpoint.model_validate_json(r["data"]) for r in rows]

    def search_checkpoints(self, project: str, query: str) -> list[Checkpoint]:
        """Naive text search across checkpoint JSON."""
        rows = self._conn.execute(
            "SELECT data FROM checkpoints WHERE project = ? ORDER BY timestamp DESC",
            (project,),
        ).fetchall()
        results = []
        q = query.lower()
        for row in rows:
            if q in row["data"].lower():
                results.append(Checkpoint.model_validate_json(row["data"]))
        return results

    # ------------------------------------------------------------------
    # Handoffs
    # ------------------------------------------------------------------

    def save_handoff(self, handoff: Handoff) -> Handoff:
        self._conn.execute(
            "INSERT OR REPLACE INTO handoffs(id, checkpoint_id, project, generated_at, data) "
            "VALUES (?,?,?,?,?)",
            (
                handoff.id,
                handoff.checkpoint_id,
                handoff.project,
                handoff.generated_at.isoformat(),
                handoff.model_dump_json(),
            ),
        )
        self._conn.commit()
        return handoff

    def latest_handoff(self, project: str) -> Handoff | None:
        row = self._conn.execute(
            "SELECT data FROM handoffs WHERE project = ? ORDER BY generated_at DESC LIMIT 1",
            (project,),
        ).fetchone()
        return Handoff.model_validate_json(row["data"]) if row else None

    def list_projects(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT project FROM checkpoints ORDER BY project"
        ).fetchall()
        return [r["project"] for r in rows]

    def close(self) -> None:
        self._conn.close()
