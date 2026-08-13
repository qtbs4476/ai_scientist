# AI Scientist Mock Fullstack

### 1. 三重审查详情做深

每个审查不只是“通过 / 不通过”，会返回结构化详情：

- 审查状态
- 审查评分
- 审查结论
- 审查标准
- 每个标准的通过情况
- 发现的问题
- 问题严重程度
- 问题依据
- 修改建议
- 审查证据

前端点击“查看详细审查”即可在右侧抽屉查看。

### 2. 自动最多 3 轮，失败后强制人工介入

系统不会无限循环，也不会为了“过审”自动降低标准。

流程：

```text
第1轮审查
→ 失败
→ 自动修订

第2轮审查
→ 失败
→ 自动修订

第3轮审查
→ 仍失败
→ 停止自动修订
→ 进入“需要人工介入”
→ 专家在聊天框输入意见
→ 判断影响哪些审查
→ 重新执行相关审查
```

为了方便演示：

- **Science125 #13**：演示自动修订后通过
- **Science125 #27**：演示 3 轮自动审查仍失败，然后要求人工介入

### 3. SQLite 真持久化历史研究

新增：

```text
src/db.py
data/ai_scientist.db   # 第一次启动后自动生成
```

研究记录会保存到 SQLite。

这意味着：

- 关闭浏览器不丢
- 停止 FastAPI 再启动也不丢
- 左侧“历史研究”来自数据库
- 人工意见、审查状态、假设、最终结果都会持久化

不再依赖 Python 内存字典保存历史。

## 其他能力

- GPT 式研究工作台
- Science125 问题搜索 / 选择
- SSE 流式科研过程
- 候选假设
- 三重科学审查
- 自动修订
- 人工随时介入
- 最终综合结论
- 完整科研报告
- Markdown 下载
- 浏览器打印 / 保存 PDF
- 停止研究
- 左中右独立滚动

## 启动

Windows：双击 `start.bat`

Linux / macOS：

```bash
chmod +x start.sh
./start.sh
```

打开浏览器访问：

```text
http://127.0.0.1:8899
```

首次启动会自动创建 `.venv` 虚拟环境并安装 `requirements.txt` 中的依赖。

## 目录

```text
ai_scientist/
├─ src/                  # 后端（FastAPI + Mock 引擎）
│  ├─ __init__.py
│  ├─ app.py
│  ├─ db.py
│  └─ mock_engine.py
├─ web/                  # 前端
│  ├─ index.html
│  ├─ styles.css
│  ├─ app.js
│  ├─ report.html
│  ├─ report.css
│  ├─ report.js
│  └─ vendor/gsap.min.js
├─ data/
│  └─ science_125.json   # ai_scientist.db 首次启动生成（gitignore）
├─ docs/
│  └─ API.md             # 前后端数据契约
├─ outputs/              # 报告产物输出目录
├─ requirements.txt
├─ start.bat
├─ start.sh
├─ .gitignore
└─ README.md
```

## 后端真实替换时建议保持的结构

完整的前后端数据契约（REST 接口、SSE 事件、数据结构、HTTP 头 / CORS）见 **[API.md](docs/API.md)**。

真实 Agent 只需严格按 `API.md` 产出数据、保持字段名 / 枚举值 / 嵌套结构不变，前端无需重写，只替换 Mock 引擎即可。
