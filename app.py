"""FastAPI 服务（Intake :5026）。"""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ako_intake.config import load_config
from ako_intake.core.graph import compile_graph
from ako_intake.db.queue_store import QueueStore
from ako_intake.db.session_store import SessionStore
from ako_intake.gateways.monitor import health_payload, metrics_payload
from ako_intake.probes.health_probes import probe_all
from ako_intake.services.observability import Metrics
from ako_intake.utils.logging import setup_logging

setup_logging()
config = load_config()
metrics = Metrics()
session_store = SessionStore(config.db.session_db)
queue_store = QueueStore(config.db.queue_db)
_graph = compile_graph(config)

app = FastAPI(title="AKO_hub_intake_agent", version="0.1.0")


class ReviewBody(BaseModel):
    session_id: str
    review_score: float
    human_confirmed: bool = False


@app.get("/health")
def health() -> Dict[str, Any]:
    return health_payload(probe_all(config))


@app.get("/metrics")
def metrics_endpoint() -> Dict[str, Any]:
    return metrics_payload(metrics)


@app.get("/api/v1/intake/sessions/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    state = session_store.load(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")
    return state


@app.post("/api/v1/intake/review")
def submit_review(body: ReviewBody) -> Dict[str, Any]:
    state = session_store.load(body.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")
    state["semantic_review_score"] = body.review_score
    state["human_confirmed"] = body.human_confirmed
    result = _graph.invoke(state)
    session_store.save(body.session_id, str(result.get("status", "UNKNOWN")), result)
    return {"session_id": body.session_id, "status": result.get("status"), "state": result}


@app.websocket("/ws/intake")
async def ws_intake(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            message = json.loads(await websocket.receive_text())
            msg_type = message.get("type")
            if msg_type == "intake_input":
                session_id = message.get("session_id", "ws-session")
                state = _graph.invoke(
                    {
                        "session_id": session_id,
                        "status": "PARSING",
                        "raw_input": message.get("text", ""),
                        "clarification_log": [],
                        "pending_answers": [],
                        "p0_rounds": 0,
                        "queue": "main",
                    }
                )
                session_store.save(session_id, str(state.get("status", "UNKNOWN")), state)
                metrics.increment("sessions_total")
                await websocket.send_text(json.dumps(state, ensure_ascii=False))
            elif msg_type == "p0_response":
                session_id = message.get("session_id", "ws-session")
                state = session_store.load(session_id) or {}
                state["pending_answers"] = message.get("answers", [])
                result = _graph.invoke(state)
                session_store.save(session_id, str(result.get("status", "UNKNOWN")), result)
                await websocket.send_text(json.dumps(result, ensure_ascii=False))
            else:
                await websocket.send_text(json.dumps({"error": "unknown message type"}, ensure_ascii=False))
    except WebSocketDisconnect:
        return

