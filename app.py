"""FastAPI 服务（Intake :5026）。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ako_intake.adapters.ws_protocol import WsSessionHandler
from ako_intake.config import load_config
from ako_intake.core.graph import compile_graph
from ako_intake.db.queue_store import QueueStore
from ako_intake.db.session_store import SessionStore
from ako_intake.gateways.monitor import health_payload, metrics_payload
from ako_intake.llm.budget import BudgetTracker
from ako_intake.probes.health_probes import probe_all
from ako_intake.services.observability import Metrics
from ako_intake.utils.logging import setup_logging

setup_logging()
config = load_config()
metrics = Metrics()
session_store = SessionStore(config.db.session_db)
queue_store = QueueStore(config.db.queue_db)
_graph = compile_graph(config)
budget_tracker = BudgetTracker(config.budget.monthly_quota_tokens)

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
    handler = WsSessionHandler(config, session_store, queue_store, _graph, metrics, budget_tracker)
    try:
        while True:
            raw = await websocket.receive_text()
            for msg in handler.handle_text(raw):
                await websocket.send_text(msg.model_dump_json(exclude_none=True))
    except WebSocketDisconnect:
        return

