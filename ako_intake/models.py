"""Pydantic 数据契约（FI-III-09 中间输出结构化）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class IntakeInput(BaseModel):
    """阶段1输入契约。"""

    raw_text: str = Field(min_length=10, max_length=2000)
    session_id: str = ""


class Entity(BaseModel):
    """解析实体。"""

    type: Literal["module", "action", "scope", "time_ref", "object"]
    value: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AmbiguityItem(BaseModel):
    """歧义条目（L1致命/L2核心/L3次要）。"""

    field: str
    issue: str
    level: Literal["L1", "L2", "L3"]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    required_clarification: bool = True


class AmbiguityReport(BaseModel):
    """歧义报告（M02 输出）。"""

    fatal: List[AmbiguityItem] = Field(default_factory=list)
    core: List[AmbiguityItem] = Field(default_factory=list)
    minor: List[AmbiguityItem] = Field(default_factory=list)

    def needs_clarification(self, threshold: float = 0.7) -> bool:
        """是否存在必须澄清的歧义（L1/L2 或低置信度 L3）。"""
        if self.fatal or self.core:
            return True
        return any(item.confidence < threshold for item in self.minor)

    def resolved(self) -> bool:
        return not self.fatal and not self.core and all(item.confidence >= 0.7 for item in self.minor)


class IntentTree(BaseModel):
    """意图树（M01 输出）。"""

    entities: List[Entity] = Field(default_factory=list)
    action_candidates: List[str] = Field(default_factory=list)
    ambiguity_report: AmbiguityReport = Field(default_factory=AmbiguityReport)

    def entity_value(self, entity_type: str) -> Optional[str]:
        """取指定类型实体值。"""
        for entity in self.entities:
            if entity.type == entity_type:
                return entity.value
        return None


class Question(BaseModel):
    """P0 反问卡片（M03 输出）。"""

    qid: str
    field: str
    text: str
    type: Literal["single_choice", "open", "confirm"] = "single_choice"
    options: List[str] = Field(default_factory=list)
    required: bool = True


class Answer(BaseModel):
    """用户答复。"""

    qid: str
    value: str


class ClarificationLogEntry(BaseModel):
    """澄清记录。"""

    round: int
    questions: List[Question] = Field(default_factory=list)
    answers: List[Answer] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class Ako1WorkOrder(BaseModel):
    """ako1 标准工单（8 刚性字段）。"""

    wo_number: str
    module: str
    action: str
    scope: str
    rules: List[str] = Field(default_factory=list)
    prohibitions: List[str] = Field(default_factory=list)
    deliverable: str
    deadline: str
    intake_session_id: str = ""
    clarification_rounds: int = 0
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    review_score: Optional[float] = None
    risk_flag: str = ""
    fallback_reason: str = ""
    queue: Literal["main", "manual_review"] = "main"

    def to_payload(self) -> Dict[str, Any]:
        """转投递负载（YAML/JSON 序列化友好）。"""
        return self.model_dump(exclude_none=True)


class ReviewRecord(BaseModel):
    """独立评审记录（M07 输出）。"""

    review_score: float = Field(ge=0.0, le=1.0)
    structural_passed: bool = True
    differences: List[str] = Field(default_factory=list)
    reviewed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class HubAck(BaseModel):
    """Hub 回执。"""

    status: str
    wo_number: str = ""
    queue_position: int = 0
    estimated_start: str = ""
    hub_trace_id: str = ""


class RegistryVerifyResult(BaseModel):
    """registry verify 结果（投递前门禁）。"""

    registered: bool = False
    level: str = "unrated"
    deployable: bool = False
    trust_boundary_ok: bool = False
    reasons: List[str] = Field(default_factory=list)

