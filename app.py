"""FastAPI 服务（Intake :5026）。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from ako_intake.adapters.ws_protocol import WsSessionHandler, bootstrap_payload
from ako_intake.config import load_config
from ako_intake.core.graph import compile_graph
from ako_intake.core.pipeline import flush_queue, run_full
from ako_intake.db.queue_store import QueueStore
from ako_intake.db.session_store import SessionStore
from ako_intake.gateways.hub_client import HubClient
from ako_intake.gateways.identity_client import login_human, verify_human
from ako_intake.gateways.monitor import health_payload, metrics_payload
from ako_intake.llm.budget import BudgetTracker
from ako_intake.models import Ako1WorkOrder
from ako_intake.probes.health_probes import probe_all
from ako_intake.services.form_builder import validate_work_order
from ako_intake.services.observability import Metrics
from ako_intake.services.reviewer import review_work_order
from ako_intake.utils.logging import setup_logging
from ako_intake.utils.naming import unique_draft_wo_number

setup_logging()
config = load_config()
metrics = Metrics()
session_store = SessionStore(config.db.session_db)
queue_store = QueueStore(config.db.queue_db)
_graph = compile_graph(config)
budget_tracker = BudgetTracker(config.budget.monthly_quota_tokens)

app = FastAPI(title="AKO_hub_intake_agent", version="0.1.0")


def require_auth(authorization: str = Header(default="")) -> None:
    """REST Bearer 门禁（spec 3.6）；identity 未配置时开发态放行（R3）。"""
    if not config.gateways.identity_base_url:
        return
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    result = verify_human(token, config.gateways.identity_base_url)
    if not result.get("ok"):
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")


class ReviewBody(BaseModel):
    session_id: str
    review_score: float
    human_confirmed: bool = False


@app.get("/health")
def health() -> Dict[str, Any]:
    return health_payload(probe_all(config))


@app.get("/metrics", dependencies=[Depends(require_auth)])
def metrics_endpoint() -> Dict[str, Any]:
    payload = metrics_payload(metrics, budget=budget_tracker.snapshot())
    payload["queue"] = queue_store.stats()
    return payload


@app.get("/api/v1/intake/sessions/{session_id}", dependencies=[Depends(require_auth)])
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
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=config.ws.auth_timeout_seconds)
        for msg in handler.handle_text(raw):
            await websocket.send_text(msg.model_dump_json(exclude_none=True))
        while True:
            raw = await websocket.receive_text()
            for msg in handler.handle_text(raw):
                await websocket.send_text(msg.model_dump_json(exclude_none=True))
    except WebSocketDisconnect:
        return
    except asyncio.TimeoutError:
        await websocket.send_text(
            json.dumps({"v": 2, "type": "error", "payload": {"code": "AUTH_REQUIRED", "message": "auth 超时"}}, ensure_ascii=False)
        )
        await websocket.close()
        return


class CreateSessionBody(BaseModel):
    raw_text: Optional[str] = None
    draft_wo: Optional[Dict[str, Any]] = None


class IdentityLoginBody(BaseModel):
    account: str
    fingerprint: str


class IdentityVerifyBody(BaseModel):
    token: str


@app.get("/api/v1/bootstrap", dependencies=[Depends(require_auth)])
def bootstrap() -> Dict[str, Any]:
    return bootstrap_payload(config, budget_tracker)


@app.get("/api/v1/intake/sessions", dependencies=[Depends(require_auth)])
def list_sessions() -> Dict[str, Any]:
    return {"sessions": session_store.list_recent()}


@app.post("/api/v1/intake/sessions", dependencies=[Depends(require_auth)])
def create_session(body: CreateSessionBody) -> Dict[str, Any]:
    session_id = f"sess-{datetime.now().strftime('%Y%m%d-%H%M%S%f')}"  # 微秒防同秒碰撞（终审 I3）
    if body.draft_wo is not None:
        draft = {**body.draft_wo}
        # 工单号由系统生成（白皮书 US-003），用户无需填写；当日唯一（终审 C2）
        draft.setdefault("wo_number", unique_draft_wo_number())
        try:
            wo = Ako1WorkOrder.model_validate(draft)
        except ValidationError as exc:
            # 缺必填字段（非空值）→ 400 schema_error（设计 7.5，白皮书 S80 schema_error）
            raise HTTPException(status_code=400, detail=f"schema_error: {exc}")
        problems = validate_work_order(wo)
        if problems:
            raise HTTPException(status_code=400, detail="schema_error: " + "; ".join(problems))
        record = review_work_order(wo, config.intake.review_score_threshold)
        state = {
            "session_id": session_id,
            "status": "REVIEWING",
            "raw_input": "[expert]",
            "draft_work_order": wo.model_dump(),
            "review_record": record.model_dump(),
            "clarification_log": [],
            "pending_answers": [],
            "p0_rounds": 0,
            "queue": "main",
        }
        session_store.save(session_id, "REVIEWING", state)
        return {"session_id": session_id, "status": "REVIEWING", "review_record": record.model_dump()}
    if body.raw_text:
        state = run_full(body.raw_text, session_id, config)
        session_store.save(session_id, str(state.get("status", "UNKNOWN")), state)
        return {"session_id": session_id, "status": state.get("status")}
    state = {
        "session_id": session_id,
        "status": "IDLE",
        "raw_input": body.raw_text or "",
        "clarification_log": [],
        "pending_answers": [],
        "p0_rounds": 0,
        "queue": "main",
    }
    session_store.save(session_id, "IDLE", state)
    return {"session_id": session_id, "status": "IDLE"}


@app.post("/api/v1/intake/sessions/{session_id}/abandon", dependencies=[Depends(require_auth)])
def abandon_session(session_id: str) -> Dict[str, Any]:
    state = session_store.load(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")
    state["status"] = "ABANDONED"
    session_store.save(session_id, "ABANDONED", state)
    return {"session_id": session_id, "status": "ABANDONED"}


@app.get("/api/v1/intake/queue/stats", dependencies=[Depends(require_auth)])
def queue_stats() -> Dict[str, Any]:
    stats = queue_store.stats()
    # 空队列时 stats() 无对应分组，端点契约固定返回 {pending, done, failed}
    return {
        "pending": stats.get("pending", 0),
        "done": stats.get("done", 0),
        "failed": stats.get("failed", 0),
    }


@app.post("/api/v1/intake/queue/flush", dependencies=[Depends(require_auth)])
def queue_flush() -> Dict[str, Any]:
    hub = HubClient(config.gateways.hub_base_url)
    flushed = flush_queue(queue_store, hub, config)
    return {"flushed": flushed}


@app.post("/api/v1/identity/login")
def identity_login(body: IdentityLoginBody) -> Dict[str, Any]:
    result = login_human(body.account, body.fingerprint, config.gateways.identity_base_url)
    if not result.get("ok"):
        raise HTTPException(status_code=401, detail=str(result.get("error", "login failed")))
    return {"token": result["token"], "expires_at": result.get("expires_at", ""), "identity": {"account": body.account}}


@app.post("/api/v1/identity/verify")
def identity_verify(body: IdentityVerifyBody) -> Dict[str, Any]:
    return verify_human(body.token, config.gateways.identity_base_url)

