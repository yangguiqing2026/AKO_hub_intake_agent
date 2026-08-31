"""会话状态存储（断点续传，FI-II-06）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class SessionStore:
    """SQLite 会话存储。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save(self, session_id: str, status: str, state: Dict[str, Any]) -> None:
        now = datetime.now().isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, status, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status = excluded.status,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (session_id, status, json.dumps(state, ensure_ascii=False), now, now),
            )

    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT state_json FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return json.loads(row["state_json"]) if row else None

    def list_non_terminal(self, terminal_states: tuple[str, ...] = ("DELIVERED", "FAILED", "ABANDONED", "ARCHIVED")) -> List[str]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT session_id FROM sessions WHERE status NOT IN ({})".format(
                    ",".join("?" for _ in terminal_states)
                ),
                terminal_states,
            ).fetchall()
        return [row["session_id"] for row in rows]

    def archive_expired(self, days: int = 7) -> int:
        """归档过期终态会话，返回归档数量。"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE updated_at < ? AND status IN ('DELIVERED','FAILED','ABANDONED')",
                (cutoff,),
            )
        return cursor.rowcount
