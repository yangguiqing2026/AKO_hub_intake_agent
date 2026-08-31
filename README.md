# AKO_hub_intake_agent

AKO 工厂唯一入口网关：自然语言进、YAML 工单出。

## 快速开始

```bash
pip install -r requirements.txt
python run.py                 # 启动 FastAPI 服务（:5026）
python -m ako_intake parse --text "帮我看看报价模块最近的数据"
python -m ako_intake status --session <session_id>
python -m ako_intake queue
```

## 目录结构

```text
ako_intake/    Python 包（core/services/gateways/adapters/db/llm/utils）
web/           React + TypeScript + Zustand 看板
config/        配置中心（intake_config.yaml）
tests/         pytest 单元测试
probes/        cluster_guardian 巡检探测
docs/          白皮书 v1.1.0、API、状态机
```

## 规范符合性

对齐《AKO_std_tech_maturity_v1.0.0.md》：信任边界（FI-IV-06）、一致性声明（FI-II-09）、独立评审 M07（FI-III-02）、配置外部化（FI-II-07）、可观测性（FI-II-08/FI-IV-05）、模型分级与预算软熔断（FI-IV-04）。

