"""三级记忆（FI-II-04）。"""

from __future__ import annotations

from ako_intake.db.session_store import SessionStore
from ako_intake.services.memory import MemoryService


def test_session_store_roundtrip(tmp_path) -> None:
    store = SessionStore(tmp_path / "state.db")
    store.save("sess-1", "CLARIFYING", {"session_id": "sess-1", "status": "CLARIFYING"})
    state = store.load("sess-1")
    assert state["status"] == "CLARIFYING"
    assert store.list_non_terminal() == ["sess-1"]


def test_archive_expired(tmp_path) -> None:
    store = SessionStore(tmp_path / "state.db")
    store.save("sess-old", "FAILED", {"session_id": "sess-old"})
    from datetime import datetime, timedelta

    store.save("sess-new", "DELIVERED", {"session_id": "sess-new"})
    with store._connect() as conn:
        conn.execute(
            "UPDATE sessions SET updated_at=? WHERE session_id='sess-old'",
            ((datetime.now() - timedelta(days=30)).isoformat(),),
        )
    assert store.archive_expired(days=7) == 1


def test_memory_service_preferences_and_archive(tmp_path) -> None:
    store = SessionStore(tmp_path / "state.db")
    service = MemoryService(store, tmp_path / "archive", long_term_file=tmp_path / "long.json")
    service.save_session({"session_id": "s1", "status": "DELIVERED"})
    service.archive_session({"session_id": "s1", "status": "DELIVERED"})
    service.remember_preference("s1", "AKO_quote_agent")
    service.remember_preference("s1", "AKO_quote_agent")
    assert service.get_preferred_modules() == ["AKO_quote_agent"]
    assert (tmp_path / "archive" / "session_s1.json").exists()
    assert service.load_session("s1")["status"] == "DELIVERED"

