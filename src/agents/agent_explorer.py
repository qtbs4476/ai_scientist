"""
Agent 1：探索者（Explorer）
职责：问题解构 + 文献检索 + 跨域类比迁移
基于 LangChain 1.x + 千问模型
"""

import json
import logging
import os
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from models.schemas import (
    ExplorerInput, ExplorerOutput,
    Evidence, Analogy
)
from services.chroma_service import ChromaService
from utils.llm_structured_fallback import parse_llm_json_to_model

# 加载项目根目录的 .env（= src/ 上一级）
import sys
if getattr(sys, "frozen", False):
    _PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

load_dotenv(_PROJECT_ROOT / ".env")
logger = logging.getLogger(__name__)


# ============================================================
# 1. LLM 配置
# ============================================================

_DEFAULT_MODEL = ""
_DEFAULT_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

llm = ChatOpenAI(
    model=os.getenv("QWEN_MODEL", _DEFAULT_MODEL),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("DASHSCOPE_API_BASE", _DEFAULT_API_BASE),
    temperature=0.6,
    max_tokens=4096,
    timeout=180.0,
)


# ============================================================
# 2. Prompt 模板
# ============================================================

SYSTEM_PROMPT = """你是一位顶尖的科学探索者，擅长解构复杂科学问题并挖掘多学科证据。

## 核心职责
1. **问题骨架提取**：将科学问题提炼为底层逻辑结构（如"微观单元交互→宏观现象涌现"）
2. **证据挖掘**：基于提供的文献片段提取结构化证据，每条必须附来源
3. **知识缺口识别**：指出当前文献未覆盖的盲区
4. **跨域类比**：当直接文献不足时，从其他学科借用已解决的经典案例

## 跨域类比策略
当本地知识库文献不足时，请自动启动跨域类比迁移：
- 提取问题的**底层逻辑结构**（如：微观→宏观涌现、因果关系推断、模式识别等）
- 从以下学科中寻找已解决的经典案例作为类比：
  - 物理：伊辛模型、相变、熵增原理、量子纠缠
  - 生物：集群行为、进化博弈、神经网络、基因调控
  - 计算机：强化学习、图网络、信息论、复杂度理论
  - 数学：动力系统、图论、概率图模型、拓扑学

## 输出格式（纯 JSON，字段名严格一致）
- problem_skelton (字符串，≥5 字符) —— 问题骨架（注意是 skelton，不是 skeleton）
- evidence_list (数组) —— 每条必须包含 claim + source 两个字符串键，year 可选
- knowledge_gaps (字符串数组)
- analogies (数组) —— 每条必须包含 field + phenomenon + mapping_relation 三个字符串键

【正确示例】
{
  "problem_skelton": "底层逻辑结构描述",
  "evidence_list": [
    {"claim": "证据陈述", "source": "论文来源", "year": "2023"}
  ],
  "knowledge_gaps": ["缺口1", "缺口2"],
  "analogies": [
    {"field": "统计物理", "phenomenon": "伊辛模型中的局部自旋相互作用产生宏观磁化", "mapping_relation": "局部神经元同步→全局意识状态"}
  ]
}

## 约束
- 每条证据必须绑定 source，缺失则视为无效
- 若本地文献不足，必须利用跨域类比补全，不允许返回空列表

## 语言要求（强制）
- 所有输出 JSON 字段（problem_skelton、claim、knowledge_gaps、phenomenon、mapping_relation 等）**必须使用中文**
- 允许保留的英文仅限：专有名词（如 YBCO、Riemann hypothesis、DNA、CRISPR、arXiv 编号、DOI、学科标准术语）、文献来源（source）、论文标题与作者名
- 若证据片段为英文，请在 claim 中用中文转述其核心含义，保留必要的英文术语
"""


# ============================================================
# 3. 核心函数
# ============================================================

# 检索候选池放大倍数：比最终 top_k 取更多候选，用于分来源遴选
# （扩大 k 只增加返回条数，query 仍只做 1 次 embedding，token 消耗不变）
_POOL_MULTIPLIER = 4


def _hybrid_retrieve(
    chroma: ChromaService,
    question: str,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """分来源融合检索：按相似度取前 top_k 条，不强制来源配额。

    思路：一次相似度检索取扩大后的候选池（不增加 embedding 调用），
    按 metadata 是否含 arxiv_id / openalex_id 区分三桶：
      - arXiv 在线文献（arxiv_id）
      - OpenAlex 离线文献（openalex_id）
      - 其他（Science_2025 / 本地 PDF，二者皆无专有 ID）
    组合策略：若候选池内存在 arXiv 文献，则优先纳入至少 1 条 arXiv（非强制兜底），
    剩余名额再按「OpenAlex + 其他」合并后的相似度排序依次追加，
    最终返回结果总数 ≤ top_k 条，不再限定 OpenAlex 与 arXiv 的固定比例。

    Args:
        chroma: 向量库服务
        question: 用户科学问题
        top_k: 最终返回文档数

    Returns:
        融合后的检索结果列表
    """
    pool_size = max(top_k * _POOL_MULTIPLIER, 3)
    pool = chroma.similarity_search(question, k=pool_size)

    arxiv = [r for r in pool if r["metadata"].get("arxiv_id")]
    openalex = [r for r in pool if r["metadata"].get("openalex_id")]
    other = [r for r in pool if not r["metadata"].get("arxiv_id") and not r["metadata"].get("openalex_id")]
    logger.info(
        f"分来源检索: 候选 {len(pool)} 条（arXiv={len(arxiv)}，OpenAlex={len(openalex)}，其他={len(other)}）"
    )

    merged: List[Dict[str, Any]] = []
    seen: set = set()

    def _add(results: List[Dict[str, Any]], limit: int) -> int:
        """按去重规则追加 results，返回实际追加条数"""
        added = 0
        for r in results:
            if added >= limit:
                break
            key = (r["metadata"].get("source"), r["metadata"].get("openalex_id"), r["metadata"].get("arxiv_id"), r["content"][:40])
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
            added += 1
        return added

    n_arxiv = 0
    # 1) 若存在 arXiv 在线文献，优先纳入至少 1 条（非强制兜底，池中无则跳过）
    if len(arxiv) > 0:
        n_arxiv = _add(arxiv, 1)

    # 2) 剩余名额：合并 OpenAlex + 其他按原有相似度排序依次追加，直到填满 top_k
    remaining = top_k - len(merged)
    if remaining > 0:
        # 合并 openalex + other，保持它们在 pool 中的原始相对相似度顺序
        # （先构造一个 content[:40] 辅助映射，用于快速定位顺序）
        order_map = {}
        for idx, r in enumerate(pool):
            k = r["content"][:40]
            if k not in order_map:
                order_map[k] = idx
        rest = openalex + other
        rest_sorted = sorted(rest, key=lambda r: order_map.get(r["content"][:40], 10**9))
        _add(rest_sorted, remaining)

    n_openalex = sum(1 for r in merged if r["metadata"].get("openalex_id"))
    n_arxiv_actual = sum(1 for r in merged if r["metadata"].get("arxiv_id"))
    n_other = len(merged) - n_openalex - n_arxiv_actual

    if n_arxiv_actual > 0:
        logger.info(f"已纳入 {n_arxiv_actual} 条 arXiv 在线文献参与假设构建")
    logger.info(f"证据来源构成: arXiv={n_arxiv_actual}, OpenAlex={n_openalex}, 其他={n_other}（共 {len(merged)} 条）")
    return merged


def explore(
    question: str,
    top_k: int = 3,
    max_retries: int = 3
) -> ExplorerOutput:
    """
    执行探索

    Args:
        question: 用户科学问题
        top_k: 向量检索返回文档数
        max_retries: 最大重试次数

    Returns:
        ExplorerOutput: 包含问题骨架、证据、缺口、类比

    Raises:
        RuntimeError: 超过最大重试次数仍失败
    """
    # 1. 向量检索（分来源融合：本地知识库 + 至少 1 条 arXiv 在线文献）
    chroma = ChromaService()
    results = _hybrid_retrieve(chroma, question, top_k=top_k)

    # 2. 构建 Prompt
    if results:
        evidence_context = "\n".join([
            f"- {r['content']} (来源: {r['metadata'].get('source', '未知')})"
            for r in results
        ])
    else:
        evidence_context = "（未检索到相关文献，请基于跨域类比推理）"

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"""
## 用户问题
{question}

## 本地知识库检索结果（文献片段）
{evidence_context}

请提取问题骨架、结构化证据、知识缺口和跨域类比线索，严格按 JSON 格式输出。

注意：
1. 如果文献片段不足，请主动从物理、生物、计算机、数学等学科中寻找类比案例
2. 类比必须说明 mapping_relation（如何映射到本问题）
3. 证据列表中每条都必须有 source 字段
""")
    ]

    # 3. 调用模型（带重试）
    structured_llm = llm.with_structured_output(ExplorerOutput)

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Agent 1 探索尝试 {attempt}/{max_retries}...")
            try:
                result = structured_llm.invoke(messages)
            except Exception as structured_err:
                logger.info("结构化输出失败，降级为纯文本 JSON 解析: %s",
                            type(structured_err).__name__)
                raw = llm.invoke(messages)
                raw_text = raw.content if hasattr(raw, "content") else str(raw)
                result = parse_llm_json_to_model(raw_text, ExplorerOutput)

            # 校验：证据和类比不能同时为空
            if not result.evidence_list and not result.analogies:
                raise ValueError("证据和类比均为空，需要至少一项")

            # 校验：每条证据必须有 source
            for i, ev in enumerate(result.evidence_list):
                if not ev.source or len(ev.source) < 3:
                    raise ValueError(f"证据 {i+1} 缺少有效的 source 字段")

            logger.info(f"✅ 探索完成：{len(result.evidence_list)} 条证据，{len(result.analogies)} 条类比")
            return result

        except Exception as e:
            logger.warning(f"第 {attempt} 次失败: {e}")
            last_error = e

            # 重试时降低 temperature 使输出更稳定
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"探索失败: {last_error}")


# ============================================================
# 4. LangGraph 节点
# ============================================================

class ExplorerState(BaseModel):
    question: str = ""
    explorer_output: Optional[ExplorerOutput] = None
    retry_count: int = 0
    errors: List[str] = Field(default_factory=list)


def explorer_node(state: dict) -> dict:
    """LangGraph 节点函数"""
    logger.info("进入 Explorer Node")

    try:
        result = explore(state["question"])
        return {
            "explorer_output": result.model_dump(),
            "retry_count": 0,
            "errors": []
        }
    except Exception as e:
        logger.error(f"Explorer Node 失败: {e}")
        return {
            "explorer_output": None,
            "retry_count": state.get("retry_count", 0) + 1,
            "errors": [str(e)]
        }


def build_explorer_graph():
    """构建 Explorer 子图"""
    workflow = StateGraph(ExplorerState)

    workflow.add_node("explorer", explorer_node)
    workflow.set_entry_point("explorer")

    def should_continue(state: dict) -> str:
        if state.get("errors") and state.get("retry_count", 0) < 3:
            logger.info(f"重试 Explorer: {state['retry_count']}/3")
            return "explorer"
        return "__end__"

    workflow.add_conditional_edges(
        "explorer",
        should_continue,
        {
            "explorer": "explorer",
            "__end__": END
        }
    )

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)