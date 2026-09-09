# Writer 大纲确认闭环设计（v1.0.0）

> 2026-09-09 · AKO_hub_intake_agent 设计文档
> author: AKO_studio

## 背景与问题

写作任务（module=AKO_writer_agent）经 hub 投递后，writer 停在 N0 选题待人工确认
（`human_approval_status=pending`，completed_nodes 为空），只注册了 checkpoint.json，
无大纲更无 Word 成稿——因为 writer 的两道人工确认（N0 选题 / N2 大纲）只存在于其
CLI（run.py），hub 适配器无确认通道，对话端更无从问询。

同时投递载荷缺 topic 字段，writer 落到默认主题「陶粒墙板技术应用」而非用户原意。

## 需求

写作任务大纲生成后，在工作台对话内问询确认；可输入修改意见循环修订；人工确认后
才继续生成并产出 Word 成果文件，对话内给下载链接。

## 设计决策（已与用户对齐）

1. N0 选题自动批准（用户已在对话写明主题），只在大纲（N2）环节在工作台问询。
2. 大纲修改 = 输入修改意见文字 → writer 按意见重跑 N2 → 再确认（沿用 revisions 机制）。
3. 大纲确认后到 Word 成稿需数分钟（N3 逐章 LLM→N4 去AI味→N5 排版），对话内轮询进度，完成给 docx 下载链接。
4. 授权修改 D:\AKO\AKO_hub 仓库（新增确认端点）。

## 状态机与数据流

```
用户请求 → intake 澄清 → 工单(module=AKO_writer_agent, topic=raw_input)
→ hub deliver → 派发 writer:
    N0 选题(适配器自动批准) → N1 检索 → N2 大纲 →【停: outline_pending】
→ intake 轮询 task result(带 writer 块) → 对话内大纲卡片问询
→ 确认 → hub writer/confirm(approved) → N3 正文 → N4 去AI味 → N5 Word
        → docx 复制进 hub 文件区 + file_bus 注册 + 更新 output_file_ids
        → intake 轮询到 done → 对话内下载链接
→ 修改意见 → hub writer/confirm(approved=false, revisions) → N2 重跑 → outline_pending(循环)
```

## ① Hub 侧（D:\AKO\AKO_hub）

### 1.1 适配器 `agents/ako_writer_adapter.py`
`run()` 改为：
- 创建 WriterSpoke 任务后**自动批准 N0**（`submit_human_confirm(task_id, approved=True)`）。
- 轮询至 N2 大纲待确认（`human_approval_status in (pending,)` 且已出 outline，或节点
  名称含大纲等待），**不再等待更后节点**。
- 结果 JSON（沿用 `writer_task_{task_id}.json` 落 hub 输出目录）写：
  `{task_id, writer_task_id, outline, state, human_approval_status}`，适配器返回
  `{output_files:[result.json], summary:"大纲已产出，待工作台确认", status:"outline_pending"}`。

### 1.2 新确认端点
`POST /api/v1/hub/task/{task_id}/writer/confirm`，body `{approved: bool, revisions?: str}`：
1. 从 task_queue 行找该任务的结果文件 → 解析 writer_task_id（找不到则 404）。
2. 校验 task 的 workflow 为 writer、状态允许确认。
3. 启动**后台线程**执行确认（`submit_human_confirm`）：
   - `approved=True`：N3→N4→N5，阶段性更新 task_queue 行的 `result_json.writer.state`
     （"running"/"排版中"）供轮询显示；完成把 docx **复制到 hub 文件区**
     `paths["file_root"]`（位于 D:\AKO\AKO_hub 下，intake 下载代理白名单内），
     用现有 file_bus 注册 file_registry，更新 `output_file_ids`，state 置 done，
     记录 docx 相对路径。
   - `approved=False, revisions=...`：重跑 N2（writer 内部机制），完成后回到
     outline_pending（state 置 outline_pending 携带新大纲），等待再次确认。
   - LLM/执行失败：writer error_msg 写入 result_json，state 置 error。
4. 端点立即返回 202 `{accepted: true}`（异步执行）。

### 1.3 表迁移 `task_queue`
幂等新增列 `result_json TEXT`；结果只读端点
`/api/v1/hub/task/{task_id}/result` 透出 `writer` 块
（`{state, outline, writer_task_id, docx_relpath?, error?}`）。

## ② Intake 侧（本仓库）

### 2.1 主题传递
`deliver_with_local_queue` 投递前注入 `payload["topic"] = state["raw_input"]`：
writer 适配器 `topic = kwargs.get("topic")` 现能取到用户原意（含澄清范围，
2000 字符内截断由 writer 侧处理）。

### 2.2 新 WS 入站消息 `writer_confirm`
沿用 p0_response 一问一答模式：`{session_id, task_id, approved, revisions?}`。
处理：校验会话归属与 task 匹配 → 调 hub 确认端点（httpx POST）→ 回执
「已提交，正文撰写中…」/「已提交修改意见，重新生成大纲中…」；hub 4xx/5xx → error 消息。

### 2.3 结果轮询
无需新端点：现有 `/api/v1/intake/task/{task_id}/result` 代理透传 hub JSON，
writer 块自然透出。

## ③ 前端（web/src）

`DeliveryResultCard` 轮询结果后按 `result.writer.state` 分支渲染：
- `outline_pending`：**大纲卡片**——主题/章节列表（chapter 标题+字数预估）、
  底部两操作：`[确认大纲]` + 修改意见输入框 `[提交修改意见]`。
- `running` / `排版中`：进度文案（轮询继续）。
- `done`：成功摘要 + **Word 下载链接**（用现有下载代理，.docx 已白名单）。
- `error`：错误文案。

操作经 WS `writer_confirm` 发出，回执作为对话气泡上屏。

## ④ 错误处理与测试

- writer LLM 失败：确认线程写 result_json error → 轮询侧展示错误。
- 超时：沿用 writer POLL_TIMEOUT 240s，超时 result_json state 置 error。
- 测试：
  - hub：适配器 N0 自动批准（mock WriterSpoke）、确认端点 approved/revisions/202、
    docx 复制注册。
  - intake：topic 注入（deliver payload 含 topic=raw_input）、writer_confirm 处理
    （approved / revisions / hub 错误）。
  - 前端：DeliveryResultCard 大纲卡片状态渲染（确认/修改意见按钮）。
  - 全套件回归 + 浏览器端到端走通一次。

## 不做（YAGNI）
- 不做工作台在线结构化大纲编辑器（只用修改意见文字）。
- 不改 writer agent 本体（N0/N2 确认机制已具备，仅适配器接线）。
- N0 选题不在工作台问询（自动批准）。
