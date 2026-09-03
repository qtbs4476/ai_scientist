# 前端对接 `/api/run` 接口需求文档

> **文档版本**：v1.0
> **创建日期**：2026-08-15
> **后端服务**：FastAPI（`http://127.0.0.1:8000`）
> **适用前端**：React 18 + Ant Design 5 + axios + echarts-for-react
> **状态**：后端已全部测试通过，可进入前端开发

---

## 目录

- [1. 接口概览](#1-接口概览)
- [2. 请求规范](#2-请求规范)
- [3. 响应规范](#3-响应规范)
- [4. 状态机与轮次管理](#4-状态机与轮次管理)
- [5. 前端页面结构](#5-前端页面结构)
- [6. 数据展示规范](#6-数据展示规范)
- [7. 错误处理](#7-错误处理)
- [8. 性能与超时](#8-性能与超时)
- [9. 开发与调试](#9-开发与调试)
- [10. TypeScript 类型定义](#10-typescript-类型定义)
- [附录 A：完整响应示例](#附录-a完整响应示例)
- [附录 B：字段校验规则](#附录-b字段校验规则)

---

## 1. 接口概览

### 1.1 接口列表

| 接口 | 方法 | 用途 | 耗时预期 |
|------|------|------|---------|
| `/api/run` | POST | 首次运行 / 带反馈迭代 | 90-180 秒 |
| `/api/feedback` | POST | 提交专家反馈触发迭代（与 run + feedback 等价） | 90-180 秒 |
| `/api/snapshots` | GET | 获取所有版本快照列表 | <1s |
| `/api/snapshot/{round}` | GET | 获取指定版本快照 | <1s |
| `/api/chart/overall` | GET | 综合得分折线图 | <1s |
| `/api/chart/radar` | GET | 5 维雷达图 | <1s |
| `/api/chart/granularity` | GET | L1/L2/L3 颗粒度堆叠图 | <1s |
| `/api/chart/waterfall` | GET | 缺陷修复瀑布图 | <1s |
| `/api/chart/risk` | GET | 反事实风险收敛图 | <1s |
| `/api/health` | GET | 健康检查 | <1s |

### 1.2 基础配置

```
BASE_URL = http://127.0.0.1:8000
所有接口均为 JSON 格式
CORS 已开放（allow_origins=["*"]）
无需认证（无 Token / Cookie）
```

---

## 2. 请求规范

### 2.1 首次运行（V1 生成）

**接口**：`POST /api/run`

**请求体**：

```json
{
  "question": "人类情绪起源于哪里？",
  "initial_round": "V1",
  "auto_search_papers": false,
  "paper_granularity": "fast"
}
```

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `question` | string | ✅ | 长度 ≥ 5 字符 | 科学问题 |
| `feedback` | string | ❌ | 长度 ≥ 3 字符 | 迭代时填，首次运行不填 |
| `initial_round` | string | ❌ | 默认 `"V1"` | 轮次标签，可选 `V1`/`V2`/`V3` |
| `auto_search_papers` | bool | ❌ | 默认 `false` | 是否在 pipeline 前自动检索 arXiv 文献入库（跑完按 KEEP_SEARCHED_PAPERS 清理） |
| `paper_granularity` | string | ❌ | 默认 `"fast"` | arXiv 入库粒度：`fast`=摘要模式(省 token)、`full`=全文模式(证据更细) |

> ⚠️ **首次运行时不要传 `feedback` 字段**（或传 `null`），否则会触发迭代逻辑而非首次生成。

### 2.2 带反馈迭代（V1→V2 / V2→V3）

**方式 A**：通过 `/api/run` 传 `feedback`

```json
{
  "question": "关于高温超导材料的研究：如何提升 YBCO 体系的超导转变温度(Tc)？",
  "feedback": "H1 的核心变量 σ(Δ₀) 与 δ 异质性存在因果倒置风险...",
  "initial_round": "V1"
}
```

> `initial_round` 传当前轮次（如 V1），后端会自动生成下一轮（V2）。

**方式 B**：通过 `/api/feedback`

```json
{
  "question": "关于高温超导材料的研究：如何提升 YBCO 体系的超导转变温度(Tc)？",
  "feedback": "H1 的核心变量 σ(Δ₀) 与 δ 异质性存在因果倒置风险...",
  "current_round": "V1"
}
```

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `question` | string | ✅ | 长度 ≥ 5 字符 | 同上 |
| `feedback` | string | ✅ | 长度 ≥ 3 字符 | 专家反馈内容 |
| `current_round` | string | ✅ | 正则 `^V[1-3]$` | 当前轮次 |

> ⚠️ **V3 之后不能继续迭代**：传 `current_round=V3` 会返回 HTTP 400：
> ```json
> { "detail": "已到最大迭代次数 V3，无法继续迭代" }
> ```

---

## 3. 响应规范

### 3.1 成功响应结构

所有接口统一返回：

```typescript
{
  "success": true,
  "data": { /* 业务数据 */ }
}
```

`/api/run` 和 `/api/feedback` 的 `data` 字段为完整快照（Snapshot），结构如下：

```
data
├── round                    当前轮次标签 "V1" | "V2" | "V3"
├── timestamp                ISO 8601 时间戳
├── question                 科学问题原文
├── overall_score            综合得分 (0-10)
├── granularity_score        颗粒度得分
├── granularity_stats        颗粒度统计 { L1, L2, L3 }
├── human_feedback           历史反馈列表
├── agent_explorer           Explorer 输出
├── agent_scientist          Scientist 输出
└── agent_critic             Critic 输出
```

### 3.2 字段详细规范

#### 3.2.1 `agent_explorer`（探索者输出）

```typescript
agent_explorer: {
  problem_skelton: string;         // 问题骨架（底层逻辑结构描述）
  evidence_list: Array<{
    claim: string;                  // 证据陈述
    source: string;                 // 文献来源，如 "Bednorz & Müller, 1986, Z. Phys. B"
    year: string | null;            // 发表年份（可能为 null 或被 LLM 误填为长文本）
  }>;
  knowledge_gaps: string[];         // 知识缺口列表（字符串数组）
  analogies: Array<{
    field: string;                  // 来源学科，如 "统计物理"
    phenomenon: string;             // 类比现象描述
    mapping_relation: string;       // 到当前问题的映射关系
  }>;
}
```

> ⚠️ **数据质量提醒**：`evidence_list[].year` 字段预期是年份字符串（如 `"1986"`），但实测发现 LLM 偶尔会把它填成完整描述性文本。前端展示时建议优先显示 `source` 字段，`year` 仅作辅助。

#### 3.2.2 `agent_scientist`（科学家输出）

```typescript
agent_scientist: {
  hypotheses: Array<{
    id: string;                       // 假设编号 "H1" | "H2" | "H3"
    statement: string;                // 假设完整陈述
    source: string;                   // 基于哪些文献/证据得出
    supporting_reasoning: string;     // 支持该假设的推论逻辑
    falsification_condition: string; // 可证伪条件（≥15 字符）
    plan: {
      L1_conceptual: string;          // 概念级方向
      L2_quantitative: string;        // 量化指标级（必含数值阈值）
      L3_robustness: string;           // 容错级备选方案
    };
    verification_criteria: {
      confirm: string;                // 假设成立需满足的条件
      reject: string;                  // 假设推翻需满足的条件
    };
  }>;
  cross_hypothesis_comparison: string; // 假设间对比分析（≥20 字符）
}
```

#### 3.2.3 `agent_critic`（评审官输出）

```typescript
agent_critic: {
  scores: {
    evidence: number;        // 证据强度 0-10
    falsifiability: number;   // 可证伪性 0-10
    consistency: number;      // 一致性 0-10
    novelty: number;          // 创新性 0-10
    cross_domain: number;     // 跨域程度 0-10
  };
  top_flaw: string;           // 致命缺陷诊断（≥10 字符）
  counterfactual: string;     // 反事实攻击场景（≥15 字符）
  missing_evidences: string[]; // 缺失证据清单
  detailed_review: string;    // 详细评审意见（≥30 字符，Markdown 格式）
}
```

> 💡 `detailed_review` 字段包含 Markdown 格式（含 `###` 标题、`**粗体**` 等），前端应使用 Markdown 渲染器展示。

### 3.3 错误响应结构

```typescript
{
  "detail": "错误描述字符串"
}
```

| HTTP 状态码 | 触发条件 | 示例 detail |
|------------|---------|-------------|
| 400 | V3 之后继续迭代 | `"已到最大迭代次数 V3，无法继续迭代"` |
| 422 | 请求体校验失败 | Pydantic 自动生成的字段错误详情 |
| 404 | 快照不存在 | `"快照 V5 不存在"` |
| 500 | LLM 调用失败 / 内部错误 | `"探索失败: Error code: 400 - ..."` |

---

## 4. 状态机与轮次管理

### 4.1 前端状态机

```
                    ┌──────────────┐
                    │  IDLE（空闲）  │
                    │  无快照数据    │
                    └──────┬───────┘
                           │ 用户提交问题
                           ▼
                    ┌──────────────┐
                    │  LOADING_V1   │
                    │  正在生成 V1   │  ← 显示加载动画（约 90s）
                    └──────┬───────┘
                           │ 返回 success=true
                           ▼
                    ┌──────────────┐
                    │  V1_READY     │
                    │  V1 数据就绪   │  ← 展示 V1 结果
                    └──────┬───────┘
                           │ 用户提交反馈
                           ▼
                    ┌──────────────┐
                    │  LOADING_V2   │
                    │  正在生成 V2   │  ← 显示加载动画（约 120s）
                    └──────┬───────┘
                           │ 返回 success=true
                           ▼
                    ┌──────────────┐
                    │  V2_READY     │
                    │  V2 数据就绪   │
                    └──────┬───────┘
                           │ 用户提交反馈
                           ▼
                    ┌──────────────┐
                    │  LOADING_V3   │
                    │  正在生成 V3   │
                    └──────┬───────┘
                           │ 返回 success=true
                           ▼
                    ┌──────────────┐
                    │  V3_READY     │
                    │  V3 数据就绪   │  ← 隐藏反馈输入框
                    └──────────────┘    （已达最大迭代次数）
```

### 4.2 前端状态变量建议

```typescript
type AppState =
  | { status: 'idle' }
  | { status: 'loading'; round: 'V1' | 'V2' | 'V3' }
  | { status: 'ready'; currentRound: 'V1' | 'V2' | 'V3'; snapshots: Record<string, Snapshot> }
  | { status: 'error'; message: string };
```

### 4.3 轮次切换逻辑

- 用户在左侧迭代面板点击不同版本（V1/V2/V3），右侧主区域切换显示对应版本的快照数据
- 切换版本不发起新请求，从本地 `snapshots` 缓存读取（因为每轮生成时已保存完整快照）
- 当前轮次（最新生成的）高亮显示

---

## 5. 前端页面结构

### 5.1 整体布局

```
┌─────────────────────────────────────────────────────────────┐
│  Header                                                     │
│  [Logo] AI Scientist    [模型: qwen-plus]  [● 服务正常]      │
├─────────────────────────────────────────────────────────────┤
│  Input Area（顶部输入区）                                    │
│  ┌─────────────────────────────────────────────────┐ ┌────┐ │
│  │  科学问题输入框（textarea，≥5字符）              │ │开始│ │
│  │  placeholder="输入你的科学问题..."              │ │研究│ │
│  └─────────────────────────────────────────────────┘ └────┘ │
├──────────────┬──────────────────────────────────────────────┤
│  Sidebar     │  Main Content（右侧主区域）                  │
│  (左侧面板)   │                                              │
│              │  Tabs: [Explorer] [Scientist] [Critic] [图表] │
│  迭代进度    │                                              │
│  ┌────────┐ │  ┌────────────────────────────────────────┐ │
│  │V1 ● 7.0│ │  │                                        │ │
│  │V2 ●7.94│ │  │  当前 Tab 内容（滚动区域）              │ │
│  │V3 ○ 待 │ │  │                                        │ │
│  └────────┘ │  │                                        │ │
│              │  │                                        │ │
│  反馈输入    │  └────────────────────────────────────────┘ │
│  ┌────────┐ │                                              │
│  │textarea│ │                                              │
│  │(≥3字)  │ │                                              │
│  └────────┘ │                                              │
│  [提交反馈] │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

### 5.2 各 Tab 内容详细规范

#### Tab 1: Explorer（探索者）

| 展示项 | 建议组件 | 数据来源 |
|--------|---------|---------|
| 问题骨架 | Card + 段落 | `agent_explorer.problem_skelton` |
| 证据列表 | Table（3 列：claim/source/year） | `agent_explorer.evidence_list[]` |
| 知识缺口 | List（带红色感叹号图标） | `agent_explorer.knowledge_gaps[]` |
| 跨域类比 | Collapse 折叠面板（每条：field/phenomenon/mapping_relation） | `agent_explorer.analogies[]` |

#### Tab 2: Scientist（科学家）

| 展示项 | 建议组件 | 数据来源 |
|--------|---------|---------|
| 假设卡片（2-3 张）| Card 网格布局 | `agent_scientist.hypotheses[]` |
| └ 假设编号 | Tag（H1=蓝/H2=绿/H3=橙） | `hypothesis.id` |
| └ 假设陈述 | Card 标题 | `hypothesis.statement` |
| └ 来源依据 | 小字描述 | `hypothesis.source` |
| └ 支持推论 | Collapse 折叠 | `hypothesis.supporting_reasoning` |
| └ 可证伪条件 | Alert（红色警告样式） | `hypothesis.falsification_condition` |
| └ 三级计划 | Steps 步骤组件（L1→L2→L3） | `hypothesis.plan` |
| └ 验证标准 | 两列卡片（confirm 绿/reject 红） | `hypothesis.verification_criteria` |
| 假设对比 | Card + 段落 | `agent_scientist.cross_hypothesis_comparison` |

#### Tab 3: Critic（评审官）

| 展示项 | 建议组件 | 数据来源 |
|--------|---------|---------|
| 5 维评分 | ECharts 雷达图 + 数值表格 | `agent_critic.scores` |
| 致命缺陷 | Alert（红色，醒目） | `agent_critic.top_flaw` |
| 反事实攻击 | Card（带 "假设场景" 标签） | `agent_critic.counterfactual` |
| 缺失证据 | List（带红色图标） | `agent_critic.missing_evidences[]` |
| 详细评审 | Markdown 渲染器（react-markdown） | `agent_critic.detailed_review` |
| 综合得分 | Statistic 大数字展示 | `overall_score` |

#### Tab 4: 图表（可视化）

| 展示项 | 接口 | 图表类型 | ECharts 配置要点 |
|--------|------|---------|------------------|
| 综合得分趋势 | `/api/chart/overall` | 折线图 | xAxis=轮次, yAxis=得分(0-10) |
| 5 维雷达 | `/api/chart/radar` | 雷达图 | 5 个维度，可叠加多轮对比 |
| 颗粒度堆叠 | `/api/chart/granularity` | 堆叠柱状图 | 三色（L1/L2/L3），xAxis=轮次 |
| 缺陷修复瀑布 | `/api/chart/waterfall` | 瀑布图 | 起点 → 增量 → 终点 |
| 风险收敛 | `/api/chart/risk` | 折线图 | 风险指数随迭代下降 |

---

## 6. 数据展示规范

### 6.1 数值格式化

| 字段 | 格式 | 示例 |
|------|------|------|
| `overall_score` | 保留 2 位小数 | `7.94` |
| `scores.*` | 保留 1 位小数 | `8.2` |
| `granularity_score` | 保留 2 位小数 | `3.33` |
| 时间戳 | `YYYY-MM-DD HH:mm:ss` | `2026-08-15 12:24:51` |

### 6.2 长文本处理

| 字段 | 长度预期 | 处理策略 |
|------|---------|---------|
| `problem_skelton` | 50-200 字 | 直接展示，不截断 |
| `hypothesis.statement` | 100-500 字 | 卡片内完整展示，支持折叠 |
| `detailed_review` | 500-3000 字（含 Markdown） | 必须用 Markdown 渲染器 |
| `falsification_condition` | 50-200 字 | 红色 Alert，完整展示 |
| `counterfactual` | 100-300 字 | 灰色 Card，完整展示 |

### 6.3 空值处理

部分字段可能为空数组或 `null`：

| 字段 | 空值场景 | 展示策略 |
|------|---------|---------|
| `evidence_list` | 知识库为空时 | 显示"未检索到相关文献，仅基于跨域类比" |
| `knowledge_gaps` | 偶尔为空数组 | 显示"暂无识别到知识缺口" |
| `missing_evidences` | 偶尔为空数组 | 显示"暂无缺失证据" |
| `human_feedback` | V1 首次运行时为空数组 | 不展示反馈历史区域 |

---

## 7. 错误处理

### 7.1 前端错误处理矩阵

| 场景 | 检测方式 | 用户提示 | 恢复操作 |
|------|---------|---------|---------|
| 网络断开 | axios catch | "网络连接失败，请检查服务是否启动" | 提供"重试"按钮 |
| 请求超时（>5min） | axios timeout | "请求超时，LLM 处理时间过长" | 提供"重试"按钮 |
| 400 - V3 已到上限 | `response.status === 400` | "已达到最大迭代次数（V3）" | 隐藏反馈输入框 |
| 422 - 字段校验失败 | `response.status === 422` | 展示具体字段错误（来自 detail） | 高亮对应输入框 |
| 500 - LLM 调用失败 | `response.status === 500` | "AI 处理失败：{detail 前 100 字}" | 提供"重试"按钮 |

### 7.2 加载状态处理

```typescript
// 加载期间必须显示：
// 1. 全屏 Spin 加载动画
// 2. 当前正在执行的步骤文字（"Explorer 执行中..." / "Scientist 生成假设中..." / "Critic 评审中..."）
// 3. 预计耗时提示（"预计 1-3 分钟"）
// 4. 取消按钮（可选，但无法真正取消后端请求，仅前端 abort）

// 注意：后端目前不支持 SSE 或 WebSocket，无法实时返回每个 Agent 的进度
// 如需进度反馈，需后端额外开发 SSE 接口（未来增强项）
```

---

## 8. 性能与超时

### 8.1 axios 配置建议

```typescript
const api = axios.create({
  baseURL: 'http://127.0.0.1:8000',
  timeout: 300000, // 5 分钟（V1 生成约 90s，V2 迭代约 120s，留足余量）
  headers: { 'Content-Type': 'application/json' }
});

// 响应拦截器
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.code === 'ECONNABORTED') {
      return Promise.reject(new Error('请求超时，请稍后重试'));
    }
    const detail = error.response?.data?.detail || error.message;
    return Promise.reject(new Error(detail));
  }
);
```

### 8.2 性能优化建议

| 场景 | 优化策略 |
|------|---------|
| 快照数据缓存 | 每轮生成后将快照存入 React state，切换版本不发新请求 |
| 图表数据懒加载 | 图表 Tab 切换时才请求 `/api/chart/*`，首次进入不预加载 |
| 长文本渲染 | `detailed_review` 使用 `React.memo` 包裹 Markdown 渲染器 |
| 请求去重 | 同一轮次的 `/api/run` 请求进行中时禁用提交按钮 |

---

## 9. 开发与调试

### 9.1 开发环境配置

```javascript
// vite.config.js
export default {
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
}
```

### 9.2 后端 Swagger 文档

访问 `http://127.0.0.1:8000/docs` 可查看交互式 API 文档，支持在线测试。

### 9.3 Mock 数据

开发期可使用以下 Mock 数据（基于真实 V1 响应精简）：

```json
{
  "success": true,
  "data": {
    "round": "V1",
    "timestamp": "2026-08-15T12:24:51.000584",
    "question": "如何提升 YBCO 体系的超导转变温度(Tc)？",
    "overall_score": 7.0,
    "granularity_score": 3.33,
    "granularity_stats": { "L1": 3, "L2": 3, "L3": 3 },
    "human_feedback": [],
    "agent_explorer": {
      "problem_skelton": "通过调控微观晶格/电子结构改变载流子浓度与CuO2面量子关联强度，从而优化超导序参量的宏观涌现温度Tc",
      "evidence_list": [
        { "claim": "YBCO的Tc约92K，依赖CuO2面结构完整性与氧含量", "source": "Bednorz & Müller, 1986, Z. Phys. B", "year": "1986" }
      ],
      "knowledge_gaps": ["CuO2面内短程自旋/电荷序与Tc峰值的定量动力学映射关系缺失"],
      "analogies": [
        { "field": "统计物理", "phenomenon": "伊辛模型中的局部自旋相互作用产生宏观磁化相变", "mapping_relation": "CuO2面内局域自旋涨落与空穴配对相互作用" }
      ]
    },
    "agent_scientist": {
      "hypotheses": [
        {
          "id": "H1",
          "statement": "YBCO中氧空位浓度δ的微观空间异质性决定宏观Tc的峰值位置",
          "source": "Evidence #1 + Knowledge Gap #2",
          "supporting_reasoning": "均匀掺杂模型无法解释Tc在δ≈0.05处的尖锐最大值",
          "falsification_condition": "当δ异质性熵S_δ > 0.8 kB时，若观测到Tc仍维持>90 K",
          "plan": {
            "L1_conceptual": "构建氧空位空间分布与局域超导能隙的统计耦合模型",
            "L2_quantitative": "在δ = 0.03–0.07梯度单晶中，要求σ(Δ₀)/Δ₀,mean ∈ [0.12, 0.18] 时Tc ≥ 91.5 K",
            "L3_robustness": "若纳米ARPES信噪比不足，改用扫描隧道谱（STS）微分电导dI/dV mapping"
          },
          "verification_criteria": {
            "confirm": "当σ(Δ₀)/Δ₀,mean = 0.15 ± 0.03 且 S_δ = 0.65 ± 0.05 kB 时，Tc达到全局最大值92.1 ± 0.2 K",
            "reject": "若在δ = 0.05样品中测得σ(Δ₀)/Δ₀,mean < 0.08 或 > 0.25，同时Tc仍 ≥ 91.8 K"
          }
        }
      ],
      "cross_hypothesis_comparison": "H1聚焦氧空位空间异质性的统计鲁棒性机制；H2立足高压下的电子结构RG流不动点；H3提出超越传统媒介的声子-自旋谐波锁定新通道。"
    },
    "agent_critic": {
      "scores": { "evidence": 7.5, "falsifiability": 6.0, "consistency": 8.0, "novelty": 7.0, "cross_domain": 6.5 },
      "top_flaw": "H1 将局域能隙涨落 σ(Δ₀) 视为因果主导变量，但未排除其仅为副现象",
      "counterfactual": "在原子级平整的δ=0.05单层YBCO/LSMO异质结中，若纳米ARPES仍测得σ(Δ₀)/Δ₀,mean = 0.16 ± 0.02 且Tc = 92.0 K，则该假设必然失效",
      "missing_evidences": ["YBCO δ-mapped STEM-EELS + nanoARPES correlation dataset"],
      "detailed_review": "### H1 评审意见\n**Evidence (7.5/10)**：支撑较强...\n**Falsifiability (6.0/10)**：证伪条件具操作性..."
    }
  }
}
```

### 9.4 图表接口响应示例

```json
// /api/chart/overall
{ "success": true, "data": { "xAxis": ["V1", "V2"], "scores": [7.0, 7.94] } }

// /api/chart/radar
{ "success": true, "data": { "xAxis": ["V1", "V2"], "series": [{ "name": "evidence", "data": [7.5, 7.8] }, ...] } }

// /api/chart/granularity
{ "success": true, "data": { "xAxis": ["V1", "V2"], "L1": [3, 3], "L2": [3, 3], "L3": [3, 3] } }

// /api/chart/waterfall
{ "success": true, "data": { "start_score": 7.0, "steps": [{ "label": "...", "delta": 0.94, "from_round": "V1", "to_round": "V2" }], "end_score": 7.94 } }

// /api/chart/risk
{ "success": true, "data": { "xAxis": ["V1", "V2"], "risk_index": [1.45, 0], "level": ["低危", "低危"] } }
```

---

## 10. TypeScript 类型定义

```typescript
// ============ 请求类型 ============

interface RunRequest {
  question: string;           // ≥5 字符
  feedback?: string;          // 迭代时填，≥3 字符
  initial_round?: 'V1' | 'V2' | 'V3';  // 默认 V1
  auto_search_papers?: boolean;   // 默认 false，是否自动检索 arXiv 入库
  paper_granularity?: 'fast' | 'full';  // 默认 'fast'，arXiv 入库粒度
}

interface FeedbackRequest {
  question: string;           // ≥5 字符
  feedback: string;           // ≥3 字符
  current_round: 'V1' | 'V2' | 'V3';
}

// ============ 响应类型 ============

interface ApiResponse<T> {
  success: boolean;
  data: T;
}

interface Snapshot {
  round: 'V1' | 'V2' | 'V3';
  timestamp: string;
  question: string;
  overall_score: number;
  granularity_score: number;
  granularity_stats: { L1: number; L2: number; L3: number };
  human_feedback: Array<{ content: string }>;
  agent_explorer: ExplorerOutput;
  agent_scientist: ScientistOutput;
  agent_critic: CriticOutput;
}

interface ExplorerOutput {
  problem_skelton: string;
  evidence_list: Evidence[];
  knowledge_gaps: string[];
  analogies: Analogy[];
}

interface Evidence {
  claim: string;
  source: string;
  year: string | null;
}

interface Analogy {
  field: string;
  phenomenon: string;
  mapping_relation: string;
}

interface ScientistOutput {
  hypotheses: Hypothesis[];
  cross_hypothesis_comparison: string;
}

interface Hypothesis {
  id: 'H1' | 'H2' | 'H3';
  statement: string;
  source: string;
  supporting_reasoning: string;
  falsification_condition: string;
  plan: Plan;
  verification_criteria: VerificationCriteria;
}

interface Plan {
  L1_conceptual: string;
  L2_quantitative: string;
  L3_robustness: string;
}

interface VerificationCriteria {
  confirm: string;
  reject: string;
}

interface CriticOutput {
  scores: DimensionScores;
  top_flaw: string;
  counterfactual: string;
  missing_evidences: string[];
  detailed_review: string;
}

interface DimensionScores {
  evidence: number;
  falsifiability: number;
  consistency: number;
  novelty: number;
  cross_domain: number;
}

// ============ 图表数据类型 ============

interface ChartOverallData {
  xAxis: string[];
  scores: number[];
}

interface ChartRadarData {
  xAxis: string[];
  series: Array<{ name: string; data: number[] }>;
}

interface ChartGranularityData {
  xAxis: string[];
  L1: number[];
  L2: number[];
  L3: number[];
}

interface ChartWaterfallData {
  start_score: number;
  steps: Array<{
    label: string;
    delta: number;
    from_round: string;
    to_round: string;
  }>;
  end_score: number;
}

interface ChartRiskData {
  xAxis: string[];
  risk_index: number[];
  level: string[];
}

// ============ 错误类型 ============

interface ApiError {
  detail: string;
}
```

---

## 附录 A：完整响应示例

参见 `9.3 Mock 数据` 章节。完整真实响应（约 8000 字）可参考后端测试时生成的 JSON 文件。

### A.1 V1→V2 迭代后的字段变化示例

| 字段 | V1 | V2 | 变化 |
|------|-----|-----|------|
| `round` | `"V1"` | `"V2"` | 推进一轮 |
| `overall_score` | `7.0` | `7.94` | +0.94 |
| `scores.evidence` | `7.5` | `7.8` | +0.3 |
| `scores.falsifiability` | `6.0` | `8.2` | +2.2（最显著） |
| `scores.novelty` | `7.0` | `9.0` | +2.0 |
| `human_feedback` | `[]` | `[{content: "..."}]` | 新增反馈记录 |
| `top_flaw` | "H1 因果倒置风险" | "H1-H3 共享未声明依赖" | 诊断升级 |

---

## 附录 B：字段校验规则

### B.1 后端校验（Pydantic）

| 字段 | 规则 | 错误信息 |
|------|------|---------|
| `question` | `min_length=5` | "ensure this value has at least 5 characters" |
| `feedback` | `min_length=3` | "ensure this value has at least 3 characters" |
| `current_round` | `pattern=r"^V[1-3]$"` | "string does not match regex pattern" |
| `scores.*` | `ge=0, le=10` | "value must be between 0 and 10" |
| `hypothesis.id` | `pattern=r"^H[1-3]$"` | "string does not match regex pattern" |
| `falsification_condition` | `min_length=15` | "ensure this value has at least 15 characters" |

### B.2 前端建议校验

| 字段 | 校验时机 | 规则 |
|------|---------|------|
| `question` | 提交时 | 非空 + ≥5 字符 |
| `feedback` | 提交反馈时 | 非空 + ≥3 字符 |
| `current_round` | 自动管理 | 由前端状态机控制，不暴露给用户 |
| V3 后反馈 | 提交反馈时 | 检查 `currentRound === 'V3'`，禁用提交按钮 |

---

## 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-08-15 | v1.0 | 初始版本，基于后端实测数据编写 |
| 2026-08-27 | v1.1 | `/api/run` 与 `/api/feedback` 新增 `auto_search_papers`（默认 false）、`paper_granularity`（默认 fast）；补充 request body 与 TypeScript 类型 |
