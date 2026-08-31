"""三级记忆（FI-II-04）：短期会话 / 长期偏好 / 情景归档。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ako_intake.db.session_store import SessionStore


class MemoryService:
    """记忆服务。"""

    def __init__(self, session_store: SessionStore, archive_dir: str | Path, long_term_file: str | Path | None = None) -> None:
        self.session_store = session_store
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.long_term_file = Path(long_term_file) if long_term_file else self.archive_dir.parent / "long_term_memory.json"

    def save_session(self, state: Dict[str, Any]) -> None:
        """短期记忆：会话状态持久化。"""
        session_id = str(state.get("session_id") or "unknown")
        self.session_store.save(session_id, str(state.get("status", "UNKNOWN")), state)

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.session_store.load(session_id)

    def archive_session(self, state: Dict[str, Any]) -> None:
        """情景记忆：终态会话快照归档。"""
        session_id = str(state.get("session_id") or datetime.now().strftime("%Y%m%d%H%M%S"))
        target = self.archive_dir / f"session_{session_id}.json"
        target.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def remember_preference(self, session_id: str, module: str) -> None:
        """长期记忆：记录用户常用模块。"""
        data: Dict[str, Any] = {}
        if self.long_term_file.exists():
            try:
                data = json.loads(self.long_term_file.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        prefs = data.setdefault("preferred_modules", {})
        prefs[module] = prefs.get(module, 0) + 1
        self.long_term_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_preferred_modules(self) -> List[str]:
        if not self.long_term_file.exists():
            return []
        try:
            data = json.loads(self.long_term_file.read_text(encoding="utf-8"))
            return sorted(data.get("preferred_modules", {}), key=lambda k: data["preferred_modules"][k], reverse=True)
        except Exception:
            return []

