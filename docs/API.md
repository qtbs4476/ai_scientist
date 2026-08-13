# 前后端数据契约（Backend Data Contract）

> 本文档描述**前端已实现、不会改动**的接口与数据格式。后端（真实 Agent 或 Mock）只需严格按此契约产出数据，前端无需任何改动即可工作。
>
> 当前 `src/mock_engine.py` 是本契约的**参考实现**（数据内容为写死的演示值），真实后端替换时请保持结构、只替换内容。

---

## 0. 总览

后端与前端之间有**两条通道**：

| 通道 | 方向 | 用途 |
|---|---|---|
| REST | 前端主动请求 → 后端 JSON 响应 | 取问题、开研究、提交意见、取报告等 |
| SSE | 后端单向推流 → 前端 | 研究过程实时展示（`text/event-stream`） |

**核心原则**：前端对后端返回字段是「按名取值」的。字段名、枚举值、嵌套结构三者**必须完全一致**；字段的**具体文案/数值内容**可以自由替换。

> HTTP 请求头 / 响应头 / CORS 约定见 §6。

---

## 1. REST 接口

所有接口挂在前端同源路径下（本地 `http://127.0.0.1:8899`）。

### 1.1 `GET /api/health`

健康检查，前端启动时调用。

```json
{ "ok": true, "mode": "mock", "storage": "sqlite", "version": "0.2.0" }
```

- `mode` / `storage` / `version` 为字符串即可，前端只读取 `storage` 判断是否显示「SQLite 已连接」。

### 1.2 `GET /api/questions?q=&category=`

问题搜索。参数均可选，`q` 为关键词，`category` 为分类（传 `全部` 或空表示不过滤）。

```json
{
  "items": [
    { "id": 13, "title": "我们能够预测下一场大流行病吗？", "category": "生命科学", "summary": "……" }
  ],
  "total": 125
}
```

**Question 对象**（贯穿全局的基础结构，字段固定）：

```json
{ "id": 1, "title": "…", "category": "…", "summary": "…" }
```

### 1.3 `GET /api/research`

历史研究列表。**只返回摘要**（不含 `gates/hypothesis/result`），前端左侧历史栏用。

```json
{
  "items": [
    {
      "id": "r_abcd123456",
      "question": { "id": 45, "title": "…", "category": "…", "summary": "…" },
      "status": "completed",
      "round": 2,
      "stage": "completed",
      "note": "三重审查通过",
      "updated_at": "2026-08-12T10:30:00"
    }
  ]
}
```

### 1.4 `POST /api/research/start`

请求体：`{ "question_id": 13 }`

响应：

```json
{
  "research_id": "r_abcd123456",
  "status": "running",
  "question": { "id": 13, "title": "…", "category": "…", "summary": "…" },
  "stream_url": "/api/research/r_abcd123456/stream?reason=start"
}
```

- 问题不存在返回 `404`。
- 前端只消费 `research_id`；`stream_url`、`question` 当前未被消费，可保留作扩展。

### 1.5 `GET /api/research/{research_id}`

返回**完整 Research 对象**（见 §3.1），用于历史研究回放。不存在返回 `404`。

### 1.6 `GET /api/research/{research_id}/stream?reason=start|feedback`

SSE 流（见 §2）。`reason` 取值 `start`（首次研究）或 `feedback`（人工意见后的重审）。不存在返回 `404`。

### 1.7 `POST /api/research/{research_id}/feedback`

请求体：`{ "message": "专家意见文本" }`（1~4000 字符）

响应：

```json
{
  "accepted": true,
  "research_id": "r_abcd123456",
  "round": 4,
  "impacted_gates": ["causal"],
  "message": "人工意见已加入当前研究，将触发相关审查重新执行。"
}
```

- `impacted_gates` 是受意见影响的 gate 列表，取值来自 `debate` / `trace` / `causal` 的子集。
- 不存在返回 `404`。

### 1.8 `POST /api/research/{research_id}/stop`

返回完整 Research 对象（`status` 变为 `stopped`）。不存在返回 `404`。

### 1.9 `GET /api/research/{research_id}/result`

```json
{ "research_id": "r_abcd123456", "status": "completed", "result": { /* §3.5 Result */ } }
```

`result` 在未完成时为 `null`。

### 1.10 `GET /api/research/{research_id}/report`

返回 Report 对象（见 §3.6），前端「查看完整科研报告」与独立报告页共用。

### 1.11 `GET /api/research/{research_id}/report.md`

直接返回 Markdown 文本（带 BOM），前端作为文件下载。

---

## 2. SSE 事件流

- **格式**：每条消息为 `data: <JSON>\n\n`。
- 每个 JSON **必有 `type` 字段**，其余字段随事件类型而定。
- 前端 `onmessage` 里 `JSON.parse(ev.data)` 后按 `type` 分发（见前端 `handleEvent`）。
- 前端**忽略未知的 `type`**（`handleEvent` 无 `default` 分支）——因此后端可安全新增事件类型。

### 2.1 事件总表

| `type` | 关键字段 | 说明 |
|---|---|---|
| `message` | `role, text` | 纯文本气泡（`role` 目前固定 `"assistant"`） |
| `progress` | `stage, status, label, documents?, core_citations?` | 阶段完成提示 |
| `hypothesis` | `hypothesis` | 候选假设生成 |
| `review_started` | `round, max_auto_rounds, reason?` | 一轮审查开始 |
| `audit_step` | `round, gate, step, total_steps, stage, label, text, skipped?` | 单个 gate 的审查过程（逐条增量） |
| `gate_update` | `round, gate, status, progress, issues, detail, skipped?` | 单个 gate 出结果 |
| `review_failed` | `round, failed_gates, revision_count` | 本轮有 gate 未通过 |
| `revision_started` | `round, hypothesis, changes[]` | 自动修订开始 |
| `feedback_received` | `round, message, impacted_gates` | 人工意见已接收 |
| `human_intervention_required` | `round, failed_gates, unresolved[], message` | 3 轮后仍失败，需人工 |
| `final_result` | `round, result, after_feedback?` | 最终结论 |
| `stream_end` | （无） | 流结束，前端关闭连接 |

### 2.2 每个事件的完整字段

**`message`**

```json
{ "type": "message", "role": "assistant", "text": "已读取 Science125 #13：……" }
```

**`progress`**

```json
{ "type": "progress", "stage": "problem_understanding", "status": "completed", "label": "问题理解" }
{ "type": "progress", "stage": "evidence", "status": "completed", "label": "证据准备", "documents": 156, "core_citations": 12 }
```

**`hypothesis`**

```json
{ "type": "hypothesis", "hypothesis": { "title": "…", "summary": "…", "falsifiable": "…" } }
```

**`review_started`**

```json
{ "type": "review_started", "round": 1, "max_auto_rounds": 3 }
```

人工介入流中会多一个字段：`{ "type": "review_started", "round": 4, "reason": "human_feedback", "max_auto_rounds": 3 }`

**`audit_step`**（每个 gate 依次推 3 条，`step` 从 1 到 `total_steps`=3）

```json
{
  "type": "audit_step",
  "round": 1,
  "gate": "debate",
  "step": 1,
  "total_steps": 3,
  "stage": "focus",
  "label": "审查目标",
  "text": "检查核心审查标准是否足以支持当前假设。"
}
```

- `stage` 取值：`focus` / `evidence` / `reasoning`（人工流里还有 `reuse`）。
- 人工流里，未受影响的 gate 会带 `"skipped": true`。

**`gate_update`**（一个 gate 审查结束，`detail` 是抽屉完整数据源）

```json
{
  "type": "gate_update",
  "round": 1,
  "gate": "debate",
  "status": "failed",
  "progress": 100,
  "issues": ["适用范围过宽", "反例解释不足"],
  "detail": { /* §3.3 GateDetail */ }
}
```

- `issues` 是标题字符串数组（与 `detail.issues[].title` 一致），供轻量展示。
- `progress` 目前恒为 `100`；进度条的动态动画由前端自行完成，后端不需要推中间值。

**`review_failed`**

```json
{ "type": "review_failed", "round": 1, "failed_gates": ["debate", "causal"], "revision_count": 5 }
```

**`revision_started`**

```json
{ "type": "revision_started", "round": 2, "hypothesis": { "title": "…", "summary": "…", "falsifiable": "…" }, "changes": ["缩小适用范围到具备连续监测能力的地区", "……"] }
```

**`feedback_received`**

```json
{ "type": "feedback_received", "round": 4, "message": "请重点检查低资源地区的外推边界…", "impacted_gates": ["debate"] }
```

**`human_intervention_required`**

```json
{
  "type": "human_intervention_required",
  "round": 3,
  "failed_gates": ["causal"],
  "unresolved": [
    {
      "gate": "causal",
      "gate_name": "因果审查",
      "title": "混杂因素控制不足",
      "severity": "高",
      "recommendation": "加入分层/匹配/敏感性分析，并降低因果措辞。"
    }
  ],
  "message": "已达到 3 轮自动审查上限。系统不会为了“过审”继续自我迎合，需要专家提供新的判断或约束。"
}
```

- `unresolved` 可为空数组（人工流里复检失败时为空）。

**`final_result`**

```json
{ "type": "final_result", "round": 2, "result": { /* §3.5 Result */ } }
```

人工介入流中会带 `"after_feedback": true`。

**`stream_end`**

```json
{ "type": "stream_end" }
```

### 2.3 事件序列

**首次研究（`reason=start`）**：

```
message → progress(problem_understanding) → progress(evidence) → hypothesis
→ [ 第 1..N 轮循环：
    review_started
    → audit_step×3(debate) → gate_update(debate)
    → audit_step×3(trace)  → gate_update(trace)
    → audit_step×3(causal) → gate_update(causal)
    → (全部通过 → final_result → stream_end，结束)
    → (有失败且未到上限 → review_failed → revision_started，进入下一轮)
    → (第 3 轮仍失败 → human_intervention_required → stream_end，结束)
  ]
```

**人工介入（`reason=feedback`）**：

```
feedback_received → message
→ revision_started → review_started(reason=human_feedback)
→ audit_step×3(debate) → gate_update(debate)
→ audit_step×3(trace)  → gate_update(trace)
→ audit_step×3(causal) → gate_update(causal)
→ (仍有失败 → human_intervention_required → stream_end)
→ (全部可接受 → final_result(after_feedback=true) → stream_end)
```

---

## 3. 核心数据结构

### 3.1 Research（`GET /api/research/{id}`、`/start`、`/stop` 返回）

```json
{
  "id": "r_abcd123456",
  "question": { "id": 13, "title": "…", "category": "…", "summary": "…" },
  "status": "running",
  "round": 2,
  "stage": "review",
  "created_at": "2026-08-13T10:00:00",
  "updated_at": "2026-08-13T10:00:03",
  "note": "第 2 轮三重审查",
  "gates": { "debate": { /* Gate */ }, "trace": { /* Gate */ }, "causal": { /* Gate */ } },
  "hypothesis": { "title": "…", "summary": "…", "falsifiable": "…" },
  "result": { /* Result */ },
  "feedbacks": [
    { "message": "…", "time": "10:02", "impacted_gates": ["causal"] }
  ],
  "revision_history": [
    { "from_round": 1, "to_round": 2, "changes": ["…"], "time": "10:01", "human": false }
  ],
  "stream_generation": 0
}
```

**`status` 枚举**（前端据此决定 UI 状态）：

| 值 | 含义 |
|---|---|
| `running` | 进行中 |
| `completed` | 已完成 |
| `needs_human` | 需要人工介入 |
| `stopped` | 已停止 |

**`stage` 枚举**（更细的进度描述，非固定契约，`note` 可自由组织文案）：

`created / problem_understanding / evidence / hypothesis / review / revision / completed / human_intervention / feedback_received / stopped`

### 3.2 Gate（`Research.gates[gate]`）

```json
{
  "status": "failed",
  "progress": 100,
  "issues": ["适用范围过宽"],
  "detail": { /* §3.3 */ }
}
```

**Gate `status` 枚举**：`pending / passed / conditional / failed`

> `conditional` = 有条件通过。注意 `running` 只出现在前端瞬态 UI 中，后端**不持久化也不下发**该值。

### 3.3 GateDetail（`Gate.detail`，抽屉的完整数据源）

```json
{
  "gate": "debate",
  "gate_name": "思辨审查",
  "status": "failed",
  "status_name": "未通过",
  "score": 58,
  "verdict": "发现关键逻辑漏洞，当前假设暂不应作为最终科研结论。",
  "summary": "主要问题集中在适用范围过宽、反例解释不足以及行为因素缺失。",
  "criteria": [
    { "name": "反例覆盖", "result": "未通过", "detail": "至少存在多个历史反例尚未被当前假设解释。" }
  ],
  "issues": [
    {
      "title": "适用范围过宽",
      "severity": "高",
      "evidence": "当前假设默认不同国家都拥有近似连续的监测数据。",
      "recommendation": "缩小适用范围，并把数据完整度写成明确的适用条件。"
    }
  ],
  "evidence": [
    { "source": "历史疫情时间序列", "detail": "用于寻找没有稳定前驱信号的反例。" }
  ]
}
```

- `gate` / `gate_name` 固定为 `debate/思辨审查`、`trace/溯源审查`、`causal/因果审查`。
- `criteria[].result` 枚举：`通过 / 未通过 / 有条件`。
- `issues[].severity` 枚举：`高 / 中 / 低`。
- `status_name` 与 `status` 的映射：`pending→等待、passed→通过、conditional→有条件通过、failed→未通过`。

### 3.4 Hypothesis

```json
{ "title": "…", "summary": "…", "falsifiable": "…" }
```

### 3.5 Result（`final_result.result`、`Research.result`）

```json
{
  "title": "最终科学假设标题",
  "hypothesis": "假设摘要",
  "score": 88,
  "support_evidence": 18,
  "counter_evidence": 2,
  "citations": 12,
  "conclusion": "最终综合结论……",
  "falsification": "可证伪条件……",
  "limitations": ["…", "…"],
  "review_summary": { "debate": "…", "trace": "…", "causal": "…" },
  "research_plan": ["…", "…"],
  "human_feedback_applied": null,
  "review_round": 2
}
```

- `human_feedback_applied`：无人工介入时为 `null`，有人工介入时为该意见文本。

### 3.6 Report（`GET /api/research/{id}/report`）

```json
{
  "report_title": "AI Scientist 最终科研报告",
  "research_id": "r_abcd123456",
  "generated_at": "2026-08-13T10:00:00",
  "question": { "id": 13, "title": "…", "category": "…", "summary": "…" },
  "status": "completed",
  "review_rounds": 2,
  "problem_background": "…",
  "final_hypothesis": { "title": "…", "summary": "…" },
  "metrics": { "score": 88, "support_evidence": 18, "counter_evidence": 2, "citations": 12 },
  "review_summary": { "debate": "…", "trace": "…", "causal": "…" },
  "falsification": "…",
  "limitations": ["…"],
  "research_plan": ["…"],
  "human_feedback": [ { "time": "10:02", "message": "…", "impacted_gates": ["因果审查"] } ],
  "conclusion": "…"
}
```

> 注意：Report 里的 `human_feedback[].impacted_gates` 是**中文名**（如 `["因果审查"]`），与 Research 里 `feedbacks[].impacted_gates` 的**英文 key**（`["causal"]`）不同——这是现有实现的历史差异，前端各自按自己的字段读取，后端替换时**保持各自现状即可**。

---

## 4. 生命周期 / 状态机

```
POST /start ──▶ status=running, round=0
     │
     ▼ 前端打开 stream?reason=start
initial_flow: 理解 → 证据 → 假设 → 逐轮审查(≤3)
     ├─ 全部通过 ──▶ status=completed + final_result
     ├─ 第3轮仍失败 ──▶ status=needs_human + human_intervention_required
     └─ 失败但未到上限 ──▶ 自动修订 → 下一轮

POST /feedback ──▶ status=running, round+=1, 记录 feedbacks
     │
     ▼ 前端打开 stream?reason=feedback
feedback_flow: 复检受影响的 gate
     ├─ 仍有失败 ──▶ status=needs_human + human_intervention_required
     └─ 可接受 ──▶ status=completed + final_result(after_feedback=true)

POST /stop ──▶ status=stopped（并让正在进行的流停止）
```

**流的中断（stop 的实现方式）**：后端维护 `stream_generation` 计数，`stop` 或新 `feedback` 会令其 +1；流在执行每一步前检查该值是否仍等于开流时的值，不一致就终止 yield。真实后端可自行实现等价取消机制，但需保证**停止后流能自行结束**。

---

## 5. 替换真实后端时：必须保持 vs 可自由改

### 必须严格保持（前端依赖的契约）

- 所有接口的**路径、HTTP 方法、状态码**（404 语义）。
- SSE 格式 `data: {...}\n\n` 与 `type` 字段。
- 每个事件、每个对象的**字段名与嵌套结构**。
- 枚举值：`status`（4 个）、gate `status`（4 个）、`criteria[].result`、`issues[].severity`。
- gate 的 key 恒为 `debate / trace / causal`。
- `GateDetail` 的完整嵌套结构（抽屉依赖）。

### 可自由替换（后端自己的业务）

- 所有**文案与数值**：`verdict/summary/text`、`score`、`evidence` 条数、`citations` 等。
- `stage` / `note` 的具体措辞（前端仅展示）。
- 事件之间的**延时**、是否拆分更多 `audit_step`。
- 可**新增**事件类型或对象字段（前端忽略未知项）——向后兼容的扩展是安全的。

---

## 6. HTTP 头约定（请求头 / 响应头 / CORS）

### 6.1 前端发出的「请求头」

前端所有 REST 调用统一走 `api()` 封装，会给**所有 `/api/*` 请求（含 GET）带 `Content-Type: application/json`**。SSE 用 `EventSource`，无法自定义请求头。

| 请求类型 | 请求头 |
|---|---|
| 所有 `/api/*`（GET/POST） | `Content-Type: application/json` |
| SSE 流（EventSource） | 浏览器自动带 `Accept: text/event-stream`，**不能加自定义头** |

POST 示例（开始研究）：

```http
POST /api/research/start HTTP/1.1
Host: 127.0.0.1:8899
Content-Type: application/json

{"question_id": 13}
```

POST 示例（提交意见）：

```http
POST /api/research/r_abcd123456/feedback HTTP/1.1
Host: 127.0.0.1:8899
Content-Type: application/json

{"message": "请重点检查低资源地区的外推边界"}
```

SSE 示例：

```http
GET /api/research/r_abcd123456/stream?reason=start HTTP/1.1
Host: 127.0.0.1:8899
Accept: text/event-stream
```

### 6.2 后端必须返回的「响应头」

**SSE 流**（少一个前端就断流或缓冲）：

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

**Markdown 下载**：

```http
HTTP/1.1 200 OK
Content-Type: text/markdown; charset=utf-8
Content-Disposition: attachment; filename="ai-scientist-report-{research_id}.md"
Cache-Control: no-store
X-Content-Type-Options: nosniff
```

**HTML 页面 / JSON 接口**：带 `Cache-Control: no-store`（前端要拿最新研究状态，不能被缓存）。

### 6.3 CORS（真实后端跨域部署时）

当前前端与后端**同源**（`127.0.0.1:8899`），无 CORS 需求。真实后端若部署到**不同域名/端口**：

1. POST 请求因 `Content-Type: application/json` 属「非简单请求」，会触发 **OPTIONS 预检**。后端需处理 `OPTIONS` 并返回：
   - `Access-Control-Allow-Origin`
   - `Access-Control-Allow-Headers: Content-Type`
   - `Access-Control-Allow-Methods: GET, POST, OPTIONS`
2. `EventSource` 跨域同样需要 `Access-Control-Allow-Origin`。
3. 鉴权：SSE **不能带自定义请求头**，只能走 Cookie 或 URL 参数（如 `?token=…`）。

### 6.4 自测 curl

```bash
# 开始研究
curl -X POST http://127.0.0.1:8899/api/research/start \
  -H "Content-Type: application/json" \
  -d '{"question_id": 13}'

# 看 SSE 流（-N 关缓冲，边到边打印）
curl -N http://127.0.0.1:8899/api/research/r_abcd123456/stream?reason=start

# 提交意见
curl -X POST http://127.0.0.1:8899/api/research/r_abcd123456/feedback \
  -H "Content-Type: application/json" \
  -d '{"message": "请重点检查低资源地区的外推边界"}'
```
