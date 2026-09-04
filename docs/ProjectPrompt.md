# AI Scientist 项目限定提示词（Prompt / System Card）

> 版本：v2026-08-25\
> 用途：作为项目系统提示词写入 Agent / LLM 上游，约束对本项目代码的改动、接口调用、输出格式与容错策略。\
> 维护方：AI Scientist 开发组

***

## 1. 项目身份与目标

AI Scientist 是一个**多智能体协作的科学假设生成与迭代优化系统**（前端 Web + FastAPI 后端 + Chroma 向量库 + SQLite/MySQL 快照存储）。核心链路：
用户提交科学问题 → **Explorer（问题骨架 + 证据 + 知识缺口）→ Scientist（假设）→ Critic（五维评分 + 颗粒度统计）** → 快照落盘/入库 → 用户给出专家意见 → V1→V2→V3 迭代。

所有改动必须**不破坏 Explorer / Scientist / Critic 的调用顺序、快照字段契约、前端轮询格式**。

***

## 2. 代码改动约束（MUST）

### 2.1 全局约束

- **IDE 模式下不要擅自改写代码**，必须经用户明确"执行/修复/加"等肯定指令后才落地 Edit/Write。

- SOLO 模式下保持默认。

- 新增字段时，**Pydantic 模型、前端 apiCreateJob 传参、/api/run、/api/feedback、snapshot 落盘（JSON+DB）要同步更新**，不得单边改动。

- 所有文件 I/O（`open(...)`）**必须显式指定** **`encoding="utf-8"`**；写 JSON 必须 `ensure_ascii=False`。

- `logging.basicConfig`、`print`、`stdout/stderr` 在 Windows 环境下需确保中文不会被替换为 `?`，否则走 logger + 显式 UTF-8 输出。

- Python 字符串含中文、经过 HTTP 链路进入 FastAPI 时，**必须在** **`Content-Type: application/json; charset=utf-8`** 的条件下运行；缺少 charset 的请求要通过中间件强制补齐。

- 连接 MySQL (pymysql) 时，必须在 `connect_args` 里显式指定：`charset=utf8mb4, use_unicode=True`，并启用 `pool_pre_ping=True`。

- **API 契约字段变更后，必须构造 curl / httpx 请求端到端验证**，不能只做静态代码阅读就宣称解决。

### 2.2 目录结构改动约束

```
ai_scientist/
├── docs/        ← 设计文档、限定提示词、规格（本文件所在）
├── scripts/     ← 离线脚本（seed_pdf、search_papers 等）
├── src/
│   ├── agents/         agent_orchestrator 主链路、三个 Agent 实现
│   ├── models/         database.py (SQLAlchemy + SQLite/MySQL)、schemas
│   ├── services/       chroma_service、paper_search_service、job_manager
│   ├── utils/          结构化 fallback、validators
│   ├── config/         seed_data
│   └── main.py         FastAPI 入口 + 路由
├── test/       ← 单测（不要改名 / 不要并入 scripts/）
├── web/        ← 前端静态资源（index.html / app.js / styles.css / workspace.css）
├── data/       ← SQLite DB + Chroma persist dir
├── snapshots/  ← 轮次快照 JSON（按 project_id 子目录分桶）
└── venv/       ← 现存虚拟环境，优先用其 python 启动验证
```

### 2.3 后端接口契约（不能破坏）

| 方法   | 路径                                        | 说明                                                                                                                |
| ---- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| POST | `/api/run`                                | 首次研究：`question, initial_round, project_id?, auto_search_papers?` → 返回 `{job_id, project_id, round_label, status}` |
| POST | `/api/feedback`                           | 迭代反馈：`question, feedback, current_round, project_id?, auto_search_papers?` → 返回同上；**最大 V3**                       |
| GET  | `/api/job/{job_id}`                       | 轮询进度                                                                                                              |
| POST | `/api/job/{job_id}/cancel`                | 取消任务                                                                                                              |
| GET  | `/api/jobs`                               | 全部任务（恢复刷新前 running 任务）                                                                                            |
| GET  | `/api/snapshots` & `?project_id=`         | 轮次快照（前端启动时 merge 到 historyStore）                                                                                  |
| GET  | `/api/snapshot/{round_label}?project_id=` | 单轮快照                                                                                                              |
| POST | `/api/suggest-questions`                  | 输入框浮动 chip：`context?, mode∈{question,feedback}, project_id?, top_k=3`                                             |
| POST | `/api/search-papers`                      | arXiv 检索：`query, max_results, ingest, dedupe, full_text`                                                          |
| GET  | `/api/health`                             | 健康检查                                                                                                              |
| GET  | `/api/chart-overall` 等 x5                 | 图表数据（综合/雷达/颗粒度/瀑布/风险）                                                                                             |

### 2.4 快照字段契约（`data + snapshots/<pid>/Vx.json`）

```json
{
  "round": "V1|V2|V3",
  "timestamp": "ISO8601",
  "question": "原始研究问题（必须保留完整中文，不能乱码）",
  "project_id": "uuid or user-supplied",
  "agent_explorer": { "problem_skelton": "", "evidence_list": [...], "knowledge_gaps": [...], "analogies": [...] },
  "agent_scientist": { "hypotheses": [...] },
  "agent_critic": { "scores": {...}, "top_flaw": "", "missing_evidences": [...] },
  "overall_score": 0-10,
  "granularity_score": 0-3,
  "granularity_stats": { "L1":n, "L2":n, "L3":n, "total":n },
  "human_feedback": [{"content":"专家意见"}] | []
}
```

新增字段一律**设为 Optional + 默认值**，禁止破坏反序列化。

### 2.5 前端约束

- 所有 API 调用统一走 `apiFetch(url, options, timeoutMs)`，Content-Type 必须为 `application/json; charset=utf-8`，body 走 `TextEncoder().encode(...)` 强制 UTF-8 bytes。

- 研究项目归档 key：有后端 `project_id` 就用它，否则 `legacy:${question}`。

- 前端浮动 chip 容器 ID：`#composerChips`（专家意见框上方、绝对定位）和 `#customQuestionChips`（自定义问题内、内联布局），不要改动 DOM 位置。

- chip 点击时走 `appendText(text)` 智能拼接（区分空文本、标点结尾），不要直接覆盖输入框 value。

***

## 3. 文献检索与向量库（arXiv + Chroma 策略 B）

### 3.1 自动检索流程

- 由请求体 `auto_search_papers: true` 触发；默认 `false`，**前端不要擅自打开**。

- `agent_orchestrator.run_full_pipeline(...)` 中，策略 B 的步骤：

  1. `_pre_arxiv_ids = PaperSearchService.get_existing_arxiv_ids()`（快照起点）
  2. `search_and_ingest(question, max_results=5)` → 进 Chroma
  3. 主线 3 个 Agent 运行（此时 Explorer 证据可命中新增文献）
  4. `finally`：`post_arxiv_ids - _pre_arxiv_ids` → `cleanup_by_arxiv_ids(...)` 精确删除，避免向量库膨胀

- **手动塞入 / seed\_pdf / seed\_chroma 入的文献不在 arXiv\_id 快照范围内，不会被清理**。

- 中文 question 在送入 arXiv 前必须走 `_prepare_query`：

  1. 纯 ASCII 直通；
  2. 含中文：`_translate_to_english` 调 DashScope `qwen-plus` 转为 3-6 个英文关键词，用空格拼成一个 query；
  3. 失败降级为正则清洗（保留英文字母/数字/少量符号）。

- arXiv API URL 固定为 **`http://export.arxiv.org/api/query`**（HTTP 而不是 HTTPS），follow\_redirects=True 处理官方重定向。

### 3.2 PDF 全文入库

- `ingest_pdf(papers)` → 每篇下载 `https://arxiv.org/pdf/{arxiv_id去掉版本号}.pdf` → pypdf 解文 → 切分 → 每 chunk 打 `ingest_mode=pdf, chunk_index, total_chunks` 元数据。

- PDF 下载失败或空文自动**降级为 abstract-only**，打 `ingest_mode=abstract`。

- 本地 PDF 入库（`ingest_local_pdf`）按 `source=文件名` 去重。

### 3.3 Chroma

- 使用 DashScope `text-embedding-v2`，从 `DASHSCOPE_API_KEY_EMBEDDING` 或 `DASHSCOPE_API_KEY` 取 key。

- 冷启动（suggest\_questions 中无 snapshot 可用）→ `_build_chroma_brief` 走 Chroma top-3 相似片段作为上下文，输出 `based_on=chroma:top_3`。

***

## 4. 迭代浮动 chip（suggest-questions）

### 4.1 行为

- 3 条建议；输入框 focus 时先拉一次；input 防抖 350ms 再拉一次；blur 220ms 后清空。

- 先显示 3 个 skeleton（…）再渲染真实文本，失败静默清空。

- feedback 模式：当 `currentProjectKey` 是后端生成的真实 project\_id（非 `legacy:*`），会把 `project_id` 带上，以便 `suggest_questions` 读到最新 snapshot 做引导。

- based\_on 字段三值：`snapshot:Vx`（含五维得分、top\_flaw、missing\_evidences）→ 优先级最高；`chroma:top_3` → 冷启动兜底；`context_only` → 无任何 snapshot/Chroma，纯按用户输入前缀生成；`error` → 调用链异常。

***

## 5. 颗粒度评分规则（供理解）

- L1 = 只含 Claim 的句子；L2 = 含 Method/Evaluation；L3 = 含量化指标/对比方法/数值结果。

- `granularity_score` = `(1.0*L1 + 2.0*L2 + 3.0*L3) / total`，范围 0-3。质量加权时对 top hypotheses 额外乘系数。

- 若 `granularity_score > 3.0`，必是加权异常，需要先检查加权倍数公式边界。

***

## 6. 运行 / 启动 / 验证规则

### 6.1 启动方式

项目根目录 `e:\project\AIScientist\science\AI_Scientist\ai_scientist\`：

```bat
venv\Scripts\python.exe src\main.py
```

默认监听 `0.0.0.0:8848`（来自 `PORT` 环境变量，默认 8848）。

### 6.2 启动前与常见错误

- **`AttributeError: 'NoneType' object has no attribute 'splitlines'`**：通常是 `_free_port` 中 `subprocess.run` 返回 `out=None`；排查是否是命令在当前 shell 下不输出 netstat，或把该函数包一层 `out = out or ""`。

- **`LangSmithAuthError`** **/ 401 Unauthorized**：`set LANGCHAIN_TRACING_V2=false` 关闭旁路追踪，不影响主链路。

- **`ConnectionResetError`（HTTP video）**：欢迎页 `welcome.mp4` 断点续传主动断开，忽略。

- **乱码问号 '????'**：按 §2.1 + §2.2 + §2.5 三层（前端 charset/TextEncoder → ForceUTF8Middleware → pymysql connect\_args）重新核查；用 `_enqueue` 的 `[UTF-8 校验]` 日志判断出现在哪一层。

### 6.3 验证清单（每次改动后必须执行）

1. `GET /api/health` → 200
2. `POST /api/suggest-questions {mode: "question"}` → 返回 questions 数组 length=3
3. `POST /api/run`（中文问题，auto\_search\_papers=false）→ 入队日志显示 `[UTF-8 校验] question 入队正常`；job 完成后 `/api/snapshots?project_id=...` 的 question 与原中文逐字相等
4. `POST /api/feedback`（带 `project_id + auto_search_papers=true`）→ 必须出现 `📚 自动检索入库: 检索 N 篇, 入库 M 篇` 以及结束时 `🧹 已清理本次临时文献 X/Y 篇`
5. 浏览器刷新后，历史档案、顶栏 question chip、详情页标题三处不乱码

***

## 7. 输出格式约束（Agent 自己的响应）

- **先给出定位 → 再给出最小改动 → 最后给出验证结果**，禁止输出大段复盘总结代替具体修复。

- 涉及乱码/编码问题，必须给出 "字符被替换为 `?` 的机制解释"，并指明是否出现在文件编码 / 请求体解析 / SQL 连接 / 日志输出 四层中的哪一层。

- 对数据库相关的操作，先 `read` 再 `edit`，不要使用盲写、不要用 `echo|` 或 PowerShell 原生重定向生成含中文的脚本。

- 如果用户表示 "还不对 / 还是乱码 / 问题未解决"，立刻切到 TRAE-debugger 或最小可复现脚本，禁止继续用静态阅读反复猜测。

