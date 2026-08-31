"""配置中心（FI-II-07 配置外部化）。

配置来源优先级：环境变量 > config/intake_config.yaml > 内置默认值。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH: Path = PROJECT_ROOT / "config" / "intake_config.yaml"


def _env(key: str, default: Any) -> Any:
    """读取环境变量，空串视为未设置。"""
    value = os.environ.get(key, "")
    return value if value != "" else default


@dataclass
class IntakeSettings:
    """Intake 流程参数。"""

    max_p0_rounds: int = 3
    question_timeout_seconds: int = 300
    max_questions_per_round: int = 3
    default_deadline_minutes: int = 90
    review_score_threshold: float = 0.9
    delivery_max_retries: int = 10
    retry_base_seconds: int = 60
    retry_max_seconds: int = 600
    wo_allocate_ttl_seconds: int = 300


@dataclass
class BudgetSettings:
    """预算与软熔断参数（FI-IV-04）。"""

    soft_limit_percent: float = 5.0
    monthly_quota_tokens: int = 1_000_000


@dataclass
class LlmRouterSettings:
    """模型分级路由（FI-IV-04）。"""

    simple: str = "qwen2.5-7b"
    complex: str = "deepseek-v3"
    use_llm: bool = False
    ollama_base_url: str = "http://localhost:11434"
    deepseek_base_url: str = ""


@dataclass
class ReviewerSettings:
    """独立评审参数（FI-III-02）。"""

    fallback_semantic_score: float = 1.0
    use_semantic_llm: bool = False


@dataclass
class GatewaySettings:
    """对外网关地址。"""

    identity_base_url: str = ""
    registry_base_url: str = ""
    hub_base_url: str = "http://localhost:8080"
    heartbeat_interval_seconds: int = 30


@dataclass
class DbSettings:
    """SQLite 路径。"""

    session_db: str = "data/sessions/state.db"
    queue_db: str = "data/intake_queue/pending.db"
    archive_dir: str = "data/archive"


@dataclass
class TermEntry:
    """术语表条目（M05 知识桥只读索引）。"""

    term: str
    module: str
    actions: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    """应用总配置。"""

    agent_id: str = "AKO_hub_intake_agent"
    host: str = "0.0.0.0"
    port: int = 5026
    intake: IntakeSettings = field(default_factory=IntakeSettings)
    budget: BudgetSettings = field(default_factory=BudgetSettings)
    llm_router: LlmRouterSettings = field(default_factory=LlmRouterSettings)
    reviewer: ReviewerSettings = field(default_factory=ReviewerSettings)
    knowledge_base_url: str = "http://localhost:8000"
    knowledge_enabled: bool = False
    gateways: GatewaySettings = field(default_factory=GatewaySettings)
    db: DbSettings = field(default_factory=DbSettings)
    terms: list[TermEntry] = field(default_factory=list)

    def resolve_paths(self) -> AppConfig:
        """将相对数据路径解析为绝对路径，并确保父目录存在。"""

        def resolve(rel: str) -> Path:
            p = Path(rel)
            return p if p.is_absolute() else PROJECT_ROOT / p

        self.db.session_db = str(resolve(self.db.session_db))
        self.db.queue_db = str(resolve(self.db.queue_db))
        self.db.archive_dir = str(resolve(self.db.archive_dir))
        for p in (self.db.session_db, self.db.queue_db, self.db.archive_dir):
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        return self


def _load_yaml(path: Path) -> Dict[str, Any]:
    """读取 YAML 配置，失败返回空字典。"""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_config(path: str | Path | None = None) -> AppConfig:
    """加载配置（环境变量优先）。"""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = _load_yaml(cfg_path)

    service = raw.get("service", {})
    intake_raw = raw.get("intake", {})
    budget_raw = raw.get("budget", {})
    router_raw = raw.get("llm_router", {})
    reviewer_raw = raw.get("reviewer", {})
    gateways_raw = raw.get("gateways", {})
    db_raw = raw.get("db", {})
    knowledge_raw = raw.get("knowledge", {})
    terms_raw = raw.get("terms", [])

    config = AppConfig(
        agent_id=_env("INTAKE_AGENT_ID", service.get("agent_id", "AKO_hub_intake_agent")),
        host=_env("INTAKE_HOST", service.get("host", "0.0.0.0")),
        port=int(_env("INTAKE_PORT", service.get("port", 5026))),
        intake=IntakeSettings(
            max_p0_rounds=int(intake_raw.get("max_p0_rounds", 3)),
            question_timeout_seconds=int(intake_raw.get("question_timeout_seconds", 300)),
            max_questions_per_round=int(intake_raw.get("max_questions_per_round", 3)),
            default_deadline_minutes=int(intake_raw.get("default_deadline_minutes", 90)),
            review_score_threshold=float(intake_raw.get("review_score_threshold", 0.9)),
            delivery_max_retries=int(intake_raw.get("delivery_max_retries", 10)),
            retry_base_seconds=int(intake_raw.get("retry_base_seconds", 60)),
            retry_max_seconds=int(intake_raw.get("retry_max_seconds", 600)),
            wo_allocate_ttl_seconds=int(intake_raw.get("wo_allocate_ttl_seconds", 300)),
        ),
        budget=BudgetSettings(
            soft_limit_percent=float(budget_raw.get("soft_limit_percent", 5.0)),
            monthly_quota_tokens=int(budget_raw.get("monthly_quota_tokens", 1_000_000)),
        ),
        llm_router=LlmRouterSettings(
            simple=router_raw.get("simple", "qwen2.5-7b"),
            complex=router_raw.get("complex", "deepseek-v3"),
            use_llm=bool(router_raw.get("use_llm", False)),
            ollama_base_url=router_raw.get("ollama_base_url", "http://localhost:11434"),
            deepseek_base_url=router_raw.get("deepseek_base_url", ""),
        ),
        reviewer=ReviewerSettings(
            fallback_semantic_score=float(reviewer_raw.get("fallback_semantic_score", 1.0)),
            use_semantic_llm=bool(reviewer_raw.get("use_semantic_llm", False)),
        ),
        knowledge_base_url=_env("INTAKE_KNOWLEDGE_URL", knowledge_raw.get("base_url", "http://localhost:8000")),
        knowledge_enabled=bool(knowledge_raw.get("enabled", False)),
        gateways=GatewaySettings(
            identity_base_url=_env("INTAKE_IDENTITY_URL", gateways_raw.get("identity_base_url", "")),
            registry_base_url=_env("INTAKE_REGISTRY_URL", gateways_raw.get("registry_base_url", "")),
            hub_base_url=_env("INTAKE_HUB_URL", gateways_raw.get("hub_base_url", "http://localhost:8080")),
            heartbeat_interval_seconds=int(gateways_raw.get("heartbeat_interval_seconds", 30)),
        ),
        db=DbSettings(
            session_db=_env("INTAKE_SESSION_DB", db_raw.get("session_db", "data/sessions/state.db")),
            queue_db=_env("INTAKE_QUEUE_DB", db_raw.get("queue_db", "data/intake_queue/pending.db")),
            archive_dir=_env("INTAKE_ARCHIVE_DIR", db_raw.get("archive_dir", "data/archive")),
        ),
        terms=[
            TermEntry(
                term=item.get("term", ""),
                module=item.get("module", ""),
                actions=list(item.get("actions", [])),
            )
            for item in terms_raw
            if isinstance(item, dict) and item.get("term")
        ],
    )
    return config.resolve_paths()

