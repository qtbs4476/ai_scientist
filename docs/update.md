# 变更记录

## 2026-09-04

### 1. Chroma 双重 Bug 修复：冷启动 15 条 → 真实 1715 条知识库
- **改动文件**：`src/services/chroma_service.py`、`data/chroma_db/chroma.sqlite3`（通过 commit 纳管）、本地 `.env`（不进仓库，部署必填）
- **根因**：出现「count_documents()=15 冷启动」是两个 Bug 同时存在：
  1. `ChromaService.__init__` 的 `collection_name` 参数被硬编码为 `"knowledge_base"`，完全忽略 `.env` 里的 `CHROMA_COLLECTION_NAME` 与兼容别名 `CHROMA_COLLECTION`；
  2. 本地 FLA 分支此前执行 `git reset --hard main`，把 FLA 已纳入版本控制的真实 `chroma.sqlite3` 注册表冲回了 main 的 15 条。
- **修复**：
  1. 代码层：`src/services/chroma_service.py` 重写 collection_name 解析链为「显式非空实参 > CHROMA_COLLECTION_NAME env > CHROMA_COLLECTION env（兼容旧配置）> 默认 knowledge_base」；空字符串统一回退。
  2. 数据层：`chroma.sqlite3` 对齐 origin/FLA-workspace @59a2bc7 版本（单 collection=knowledge_base，注册表 1715 条 = OpenAlex 离线 + arXiv 在线 + seed 合并）。
- **部署注意**：`.env` 被 `.gitignore` 忽略不进仓库；部署时 **必须** 填入 `CHROMA_COLLECTION_NAME=knowledge_base` 与 SQLite 注册表名完全一致，否则会新建一个同名空集合并导致 count=0。
- **验证**：`ChromaService().count_documents()` 返回值稳定为 **1715**。

### 2. 本地 FLA-workspace 分支回收：丢失的 4 个 origin commit 全部吸收（纯本地引用无 --force）
- **问题**：本地 `reset --hard main` 让 FLA 回退到 main，丢掉了远端 `origin/FLA-workspace` 上存在的 4 个 commit（59a2bc7 / 26d5867 / ccd435e / 1fc249d）。
- **方式**：不依赖联网 pull（此前 GitHub HTTPS 偶发 Connection was reset），直接使用本地已 fetch 缓存的 `refs/remotes/origin/FLA-workspace`：
  1. 先保存未提交工作为 stash（消息：pre-rebase-originFLA4-20260904-1157）；
  2. `git reset --hard origin/FLA-workspace` 把本地 FLA HEAD 从 1dabed4 搬到 **1fc249d**（与 origin/FLA 完全一致）；
  3. 再 stash pop 还原本轮本地修改，并解三处冲突（见 09-04 第 3 条）。
- **结果**：`rev-list --left-right origin/FLA-workspace...FLA-workspace == 0 0` ✅；top-4 commit 完整回显（59a2bc7 chroma 纳管 / 26d5867 merge main / ccd435e sidebar 修复 / 1fc249d 移除多模态）。
- **安全**：全程无 `--force`，且保留快照分支 `sync-FLA4-before = backup/FLA-before-chroma-fix-20260904-112409 = 1dabed4` 供回退。

### 3. 解 stash 冲突 3 处：chroma.sqlite3 + update.md + styles.css
- `data/chroma_db/chroma.sqlite3`（AA）：保留 HEAD = origin/FLA 的真实 1715 注册版。
- `docs/update.md`（UU）：保留上游 origin/FLA 的 09-03 主条目（模块展示 HTML 拆分 + 浅色主题），再在 09-03 下追加本地增量条目「收起态内容宽度优化」（右栏隐藏 + chat-inner 渐进放宽），并清理合并残留的重复 `## 2026-09-03` header。
- `web/styles.css`（UU）：保留上游 ccd435e 的 `.has-research` 选择器（收起限定到研究工作区，不污染首页），再合并本地两份新规则：
  1. 双边收起时隐藏 `.right` 面板（visibility/opacity/border-left/pointer-events 全置空）；
  2. 补全 `.chat-inner` 渐进宽度（单边收起 = 1040px，双边收起 = 1200px），同样挂在 `.app.has-research` 下。
- **处理完毕后**：stash 条目 drop 清理；`git status --porcelain` 中无任何 UU/AA/AU/UA/DU/UD/DD 行。

### 4. 最终提交拆分：2 个 commit 组成本次工作增量
- **前置处理**：`git reset --mixed HEAD` 把冲突解决后自动 staged 的 5 个文件全部撤回到工作区，再按「代码类 vs 文档类」分两批 add。
- **Commit 1（SHA：4d14101）** — 标题：`fix(chroma): 修复ChromaService未读取CHROMA_COLLECTION_NAME环境变量，并确保真实知识库(1715 docs)被正确加载`
  - staged 仅含：`src/services/chroma_service.py`（sqlite3 和 HEAD 一致无 delta，未产生额外 diff）；全程未纳入 `data/chroma_db/16547ed5*` 的 4 个冷启动 bin 文件。
- **Commit 2（SHA：4604afd）** — 标题：`docs & ui: 更新模块展示文档+结构说明+09-03更新日志,并补全侧栏收起态右栏隐藏与chat-inner渐进宽度`
  - staged 仅含：`docs/ProjectPrompt.md`、`docs/ProjectStructure.md`、`docs/update.md`、`web/styles.css`。
- **push 前置条件**：`rev-list --left-right origin/FLA-workspace...FLA-workspace = 0 2`（0 behind / 2 ahead），属纯粹 fast-forward。下一步直接 `git push origin FLA-workspace` 即可，无需 force。

### 5. 清理向量库孤儿目录：删除 data/chroma_db/16547ed5…（保留真实 904ab7d8 HNSW 索引）
- **注册表证据**：当前 `chroma.sqlite3` 中 `collections.id = 89b84cca-e96e-4fb8-adfa-83aaa3918a6b`（name=knowledge_base, dim=1024），其 HNSW segment.id = **`904ab7d8-88c8-422d-b750-7389c12425aa`**（5 个文件 / 7.7 MB，被 git 跟踪）。
- **目录对比**：
  - `904ab7d8…`：当前真实 HNSW 索引（5 files, 7729 KB，git-tracked=5）→ 活；绝对不能删。
  - `16547ed5…`：无任何 collection/segment 引用（0 registry）→ 冷启动 15 条时的孤儿目录。414 KB 垃圾，git untracked。
- **清理方式**：Move 到 `$env:TEMP\16547ed5-chroma-orphan-<timestamp>`（安全可恢复），而非直接永久删。
- **清理后验证**：count_documents() 仍 1715；similarity_search(k=3) 返回 3 条（#1 openalex / #2 Pearl 2009 Causality / #3 Pearl 1995 Biometrika）→ HNSW 走 904 目录完全正常；git status 中 `16547ed5` untracked 行消失。

### 6. 下一步工作指引（待执行）
1. 推送到 fork 远端：`git push origin FLA-workspace`（预计 fast-forward 成功）。
2. 推送后验证本地 SHA 与远端 `refs/heads/FLA-workspace` 完全一致（`git rev-parse FLA-workspace` vs `git ls-remote origin refs/heads/FLA-workspace`）。
3. 在 GitHub 开 PR：
   - **Base**：`qtbs4476/ai_scientist main`
   - **Head**：`thisonvo06/ai_scientist FLA-workspace`
   - PR 标题建议：`fix(chroma): env CHROMA_COLLECTION_NAME 读取 + 真实 1715-db sqlite3 恢复(cold 15→1715); 侧栏收起宽度+docs更新`
   - PR 主体要点：ChromaService 双环境变量回退链、chroma.sqlite3 从 FLA 真实版本恢复（含真实 HNSW 904ab7d8 segment UUID，已被 59a2bc7 纳管进 git）、首页不受影响的侧栏 has-research 限定 + chat-inner 渐进宽度、文档更新说明、孤儿 16547ed5 目录已从工作区清理（已在本机未跟踪层面删除）。

## 2026-09-03

### 1. 新建前端视频模块展示文件
- **改动文件夹**：`report/模块展示/`（新建）
- **需求**：前端视频演示手稿旁白部分全部念出时间过长，需将详细模块设计拆分为独立 HTML 文件，方便直接截图插入视频展示，缩短读稿时长。
- **新增文件**（共 10 个）：
  1. `三级模型分离策略.html` — Scientist/Critic/Explorer 三级模型分离策略可视化
  2. `五层系统架构.html` — 五层分层架构（前端→FastAPI→智能体→模型→存储）
  3. `四智能体协作流程.html` — Explorer→Scientist→Critic→Orchestrator 协作流水线
  4. `Explorer输出结构.html` — Explorer 四部分输出（问题骨架/证据列表/知识缺口/跨域类比）
  5. `Scientist假设卡片设计.html` — 假设卡片含证伪条件/L1-L2-L3 三层计划/双阈值验证
  6. `Critic五维评分与缺陷诊断.html` — 五维雷达图/致命缺陷/反事实三级逻辑检查
  7. `V1V2迭代对比.html` — V1→V2 分数对比/三大关键变化/快照留痕
  8. `专家反馈与人在回路.html` — 智能建议推送/反馈面板/迭代机制
  9. `可视化图表与报告导出.html` — 5 个 ECharts 图表 + 十项标准化报告模板
  10. `四大核心亮点.html` — 证据与假设分离/量化可证伪/闭环迭代/多模态+125题全覆盖
- **设计说明**：所有文件统一深色主题，与原手稿风格一致，自包含内联 CSS，可直接浏览器打开截图。
- **浅色主题**：为 10 个文件统一添加浅色主题切换功能——右上角固定 ☀️/🌙 按钮一键切换深色/浅色主题。浅色主题使用 GitHub Light 配色（背景 #f6f8fa、文字 #1f2328、强调色 #0969da 等），SVG 图表颜色同步切换，渐变背景适配浅色模式。

### 2. 收起态内容宽度优化：右栏面板隐藏 + chat-inner 渐进放宽
- **改动文件**：`web/styles.css`
- **需求**：侧栏收起后中间区域变宽，但 `.chat-inner` 最大宽度仍 880px，留白过多；且右栏收起时 280px 仍占位但面板不隐藏（visibility 仍可见元素）。
- **改动**：
  1. 双边收起态同步隐藏 `.right` 面板：`visibility:hidden; opacity:0; border-left:0; pointer-events:none`。
  2. 单收 1 侧：`.chat-inner` 最大宽度 **1040px**。
  3. 双收 2 侧：`.chat-inner` 最大宽度 **1200px**。
  4. 所有规则限定 `.has-research`，不影响首页的侧栏布局。
- **说明**：本条目对应「详细评审意见单行压缩竖排修复」后，收起态内容利用效率的二次提升；与「双侧栏同时收起空白修复」一起形成完整的收起态闭环。

## 2026-09-02

### 1. 左右边框栏同时收起时中间区域留白修复
- **改动文件**：`web/styles.css`
- **需求**：左右边框栏都收起时，中间区域应铺满全屏，而不是右侧出现一片空白。
- **根因**：`.app` 是三列网格 `272px minmax(0,1fr) 280px`（左栏/中间/右栏）。左收起规则 `.app.has-research.sidebar-collapsed`（3 个类）优先级高于右收起规则 `.app.feedback-collapsed`（1 个类），因此两者同时存在时，只有左收起规则生效，网格为 `0 minmax(0,1fr) 280px`——右栏仍保留 280px 但面板被隐藏（`visibility:hidden`），中间右侧留下一片空白。
- **改动**：在 `styles.css` 第 18 行左收起规则后新增组合规则：
  ```css
  .app.has-research.sidebar-collapsed.feedback-collapsed{grid-template-columns:0 minmax(0,1fr) 0}
  .app.has-research.sidebar-collapsed.feedback-collapsed .topbar{grid-column:2 / 3}
  ```
  该选择器（4 个类）优先级高于两个单边收起规则，左右同时收起时三列均归零，中间区域自动铺满；并同步把顶栏从默认跨列 `2 / 4` 收窄为 `2 / 3`。网格自带 `transition:grid-template-columns .22s`，收起动画平滑。

### 2. 首页隐藏「返回首页」和「反馈」按钮
- **改动文件**：`web/styles.css`

- **需求**：右上角「返回首页」(`#homeBtn`) 和「反馈」(`#feedbackToggle`) 图标仅在研究项目开始后显示，在首页不显示。

- **改动**：在 `styles.css` 第 106 行已有规则 `.app:not(.has-research) .danger-btn{display:none}` 之后，新增 `.app:not(.has-research) .home-btn,.app:not(.has-research) .fb-toggle-btn{display:none}`。

- **原理**：应用通过 `.app` 元素的 `has-research` CSS 类区分首页与研究中状态（`setWorkspaceMode(true/false)` 切换）。首页时无此类，CSS 选择器匹配并隐藏两个按钮；研究开始后添加此类，按钮自动显示。与已有的 `.danger-btn`（取消按钮）隐藏逻辑完全一致。

### 2. 首页固定展开侧栏 + 移除收起按钮
- **改动文件**：`web/styles.css`、`web/index.html`
- **需求**：首页（未开始研究）不需要收起历史档案栏的能力，侧栏恒为展开；研究工作区保持可收起。
- **改动**：
  1. `styles.css:18` 两条收起规则的选择器由 `.app.sidebar-collapsed` 收窄为 `.app.has-research.sidebar-collapsed`，使 `sidebar-collapsed` 类在首页成为空操作。
  2. `styles.css:106` 在已有的首页隐藏按钮规则里追加 `.app:not(.has-research) .sidebar-toggle{display:none}`。
  3. `index.html:9` 样式表版本号 `?v=20260901-fb-preview` → `?v=20260902-home-sidebar`，避免沿用旧缓存。
- **原理**：`sidebar-collapsed` 状态记在 `localStorage`（`ai_scientist.sidebar.collapsed.v1`），首页与工作区共用同一份。若只在首页藏掉按钮，用户从「已收起」的工作区返回首页时会留下 272px 空白条且没有按钮能恢复。因此改在 CSS 层把「收起」限定到 `.has-research`：首页无论类名如何都渲染完整侧栏，`localStorage` 与工作区切换逻辑都不动，`#sidebarToggle` 元素也保留（`app.js:161` 依赖它存在，删 DOM 会让 `init()` 抛错）。
- **验证**：1700px 桌面视口实测四种状态 —— 首页 `第一列=272px / .left visible / 按钮 display:none`；首页强加 `sidebar-collapsed` 仍为 `272px / visible`；工作区点按钮 → `0px / hidden`，再点 → `272px / visible`。

## 2026-09-01

### 1. 三级模型分离（`.env` 新增 `QWEN_MODEL_CRITIC`）

- **改动文件**：`.env`、`.env.example`、`src/agents/agent_critic.py`、`README.md`

- **改动**：在 `QWEN_MODEL` / `QWEN_MODEL_SCIENTIST` 之外，新增 `QWEN_MODEL_CRITIC` 供 Critic 独立选型（`agent_critic.py` 用 `QWEN_MODEL_CRITIC or QWEN_MODEL` 回退链）。

- **当前配置**：

  | 变量                     | 值               | 用途                              |
  | ---------------------- | --------------- | ------------------------------- |
  | `QWEN_MODEL`           | `qwen3.8-flash` | Explorer / Orchestrator / 检索词翻译 |
  | `QWEN_MODEL_SCIENTIST` | `qwen3.7-plus`  | Scientist 假设生成（提速，可升回 max）      |
  | `QWEN_MODEL_CRITIC`    | `qwen3.7-flash` | Critic 结构化评分（提速档，可换回 plus）      |
  | `QWEN_VL_MODEL`        | `qwen3.8-flash` | 视觉理解                            |

- **约束**：三个 Agent 都走 `with_structured_output()`，须用支持 JSON Schema 的模型（仅 Qwen3.7/3.8 系列）；`qwen3.6-plus`/`qwen3.5-plus` 仅 JSON Object 模式。

### 2. 视觉模型迁移：弃用 `qwen-vl-max` → `qwen3.8-flash`

- **改动文件**：`.env`、`.env.example`、`src/agents/agent_explorer.py`、`src/agents/agent_scientist.py`、`src/services/paper_search_service.py`、`README.md`

- **背景**：官方已将 `qwen-vl-max`/`qwen-vl-plus` 标记为旧版并逐步弃用，推荐迁移到原生多模态 Qwen3.x 系列。

- **改动**：`QWEN_VL_MODEL=qwen3.8-flash`，并把 4 处硬编码兜底默认值 `qwen-vl-max` 一并更新。

- **验证**：视觉 + 结构化输出组合实测通过（正确识图、返回规范 JSON）。

### 3. 修复「建议问题悬浮提示不显示」

- **改动文件**：`src/agents/agent_orchestrator.py`（`_get_suggest_llm`）

- **问题**：建议生成改用 `qwen3.8-flash`（思考模型）后，`max_tokens=512` 被 reasoning token 全部吃光，`content=''`，JSON 解析失败 → 前端拿不到 `questions` → 清空提示框。实测：长上下文下 `output_token_details={'reasoning':512}`、`content=''`。

- **修复**：`_get_suggest_llm` 加 `extra_body={"enable_thinking": False}`（轻量任务关闭思考），并把 `max_tokens` 512→2048、`timeout` 30→60 作余量兜底。

- **验证**：真实 `suggest_questions()` + V3 快照长上下文，1.5s 返回 3 条规范问题（`dim` 为 deep\_dive/method/cross\_domain），`error=None`。

- **注意**：不要用 `.bind(extra_body=...)` 方式传 `enable_thinking`——实测该路径思考未被可靠关闭（14.6s，逼近前端 12s 超时），须放在构造器里。

### 4. 三个 Agent `max_tokens` 4096 → 16384（避免截断重试）

- **改动文件**：`src/agents/agent_explorer.py`（2 处）、`src/agents/agent_scientist.py`（4 处）、`src/agents/agent_critic.py`（1 处）

- **背景**：换用 Qwen3.x 思考模型后，reasoning token 计入 `max_tokens`。4096 预算下，长输出（Scientist 多条假设+三级计划、Critic 五维+反事实三检验大 JSON）易被 reasoning 挤占导致正文截断 → `with_structured_output` 解析失败 → 降级纯文本再失败 → 触发整轮重试，单次耗时翻倍。

- **改动**：7 处 `max_tokens=4096` 统一提到 `16384`（实测三模型均接受 32768，留足余量）。`timeout` 保持 180s。

- **附带实测**：Critic 从 `qwen3.7-plus` 换 `qwen3.7-flash` 仅提速约 15%（39.9s→34.1s），且评分口径变宽松（evidence 3→7）；真正瓶颈是 Scientist 的 `qwen3.8-max`（单轮 6 分钟级），非 Critic。

### 5. Scientist 降档：`qwen3.8-max` → `qwen3.7-plus`

- **改动文件**：`.env`、`.env.example`、`README.md`

- **背景**：Scientist 是 pipeline 最慢环节（max 单轮 6 分钟级）。

- **实测对比**（真实 `ScientistOutput` 结构化输出，各 1 次）：`qwen3.7-plus` 38.3s 通过校验；`qwen3.8-max` 142.1s 且因 `L2_quantitative` 缺数值阈值被 validator 拒绝。plus 快约 3.7 倍且这轮更稳。

- **回退**：若假设质量不足，改回 `QWEN_MODEL_SCIENTIST=qwen3.8-max` 即可（无需动代码）。

### 6. 修复「知识缺口显示 `! ,`」

- **改动文件**：`src/models/schemas.py`（`ExplorerOutput` 新增 `knowledge_gaps` 校验器）

- **诊断**：**非前端渲染失败**。前端 `renderExplorer` 的 `gaps.map(...)` 忠实渲染，`!` 恒为图标 `gap-ico`，后面的 `,` 是 `esc(g)` 的条目内容。查 V3 快照 `agent_explorer.knowledge_gaps` 原始值为 `["", ""]`（单条、值为逗号分隔符 `", "`），V1/V2/V3 三轮一致。

- **根因**：Explorer 文本模型 `qwen3.8-flash` 结构化输出数组纪律弱，在「无明显缺口」时未返回空列表，而是吐出用逗号拼接的空占位项。

- **修复**：`ExplorerOutput.knowledge_gaps` 加 `mode="before"` 校验器，过滤掉不含字母/数字/中文的退化条目（`","`、空白、纯标点）；全空时前端自然回落到「暂无识别到知识缺口」空状态。

- **注意**：仅对**新 run** 生效；已有 V3 快照仍存旧脏数据，需重跑该轮才会刷新。

### 7. 修复「双击 `start.bat` 打不开前端页面」

- **改动文件**：`start.bat`、`scripts/_boot_runner.py`、`.gitattributes`（新增）

- **诊断**：`start.bat` 首字节为 `EF BB BF`（UTF-8 BOM），且全文件为**纯 LF 行尾**（`git ls-files --eol` → `i/lf w/lf`，仓库无 `.gitattributes`）。cmd.exe 的批处理解析器只保证 CRLF：BOM 让首行 `@echo off` 变成非法命令，纯 LF 会让 `^` 续行（原第 56-57 行的 PowerShell 健康检查）和多行 `( )` 块静默失效。旁证：全项目找不到 `data/boot.log`，说明执行流从未真正走到启动服务那一步。

- **次因**：① 脚本 `set "AUTO_OPEN_BROWSER=0"` 被子进程继承，关掉了 `main.py:_open_browser` 的自启浏览器，于是「打开前端」完全依赖那一次 45 秒健康检查——而首次启动的知识库初始化自身就要 10-30 秒，极易超时。② 原 `_boot_runner.py` 用 `subprocess.run(stdout=PIPE)`，只在子进程退出后才一次性吐字，常驻服务全程空白，崩溃也拿不到 Traceback。③ 自重启分支的 `"""%_BAT%"""` 前后引号不对称。

- **修复**：

  1. `start.bat` 重写为 **ASCII + 无 BOM + CRLF**；健康检查改为**单行** PowerShell（不再依赖 `^` 续行），超时 45s → **120s**；启动前先探测 `import fastapi, uvicorn`，环境坏了直接报错退出而不是静默超时；**无论健康检查成败都执行** **`start "" <URL>`**（失败时额外打印 boot.log 尾部 40 行）；自重启与服务窗口改用 `cmd /K call "<path>"` 形式，去掉易碎的嵌套引号；`/D "%~dp0."` 避免尾部反斜杠吃掉引号。
  2. `_boot_runner.py` 改为 `Popen` + **逐行流式**双写（控制台 + boot.log），并处理 Ctrl+C 时终止子进程；docstring 改原始串消除 `SyntaxWarning`。
  3. 新增 `.gitattributes`：`*.bat/*.cmd/*.ps1 → eol=crlf`、`*.sh → eol=lf`，防止以后被编辑器或 `core.autocrlf=true` 再次写成 LF。

- **验证**：已确证 `start.bat` 无 BOM / 全 CRLF / 纯 ASCII；`_boot_runner.py` `py_compile` 通过；PowerShell 探测命令在 Windows PowerShell 5.1 下解析执行正常（服务未起时按预期返回 1）。**双击端到端流程未实测**（该执行命令被权限层拦截），需用户本人双击确认。

### 8. 回归修复：双击弹出两个前端页 + 服务日志中文乱码

- **改动文件**：`start.bat`、`scripts/_boot_runner.py`

- **现象**：双击后浏览器出现两个完全相同的 `127.0.0.1:8848/static/index.html` 标签页；服务窗口日志里中文显示为 `◇◇◇W◇◇◇1715`。

- **根因 1（双开）**：第 7 条重写 `start.bat` 时漏掉了原有的 `set "AUTO_OPEN_BROWSER=0"`。该变量本应通过环境继承传给服务窗口，用来关掉 `src/main.py:_open_browser()`（`main.py:510` 的 `webbrowser.open`）；缺了它，服务端与脚本各开一次页。`load_dotenv()`（`main.py:48`）未传 `override=True`，所以脚本里 `set` 的值优先于 `.env`，即使 `.env` 写了 `AUTO_OPEN_BROWSER=1` 也不会复活双开。

- **修复 1**：配置区恢复 `set "AUTO_OPEN_BROWSER=0"`，开页职责单一化——只由 `start.bat` 打开一次。

- **根因 2（乱码）**：子进程的 stdout 被 runner 用管道接管，中文 Windows 下 Python 对管道按 ANSI 代码页（cp936）编码日志，而 `_boot_runner.py` 固定 `decode("utf-8", errors="replace")` → 中文字节被替换成 U+FFFD。

- **修复 2**：给子进程显式注入 `PYTHONIOENCODING=utf-8`（`env=dict(os.environ, ...)`），让它按 UTF-8 吐字，与 runner 的解码一致；runner 自身写控制台仍按控制台代码页编码，服务窗口显示正常。

- **根因 3（行距翻倍）**：子进程文本层已把 `\n` 转成 `\r\n`，`log_fp` 又以默认 `newline=None` 打开，写 `\n` 再转一次 → 落盘 `\r\r\n`。

- **修复 3**：`log_fp` 改为 `newline="\n"`，并在流式循环里把行尾 `\r\n` 归一为 `\n`。

- **验证**：临时子进程打印中文经 runner 落盘，日志字节断言得到 `ENC=utf-8`、`ZS=\u77e5\u8bc6\u5df2\u5c31\u7eea`（即"知识已就绪"，合法 UTF-8）、`has_cr_cr_lf=False`、全文件纯 LF；`start.bat` 复查仍为无 BOM / 全 CRLF / 纯 ASCII。双开一项因无法执行 `start.bat` 未做运行时验证，按代码路径推定。

***

## 2026-08-27

### 1. 证据列表：由「固定配额」改回「纯 Top-3」

- **改动文件**：`src/agents/agent_explorer.py`

- **背景**：上一版为满足"3 个 OpenAlex + 1 个 arXiv"的展示要求，在 `_hybrid_retrieve` 里写死三桶配额（`n_arxiv_target=1, n_openalex_target=top_k-1`），`explore` 默认 `top_k=4`。

- **现状（本轮）**：

  - `explore(top_k=3)`：默认证据条数由 4 → **3**。

  - `_hybrid_retrieve(chroma, question, top_k=3)`：**去掉 openalex\_target 的强制配额**。

  - 组合策略改为：若候选池存在 arXiv 文献则优先纳入 **至少 1 条（非强制兜底）**，剩余名额按「OpenAlex + 其他」合并后的相似度顺序追加，直到填满 `top_k`；返回总数 ≤ `top_k`。

- **日志**：保留 `证据来源构成: arXiv=?, OpenAlex=?, 其他=?（共 N 条）` 便于验证 N=3。

### 2. 后端启动可靠性修复：`_free_port` 崩溃

- **改动文件**：`src/main.py`（`_free_port` 函数）

- **问题**：`subprocess.run(["netstat","-ano"], text=True)` 在中文 Windows 下 stdout 字节非 UTF-8（GBK/头部 BOM），导致解码异常被捕获返回 `None`，随后 `None.splitlines()` 抛 `AttributeError`，服务无法启动。

- **修复**：改为 `capture_output=True`（不指定 `text=True`），对原始 bytes 依次用 `utf-8` → `mbcs` 容错解码（`errors="replace"`），并对 `None`/空作 `""` 兜底，不再阻塞启动。

### 3. 环境变量与新配置项（`.env`）

| 变量                       | 默认                        | 说明                                                                 |
| ------------------------ | ------------------------- | ------------------------------------------------------------------ |
| `QWEN_MODEL`             | `qwen-plus`               | 本地实测 `qwen3.7-plus`（含 reasoning tokens，`max_tokens`/`timeout` 需放大） |
| `QWEN_MODEL_EMBEDDING`   | `qwen3.7-text-embedding`  | 1024 维向量模型                                                         |
| `KEEP_SEARCHED_PAPERS`   | `false`                   | 在线检索（arXiv）入库文献是否保留（`true` 供 125 题全量复用证据）                          |
| `OPENALEX_EMAIL`         | —                         | OpenAlex 礼貌池邮箱                                                     |
| `CHROMA_COLLECTION_NAME` | `ai_scientist_literature` | 向量库 collection                                                     |

### 4. 启动方式（务必遵守）

`start.bat` / 命令行均要求：

```bat
venv\Scripts\python.exe src\main.py   # 必须：项目根目录 + venv python
```

### 5. 中文命中 arXiv 检索（前置会话，保留结论）

- `_translate_to_english` 重写：`sci2025_problems.json` 离线中英对照兜底 + `.env` 私有 endpoint env 化 + 3 次重试 + `timeout=90` + `max_tokens=300`，兼容 `reasoning_content`。

### 6. Token / 时间量级参考（125 题全量）

- 单题约 **40\~50k** 输入 token + **26\~27k** 输出（含 reasoning）。

- 125 题总量约 **8\~10M token**；串行约 **11.5h**，并发度 2 约 5\~6h。

- 显著降本手段（未落地，按需评估）：`MAX_ITERATIONS 3→1`（−60~~65%）、换非推理模型（−30~~40%）、缩 evidence 条数 + quick 粒度（−15~~20%）、关闭~~ ~~`auto_search_papers`（−5~~10%）。

***

## 2026-08-31

### 1. V2/V3 迭代复用 V1 Explorer 检索结果

- **改动文件**：`src/agents/agent_orchestrator.py`

- **背景**：V1→V2→V3 迭代时，Explorer 每轮重新检索导致证据集漂移，综合得分逐轮下降。

- **改动**：

  - `run_full_pipeline` 新增 `prev_explorer_output` 变量，从上一轮快照中读取 `agent_explorer` 输出。

  - V2/V3 的 Step 1 直接构造 `ExplorerOutput(**prev_explorer_output)`，跳过 `explore()` 调用。

  - 仅 V1（无上一轮快照时）执行实际检索。

- **效果**：迭代轮次间证据集保持一致，消除因检索漂移导致的分数退化。

### 2. Scientist 迭代时强制锚定已有证据

- **改动文件**：`src/agents/agent_scientist.py`

- **背景**：即使证据集固定，Scientist 在迭代中仍可能脱离已有证据、凭空引入新文献，导致评审扣分。

- **改动**：

  - SYSTEM\_PROMPT 新增第 4 条核心约束「证据锚定原则」：`source` 字段必须引用提供的证据来源之一。

  - 新增 `iteration_anchor` 提示段（仅在迭代 + 有证据列表时注入），以最高优先级列出可用证据来源，禁止引入未提供的新文献。

  - 跨域类比推测须在 source 中标注"基于类比推测"。

- **效果**：迭代生成的假设严格扎根于固定证据集，减少因"虚构文献"导致的 evidence 维度扣分。

### 3. Critic 迭代评分改为关注相对改进

- **改动文件**：`src/agents/agent_critic.py`

- **背景**：Critic 在 V2/V3 仍以绝对标准打分，未考虑 Scientist 已针对上轮缺陷做了改进，导致分数不升反降。

- **改动**：

  - 计算上轮均分 `prev_total` 和最弱两个维度 `weak_dims`，注入迭代上下文。

  - 用 5 条「评分原则（最高优先级）」替换原有的简单验证指令：

    1. 关注相对改进而非绝对分数
    2. 保护已有优势维度（≥8 分降幅不超过 1.5）
    3. 聚焦薄弱维度突破
    4. 避免矫枉过正惩罚（合理权衡不视为退步）
    5. 评分锚定：各维度差值应在 \[-2, +3] 范围内

- **效果**：Critic 评分更能反映迭代的实际进步，避免因绝对标准过严导致分数逐轮递减。

### 4. 图片预览选择器修复与提交时机优化

- **改动文件**：`web/app.js`、`web/index.html`、`src/main.py`

- **问题背景**：用户反馈在 V2/V3 迭代提交反馈时，粘贴截图并输入文本后点击提交，文本消失了但图片仍留在输入框中。

#### 问题 1：图片预览从未渲染（根本原因）

- **现象**：图片预览区域始终为空，清除操作无效。

- **原因**：`renderImagePreviews` 函数中 `$(containerId)` 使用了 `document.querySelector`，需要 CSS 选择器格式（如 `#composerImagePreview`），但调用时传入的是纯 ID 字符串（如 `"composerImagePreview"`）。`querySelector('composerImagePreview')` 会查找 `<composerImagePreview>` 标签（不存在），而非 `#composerImagePreview` 元素。

- **影响**：图片预览从未被渲染；清除操作调用 `box.innerHTML = ""` 时 `box` 为 `null`，直接 return。

- **修复**：

```javascript
// 修改前（app.js:242）
const box = $(containerId);

// 修改后
const box = document.getElementById(containerId.replace(/^#/, ''));
```

#### 问题 2：修复后出现新报错

- **现象**：修复问题 1 后，页面报错 `Uncaught SyntaxError: Failed to execute 'querySelector' on 'Document': '#composerImagePreview' is not a valid selector.`

- **原因**：`bindImageUpload` 函数调用 `renderImagePreviews` 时，传入的 `previewId` 参数已带 `#` 前缀（如 `"#composerImagePreview"`）。第一次修复使用 `$('#' + containerId)`，导致选择器变成 `##composerImagePreview`（无效选择器）。

- **修复**：使用 `document.getElementById` 并自动去除可能存在的 `#` 前缀，兼容两种调用方式。

#### 问题 3：图片清除时机不当

- **现象**：即使图片预览能正常渲染，提交后图片清除需要等待 `enqueueJob` 的 HTTP 请求完成才执行。对于大图片，请求可能耗时数秒，期间用户看到图片仍在输入框，误以为未提交。

- **原因**：原代码在 `await enqueueJob(...)` **之后**才清除图片和文本。

- **修复**：调整执行顺序——先清空 UI，再发起异步请求；失败时恢复图片和文本：

```javascript
// app.js:1678-1689
try {
  const imgs = composerImages.slice();
  const savedText = text;
  composerImages.length = 0;
  renderImagePreviews(composerImages, "composerImagePreview");
  $("#expertInput").value = "";
  await enqueueJob(question, fromRound, savedText, proj.project_id, imgs);
} catch (e) {
  // 失败时恢复
  composerImages.push(...imgs);
  renderImagePreviews(composerImages, "composerImagePreview");
  $("#expertInput").value = savedText;
  // ... 错误处理
}
```

#### 问题 4：后端缺少图片接收日志

- **现象**：无法从服务器日志确认后端是否收到了图片数据。

- **修复**：在 `/api/feedback` 和 `/api/run` 的入队日志中增加 `images=N` 字段：

```python
# src/main.py
logger.info("已入队迭代任务 %s（%s，%s，images=%d）", job.job_id, job.project_id, round_label, len(request.images) if request.images else 0)
logger.info("已入队任务 %s（%s，%s，images=%d）", job.job_id, job.project_id, round_label, len(request.images) if request.images else 0)
```

#### 测试验证

1. ✅ 图片预览正常渲染（兼容带/不带 `#` 前缀的调用方式）
2. ✅ 提交后图片预览和文本立即清除
3. ✅ 提交失败时图片和文本自动恢复
4. ✅ POST /api/feedback 返回 200，图片数据成功发送到后端
5. ✅ V3 流水线正常执行，综合得分从 6.94 提升到 7.16

## 2026-09-01

### 1. PDF/Markdown 文档上传功能

- **改动文件**：`src/services/document_parser.py`（新建）、`src/main.py`、`src/agents/agent_orchestrator.py`、`src/agents/agent_scientist.py`、`web/app.js`、`web/index.html`、`web/styles.css`

- **功能描述**：支持用户上传 PDF 和 Markdown 文档，后端解析提取文本后注入 Agent prompt，作为证据来源。

#### 新增模块

**后端**：

| 文件                                | 说明                                   |
| --------------------------------- | ------------------------------------ |
| `src/services/document_parser.py` | 文档解析服务，支持 PDF（pypdf）和 Markdown（直接读取） |

**前端**：

| 文件               | 说明                                                                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `web/app.js`     | 添加 `composerDocuments`/`customDocuments` 状态、`renderDocumentPreviews`、`handleDocumentFiles`、`documentsToBase64List`、`_extractClipboardFiles` |
| `web/index.html` | 添加 `#composerDocPreview`/`#customDocPreview` 容器；更新 `accept="image/*,.pdf,.md,.markdown"`                                                    |
| `web/styles.css` | 添加文档预览样式（`.doc-thumb`、`.doc-icon`、`.doc-name`、`.remove-doc`）                                                                                |

#### 数据流

```
用户选择文档 → 前端读取为 base64 → POST /api/feedback {documents: [...]}
→ 后端解析文档提取文本 → 注入 Scientist prompt → Agent 结合文档内容生成假设
```

#### 遇到的问题及解决方法

**问题 1：粘贴文档无效**

- **现象**：从资源管理器复制 PDF 后粘贴到输入框，无反应。

- **原因**：粘贴处理器只调用 `_extractClipboardImages` 提取图片，没有处理文档。

- **修复**：新增 `_extractClipboardFiles` 函数，同时提取图片和文档；更新粘贴处理器调用 `handleFiles`。

**问题 2：文档预览选择器**

- **现象**：与图片预览相同的选择器问题。

- **修复**：复用图片预览的修复方案，使用 `document.getElementById(containerId.replace(/^#/, ''))`。

#### 功能限制

| 限制     | 值                        |
| ------ | ------------------------ |
| 文档大小   | ≤10MB                    |
| 文档数量   | ≤3 个                     |
| 提取文本长度 | ≤50000 字符（超出截断）          |
| 支持格式   | `.pdf`、`.md`、`.markdown` |
| 不支持    | 加密 PDF、扫描版 PDF（无法提取文本）   |

#### 依赖说明

无需新增依赖，复用已有的 `pypdf` 库（requirements.txt 第 51 行）。详见 `experiment.txt` 文件。

#### 测试验证

1. ✅ 文档预览正常渲染（显示文件名和删除按钮）
2. ✅ 点击上传按钮可选择文档
3. ✅ 拖拽文档到输入框可添加
4. ✅ 粘贴文档可添加
5. ✅ 提交后文档预览立即清除
6. ✅ 提交失败时文档自动恢复

