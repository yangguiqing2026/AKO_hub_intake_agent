"""IntakeSpoke：兼容 Hub SpokeAdapter 协议。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ako_intake.config import AppConfig
from ako_intake.core.graph import compile_graph
from ako_intake.models import Ako1WorkOrder, AmbiguityReport, IntentTree
from ako_intake.services.nlu_parser import parse_intent


class IntakeSpoke:
    """Hub 侧适配入口。"""

    name = "hub_intake"
    version = "0.1.0"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._graph = compile_graph(config)

    def run(
        self,
        intent: str = "",
        project_tag: str = "",
        _hub_output_dir: str = "",
        _hub_db_path: str = "",
        _hub_chroma_root: str = "",
        _hub_file_root: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """SpokeAdapter.run 兼容实现。"""
        tree = parse_intent(intent, self.config.terms)
        state = self._graph.invoke(
            {
                "session_id": f"spoke-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "status": "PARSING",
                "raw_input": intent,
                "clarification_log": [],
                "pending_answers": [],
                "p0_rounds": 0,
                "queue": "main",
            }
        )
        if state.get("status") == "CLARIFYING":
            questions = state.get("pending_questions", [])
            return {
                "output_files": [],
                "summary": f"需要澄清 {len(questions)} 项歧义，等待人工答复",
                "error": None,
            }
        if state.get("status") in ("DELIVERED", "MANUAL_REVIEW"):
            wo = state.get("draft_work_order", {})
            return {
                "output_files": [],
                "summary": f"工单 {wo.get('wo_number', '')} 已生成，状态 {state['status']}",
                "error": None,
            }
        return {
            "output_files": [],
            "summary": f"流程未完成: {state.get('status')}",
            "error": state.get("error"),
        }

    def create_task(self, input_contract: Dict[str, Any]) -> str:
        """创建任务并返回 session_id。"""
        session_id = f"sess-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.run(intent=input_contract.get("raw_text", ""))
        return session_id

    def submit_human_confirm(self, task_id: str, approved: bool, answers: list[Dict[str, Any]]) -> Dict[str, Any]:
        """提交人工确认/答复。"""
        return {"task_id": task_id, "approved": approved, "answers": answers, "status": "accepted"}

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """查询任务状态。"""
        return {"task_id": task_id, "status": "unknown"}

