"""
Agent 4：指挥家（Orchestrator）
职责：流水线调度 + 人在回路解析 + 全链路重跑 + 快照管理
基于 LangGraph 1.x + FastAPI
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal, Callable
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from models.schemas import (
    ExplorerOutput, ScientistOutput, CriticOutput,
    DimensionScores, OverallScore
)
from agents.agent_explorer import explore
from agents.agent_scientist import generate_hypotheses
from agents.agent_critic import critique, calculate_overall_score
from models.database import SessionLocal, SnapshotRecord, USES_MYSQL
from services.job_manager import PipelineCancelled, RoundLimitError

# 加载项目根目录的 .env
import sys
if getattr(sys, "frozen", False):
    _PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

load_dotenv(_PROJECT_ROOT / ".env")
logger = logging.getLogger(__name__)

# 在线检索的 arXiv 临时文献：跑完 pipeline 后是否保留在向量库中。
# KEEP_SEARCHED_PAPERS=true 时保留（入库即长期生效，不再清理）；
# 否则执行策略 B（精确清理本次塞入的临时文献，避免污染长期知识库）。
KEEP_SEARCHED_PAPERS = os.getenv("KEEP_SEARCHED_PAPERS", "false").strip().lower() in {"1", "true", "yes"}


# ============================================================
# 1. 配置
# ============================================================

WEIGHTS = {
    "evidence": 0.25,
    "falsifiability": 0.25,
    "consistency": 0.20,
    "novelty": 0.15,
    "cross_domain": 0.15,
}

SNAPSHOTS_PATH = os.getenv(
    "SNAPSHOTS_PATH",
    str(_PROJECT_ROOT / "snapshots")
)

MAX_ROUND = 3


def validate_round_limit(current_round: str) -> None:
    """集中式 V3 边界守卫：超过最大迭代轮次时抛 RoundLimitError。

    后台任务与同步接口统一走这里，避免只在前端/单点漏检。
    """
    if current_round == f"V{MAX_ROUND}":
        raise RoundLimitError(f"已到最大迭代次数 V{MAX_ROUND}，无法继续迭代")


def next_round_label(current_round: str) -> str:
    return f"V{int(current_round[1:]) + 1}"


def _project_snapshot_dir(project_id: Optional[str]) -> str:
    """快照目录：有 project_id 时用独立子目录，否则回退到根目录（legacy 单项目模式）。"""
    d = os.path.join(SNAPSHOTS_PATH, project_id) if project_id else SNAPSHOTS_PATH
    os.makedirs(d, exist_ok=True)
    return d


def _round_path(project_id: Optional[str], round_label: str) -> str:
    return os.path.join(_project_snapshot_dir(project_id), f"{round_label}.json")


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    """容错读取 JSON 文件，损坏或缺失返回 None。"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_project_snapshots(project_id: Optional[str]) -> List[Dict[str, Any]]:
    """读取单个项目（或 legacy 根目录）的所有轮次快照，按轮次排序。"""
    if project_id:
        d = os.path.join(SNAPSHOTS_PATH, project_id)
        if not os.path.isdir(d):
            return []
        snaps = []
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                s = _load_json(os.path.join(d, fn))
                if s:
                    s.setdefault("project_id", project_id)
                    snaps.append(s)
        return snaps

    # legacy 根目录文件（单项目模式的旧数据）
    snaps = []
    if not os.path.exists(SNAPSHOTS_PATH):
        return snaps
    for fn in sorted(os.listdir(SNAPSHOTS_PATH)):
        if fn.endswith(".json"):
            s = _load_json(os.path.join(SNAPSHOTS_PATH, fn))
            if s:
                snaps.append(s)
    return snaps


# ============================================================
# 2. 综合评分与统计
# ============================================================

def _l1_quality(text: str) -> float:
    if len(text) < 10:
        return 0.0
    score = 1.0
    score += min(1.0, len(text) / 100)
    keywords = ["方法", "模型", "算法", "框架", "机制", "结构", "模块", "分解", "学习", "推理", "映射", "变换"]
    kw_count = sum(1 for kw in keywords if kw in text)
    score += min(1.0, kw_count * 0.15)
    return min(3.0, round(score, 2))


def _l2_quality(text: str) -> float:
    if not text or not re.search(r'\d+', text) or len(text) < 15:
        return 0.0
    score = 1.0
    num_count = len(re.findall(r'\d+', text))
    if num_count >= 5:
        score += 1.0
    elif num_count >= 3:
        score += 0.5
    score += min(1.0, len(text) / 80)
    return min(3.0, round(score, 2))


def _l3_quality(text: str) -> float:
    if not text or len(text) < 20:
        return 0.0
    risk_kws = ["若", "如果", "万一", "一旦", "假设", "alternative", "fallback"]
    mitigate_kws = ["备选", "替代", "对照", "切换", "转换", "降级", "补救"]
    risk_count = sum(1 for kw in risk_kws if kw in text)
    mitigate_count = sum(1 for kw in mitigate_kws if kw in text)
    if risk_count == 0:
        return 0.0
    score = 1.0
    if risk_count >= 2:
        score += 0.5
    if mitigate_count >= 2:
        score += 0.5
    score += min(1.0, len(text) / 100)
    return min(3.0, round(score, 2))


def calculate_granularity_stats(hypotheses: List[Dict]) -> Dict[str, float]:
    """统计计划颗粒度（质量加权评估，0-3 分梯度）"""
    stats = {"L1": 0.0, "L2": 0.0, "L3": 0.0}
    for h in hypotheses:
        plan = h.get("plan", {})
        stats["L1"] += _l1_quality(plan.get("L1_conceptual", ""))
        stats["L2"] += _l2_quality(plan.get("L2_quantitative", ""))
        stats["L3"] += _l3_quality(plan.get("L3_robustness", ""))
    return {k: round(v, 2) for k, v in stats.items()}


def calculate_granularity_score(stats: Dict[str, float]) -> float:
    """计算颗粒度得分，按绝对质量归一化，范围 0-6
    MAX = 3 条假设 × 3.0 质量分 × 权重和(1+3+6) = 90
    """
    MAX_POSSIBLE = 3 * 3.0 * 10
    weighted_sum = stats["L1"] * 1 + stats["L2"] * 3 + stats["L3"] * 6
    return round((weighted_sum / MAX_POSSIBLE) * 6, 2)


# ============================================================
# 3. 核心编排函数
# ============================================================

def run_full_pipeline(
    question: str,
    feedback: Optional[str] = None,
    round_label: str = "V1",
    project_id: Optional[str] = None,
    progress_callback: Optional[Callable[[Optional[str], Optional[int]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    auto_search_papers: bool = False,
    paper_granularity: str = "fast",
) -> Dict[str, Any]:
    """
    执行完整流水线

    project_id: 项目隔离标识（快照写入 snapshots/{project_id}/ 子目录）。
    progress_callback: 上报当前阶段（explorer/scientist/critic）与粗略进度。
    cancel_check: 在步骤边界轮询取消标志，命中即抛 PipelineCancelled。
    paper_granularity: arXiv 临时文献入库粒度，控制 embedding token 消耗：
        - "fast"（默认，摘要模式）：每篇仅入标题+摘要，chunk 少、token 省约 96%
        - "full"（严格模式）：下载 PDF 全文分块入库，证据更细但 token 消耗大
    """
    logger.info(f"=" * 60)
    logger.info(f"开始执行 {round_label}（project={project_id or 'legacy'}）")
    logger.info(f"=" * 60)

    def _check_cancel() -> None:
        if cancel_check and cancel_check():
            logger.info(f"{round_label} 收到取消请求，中止流水线")
            raise PipelineCancelled()

    # 新研究首轮（无反馈的 V1）：仅清除当前项目残留的 V2/V3 快照文件，
    # 避免图表/快照接口把旧研究的迭代轮次与新研究混排在一起
    if round_label == "V1" and not feedback:
        for stale_round in ("V2", "V3"):
            stale_path = _round_path(project_id, stale_round)
            if os.path.exists(stale_path):
                try:
                    os.remove(stale_path)
                    logger.info(f"已清除上一研究的残留快照 {stale_round}.json")
                except OSError as rm_err:
                    logger.warning(f"清除残留快照失败 {stale_path}: {rm_err}")

    # ====== 读取上一轮快照，将 Critic 评审结果传给 Scientist ======
    prev_critic_output = None
    prev_overall_score = None
    prev_round_num = int(round_label[1:])
    if prev_round_num > 1:
        prev_round_label = f"V{prev_round_num - 1}"
        prev_snapshot = _load_json(_round_path(project_id, prev_round_label))
        if prev_snapshot:
            prev_critic_output = prev_snapshot.get("agent_critic")
            prev_overall_score = prev_snapshot.get("overall_score")
            logger.info(f"已加载上一轮 {prev_round_label} Critic 结果（综合得分 {prev_overall_score}），将注入 Scientist")
        else:
            logger.info(f"上一轮 {prev_round_label} 快照不存在，本轮 Scientist 不参考历史评审")

    # ====== 自动检索 arXiv 文献入库（可选）======
    # 策略 B：pipeline 开始前快照现有 arxiv_id 集合，结束后精确清理本次塞入的文献
    _paper_svc = None
    _pre_arxiv_ids: set = set()
    if auto_search_papers:
        try:
            from services.paper_search_service import PaperSearchService
            _paper_svc = PaperSearchService()
            _pre_arxiv_ids = _paper_svc.get_existing_arxiv_ids()
            _granularity = paper_granularity if paper_granularity in ("fast", "full") else "fast"
            _full_text = (_granularity == "full")
            ingest_result = _paper_svc.search_and_ingest(
                question,
                max_results=5,
                full_text=_full_text,
            )
            logger.info(
                f"📚 自动检索入库: 检索 {ingest_result.get('retrieved', 0)} 篇, "
                f"入库 {ingest_result.get('ingested', 0)} 篇 "
                f"(粒度={_granularity}, full_text={_full_text})"
            )
        except Exception as e:
            logger.warning(f"自动检索文献失败，跳过（不影响主流程）: {e}")
            _paper_svc = None  # 标记不清理

    try:
        # Step 1: Explorer
        logger.info("Step 1: 探索者执行中...")
        if progress_callback:
            progress_callback("explorer", 15)
        _check_cancel()
        explorer_result = explore(question)

        # Step 2: Scientist
        logger.info("Step 2: 科学家执行中...")
        if progress_callback:
            progress_callback("scientist", 50)
        _check_cancel()
        scientist_result = generate_hypotheses(
            problem_skelton=explorer_result.problem_skelton,
            evidence_list=[e.model_dump() for e in explorer_result.evidence_list],
            knowledge_gaps=explorer_result.knowledge_gaps,
            analogies=[a.model_dump() for a in explorer_result.analogies],
            feedback=feedback,
            prev_critic_output=prev_critic_output,
            prev_overall_score=prev_overall_score,
        )

        # Step 3: Critic
        logger.info("Step 3: 评审官执行中...")
        if progress_callback:
            progress_callback("critic", 85)
        _check_cancel()
        prev_scores_for_critic = None
        if prev_critic_output:
            prev_scores_for_critic = prev_critic_output.get("scores")
        critic_result = critique(
            hypotheses=[h.model_dump() for h in scientist_result.hypotheses],
            round_label=round_label,
            prev_scores=prev_scores_for_critic,
        )

        # Step 4: 计算综合得分
        overall_score = calculate_overall_score(
            critic_result.scores,
            penalty=0.0
        )

        # 评分对比：若低于上一轮，记录警告（帮助定位迭代退化）
        if prev_overall_score is not None and overall_score < prev_overall_score:
            logger.warning(
                f"⚠️ {round_label} 评分 ({overall_score}) 低于上一轮 "
                f"({prev_overall_score})，退化 {round(prev_overall_score - overall_score, 2)} 分！"
            )
        elif prev_overall_score is not None:
            improvement = round(overall_score - prev_overall_score, 2)
            logger.info(f"📈 {round_label} 评分较上一轮提升 {improvement} 分")

        # Step 5: 统计颗粒度
        granularity_stats = calculate_granularity_stats(
            [h.model_dump() for h in scientist_result.hypotheses]
        )
        granularity_score = calculate_granularity_score(granularity_stats)

        # Step 6: 构建快照
        snapshot = {
            "round": round_label,
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "project_id": project_id,
            "agent_explorer": explorer_result.model_dump(),
            "agent_scientist": scientist_result.model_dump(),
            "agent_critic": critic_result.model_dump(),
            "overall_score": overall_score,
            "granularity_score": granularity_score,
            "human_feedback": [{"content": feedback}] if feedback else [],
            "granularity_stats": granularity_stats,
        }

        # Step 7: 保存快照（文件 + 数据库，数据库失败不影响主流程）
        filepath = _round_path(project_id, round_label)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
        except Exception as file_err:
            logger.warning(f"快照文件写入失败（不影响本次运行结果）: {file_err}")

        # 写入数据库（仅当启用了 MySQL 才尝试；未配置/落到 SQLite 时跳过，以 JSON 快照为准）
        if not USES_MYSQL:
            logger.info("   未启用 MySQL，跳过数据库快照（仅保存 JSON 文件）")
        else:
            try:
                db = SessionLocal()
                record = SnapshotRecord(
                    round=round_label,
                    question=question,
                    overall_score=overall_score,
                    explorer_output=explorer_result.model_dump(),
                    scientist_output=scientist_result.model_dump(),
                    critic_output=critic_result.model_dump(),
                    granularity_stats=granularity_stats,
                    human_feedback=[{"content": feedback}] if feedback else []
                )
                db.add(record)
                db.commit()
                logger.info(f"   数据库快照已写入 (id={record.id})")
            except Exception as db_err:
                logger.warning(f"数据库快照写入失败（降级为仅保存 JSON 文件）: {db_err}")
                if 'db' in locals():
                    db.rollback()
            finally:
                if 'db' in locals():
                    db.close()

        logger.info(f"✅ {round_label} 完成，综合得分: {overall_score}")
        logger.info(f"   颗粒度: L1={granularity_stats['L1']}, L2={granularity_stats['L2']}, L3={granularity_stats['L3']}")

        return snapshot
    finally:
        # ====== 精确清理本次塞入的临时文献（策略 B）======
        # 仅当 KEEP_SEARCHED_PAPERS=false 时清理；设为 true 则在线检索的文献保留入库。
        # 即使 pipeline 失败/取消也执行清理，避免污染长期知识库（开关为 false 时）。
        if _paper_svc is not None and not KEEP_SEARCHED_PAPERS:
            try:
                post_arxiv_ids = _paper_svc.get_existing_arxiv_ids()
                new_ids = post_arxiv_ids - _pre_arxiv_ids
                if new_ids:
                    cleaned = _paper_svc.cleanup_by_arxiv_ids(list(new_ids))
                    logger.info(f"🧹 已清理本次临时文献 {cleaned}/{len(new_ids)} 篇")
            except Exception as e:
                logger.warning(f"清理临时文献失败: {e}")


def iterate_with_feedback(
    question: str,
    feedback: str,
    current_round: str,
    project_id: Optional[str] = None,
    progress_callback: Optional[Callable[[Optional[str], Optional[int]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    auto_search_papers: bool = False,
    paper_granularity: str = "fast",
) -> Dict[str, Any]:
    """
    在人在回路反馈后执行迭代
    """
    # 集中式 V3 边界守卫（防御性：main.py 端点已校验，这里兜底）
    validate_round_limit(current_round)
    next_round = next_round_label(current_round)
    logger.info(f"收到反馈，触发 {next_round} 全链路重跑...")

    return run_full_pipeline(
        question=question,
        feedback=feedback,
        round_label=next_round,
        project_id=project_id,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        auto_search_papers=auto_search_papers,
        paper_granularity=paper_granularity,
    )


# ============================================================
# 4. 前端图表数据接口
# ============================================================

def get_snapshot(round_label: str, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """读取指定项目下某轮次的快照"""
    return _load_json(_round_path(project_id, round_label))


def get_all_snapshots() -> List[Dict[str, Any]]:
    """获取所有项目的所有快照（含 legacy 根目录），每条带 project_id 字段。"""
    snapshots = []
    if not os.path.exists(SNAPSHOTS_PATH):
        return snapshots
    # 先按项目子目录扫描，再扫描 legacy 根目录文件
    for entry in sorted(os.listdir(SNAPSHOTS_PATH)):
        full = os.path.join(SNAPSHOTS_PATH, entry)
        if os.path.isdir(full):
            snapshots.extend(get_project_snapshots(entry))
    snapshots.extend(get_project_snapshots(None))
    return snapshots


def get_chart_overall(project_id: Optional[str] = None) -> Dict[str, Any]:
    """获取综合得分折线图数据（按项目隔离）"""
    snapshots = get_project_snapshots(project_id)
    if not snapshots:
        return {"xAxis": [], "series": {"overall_score": [], "granularity_score": []}}
    return {
        "xAxis": [s["round"] for s in snapshots],
        "series": {
            "overall_score": [s["overall_score"] for s in snapshots],
            "granularity_score": [s.get("granularity_score", 0) for s in snapshots],
        }
    }


def get_chart_radar(project_id: Optional[str] = None) -> Dict[str, Any]:
    """获取雷达图数据（按项目隔离）"""
    snapshots = get_project_snapshots(project_id)
    if not snapshots:
        return {"dimensions": [], "series": {}}

    dimensions = ["evidence", "falsifiability", "consistency", "novelty", "cross_domain"]
    result = {
        "dimensions": dimensions,
        "series": {}
    }
    for s in snapshots:
        scores = s["agent_critic"]["scores"]
        result["series"][s["round"]] = [scores[d] for d in dimensions]
    return result


def get_chart_granularity(project_id: Optional[str] = None) -> Dict[str, Any]:
    """获取颗粒度堆叠图数据（按项目隔离）"""
    snapshots = get_project_snapshots(project_id)
    if not snapshots:
        return {"xAxis": [], "L1": [], "L2": [], "L3": []}
    return {
        "xAxis": [s["round"] for s in snapshots],
        "L1": [s["granularity_stats"]["L1"] for s in snapshots],
        "L2": [s["granularity_stats"]["L2"] for s in snapshots],
        "L3": [s["granularity_stats"]["L3"] for s in snapshots],
    }


def get_chart_waterfall(project_id: Optional[str] = None) -> Dict[str, Any]:
    """获取缺陷修复瀑布图数据（按项目隔离）"""
    snapshots = get_project_snapshots(project_id)
    if len(snapshots) < 2:
        return {"start_score": 0, "steps": [], "end_score": 0}

    result = []
    for i in range(1, len(snapshots)):
        prev = snapshots[i-1]
        curr = snapshots[i]
        delta = round(curr["overall_score"] - prev["overall_score"], 2)

        # 获取本轮修复的缺陷（从 Critic 的 top_flaw 和 feedback 推断）
        critic = curr["agent_critic"]
        step = {
            "label": critic.get("top_flaw", "")[:20] + "...",
            "delta": delta,
            "from_round": prev["round"],
            "to_round": curr["round"]
        }
        result.append(step)

    return {
        "start_score": snapshots[0]["overall_score"],
        "steps": result,
        "end_score": snapshots[-1]["overall_score"]
    }


def get_chart_risk(project_id: Optional[str] = None) -> Dict[str, Any]:
    """获取反事实风险收敛图数据（按项目隔离）"""
    snapshots = get_project_snapshots(project_id)
    if not snapshots:
        return {"xAxis": [], "risk_index": [], "level": []}

    # 根据 counterfactual 长度粗略估算风险指数（越短说明越苛刻=风险越高）
    risk_levels = []
    for s in snapshots:
        cf = s["agent_critic"].get("counterfactual", "")
        # 简单启发：长度越短风险越高（更苛刻的条件）
        risk = max(0, min(10, 10 - len(cf) / 20))
        risk_levels.append(round(risk, 2))

    return {
        "xAxis": [s["round"] for s in snapshots],
        "risk_index": risk_levels,
        "level": ["高危" if r > 6 else "中危" if r > 3 else "低危" for r in risk_levels]
    }


# ============================================================
# 5. LangGraph 编排
# ============================================================

class OrchestratorState(BaseModel):
    question: str = ""
    feedback: Optional[str] = None
    current_round: str = "V1"
    max_rounds: int = 3

    explorer_output: Optional[ExplorerOutput] = None
    scientist_output: Optional[ScientistOutput] = None
    critic_output: Optional[CriticOutput] = None

    overall_score: float = 0.0
    snapshot: Optional[Dict[str, Any]] = None
    errors: List[str] = Field(default_factory=list)
    retry_count: int = 0


def orchestrator_node(state: dict) -> dict:
    """Orchestrator 主节点"""
    logger.info(f"Orchestrator 执行 {state['current_round']}")

    try:
        snapshot = run_full_pipeline(
            question=state["question"],
            feedback=state.get("feedback"),
            round_label=state["current_round"]
        )

        return {
            "snapshot": snapshot,
            "overall_score": snapshot["overall_score"],
            "explorer_output": snapshot["agent_explorer"],
            "scientist_output": snapshot["agent_scientist"],
            "critic_output": snapshot["agent_critic"],
            "errors": [],
            "retry_count": 0
        }
    except Exception as e:
        logger.error(f"Orchestrator 失败: {e}")
        return {
            "errors": [str(e)],
            "retry_count": state.get("retry_count", 0) + 1
        }


# ============================================================
# 6. 智能建议问题生成（输入框自动补全）
# ============================================================

_suggest_llm = None


def _get_suggest_llm():
    """懒加载建议问题生成 LLM（避免无 DASHSCOPE_API_KEY 时启动失败）"""
    global _suggest_llm
    if _suggest_llm is None:
        from langchain_openai import ChatOpenAI
        _suggest_llm = ChatOpenAI(
            model=os.getenv("QWEN_MODEL", ""),
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url=os.getenv("DASHSCOPE_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            temperature=0.5,
            max_tokens=512,
            timeout=30.0,
        )
    return _suggest_llm


def _build_snapshot_brief(project_id: Optional[str]) -> tuple[str, str]:
    """从最近一轮 snapshot 提取研究上下文摘要。返回 (brief, based_on)。"""
    snaps = get_project_snapshots(project_id)
    if not snaps:
        return "", "context_only"

    latest = snaps[-1]
    based_on = f"snapshot:{latest.get('round', 'V?')}"

    scientist_out = latest.get("agent_scientist") or {}
    critic_out = latest.get("agent_critic") or {}

    hypotheses = scientist_out.get("hypotheses") or []
    h_brief = "\n".join(
        f"  {i+1}. {h.get('title', '无标题')[:80]}"
        + (f"（{h.get('plan', {}).get('L1_conceptual', '')[:60]}）"
           if h.get('plan', {}).get('L1_conceptual') else "")
        for i, h in enumerate(hypotheses[:3])
    ) or "  - 无假设"

    top_flaw = (critic_out.get("top_flaw") or "无")[:150]
    missing_evs = critic_out.get("missing_evidences") or []
    missing_brief = "\n".join(f"  - {e[:80]}" for e in missing_evs[:3]) if missing_evs else "  - 无"

    scores = critic_out.get("scores") or {}
    overall = latest.get("overall_score", 0)

    # 短板定向：找出五维中最低的一维，作为 prompt 引导的优先提问方向
    _weak_dims = ["evidence", "falsifiability", "consistency", "novelty", "cross_domain"]
    weak_dim, weak_value = None, None
    for k in _weak_dims:
        try:
            v = float(scores.get(k))
        except (TypeError, ValueError):
            continue
        if weak_value is None or v < weak_value:
            weak_value, weak_dim = v, k
    weak_hint = f"\n- 薄弱维度: {weak_dim}（{weak_value}）——优先追问如何补强该维度" if weak_dim else ""

    brief = f"""【当前研究进展】
- 最新轮次: {latest.get('round', 'V?')}  综合得分: {overall}
- 五维评分: evidence={scores.get('evidence', '?')}, falsifiability={scores.get('falsifiability', '?')}, consistency={scores.get('consistency', '?')}, novelty={scores.get('novelty', '?')}, cross_domain={scores.get('cross_domain', '?')}
- 当前假设:
{h_brief}
- Critic 致命缺陷: {top_flaw}
- Critic 缺失证据:
{missing_brief}{weak_hint}
"""
    return brief, based_on


def _build_covered_brief(project_id: Optional[str]) -> str:
    """从该项目历史轮次的 human_feedback 中提取“已追问/反馈过的方向”。

    目的：第 4 项改进——让 LLM 避开已覆盖方向、往未探索处走，避免每次生成
    风格相近的追问。仅在 snapshot 路径（有历史）时有内容。
    """
    snaps = get_project_snapshots(project_id)
    if not snaps:
        return ""
    covered: List[str] = []
    for s in snaps[-5:]:  # 最近 5 轮
        fb = s.get("human_feedback") or []
        items = fb if isinstance(fb, list) else []
        for it in items:
            c = str(it.get("content") if isinstance(it, dict) else it).strip()
            if c and c not in covered:
                covered.append(c[:60])
    if not covered:
        return ""
    lines = "\n".join(f"  - {c}" for c in covered)
    return f"\n【已追问/反馈过的方向】（请避开重复，往未探索处走）\n{lines}\n"


def _build_chroma_brief(context: str) -> tuple[str, str]:
    """冷启动兜底：用 Chroma 向量库检索 top-3 文献片段作为上下文。

    无 snapshot 时调用，让 LLM 至少能基于已塞入库里的文献生成建议，
    避免冷启动场景下建议完全无锚点。

    Returns:
        (brief, based_on)：brief 为空表示向量库也为空（连 Chroma 都没东西）
    """
    try:
        from services.chroma_service import ChromaService
    except Exception as e:
        logger.warning(f"ChromaService 导入失败，跳过向量库兜底: {e}")
        return "", "context_only"

    # context 太短时用默认 query，避免检索命中噪声
    query = context.strip() if len(context.strip()) >= 5 else "scientific hypothesis research method"

    try:
        svc = ChromaService()
        results = svc.similarity_search(query, k=3)
    except Exception as e:
        logger.warning(f"Chroma 检索失败，跳过向量库兜底: {e}")
        return "", "context_only"

    if not results:
        return "", "context_only"

    # 拼接 brief：每条文献片段 + 来源
    lines = []
    for i, r in enumerate(results, 1):
        content = (r.get("content") or "").strip()
        if not content:
            continue
        # 截 200 字符避免 prompt 过长
        if len(content) > 200:
            content = content[:200] + "..."
        source = (r.get("metadata") or {}).get("source", "未知来源")
        lines.append(f"  {i}. {content}  (来源: {source})")

    if not lines:
        return "", "context_only"

    brief = f"""【向量库相关文献片段】（冷启动兜底，无 snapshot 可用）
{chr(10).join(lines)}
"""
    return brief, "chroma:top_3"


def _based_on_desc(based_on: str) -> str:
    """把 based_on 标签翻译成前端可展示的资源口径说明（第 6 项透明度）。"""
    key = based_on.split(":")[0] if ":" in based_on else based_on
    return {
        "snapshot": "依据最近一轮研究进展（假设 / Critic 缺陷 / 薄弱维度）",
        "chroma": "依据文献库检索到的资料片段",
        "context_only": "仅依据你当前的输入",
        "error": "",
    }.get(key, "")


def suggest_questions(
    context: str = "",
    mode: str = "question",
    project_id: Optional[str] = None,
    top_k: int = 3,
) -> Dict[str, Any]:
    """
    基于当前研究上下文生成 N 条迭代相关问题。

    上下文来源优先级：
        1. 最近一轮 snapshot（hypotheses + critic 评审）
        2. Chroma 向量库检索（冷启动兜底，无 snapshot 时用）
        3. 仅用户前缀 + system prompt（最终兜底，向量库也为空时）

    Args:
        context: 用户已输入的前缀（可空），作为引导词让建议自然延伸
        mode: "question"（追问方向）或 "feedback"（改进建议）
        project_id: 项目 ID（用于读取最近 snapshot）
        top_k: 生成数量（1-5）

    Returns:
        {questions: List[str], dims: List[str], based_on: "snapshot:Vx" | "chroma:top_3" | "context_only" | "error",
         based_on_desc: str}
    """
    try:
        llm = _get_suggest_llm()
    except Exception as e:
        logger.warning(f"建议 LLM 初始化失败: {e}")
        return {"questions": [], "based_on": "error", "error": str(e)}

    # 来源 1：最近 snapshot
    snapshot_brief, based_on = _build_snapshot_brief(project_id)

    # 来源 2（兜底）：Chroma 向量库检索
    if not snapshot_brief:
        snapshot_brief, based_on = _build_chroma_brief(context)
        if snapshot_brief:
            logger.info(f"冷启动兜底：基于 Chroma 向量库生成建议（query={context[:30]!r}）")

    # 来源 3（最终兜底）：只靠 context + system prompt，brief 为空

    if mode == "feedback":
        task_desc = "用户要在反馈框输入改进建议。生成 N 条最值得提的改进方向（聚焦补证据/改方法/换视角）"
    else:
        task_desc = "用户要追问新问题。生成 N 条最值得继续追问的迭代相关问题（涵盖深挖证据/改进方法/跨域类比）"

    context_hint = f"\n【用户已输入前缀】（建议应自然延伸此前缀）\n{context}" if context else ""

    # 第 4 项：snapshot 路径时注入“已追问/反馈过的方向”，避免生成重复追问
    covered_brief = ""
    if based_on.startswith("snapshot:"):
        covered_brief = _build_covered_brief(project_id)

    system_content = (
        f"你是科研迭代助手。基于当前研究上下文，生成 {top_k} 条用户最可能追问的迭代相关问题。\n\n"
        "要求：\n"
        "1. 每条 15-40 字符，简洁直接\n"
        "2. 按维度覆盖：1 个 deep_dive（深挖证据/数据），1 个 method（改进方法/实验设计），1 个 cross_domain（跨域类比/新视角）；若上下文提示了【薄弱维度】，请优先对该维度提问\n"
        "3. 若提供了【已追问/反馈过的方向】，请避开重复、往未探索处延伸\n"
        "4. 直接可执行（用户点击即发送）\n"
        "5. 仅输出 JSON 数组，每项含 dim 与 question：\n"
        "   [{\"dim\":\"deep_dive\",\"question\":\"问题1\"},{\"dim\":\"method\",\"question\":\"问题2\"},{\"dim\":\"cross_domain\",\"question\":\"问题3\"}]\n"
        "   dim 仅允许 deep_dive | method | cross_domain 之一\n"
        "6. 不要任何额外说明、不要 markdown 代码块、不要前后空行"
    )

    human_content = f"{snapshot_brief}{covered_brief}{context_hint}\n\n【任务】{task_desc}\n"

    # 第 6 项：基于脚本做透明化说明
    desc = _based_on_desc(based_on)

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        resp = llm.invoke([SystemMessage(content=system_content), HumanMessage(content=human_content)])
        text = resp.content.strip()

        # 容错：剥离 markdown 代码块
        if text.startswith("```"):
            text = re.sub(r"^```[a-z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text).strip()

        data = json.loads(text)
        questions: List[str] = []
        dims: List[str] = []
        if isinstance(data, list):
            if all(isinstance(x, str) for x in data):
                # 兼容旧版纯字符串数组输出
                questions = [x.strip() for x in data if x.strip()][:top_k]
            else:
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    q = str(item.get("question", "")).strip()
                    dim = str(item.get("dim", "")).strip()
                    if q and q not in questions:
                        questions.append(q[:80])
                        dims.append(dim if dim in {"deep_dive", "method", "cross_domain"} else "other")

        if not questions:
            return {"questions": [], "dims": [], "based_on": based_on, "based_on_desc": desc,
                    "error": "LLM 未返回有效问题"}

        return {
            "questions": questions[:top_k],
            "dims": (dims or [])[:top_k],
            "based_on": based_on,
            "based_on_desc": desc,
        }
    except Exception as e:
        logger.warning(f"建议生成失败: {e}")
        return {"questions": [], "dims": [], "based_on": "error", "based_on_desc": "", "error": str(e)}


def build_orchestrator_graph():
    """构建完整编排图"""
    workflow = StateGraph(OrchestratorState)

    workflow.add_node("orchestrator", orchestrator_node)
    workflow.set_entry_point("orchestrator")

    def should_continue(state: dict) -> Literal["orchestrator", "__end__"]:
        if state.get("errors") and state.get("retry_count", 0) < 3:
            logger.info(f"Orchestrator 重试: {state['retry_count']}/3")
            return "orchestrator"
        return "__end__"

    workflow.add_conditional_edges(
        "orchestrator",
        should_continue,
        {
            "orchestrator": "orchestrator",
            "__end__": END
        }
    )

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)