"""FastAPI 服务（Intake :5026）。"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

from ako_intake.adapters.ws_protocol import WsSessionHandler, bootstrap_payload
from ako_intake.config import load_config
from ako_intake.core.graph import compile_graph
from ako_intake.core.pipeline import flush_queue, run_full
from ako_intake.db.queue_store import QueueStore
from ako_intake.db.session_store import SessionStore
from ako_intake.gateways.hub_client import HubClient
from ako_intake.gateways.identity_client import load_registry_mirror, login_human, verify_human
from ako_intake.services.auth_sessions import (
    DEV_IDENTITY,
    AuthIdentity,
    configure_registry_loader,
    issue_session,
    login_throttle,
    validate_session,
)
from ako_intake.gateways.monitor import health_payload, metrics_payload
from ako_intake.llm.budget import BudgetTracker
from ako_intake.models import Ako1WorkOrder
from ako_intake.probes.health_probes import probe_all
from ako_intake.services.form_builder import validate_work_order
from ako_intake.services.observability import Metrics
from ako_intake.services.reviewer import review_work_order
from ako_intake.utils.logging import setup_logging
from ako_intake.utils.naming import unique_draft_wo_number, unique_session_id

setup_logging()
config = load_config()
metrics = Metrics()
session_store = SessionStore(config.db.session_db)
queue_store = QueueStore(config.db.queue_db)
_graph = compile_graph(config)
budget_tracker = BudgetTracker(config.budget.monthly_quota_tokens)

# ── 治理看板心跳（agent_card heartbeat.endpoint 声明的接线，2026-09-03）────────
# 此前 card 声明 30s/5000 心跳但无实现 → 治理看板恒显 intake offline。
_HB_ENDPOINT = "http://127.0.0.1:5000/heartbeat"
_HB_INTERVAL = 30


async def _hub_heartbeat_loop() -> None:
    """周期向 AKO_hub 心跳服务(:5000)上报，供治理看板在线判定。"""
    import httpx
    while True:
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                await client.post(_HB_ENDPOINT, json={
                    "agent_id": "AKO_hub_intake_agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "alive",
                    "cpu_percent": 0.0,
                    "memory_mb": 0.0,
                })
        except Exception:
            pass  # hub 不在线时静默，下一周期重试
        await asyncio.sleep(_HB_INTERVAL)


@asynccontextmanager
async def _lifespan(app_: FastAPI):
    # 会话层接线注册册镜像：登录反查 + 权限实时回收（≤30s）
    configure_registry_loader(
        lambda: load_registry_mirror(config.gateways.identity_registry_path)
    )
    task = asyncio.create_task(_hub_heartbeat_loop())
    yield
    task.cancel()


app = FastAPI(title="AKO_hub_intake_agent", version="0.1.0", lifespan=_lifespan)


def require_auth(authorization: str = Header(default="")) -> AuthIdentity:
    """REST Bearer 门禁（spec 3.6）；identity 未配置时开发态放行（R3）。

    2026-09-03 多员工隔离：identity_base_url 已配置时校验 intake 会话层 token
    （登录时签发，不再直连 identity 服务），返回已认证身份供归属判定。
    """
    if not config.gateways.identity_base_url:
        return DEV_IDENTITY
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    identity = validate_session(token, dev_mode=False)
    if identity is None:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    return identity


def _owned_state(auth: AuthIdentity, session_id: str) -> Dict[str, Any]:
    """加载会话并做归属校验：不存在 404；非本人且非安全官（intake_audit）403。

    历史会话（owner=''）仅安全官可访问。
    """
    state = session_store.load(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")
    owner = session_store.owner_of(session_id)
    if owner is not None and owner != auth.human_id and not auth.is_audit:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return state


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
def get_session(session_id: str, auth: AuthIdentity = Depends(require_auth)) -> Dict[str, Any]:
    state = _owned_state(auth, session_id)
    return state


@app.post("/api/v1/intake/review", dependencies=[Depends(require_auth)])
def submit_review(body: ReviewBody, auth: AuthIdentity = Depends(require_auth)) -> Dict[str, Any]:
    state = _owned_state(auth, body.session_id)
    state["semantic_review_score"] = body.review_score
    state["human_confirmed"] = body.human_confirmed
    result = _graph.invoke(state)
    session_store.save(body.session_id, str(result.get("status", "UNKNOWN")), result, owner=auth.human_id)
    return {"session_id": body.session_id, "status": result.get("status"), "state": result}


# ── 2026-09-04：任务结果回显（对话内给摘要/下载） ───────────────────

@app.get("/api/v1/intake/task/{task_id}/result", dependencies=[Depends(require_auth)])
def task_result(task_id: str, auth: AuthIdentity = Depends(require_auth)) -> Dict[str, Any]:
    """代理 hub 任务结果（只读）。"""
    import httpx

    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(f"{config.gateways.hub_base_url}/api/v1/hub/task/{task_id}/result")
        if r.status_code == 200:
            return r.json()
        return {"error": f"hub {r.status_code}: {r.text[:200]}", "task_id": task_id}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "task_id": task_id}


@app.get("/api/v1/intake/download")
def download_file(
    path: str = Query(...),
    auth: AuthIdentity = Depends(require_auth),
):
    """结果文件下载代理：仅允许 hub 文件区内白名单扩展名。"""
    from pathlib import Path

    target = Path(path).resolve()
    hub_root = Path(r"D:\AKO\AKO_hub").resolve()
    if not str(target).startswith(str(hub_root)):
        raise HTTPException(status_code=403, detail="FORBIDDEN_PATH")
    if target.suffix.lower() not in {".json", ".md", ".pdf", ".jpg", ".jpeg", ".png", ".csv", ".txt", ".docx", ".xlsx"}:
        raise HTTPException(status_code=403, detail="FORBIDDEN_TYPE")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")
    return FileResponse(target, filename=target.name)


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
def list_sessions(auth: AuthIdentity = Depends(require_auth)) -> Dict[str, Any]:
    """会话列表（2026-09-03 多员工隔离：员工仅见自己的；安全官 intake_audit 见全量）。"""
    owner = None if auth.is_audit else auth.human_id
    return {"sessions": session_store.list_recent(owner=owner)}


@app.post("/api/v1/intake/sessions", dependencies=[Depends(require_auth)])
def create_session(body: CreateSessionBody, auth: AuthIdentity = Depends(require_auth)) -> Dict[str, Any]:
    session_id = unique_session_id()  # 微秒+计数器防碰撞（基线 flaky 修复）
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
        session_store.save(session_id, "REVIEWING", state, owner=auth.human_id)
        return {"session_id": session_id, "status": "REVIEWING", "review_record": record.model_dump()}
    if body.raw_text:
        state = run_full(body.raw_text, session_id, config)
        session_store.save(session_id, str(state.get("status", "UNKNOWN")), state, owner=auth.human_id)
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
    session_store.save(session_id, "IDLE", state, owner=auth.human_id)
    return {"session_id": session_id, "status": "IDLE"}


@app.post("/api/v1/intake/sessions/{session_id}/abandon", dependencies=[Depends(require_auth)])
def abandon_session(session_id: str, auth: AuthIdentity = Depends(require_auth)) -> Dict[str, Any]:
    state = _owned_state(auth, session_id)
    state["status"] = "ABANDONED"
    session_store.save(session_id, "ABANDONED", state, owner=auth.human_id)
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
def identity_login(body: IdentityLoginBody, request: Request) -> Dict[str, Any]:
    """员工登录（2026-09-03）：姓名→注册册反查→identity 指纹核验→签发 intake 会话。

    响应为超集：{token, expires_at, identity:{account, human_id, role, permissions}}，
    前端仅消费 token + identity.account（零破坏）。
    """
    if not config.gateways.identity_base_url:
        # 开发态（identity 未配置）：维持 mock（dev-token），保既有测试/本地开发语义
        return {"token": "dev-token", "expires_at": "", "identity": {"account": body.account}}
    ip = request.client.host if request.client else "unknown"
    throttle_msg = login_throttle(ip)
    if throttle_msg:
        raise HTTPException(status_code=429, detail=throttle_msg)
    result = login_human(
        body.account,
        body.fingerprint,
        config.gateways.identity_base_url,
        config.gateways.identity_registry_path,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=401, detail=str(result.get("error", "login failed")))
    token = issue_session(
        str(result["human_id"]), str(result["name"]),
        str(result.get("role", "员工_L1")), [str(p) for p in result.get("permissions", [])],
    )
    return {
        "token": token,
        "expires_at": "",
        "identity": {
            "account": body.account,
            "human_id": result["human_id"],
            "role": result.get("role", "员工_L1"),
            "permissions": result.get("permissions", []),
        },
    }


@app.post("/api/v1/identity/verify")
def identity_verify(body: IdentityVerifyBody) -> Dict[str, Any]:
    return verify_human(body.token, config.gateways.identity_base_url)

