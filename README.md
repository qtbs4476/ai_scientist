# AI Scientist

基于 Qwen 与多智能体协作的科学假设生成和迭代评审系统。

用户输入一个科学问题后，系统会依次完成文献证据检索、候选假设生成、可证伪实验设计和五维质量评审，并允许研究者通过专家反馈继续生成 V2、V3 迭代版本。

## 核心能力

- **多智能体研究流水线**：Explorer、Scientist、Critic 分工协作。
- **检索增强生成**：使用 Chroma 向量库检索本地科学文献和种子知识；默认给出一条文献按相似度取 **Top-3** 证据（含至少 1 条 arXiv 在线文献），不再强制限定 OpenAlex/arXiv 来源比例。
- **科学问题集支持**：内置《Science 125 题》中英对照库与 OpenAlex 离线预采集（593 篇/1337 chunks），中文问题可离线命中再回退 LLM 翻译，确保能命中 arXiv 在线检索。
- **可验证假设生成**：输出假设陈述、推论逻辑、可证伪条件及 L1/L2/L3 研究计划。
- **五维质量评审**：从证据、可证伪性、理论一致性、新颖度和跨域适配度进行评分。
- **人在回路迭代**：专家反馈可触发 V1 → V2 → V3 全链路重新研究。
- **后台任务管理**：支持排队、进度轮询、取消、失败重试和刷新恢复。
- **研究档案与报告**：按项目保存历史轮次，提供趋势图表、完整报告和 Markdown 下载。
- **开箱即用存储**：默认使用 SQLite，可选 MySQL；知识库默认使用本地 Chroma。

## 系统流程

```text
科学问题
   │
   ▼
Explorer ── 文献检索、证据整理、知识缺口、跨域类比
   │
   ▼
Scientist ── 候选假设、可证伪条件、三级研究计划
   │
   ▼
Critic ── 五维评分、致命缺陷、反事实攻击、缺失证据
   │
   ▼
研究快照 V1 ── 专家反馈 ── V2 ── 专家反馈 ── V3
```

## 技术栈

| 层级 | 技术 |
|---|---|
| 大模型 | 阿里云百炼 DashScope、Qwen |
| 智能体 | LangChain、LangGraph、Pydantic |
| 后端 | FastAPI、Uvicorn |
| 向量检索 | ChromaDB、DashScope Embedding |
| 数据存储 | SQLite（默认）/ MySQL、SQLAlchemy |
| 前端 | 原生 HTML、CSS、JavaScript、ECharts、GSAP |

## 快速开始

### 1. 获取代码

```bash
git clone https://github.com/qtbs4476/ai_scientist.git
cd ai_scientist
```

### 2. 创建虚拟环境

推荐使用 Python 3.11–3.13。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux / macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

在项目根目录创建 `.env`：

```dotenv
# 阿里云百炼
DASHSCOPE_API_KEY=your_dashscope_api_key
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus   # 建议 qwen-plus；当前本地 .env 实测用 qwen3.7-plus

# 向量模型；可按百炼账号可用模型调整
QWEN_MODEL_EMBEDDING=qwen3.7-text-embedding
DASHSCOPE_API_KEY_EMBEDDING=

# 服务
PORT=8848
AUTO_OPEN_BROWSER=1

# 本地向量库
CHROMA_DB_PATH=./data/chroma_db
CHROMA_COLLECTION_NAME=ai_scientist_literature

# 在线检索文献保留开关：true 保留（供 125 题全量复用证据），false 精确清理本次临时文献
KEEP_SEARCHED_PAPERS=false

# OpenAlex 礼貌池邮箱（离线采集 X-Token/mailto，可选）
OPENALEX_EMAIL=

# 默认无需配置，系统会使用 SQLite
# DATABASE_URL=sqlite:///data/ai_scientist.db
```

> 不要将包含真实 API Key 的 `.env` 提交到 GitHub。

### 4. 启动

Windows 用户可以直接双击：

```text
start.bat
```

脚本会结束占用 `8848` 端口的旧进程、启动服务，等待页面可访问后自动打开浏览器。

也可以手动启动（**必须用项目 venv 内的 python，并从项目根目录运行**，否则会因缺少 `langchain_chroma` 等依赖或找不到 `src.main` 而失败）：

```bash
venv\Scripts\python.exe src\main.py
```

然后访问：

```text
http://127.0.0.1:8848/static/index.html
```

首次启动且已配置 DashScope API Key 时，如果 Chroma 知识库为空，系统会自动写入内置种子文献。

## 使用方式

1. 点击“新建研究”，选择示例问题或输入自定义科学问题。
2. 等待 Explorer、Scientist、Critic 流水线完成。
3. 查看证据、候选假设、实验计划、五维评分和迭代图表。
4. 在底部输入专家意见，生成下一轮研究结果。
5. 最多迭代至 V3，可随时查看历史轮次或下载 Markdown 报告。

研究任务在后台执行。切换项目或返回首页不会中断任务；需要终止时使用顶部“取消”按钮。

## 配置说明

| 环境变量 | 必填 | 默认值 | 说明 |
|---|---:|---|---|
| `DASHSCOPE_API_KEY` | 是 | — | 阿里云百炼 API Key |
| `DASHSCOPE_API_BASE` | 否 | 百炼兼容接口 | OpenAI 兼容 API 地址 |
| `QWEN_MODEL` | 否 | `qwen-plus` | Explorer、Scientist、Critic 使用的模型（本地实测 `qwen3.7-plus`） |
| `QWEN_MODEL_EMBEDDING` | 否 | 项目配置值 | Chroma 文档向量模型（`qwen3.7-text-embedding`，1024 维） |
| `DASHSCOPE_API_KEY_EMBEDDING` | 否 | 主 API Key | 独立的 Embedding API Key |
| `PORT` | 否 | `8848` | Web 服务端口 |
| `AUTO_OPEN_BROWSER` | 否 | `1` | 启动后是否自动打开浏览器 |
| `CHROMA_DB_PATH` | 否 | `./data/chroma_db` | Chroma 持久化目录 |
| `CHROMA_COLLECTION_NAME` | 否 | `ai_scientist_literature` | Chroma collection 名称 |
| `KEEP_SEARCHED_PAPERS` | 否 | `false` | 在线检索（arXiv）入库文献跑完后是否保留在向量库 |
| `OPENALEX_EMAIL` | 否 | — | 离线 OpenAlex 采集礼貌池邮箱（提升 QPS） |
| `DATABASE_URL` | 否 | SQLite | SQLAlchemy 数据库连接地址 |

如需使用 MySQL，可以配置 `DATABASE_URL`，或提供以下变量：

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=ai_scientist
```

## API

服务启动后可访问 FastAPI 接口。核心端点如下：

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 服务和模型配置健康检查 |
| `POST` | `/api/run` | 创建 V1 研究任务 |
| `POST` | `/api/feedback` | 提交专家反馈并生成下一轮 |
| `GET` | `/api/job/{job_id}` | 查询任务状态和真实执行阶段 |
| `POST` | `/api/job/{job_id}/cancel` | 请求取消任务 |
| `GET` | `/api/jobs` | 获取活动任务列表 |
| `GET` | `/api/snapshots` | 获取研究快照，可按 `project_id` 过滤 |
| `GET` | `/api/chart/overall` | 综合得分趋势 |
| `GET` | `/api/chart/radar` | 五维评分对比 |
| `GET` | `/api/chart/granularity` | 研究计划颗粒度 |
| `GET` | `/api/chart/waterfall` | 缺陷修复瀑布图 |
| `GET` | `/api/chart/risk` | 反事实风险趋势 |

示例：

```bash
curl -X POST http://127.0.0.1:8848/api/run \
  -H "Content-Type: application/json" \
  -d '{"question":"如何从观测数据中稳健识别因果效应？","initial_round":"V1"}'
```

## 项目结构

```text
ai_scientist/
├─ src/
│  ├─ agents/                 # Explorer、Scientist、Critic 与流水线编排
│  ├─ config/                 # 内置种子文献和配置
│  ├─ models/                 # Pydantic 模型与数据库模型
│  ├─ services/               # 后台任务管理、Chroma 服务
│  ├─ utils/                  # 校验与结构化输出回退解析
│  └─ main.py                 # FastAPI 服务入口
├─ web/                       # 原生前端、报告页、ECharts/GSAP
├─ tests/                     # 离线测试
├─ scripts/                   # 数据库和知识库初始化脚本
├─ docs/                      # 架构与接口文档
├─ snapshots/                 # 研究快照文件
├─ data/                      # SQLite 与 Chroma 运行数据
├─ start.bat                  # Windows 一键启动
└─ requirements.txt
```

## 数据与运行文件

- `data/`、`snapshots/` 和 `outputs/` 可能包含运行时生成的数据。
- 正式部署前建议根据数据保留策略配置备份、清理和 `.gitignore`。
- SQLite 的 `-wal`、`-shm` 文件属于运行期文件，不应作为长期数据备份。

## 测试

安装测试依赖后运行：

```bash
python -m pytest -q
```

也可以运行无需 API Key 的结构化输出回退测试：

```bash
python -m tests.test_fallback_parser
```

## 相关文档

- [项目完整设计文档](docs/ProjectStructure.md)
- [前端与 API 运行规范](docs/frontend_api_run_spec.md)
- [脚本说明](scripts/README.md)

## 注意事项

- 大模型生成内容可能存在事实或引用偏差，研究结果必须由领域专家复核。
- 系统用于辅助提出和评估研究假设，不应替代实验验证、同行评议或正式科研决策。
- 首次运行会调用模型和 Embedding API，可能产生相应的云服务费用。
