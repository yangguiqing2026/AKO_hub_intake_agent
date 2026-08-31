---
title: AKO_hub_intake_agent 顶层设计白皮书
description: AKO Hub前端语义翻译与工单自动填写Agent的顶层设计文档。负责将人类自然语言转化为结构化ako1工单，经P0歧义消解后投递至AKO_hub，实现"自然语言进、YAML工单出"的工厂大门管控。
author: AKO_studio
date: 2026-08-31
version: v1.1.0
tags: [governance, quality, agent, workflow]
---

# AKO_hub_intake_agent 顶层设计白皮书

> **文档定位**：本白皮书为 AKO_hub_intake_agent 的顶层设计文档，定义其作为AKO工厂"唯一大门"的架构、协议、状态机与验收标准。所有开发活动须以此文档为基准，任何偏离须经AKO_build_agent审计并签入ChangeSet。
>
> **v1.1.0 修订说明**：依据《AKO_hub_intake_design_plan_v1.0.0.md》融入成熟度标准（AKO_std_tech_maturity_v1.0.0.md）五维符合性深化意见：补齐信任边界注册（FI-IV-06/VETO-09）、一致性声明（FI-II-09）、注册与等级校验（FI-IV-01）、监控接口（FI-IV-05）、独立评审 M07（FI-III-02）、记忆体系三级（FI-II-04）、配置外部化（FI-II-07）、模型分级与预算软熔断（FI-IV-04）、自身生命周期与文明职能类型。修订明细见附录D。
>
> **适用范围**：AKO Agent舰队全体（40个Agent）、AKO_hub总调度中心、AKO_Law_Vault治理层。

---

## 第一章 元信息

| 字段 | 内容 |
|------|------|
| **Agent名称** | AKO_hub_intake_agent |
| **命名规范** | AKO_xxx_agent（仅AKO大写，其余全小写，下划线分隔） |
| **Agent定位** | AKO工厂前端唯一入口网关（Intake Gateway）。人类自然语言的"翻译官"与ako1工单的"立法预审员"。 |
| **部署拓扑** | 独立Agent，与AKO_hub解耦。前端仅暴露一个看板（Web UI，暖金企业色系），AKO_hub完全隐藏于后端。 |
| **核心使命** | 将自然语言的混沌转化为有法可依的YAML工单；在工厂大门外完成所有歧义消解，确保进入Hub的每一张工单都是"已澄清、已结构化、已编号"的合法指令。 |
| **关联系统** | AKO_hub（调度中心）、AKO_registry_agent（注册与等级校验）、AKO_identity_service（人类门禁）、AKO_Law_Vault（规范与术语库）、各业务Agent领域知识库（只读索引）、AKO_cluster_guardian（巡检与质检） |
| **协议基准** | P0强制暂停→反向提问→内部消化→工程编号输出协议（2026-08-04生效） |
| **工单模板基准** | ako1标准工单模板（常用语"ako1"唤出） |
| **文档编号** | AKO_HUB_INTAKE_AGENT_WHITEPAPER_v1.1.0 |
| **规范符合性基准** | AKO_std_tech_maturity_v1.0.0.md（五维评估、12铁律、FI指标、VETO-09） |
| **版本关系** | v1.1.0 取代 v1.0.0（v1.0.0 保留为历史版本，待按生命周期流程标记 SUPERSEDED） |
| **审签状态** | 草案待审签（v1.1.0） |

### 术语表

| 术语 | 定义 |
|------|------|
| **Intake** | 工单摄入层。所有人类意图进入AKO工厂的唯一合法通道。 |
| **P0反问** | 检测到语义歧义时，强制暂停当前流程，逐条向用户反向提问，直至100%明确。 |
| **ako1工单** | AKO标准工单模板，含8个刚性字段：工单号、模块、动作、范围、铁律、禁止、交付、时限。 |
| **歧义漂移** | 自然语言中未声明变量导致的语义解析偏差，是幻觉与执行偏离的根源。 |
| **看板** | 前端唯一交互界面。用户在此输入自然语言、接收P0反问、确认工单。 |
| **草稿编号** | intake阶段生成的临时工单标识（WO-DRAFT-YYYYMMDD-NNN），Hub正式授号后替换为正式编号。 |
| **信任边界** | 注册时声明的五字段模型：capabilities / allowed_callers（默认拒绝）/ data_access_level / consistency_requirement / resource_quota（FI-IV-06）。 |
| **一致性模型** | strong / eventual / read_your_writes 三选一声明（FI-II-09），注册与证书中保持一致。 |
| **独立评审** | 由与生成模块不同的实例对工单进行结构与语义复核（铁律2/9、FI-III-02）。 |
| **文明职能类型** | 创新型 / 基础稳态型，P0 立项时标记（FI-I-05）。 |

---

## 第二章 用户故事

### US-001 自然语言输入
> **作为** AKO体系的使用者（人类），
> **我希望** 在看板上用日常语言描述我的需求，例如"帮我看看那个报价模块最近的数据有没有问题"，
> **从而** 不需要手动记忆和填写复杂的ako1工单模板。

**验收要点**：
- 支持中文自然语言输入，允许口语化、省略主语、存在指代（"那个""最近"）。
- 输入框为看板唯一显性交互元素，其余Hub功能全部隐藏。

### US-002 P0歧义消解
> **作为** AKO体系的使用者，
> **我希望** 当我的描述存在歧义时，系统能精准地指出"哪里不清楚"并给出选项让我选择，
> **从而** 避免AI"猜错"导致下游执行偏离。

**验收要点**：
- 反问须定位到具体"未声明变量"（如："您说的'看看'是指审计、修复还是优化？"）。
- 每轮反问最多同时提出3个问题，防止信息过载。
- 用户可随时选择"我不确定，按最保守策略处理"，触发降级路径。

### US-003 自动化工单生成
> **作为** AKO体系的使用者，
> **我希望** 在澄清所有歧义后，系统自动帮我填好ako1工单并展示给我确认，
> **从而** 我只需点击"确认投递"即可，无需手动搬运信息。

**验收要点**：
- 工单8个字段必须100%填满，不允许空值（核心字段由用户确认，次要字段可Agent推断并标注置信度）。
- 工单展示格式为标准ako1模板，人类可手动微调后再投递。

### US-004 Hub无感调度
> **作为** AKO_hub调度员，
> **我希望** 我只收到结构完整、编号规范、无歧义的YAML工单，
> **从而** 我不需要处理自然语言，只专注于调度与负载均衡。

**验收要点**：
- Hub API只接受符合ako1 schema的JSON/YAML负载，拒绝任何自然语言原文。
- Hub不暴露给前端，所有通信由intake Agent代理。

### US-005 治理可追溯
> **作为** AKO治理层，
> **我希望** 每一张进入工厂的工单都有完整的"原始输入→反问记录→最终工单"全链路日志，
> **从而** 当执行出现偏差时，可以追溯到源头是语义理解错误还是用户意图变更。

**验收要点**：
- 全链路日志存入AKO_Law_Vault/600_生命周期/。
- 日志包含：原始输入文本、P0反问轮次、用户每次答复、最终工单快照、时间戳、置信度评分。

---

## 第三章 横向阶段分解

整个Intake流程划分为6个横向阶段，构成一条"单向不可逆"的流水线。每个阶段有明确的输入、输出与准入准出标准。

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  阶段1      │ →  │  阶段2      │ →  │  阶段3      │ →  │  阶段4      │ →  │  阶段5      │ →  │  阶段6      │
│ 自然语言输入 │    │ 语义解析与   │    │ P0反向提问   │    │ 内部消化与   │    │ 工单投递     │    │ Hub调度执行  │
│             │    │ 歧义检测     │    │ 歧义消解     │    │ 工单生成     │    │             │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
     人类              Agent              Agent+人类          Agent              Agent              Hub
```

### 阶段1：自然语言输入（Human Layer）
- **触发方式**：用户在看板输入框键入或语音转文字。
- **输入物**：原始自然语言字符串（允许口语化、不完整、含指代）。
- **输出物**：原始文本 + 会话上下文ID（Session ID）。
- **准入标准**：无。任何文本均可进入。
- **准出标准**：文本非空且长度在10~2000字符之间。
- **异常处理**：超长文本截断并提示；空文本直接拒绝。

### 阶段2：语义解析与歧义检测（Parse & Detect）
- **负责模块**：NLU Parser + Ambiguity Detector
- **输入物**：原始文本 + Session上下文。
- **核心动作**：
  1. **实体抽取**：识别模块名（如"报价模块"）、动作意图（如"看看""优化"）、对象范围。
  2. **术语对齐**：将口语映射到AKO_Law_Vault标准术语（如"看看"→审计/修复/优化的候选集）。
  3. **缺失检测**：对照ako1模板8个字段，检测哪些字段在原文中**未声明**。
  4. **歧义分级**：
     - **L1-致命歧义**：动作（修复/新增/重构/设计/审签）未识别 → 必须触发P0。
     - **L2-核心歧义**：范围（只动/不动）未声明 → 必须触发P0。
     - **L3-次要歧义**：铁律/禁止/交付/时限未声明 → Agent可推断，标注置信度，不强制P0（但置信度<0.7时仍触发）。
- **输出物**：解析树（Parsed Intent）+ 歧义报告（Ambiguity Report）。
- **准出标准**：歧义报告生成完毕，所有字段标记为"已声明"/"未声明-可推断"/"未声明-需澄清"。

### 阶段3：P0反向提问（Interrogate）
- **负责模块**：P0 Interrogator
- **触发条件**：阶段2报告中存在任何L1/L2歧义，或L3歧义置信度<0.7。
- **核心动作**：
  1. **强制暂停**：当前工单生成流程挂起，状态机进入CLARIFYING。
  2. **反向提问**：按优先级排序（L1→L2→L3），逐条向用户展示问题。
     - 格式："检测到歧义：[具体问题]。请选择或补充："
     - 选项型：提供2~5个单选按钮（如"优化"的目标维度：速度/内存/可读性/兼容性）。
     - 填空型：开放输入（如"请明确'那个'具体指哪个模块？"）。
  3. **用户答复捕获**：记录用户每次选择/输入，更新Session上下文。
  4. **循环检测**：每轮答复后重新运行歧义检测，直至报告清零或达到最大轮次（默认3轮）。
- **输出物**：澄清记录（Clarification Log）+ 补全后的解析树。
- **准出标准**：L1/L2歧义全部清零；L3歧义全部有推断值（无论人工确认或Agent推断）。
- **最大轮次**：3轮。超过3轮仍未清零，触发异常Fallback（见第七章）。

### 阶段4：内部消化与工单生成（Form Building）
- **负责模块**：Form Builder
- **触发条件**：阶段3完成，解析树已完整。
- **核心动作**：
  1. **字段映射**：将解析树映射到ako1模板8个字段。
  2. **智能推断**：对未人工确认的L3字段，Agent基于领域知识库推断默认值：
     - 时限：默认90分钟（ako1模板默认值）。
     - 铁律：默认3条通用铁律（不修改生产环境、Git版本控制、关键模块人工Review）。
     - 交付：根据动作类型推断（修复→输出修复报告+PR链接；审计→输出审计日志）。
  3. **草稿编号生成**：WO-DRAFT-YYYYMMDD-NNN（Hub正式授号后替换）。
  4. **工单预览**：在看板展示完整ako1工单，允许用户手动微调。
  5. **独立评审（M07）**：结构评审（Pydantic+规则引擎）+ 语义评审（第二LLM，与生成不同实例）；review_score < 0.9 强制人工确认。
- **输出物**：完整ako1工单（YAML格式）+ 置信度标注 + 评审记录。
- **准出标准**：8个字段全部非空，YAML schema校验通过，独立评审通过或人工确认完成。

### 阶段4.5 独立评审（M07）
- **负责模块**：Independent Reviewer
- **输入物**：完整ako1工单 + 原始意图树 + 澄清记录。
- **核心动作**：
  1. 结构评审：Pydantic Schema + 规则引擎复核字段完整性、值域与 ako1 模板一致。
  2. 语义评审：第二 LLM（与生成模型不同实例，如 DeepSeek）复核 action/scope 与原始意图一致性，输出 review_score。
  3. 门控：review_score < 0.9 → 强制人工确认；否则自动放行至投递。
- **输出物**：评审记录（含 review_score、差异清单）。
- **准出标准**：评审通过或人工确认完成。

### 阶段5：工单投递（Delivery）
- **负责模块**：Delivery Gateway
- **触发条件**：用户在看板点击"确认投递"。
- **核心动作**：
  1. **Schema校验**：最终校验ako1工单格式（字段完整性、值域合法性）。
  2. **编号申请**：向Hub发送"编号申请"请求，Hub返回正式工单号 WO-HAI-YYYYMMDD-NNN。
  3. **工单固化**：草稿编号替换为正式编号，工单状态设为READY。
  4. **投递Hub**：通过内部API将YAML工单推送至AKO_hub的待调度队列。
  5. **回执确认**：等待Hub返回ACK，确认工单已进入队列。
- **输出物**：Hub回执 + 正式工单号 + 投递时间戳。
- **准出标准**：Hub返回ACK，工单在Hub队列中可查。

### 阶段6：Hub调度执行（Hub Layer）
- **负责系统**：AKO_hub
- **输入物**：来自intake Agent的正式ako1工单。
- **核心动作**：解析工单【模块】与【动作】字段，路由至目标业务Agent的待执行队列。
- **关键约束**：Hub**不**处理自然语言，**不**与用户直接交互，**不**做语义解析。Hub只认YAML工单。

---

## 第四章 纵向层级映射

AKO_hub_intake_agent 在AKO文明体系中位于L1（网关层），承上启下，是人与机器文明之间的"翻译官"。

```
┌─────────────────────────────────────────────────────────────────┐
│ L0 用户层（User Layer）                                          │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 人类：自然语言输入、P0反问答复、工单确认                       │ │
│ └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ L1 网关层（Intake Gateway）  ← AKO_hub_intake_agent 所在层      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 语义解析 │ 歧义检测 │ P0反问 │ 工单生成 │ 独立评审 │ 投递网关   │ │
│ └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ L2 调度层（Dispatch Layer）                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ AKO_hub：负载均衡、Agent路由、状态监控、ChangeSet管理        │ │
│ └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ L3 执行层（Execution Layer）                                     │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 业务Agent：AKO_quote_agent、AKO_netwatch_agent 等（40个）    │ │
│ └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ L4 治理层（Governance Layer）                                    │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ AKO_Law_Vault │ AKO_cluster_guardian │ 审计Agent │ 质检Agent  │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**层级间通信契约**：
- L0→L1：自然语言文本（HTTP/WebSocket）。
- L1→L0：结构化反问卡片（JSON，含选项/填空）。
- L1→L2：标准ako1工单（YAML/JSON，通过内部REST API）。
- L2→L1：工单编号回执、ACK确认、队列状态查询。
- L1→L4：全链路日志（写入AKO_Law_Vault/600_生命周期/）。
- L4→L1：规范更新推送（AKO_Law_Vault中术语表/模板变更时，实时同步至intake Agent）。

---

## 第五章 模块清单

AKO_hub_intake_agent 由7个核心模块构成，每个模块独立版本控制，通过内部消息总线通信。

### M01 NLU Parser（自然语言理解模块）
- **职责**：将原始自然语言文本解析为结构化意图树（Intent Tree）。
- **关键技术**：
  - 基于LLM的语义抽取（本地部署，条件成熟后迁阿里云）。
  - 模型分级路由（FI-IV-04）：简单查询→规则引擎或 Qwen2.5-7B；复杂歧义→DeepSeek/阿里云；按会话记账 Token 与成本（偏差≤±20%）。
  - 领域Prompt工程：注入AKO_Law_Vault术语表与模块清单，约束解析范围。
  - 指代消解：利用Session上下文解析"那个""最近"等指代词。
- **输入**：原始文本 + Session上下文。
- **输出**：Intent Tree（JSON结构，含entities、actions、targets、modifiers）。
- **版本**：v1.0.0

### M02 Ambiguity Detector（歧义检测器）
- **职责**：对照ako1模板，识别未声明变量并分级。
- **关键技术**：
  - 规则引擎：L1/L2歧义的硬规则匹配（如动作字段缺失直接触发P0）。
  - 置信度模型：对L3字段，基于历史数据训练推断置信度评分。
- **输入**：Intent Tree。
- **输出**：Ambiguity Report（含字段缺失清单、歧义等级、建议反问模板）。
- **版本**：v1.0.0

### M03 P0 Interrogator（反向提问引擎）
- **职责**：执行P0协议，生成反问内容并管理多轮对话状态。
- **关键技术**：
  - 反问模板库：按字段类型预制反问模板（选择型/填空型/确认型）。
  - 轮次管理：最大3轮，每轮后重新运行M02检测。
  - 会话状态机：维护CLARIFYING状态的上下文。
- **输入**：Ambiguity Report + Session历史。
- **输出**：反问卡片（JSON）→ 看板展示；Clarification Log（内部存储）。
- **版本**：v1.0.0

### M04 Form Builder（工单生成器）
- **职责**：将澄清后的Intent Tree转化为标准ako1工单。
- **关键技术**：
  - 模板引擎：Jinja2（与AKO_netwatch_agent统一技术栈）。
  - 字段推断引擎：基于动作类型、模块类型、历史工单模式推断缺省值。
  - Schema校验：Pydantic模型严格校验ako1字段类型与值域。
- **输入**：补全后的Intent Tree + Clarification Log。
- **输出**：ako1工单（YAML格式）+ 置信度标注。
- **版本**：v1.0.0

### M05 Knowledge Bridge（知识库连接器）
- **职责**：为语义解析提供领域知识支撑，确保"墙板""报价"等术语被正确理解。
- **关键技术**：
  - 只读索引：读取AKO_Law_Vault术语表、各业务Agent的领域知识库索引（不写入）。
  - 向量检索：RAG架构，将用户输入与知识库做语义匹配，补充解析上下文。
  - 缓存层：热点术语本地缓存，降低知识库查询延迟。
- **输入**：查询关键词（如"墙板""导数据"）。
- **输出**：术语定义、候选动作集、关联模块列表。
- **版本**：v1.0.0

### M06 Delivery Gateway（投递网关）
- **职责**：与AKO_hub对接，完成工单编号申请与投递。
- **关键技术**：
  - REST API Client：向Hub发送编号申请与工单投递请求。
  - 本地缓存队列：Hub不可达时，工单进入本地持久化队列，定时重试。
  - 幂等控制：同一草稿编号只投递一次，防止重复。
  - 一致性声明（FI-II-09）：编号申请与投递 ACK 采用 strong（幂等键=draft_wo_number）；本地重试队列采用 eventual。
  - 熔断器（FI-III-05）：Hub Client 设置超时与重试上限；超过月配额5%触发预算软熔断（见7.6）。
- **输入**：已确认的ako1工单。
- **输出**：Hub ACK + 正式工单号；或失败记录（进入异常Fallback）。
- **版本**：v1.0.0

### M07 Independent Reviewer（独立评审模块）
- **职责**：对 Form Builder 产出的工单执行独立复核，保证生成与评审分离（铁律2/9、FI-III-02）。
- **关键技术**：
  - 结构评审：Pydantic + 规则引擎（与 M04 共用 Schema Registry）。
  - 语义评审：第二 LLM（与 M01 生成模型不同实例），比对工单 action/scope 与原始意图。
  - 评审门控：review_score < 0.9 强制人工确认；评审记录可追溯。
- **输入**：ako1工单 + Intent Tree + Clarification Log。
- **输出**：评审记录（review_score、差异清单）。
- **版本**：v1.1.0

---

## 第六章 State通信协议

### 6.1 内部状态定义（Intake Agent内部）

Agent内部维护一个Session级状态对象，驱动LangGraph状态机流转。

```yaml
# intake_session_state.yaml
session_id: "sess-20260830-001"
status: "CLARIFYING"  # IDLE / PARSING / AMBIGUITY_DETECTED / CLARIFYING / RESOLVED / FORM_BUILDING / VALIDATING / REVIEWING / DELIVERED / FAILED
raw_input: "帮我看看那个报价模块最近的数据有没有问题"
parse_tree:
  entities:
    - type: "module"
      value: "报价模块"
      confidence: 0.92
    - type: "time_ref"
      value: "最近"
      resolved: "2026-08-23 ~ 2026-08-30"
  action_candidates:
    - "审计"
    - "修复"
    - "查看"
  ambiguity_report:
    fatal: []
    core: 
      - field: "action"
        issue: "动作未明确：'看看'可映射为审计/修复/查看"
        required_clarification: true
    minor:
      - field: "scope"
        issue: "范围未声明"
        confidence: 0.45
        agent_inferred: "全局审计"
  clarification_log:
    - round: 1
      questions:
        - "您说的'看看'是指：1)审计 2)修复 3)仅查看状态？"
      answer: "审计"
      timestamp: "2026-08-30T10:35:00+08:00"
  draft_work_order:
    wo_number: "WO-DRAFT-20260830-001"
    module: "AKO_quote_agent"
    action: "审签"
    scope: "只动报价数据校验逻辑，不动数据库结构"
    rules:
      - "不修改生产环境"
      - "Git版本控制"
      - "关键模块人工Review"
    prohibitions:
      - "禁止直接修改生产数据库"
    deliverable: "输出审计报告，标注异常数据条目"
    deadline: "90分钟"
  final_work_order: null  # 投递后填充
  hub_ack: null
  review_score: null      # M07 独立评审评分，<0.9 强制人工确认
  error_log: []
  created_at: "2026-08-30T10:34:00+08:00"
  updated_at: "2026-08-30T10:35:30+08:00"
```

### 6.2 与Hub的API契约

#### 6.2.1 申请正式工单号

```http
POST /api/v1/hub/wo/allocate
Content-Type: application/json
X-Intake-Agent-Key: <secret>

{
  "session_id": "sess-20260830-001",
  "draft_wo_number": "WO-DRAFT-20260830-001",
  "module": "AKO_quote_agent",
  "action": "审签",
  "requested_at": "2026-08-30T10:36:00+08:00"
}
```

**Hub响应**：
```json
{
  "status": "allocated",
  "formal_wo_number": "WO-HAI-20260830-089",
  "allocated_at": "2026-08-30T10:36:01+08:00",
  "ttl_seconds": 300
}
```
> 注：TTL 300秒表示intake Agent须在5分钟内完成投递，否则编号回收。

#### 6.2.2 投递正式工单

```http
POST /api/v1/hub/wo/deliver
Content-Type: application/yaml
X-Intake-Agent-Key: <secret>

---
wo_number: "WO-HAI-20260830-089"
module: "AKO_quote_agent"
action: "审签"
scope: "只动报价数据校验逻辑，不动数据库结构"
rules:
  - "不修改生产环境"
  - "Git版本控制"
  - "关键模块人工Review"
prohibitions:
  - "禁止直接修改生产数据库"
deliverable: "输出审计报告，标注异常数据条目"
deadline: "90分钟"
intake_session_id: "sess-20260830-001"
clarification_rounds: 1
confidence_score: 0.95
submitted_at: "2026-08-30T10:36:30+08:00"
```

**Hub响应**：
```json
{
  "status": "acknowledged",
  "queue_position": 3,
  "estimated_start": "2026-08-30T10:40:00+08:00",
  "hub_trace_id": "hub-trace-20260830-089"
}
```
> 一致性（FI-II-09）：allocate/deliver 均以 draft_wo_number 为幂等键，采用 strong 一致性；Hub 侧应保证同一会话工单状态唯一。

### 6.3 与看板前端的通信协议

看板前端与intake Agent通过WebSocket长连接通信，实时推送反问卡片与工单预览。

```json
// 反问卡片（Server → Client）
{
  "type": "p0_interrogation",
  "session_id": "sess-20260830-001",
  "round": 1,
  "questions": [
    {
      "qid": "q-001",
      "field": "action",
      "text": "您说的'看看'是指以下哪种动作？",
      "type": "single_choice",
      "options": ["审计", "修复", "查看状态"],
      "required": true
    }
  ],
  "timeout_seconds": 300
}

// 用户答复（Client → Server）
{
  "type": "p0_response",
  "session_id": "sess-20260830-001",
  "round": 1,
  "answers": [
    {
      "qid": "q-001",
      "value": "审计"
    }
  ]
}

// 工单预览（Server → Client）
{
  "type": "wo_preview",
  "session_id": "sess-20260830-001",
  "draft_wo": { /* 完整ako1工单对象 */ },
  "confidence_score": 0.95,
  "review_score": 0.96,
  "actions": ["confirm", "edit", "discard"]
}
```

### 6.4 记忆体系三级（FI-II-04）

| 层级 | 载体 | 内容 |
|:---|:---|:---|
| 短期 | Session 上下文（现有） | 当前轮反问与答复 |
| 长期 | 向量库（ChromaDB，PII 脱敏） | 用户常用模块/动作偏好 |
| 情景 | 600_生命周期归档 | 每次工单快照 + 澄清日志 |

### 6.5 配置外部化（FI-II-07）

全部可配置参数外部化至 YAML 配置中心，支持热更新：

```yaml
# intake_config.yaml（示例）
max_p0_rounds: 3
question_timeout_seconds: 300
default_deadline_minutes: 90
review_score_threshold: 0.9
delivery_max_retries: 10
budget_soft_limit_percent: 5
llm_router:
  simple: "qwen2.5-7b"
  complex: "deepseek-v3"
```

### 6.6 可观测性与巡检接口（FI-II-08 / FI-IV-05）

```text
GET /health                          → 存活与依赖探测（hub/registry/knowledge）
GET /metrics                         → 会话量、P0轮次分布、投递成功率、Token消耗
GET /api/v1/intake/sessions/{id}     → 运行时状态查询（断点续传调试）
POST /api/v1/intake/review           → M07 评审结果回写
结构化 JSON 日志 + hub_trace_id 全链路关联
```

---

## 第七章 异常Fallback

### 7.1 连续澄清失败（P0超时/超限）

**触发条件**：
- 用户连续3轮P0反问后，仍存在未清零的L1/L2歧义。
- 或用户在单轮反问中超时（300秒）未答复。

**处置策略（降级路径）**：
1. **状态转移**：CLARIFYING → FAILED（歧义未消解）。
2. **生成低置信度工单**：Agent按"最保守策略"推断缺失字段：
   - 动作未明确 → 默认为"审签"（只读审计，不修改）。
   - 范围未明确 → 默认为"全局审计，不动任何代码/数据"。
3. **风险标注**：工单中强制附加字段 `risk_flag: "HIGH_AMBIGUITY"` 和 `fallback_reason: "P0_MAX_ROUNDS_EXCEEDED"`。
4. **不入Hub主队列**：投递至Hub的**人工审核队列**（special_queue: manual_review），等待人类调度员确认。
5. **日志归档**：完整P0对话记录写入AKO_Law_Vault/600_生命周期/，供后续模型优化。

### 7.2 Hub不可达（投递失败）

**触发条件**：
- Hub服务返回5xx错误或连接超时。
- 或编号申请API返回429（限流）。

**处置策略**：
1. **本地持久化**：工单写入本地SQLite队列（`/data/intake_queue/pending.db`）。
2. **指数退避重试**：首次1分钟后重试，之后2x退避，最大间隔10分钟，最多重试10次。
3. **告警**：第3次失败后，向AKO_netwatch_agent发送告警（邮件+看板通知）。
4. **最终失败**：10次重试后仍失败，工单状态设为FAILED（hub_unreachable），人工介入。

### 7.3 知识库缺失（术语无法解析）

**触发条件**：
- 用户输入包含知识库中无记录的术语（如全新模块名、行业黑话）。

**处置策略**：
1. **通用推断**：基于LLM通用知识做最佳猜测，置信度强制标记为≤0.5。
2. **标注提示**：反问卡片中附加提示："系统未识别到'XXX'的标准定义，以下推断基于通用语义，请确认："
3. **知识库补录建议**：会话结束后，自动生成"术语补录建议"工单，提交给AKO_Law_Vault维护Agent。

### 7.4 用户主动放弃

**触发条件**：
- 用户在看板点击"放弃"或关闭浏览器。

**处置策略**：
1. **会话归档**：Session状态设为ABANDONED，保留已生成的解析树和反问记录。
2. **不生成工单**：不向Hub投递任何内容。
3. **定时清理**：ABANDONED会话保留7天后自动清理（符合AKO生命周期规范）。

### 7.5 工单Schema校验失败

**触发条件**：
- Form Builder生成的工单未通过Pydantic schema校验（如字段类型错误、值域越界）。

**处置策略**：
1. **内部拦截**：不投递至Hub，状态设为FAILED（schema_error）。
2. **自动修复尝试**：对常见类型错误（如时限写成"一个半小时"而非"90分钟"），尝试正则转换。
3. **修复失败则告警**：通知AKO_cluster_guardian，标记为intake Agent内部缺陷。

### 7.6 预算软熔断（FI-IV-04）

**触发条件**：单会话 Token 成本达到月配额 5%。

**处置策略**：
1. 告警 + 自动降级：当前会话切换至专家模式（纯 ako1 表单），禁用大模型解析。
2. 不阻塞大门：intake 属文明关键基础设施（唯一大门），按标准 v1.0.0-patch ① 采用软熔断，不禁用服务。
3. 记账审计：Token 消耗按会话与调用方记录，成本偏差控制在 ±20% 内。

### 7.7 独立评审未通过

**触发条件**：M07 评审 review_score < 0.9，且人工确认未在时限内完成。

**处置策略**：
1. 状态转移：REVIEWING → MANUAL_REVIEW。
2. 工单入 Hub 人工审核队列（special_queue: manual_review），等待人类调度员确认。
3. 评审差异清单随工单投递，供人工快速定位。

---

## 第八章 LangGraph状态机

AKO_hub_intake_agent 的核心流程由LangGraph状态机驱动，确保每个Session在任意时刻都有确定状态，支持断点续传与异常恢复。

### 8.1 状态定义

| 状态码 | 状态名 | 说明 |
|--------|--------|------|
| S00 | IDLE | 会话初始化，等待用户输入。 |
| S10 | PARSING | 正在运行NLU Parser，文本→Intent Tree。 |
| S20 | AMBIGUITY_DETECTED | 歧义检测完成，发现待澄清项。 |
| S22 | REVIEWING | M07 独立评审中。 |
| S30 | CLARIFYING | 正在执行P0反问，等待用户答复。 |
| S40 | RESOLVED | 所有歧义已清零，准备生成工单。 |
| S50 | FORM_BUILDING | 正在构建ako1工单。 |
| S60 | VALIDATING | Schema校验中。 |
| S65 | QUEUED_LOCAL | 工单已入本地持久化队列（Hub 不可达）。 |
| S70 | DELIVERED | 工单已成功投递至Hub，获得ACK。 |
| S80 | FAILED | 流程失败，已触发Fallback。 |
| S85 | MANUAL_REVIEW | 工单处于人工审核队列。 |
| S90 | ABANDONED | 用户主动放弃。 |
| S95 | ARCHIVED | 终态归档（7天后入600_生命周期）。 |

### 8.2 状态转换图

```
                    ┌─────────────┐
         ┌─────────│    S00      │
         │         │    IDLE     │
         │         └──────┬──────┘
         │                │ 用户输入文本
         │                ▼
         │         ┌─────────────┐
         │         │    S10      │
         │         │  PARSING    │
         │         └──────┬──────┘
         │                │ 解析完成
         │                ▼
         │         ┌─────────────┐
         │    ┌────│    S20      │
         │    │    │ AMBIGUITY   │
         │    │    │  DETECTED   │
         │    │    └──────┬──────┘
         │    │           │ 存在歧义
         │    │           ▼
         │    │    ┌─────────────┐     超过3轮/超时
         │    │    │    S30      │────────────────┐
         │    │    │ CLARIFYING  │◄───────────────┘
         │    │    └──────┬──────┘  用户答复后重新检测
         │    │           │ 歧义清零
         │    │           ▼
         │    └────►┌─────────────┐
         │          │    S40      │
         │          │  RESOLVED   │
         │          └──────┬──────┘
         │                 │
         │                 ▼
         │          ┌─────────────┐
         │          │    S50      │
         │          │FORM_BUILDING│
         │          └──────┬──────┘
         │                 │
         │                 ▼
         │          ┌─────────────┐  校验失败
         │          │    S60      │──────────────► S80 (schema_error)
         │          │ VALIDATING  │
         │          └──────┬──────┘
         │                 │ 校验通过
         │                 ▼
         │          ┌─────────────┐  投递失败
         └─────────►│    S70      │──────────────► S80 (hub_unreachable)
                    │  DELIVERED  │
                    └─────────────┘
                          │
                          ▼ 用户放弃（任意状态可转入）
                    ┌─────────────┐
                    │    S90      │
                    │  ABANDONED  │
                    └─────────────┘
```
> 注：新增状态 S22（独立评审）、S65（本地队列）、S85（人工审核）、S95（归档）的接入位置见 8.3 转换规则表；上图保持 v1.0.0 主干拓扑。

### 8.3 状态转换规则

| 转换 | 触发条件 | 执行动作 | 异常处理 |
|------|----------|----------|----------|
| S00→S10 | 用户提交文本 | 创建Session，启动M01 | 空文本/超长文本→直接拒绝，保持S00 |
| S10→S20 | Parser返回Intent Tree | 启动M02歧义检测 | Parser异常→S80(parser_error) |
| S20→S30 | Ambiguity Report存在L1/L2歧义 | 生成反问卡片，推送看板 | 检测器异常→S80(detector_error) |
| S20→S40 | 无L1/L2歧义，L3置信度≥0.7 | 跳过P0，直接进入生成 | — |
| S30→S20 | 用户答复完成 | 更新Session，重新运行M02 | 超时→S80(p0_timeout) |
| S30→S40 | 歧义清零 | — | — |
| S30→S80 | 超过3轮仍未清零 | 生成低置信度工单，入人工审核队列 | — |
| S40→S50 | 自动触发 | 启动M04 Form Builder | — |
| S50→S60 | 工单生成完毕 | 启动Pydantic Schema校验 | 生成失败→S80(builder_error) |
| S60→S22 | 校验通过 | 启动M07结构+语义评审 | 评审异常→S80(review_error) |
| S22→S70 | 评审通过/人工确认完成 + 用户确认投递 | 申请编号→投递Hub→获得ACK | 见7.2 Hub不可达Fallback |
| S22→S85 | review_score<0.9 且人工未确认 | 工单入人工审核队列 | — |
| S60→S80 | Schema校验失败 | 尝试自动修复，失败则告警 | — |
| S70→S65 | Hub 不可达（编号/投递失败） | 本地SQLite持久化+指数退避重试 | 10次失败→S80(hub_unreachable) |
| S65→S70 | Hub 恢复且重试成功 | 完成投递，获得ACK | — |
| S85→S70 | 人工确认通过 | 按确认结果投递 | — |
| 任意→S90 | 用户点击"放弃"或断开连接 | 归档Session，清理资源 | — |
| 任意→S95 | 终态会话到期 | 7天后归档至600_生命周期 | — |

### 8.4 断点续传机制

每个Session状态实时持久化到本地SQLite（`/data/sessions/state.db`）。Agent重启后：
1. 扫描所有非终态会话（S10~S60、S22、S65、S85）。
2. 根据最后状态恢复流程：
   - 若在S30（CLARIFYING），重新推送最后一轮反问卡片至看板。
   - 若在S50/S60，重新展示工单预览。
   - 若在S22（REVIEWING），重新触发M07评审。
   - 若在S65（QUEUED_LOCAL），继续重试投递。
   - 若在S85（MANUAL_REVIEW），保留人工审核状态。
3. 终态会话（S70/S80/S90）在7天后归档至AKO_Law_Vault。

---

## 第九章 开发排期

### Phase 0：合规基线与立项（Day 1-3）
- **目标**：满足成熟度标准维度I与集群协同基线，消除一票否决项。
- **交付物**：
  - P0 立项工单 WO-HAI-YYYYMMDD-NNN 与 civilization_type 标记（创新型）。
  - 白皮书合规修订（本 v1.1.0：Frontmatter/标签/签章区）。
  - 信任边界五字段注册（FI-IV-06，模板见附录C）。
  - /health 与 /metrics 巡检接口、配置外部化（6.5/6.6）。
- **验收标准**：VETO-09 检查通过（五字段齐、allowed_callers 非空）。

### Phase 1：核心解析与P0反问引擎（Week 1-2）
- **目标**：M01 NLU Parser + M02 Ambiguity Detector + M03 P0 Interrogator 闭环。
- **交付物**：
  - 本地LLM语义抽取Pipeline（基于开源模型，如Qwen2.5-7B或同级）。
  - 模型分级路由与 Token 记账（FI-IV-04）。
  - 歧义检测规则引擎（覆盖ako1全部8个字段）。
  - P0反问模板库（v1.0，含20+核心反问模板）。
  - 看板前端原型（暖金色系，输入框+反问卡片+确认按钮）。
- **验收标准**：
  - 自然语言→Intent Tree解析成功率 ≥ 85%。
  - L1/L2歧义漏检率 = 0%（硬规则不允许漏检）。
  - P0反问平均回合数 ≤ 2.5。

### Phase 2：领域知识库接入（Week 3）
- **目标**：M05 Knowledge Bridge 对接AKO_Law_Vault与各业务Agent知识库。
- **交付物**：
  - 术语表只读索引（覆盖AKObuild、AKOagent全部核心术语）。
  - RAG向量检索模块（本地Embedding模型）。
  - 缓存层（Redis或本地LRU缓存）。
- **验收标准**：
  - 术语解析准确率 ≥ 90%（基于建筑行业测试集）。
  - 知识库查询延迟 ≤ 500ms（P99）。

### Phase 3：Hub API对接与看板UI（Week 4）
- **目标**：M04 Form Builder + M06 Delivery Gateway + 看板UI正式版。
- **交付物**：
  - ako1工单Jinja2模板引擎。
  - Hub API Client（编号申请 + 投递 + ACK处理）。
  - 看板正式UI（暖金企业色系，响应式布局，支持PC/平板）。
  - 本地缓存队列（SQLite持久化）。
  - M07 独立评审模块（结构+语义评审、review_score 门控）。
- **验收标准**：
  - 工单Schema校验通过率 = 100%。
  - Hub投递成功率 ≥ 99%（模拟Hub正常场景）。
  - 看板UI交互延迟 ≤ 200ms（反问卡片渲染）。

### Phase 4：异常Fallback与巡检集成（Week 5）
- **目标**：第七章全部 Fallback（含7.6/7.7）落地 + AKO_cluster_guardian巡检对接。
- **交付物**：
  - 全部7种异常Fallback的自动化处置逻辑。
  - 本地队列重试机制（指数退避）。
  - 预算软熔断与专家模式降级。
  - 告警通道（对接AKO_netwatch_agent邮件/看板通知）。
  - LangGraph状态机断点续传机制。
  - 全链路日志格式规范与AKO_Law_Vault写入接口。
- **验收标准**：
  - 异常场景覆盖率 = 100%（5/5）。
  - Hub不可达时，工单零丢失（本地队列持久化验证）。
  - 断点续传恢复成功率 = 100%。

### Phase 5：联调与压测（Week 6）
- **目标**：端到端联调 + 压力测试 + 文档固化。
- **交付物**：
  - 与AKO_hub的端到端联调报告。
  - 并发压测报告（目标：50并发Session，平均响应<3s）。
  - 本白皮书 v1.1.0 定稿 + AKO_hub_intake_agent_manual_v1.1.0.md。
  - ChangeSet原子更新脚本。
- **验收标准**：
  - 端到端工单流转成功率 ≥ 98%。
  - 系统稳定运行72小时无内存泄漏、无状态机死锁。

---

## 第十章 验收标准

### 10.1 功能性验收

| 编号 | 验收项 | 目标值 | 测试方法 |
|------|--------|--------|----------|
| AC-01 | 自然语言→ako1工单转化率 | ≥ 90% | 100条真实业务语句测试集 |
| AC-02 | P0反问平均回合数 | ≤ 3 | 统计所有成功会话的轮次分布 |
| AC-03 | L1/L2歧义漏检率 | = 0% | 构造含致命歧义的测试用例，验证是否100%触发P0 |
| AC-04 | 工单核心字段完整度（动作+范围） | = 100% | 抽样检查所有生成工单 |
| AC-05 | 工单次要字段推断准确率 | ≥ 80% | 人工评估时限/铁律/交付的推断合理性 |
| AC-06 | Hub投递成功率 | ≥ 99.5% | 连续1000次投递测试 |
| AC-07 | Hub不可达时工单丢失率 | = 0% | 模拟Hub宕机，验证本地队列持久化 |
| AC-08 | 断点续传恢复成功率 | = 100% | 模拟Agent重启，恢复各中间状态Session |
| AC-09 | 术语解析准确率（建筑领域） | ≥ 90% | 使用AKObuild/AKOagent术语测试集 |
| AC-10 | 全链路日志完整性 | = 100% | 验证每条成功/失败会话均有完整日志归档 |

### 10.2 非功能性验收

| 编号 | 验收项 | 目标值 |
|------|--------|--------|
| AC-11 | 看板UI首屏加载时间 | ≤ 1.5s |
| AC-12 | 语义解析响应时间（P99） | ≤ 2s |
| AC-13 | P0反问卡片渲染延迟 | ≤ 200ms |
| AC-14 | 并发Session支持 | ≥ 50 |
| AC-15 | 系统连续运行稳定性 | 72小时无重启 |
| AC-16 | 代码测试覆盖率 | ≥ 70% |
| AC-17 | 敏感凭证存储 | 全部存secrets.env，代码中无硬编码 |
| AC-18 | API通信加密 | 全部HTTPS/TLS 1.3 |

### 10.3 治理合规验收

| 编号 | 验收项 | 目标值 |
|------|--------|--------|
| AC-19 | 文档作者规范 | 全部标注AKO_studio |
| AC-20 | 文件命名规范 | 符合AKO_{模块}_{描述}_vX.Y.Z.md |
| AC-21 | 标签合规 | 仅从48个叶子标签白名单选取，≤5个，仅在YAML Frontmatter |
| AC-22 | Git版本控制 | 全部代码纳入AKO治理体系，关键模块人工Review |
| AC-23 | 单元测试 | 每个模块附带单元测试，禁止直接修改生产环境 |
| AC-24 | ChangeSet原子更新 | 支持全有或全无+全量回滚 |

### 10.4 成熟度符合性验收（v1.1.0 新增）

| 编号 | 验收项 | 目标值 |
|------|--------|--------|
| AC-25 | VETO-09 信任边界注册 | 五字段齐、allowed_callers 非空 |
| AC-26 | 独立评审拦截 | 语义错误工单 100% 被拦截或人工确认 |
| AC-27 | 预算软熔断 | 月配额 5% 触发告警并降级专家模式 |
| AC-28 | 等级调度拦截 | C 级/未评级目标 100% 拦截 |
| AC-29 | 监控接口 | /health /metrics 可被 cluster_guardian 巡检探测 |
| AC-30 | 一致性一致 | 注册声明与实际行为一致（FI-II-09） |

---

## 附录 A：与现有AKO体系的衔接说明

### A.1 与P0协议的关系
本Agent是P0协议的第一个**自动化执行实例**。P0协议原定义于"AI任务转达协议"（2026-08-04），适用于Agent→Agent的任务转达。本白皮书将其前置扩展至**Human→Agent**的意图转达，实现P0协议的全链路覆盖。

### A.2 与ako1模板的关系
ako1模板（常用语"ako1"唤出）是人类手工填写的标准。本Agent的Form Builder模块以ako1为**唯一输出标准**，确保机器生成的工单与人类手工工单在结构上完全兼容，Hub无需区分来源。

### A.3 与AKO_hub的关系
AKO_hub_intake_agent 是Hub的**前置独立网关**，不是Hub的子模块。两者通过REST API松耦合。Hub的待调度队列新增一个**人工审核子队列**（special_queue: manual_review），用于接收P0失败的降级工单。

### A.4 与AKO_Law_Vault的关系
本Agent的M05 Knowledge Bridge以**只读**方式访问Law_Vault。同时，本Agent产生的新术语补录建议、全链路日志，以**写入**方式回传至Law_Vault的600_生命周期/目录，形成知识闭环。

### A.5 与 registry / identity 的关系（三重门禁，v1.1.0）

intake 作为工厂唯一大门，投递前执行三重校验：
1. 身份：看板登录接入 AKO_identity_service（六位指纹/账号门禁），会话绑定人类身份；
2. 等级：工单 module 字段经 AKO_registry_agent 解析为已注册 agent_id；C 级或未评级目标一律拦截（转人工审核队列或拒绝）；
3. 数据等级：scope 含 PII 或财务字段时标记 data_access_level，全链路日志强制脱敏。

### A.6 与成熟度标准的关系（v1.1.0）

本 Agent 按《AKO_std_tech_maturity_v1.0.0.md》五维评估自检：

| 维度 | 关键缺口（v1.0.0） | v1.1.0 补齐措施 |
|:---|:---|:---|
| I 法制合规 | 标签违规、版本格式、无 P0/签章区 | 本版修正并补 P0 立项与签章区 |
| II 架构完整 | 无一致性声明、记忆单级、参数内嵌 | 6.4/6.5、FI-II-09 声明 |
| III 技术鲁棒 | 无独立评审、无熔断器 | M07、7.6/7.7 |
| IV 集群协同 | 未注册、无监控端点、无信任边界 | 附录C 注册模板、6.6、A.5 |
| V 文明进化 | 学习与评估闭环未成 | 澄清记录回流、周度自评 |

---

## 附录 B：风险与对策

| 风险 | 概率 | 影响 | 对策 |
|------|------|------|------|
| 本地LLM语义解析准确率不达标 | 中 | 高 | 预留模型热切换接口，可无缝升级至更强本地模型或云端模型（阿里云）。 |
| 用户反感P0反问过于繁琐 | 中 | 中 | 看板提供"专家模式"（直接显示ako1表单供手工填写），绕过自然语言流程。 |
| Hub API版本变更导致投递失败 | 低 | 高 | Delivery Gateway封装Hub Client，版本适配逻辑内聚，变更时只改一处。 |
| 术语库更新不及时导致解析偏差 | 中 | 中 | 建立术语变更Webhook机制，Law_Vault更新后实时推送至intake Agent缓存。 |
| 看板成为单点故障 | 低 | 高 | 支持多实例部署，Session状态外置到共享存储（SQLite→PostgreSQL）。 |
| 预算与成本失控 | 中 | 高 | 模型分级路由 + Token记账 + 预算软熔断（7.6）。 |

---

## 附录 C：信任边界注册模板（FI-IV-06）

```yaml
agent_registration:
  agent_id: AKO_hub_intake_agent
  version: "1.1.0"
  civilization_type: "创新型"
  capabilities:
    - name: parse_natural_language
      criticality: authorization
      input_schema: "schemas/intake_input_v1.json"
      output_schema: "schemas/intent_tree_v1.json"
    - name: deliver_work_order
      criticality: contractual
      input_schema: "schemas/ako1_wo_v1.json"
      output_schema: "schemas/hub_ack_v1.json"
  allowed_callers:
    - AKO_hub_agent
    - AKO_guardian_agent
    - AKO_cluster_guardian_agent
  data_access_level: PII_RESTRICTED
  consistency_requirement: read_your_writes
  resource_quota:
    max_tokens_per_call: 4000
    timeout_seconds: 30
    retry_policy: exponential_backoff
```

## 附录 D：修订记录（v1.1.0）

| 版本 | 日期 | 修订内容 | 修订人 |
|:---|:---|:---|:---|
| v1.1.0 | 2026-08-31 | 融入成熟度标准符合性深化意见（依据 AKO_hub_intake_design_plan_v1.0.0.md）：信任边界/一致性/注册/监控/独立评审M07/记忆三级/配置外部化/模型分级与预算软熔断/生命周期与文明职能类型；Frontmatter 版本与标签合规修正；新增附录C/D与签章区 | AKO_studio |
| v1.0.0 | 2026-08-30 | 原始第一版（顶层设计基线） | AKO_studio |

---

## 签章区

| 项目 | 内容 |
|:---|:---|
| 起草 | AKO_studio（2026-08-31） |
| 审签 | 待 AKO_studio 人工签章（禁止自动化） |
| 生效日期 | 待定 |
| 下次审阅 | 生效后 3 个月 |

---

> **文档结束**
>
> 本白皮书遵循AKO体系文档规范，作者AKO_studio，版本v1.1.0。
> 任何修改须通过AKO_build_agent的ChangeSet流程，经审计签入后方可生效。
