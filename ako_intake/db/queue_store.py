"""本地投递队列（Hub 不可达零丢失，eventual 一致性）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class QueueStore:
    """SQLite 持久化重试队列。"""

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
                CREATE TABLE IF NOT EXISTS pending_wo (
                    wo_number TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def enqueue(self, wo_number: str, payload: Dict[str, Any]) -> None:
        now = datetime.now().isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO pending_wo (wo_number, payload_json, status, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?)
                ON CONFLICT(wo_number) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (wo_number, json.dumps(payload, ensure_ascii=False), now, now),
            )

    def peek_due(self, now: str | None = None) -> List[Dict[str, Any]]:
        now = now or datetime.now().isoformat()
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM pending_wo WHERE status='pending' AND (next_retry_at IS NULL OR next_retry_at <= ?)",
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_attempt(self, wo_number: str, next_retry_at: str | None) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                UPDATE pending_wo
                SET attempts = attempts + 1, next_retry_at = ?, updated_at = ?
                WHERE wo_number = ?
                """,
                (next_retry_at, datetime.now().isoformat(), wo_number),
            )

    def mark_success(self, wo_number: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE pending_wo SET status='done', updated_at=? WHERE wo_number=?",
                (datetime.now().isoformat(), wo_number),
            )

    def mark_failed(self, wo_number: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE pending_wo SET status='failed', updated_at=? WHERE wo_number=?",
                (datetime.now().isoformat(), wo_number),
            )

    def stats(self) -> Dict[str, int]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM pending_wo GROUP BY status"
            ).fetchall()
        return {r["status"]: r["cnt"] for r in row}

    @staticmethod
    def compute_backoff(attempt: int, base_seconds: int = 60, max_seconds: int = 600) -> int:
        """指数退避：base * 2^(attempt-1)，封顶 max_seconds。"""
        return min(base_seconds * (2 ** max(0, attempt - 1)), max_seconds)
