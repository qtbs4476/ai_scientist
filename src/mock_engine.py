
from __future__ import annotations

import asyncio
import copy
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from .db import count_researches, init_db, list_research_rows, load_research, save_research

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = ROOT / "data" / "science_125.json"
MAX_AUTO_ROUNDS = 3

with QUESTIONS_PATH.open("r", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

QUESTION_MAP = {int(q["id"]): q for q in QUESTIONS}

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def now_hm() -> str:
    return datetime.now().strftime("%H:%M")

def gate_name(gate: str) -> str:
    return {
        "debate": "思辨审查",
        "trace": "溯源审查",
        "causal": "因果审查",
    }.get(gate, gate)

def status_name(status: str) -> str:
    return {
        "pending": "等待",
        "running": "审查中",
        "passed": "通过",
        "conditional": "有条件通过",
        "failed": "未通过",
    }.get(status, status)

def make_gate_detail(
    gate: str,
    status: str,
    score: int,
    verdict: str,
    summary: str,
    criteria: list[tuple[str, str, str]],
    issues: list[tuple[str, str, str, str]],
    evidence: list[tuple[str, str]],
) -> dict:
    return {
        "gate": gate,
        "gate_name": gate_name(gate),
        "status": status,
        "status_name": status_name(status),
        "score": score,
        "verdict": verdict,
        "summary": summary,
        "criteria": [
            {"name": name, "result": result, "detail": detail}
            for name, result, detail in criteria
        ],
        "issues": [
            {
                "title": title,
                "severity": severity,
                "evidence": evidence_text,
                "recommendation": recommendation,
            }
            for title, severity, evidence_text, recommendation in issues
        ],
        "evidence": [
            {"source": source, "detail": detail}
            for source, detail in evidence
        ],
    }

def audit_trace(gate: str, detail: dict) -> list[dict]:
    criteria = detail.get("criteria") or []
    evidence = detail.get("evidence") or []
    issues = detail.get("issues") or []
    criteria_text = "\u3001".join(item["name"] for item in criteria[:3]) or "\u6838\u5fc3\u5ba1\u67e5\u6807\u51c6"
    source = evidence[0] if evidence else {"source": "\u5f53\u524d\u7814\u7a76\u8bb0\u5f55", "detail": "\u672a\u8fd4\u56de\u989d\u5916\u5916\u90e8\u8bc1\u636e\u3002"}
    issue = issues[0] if issues else None
    reasoning = detail.get("summary") or "\u6839\u636e\u5f53\u524d\u5ba1\u67e5\u6750\u6599\u5f62\u6210\u9636\u6bb5\u6027\u5224\u65ad\u3002"
    if issue:
        reasoning += f" \u91cd\u70b9\u6838\u67e5\uff1a{issue['evidence']}"
    return [
        {"stage": "focus", "label": "\u5ba1\u67e5\u76ee\u6807", "text": f"\u68c0\u67e5{criteria_text}\u662f\u5426\u8db3\u4ee5\u652f\u6301\u5f53\u524d\u5047\u8bbe\u3002"},
        {"stage": "evidence", "label": "\u6838\u67e5\u4f9d\u636e", "text": f"{source['source']}\uff1a{source['detail']}"},
        {"stage": "reasoning", "label": "\u5224\u65ad\u8def\u5f84", "text": reasoning},
    ]

def debate_detail(round_no: int, status: str) -> dict:
    if status == "passed":
        return make_gate_detail(
            "debate", "passed", 89,
            "关键逻辑漏洞已经得到回应，假设边界足够明确。",
            "当前假设不再把所有国家和监测条件视为同质，并主动承认反例与适用限制。",
            [
                ("反例覆盖", "通过", "已针对历史上缺少稳定前驱信号的疫情补充反例解释。"),
                ("适用边界", "通过", "适用范围缩小到具备连续监测能力的地区。"),
                ("替代解释", "通过", "已加入政策响应、行为变化与数据缺失等替代解释。"),
            ],
            [],
            [
                ("历史疫情反例集合", "用于检查候选假设是否能解释未出现明显预警信号的案例。"),
                ("假设修订记录", "第 1 轮提出的范围过宽问题已经在第 2 轮修订。"),
            ],
        )
    if status == "conditional":
        return make_gate_detail(
            "debate", "conditional", 74,
            "主要逻辑链基本成立，但仍存在一项重要边界问题。",
            "可以继续推进，但最终报告必须明确保留意见，并等待专家确认外推范围。",
            [
                ("反例覆盖", "通过", "主要反例已讨论。"),
                ("适用边界", "有条件", "低资源地区的外推边界仍缺乏足够说明。"),
                ("替代解释", "通过", "已覆盖主要替代解释。"),
            ],
            [
                ("低资源地区外推仍偏强", "中",
                 "可用数据主要来自监测体系较完整地区。",
                 "建议由专家进一步限定结论适用人群与地区。"),
            ],
            [
                ("跨地区数据可得性比较", "显示不同地区监测数据完整度存在明显差异。"),
            ],
        )
    return make_gate_detail(
        "debate", "failed", 58 if round_no == 1 else 64,
        "发现关键逻辑漏洞，当前假设暂不应作为最终科研结论。",
        "主要问题集中在适用范围过宽、反例解释不足以及行为因素缺失。",
        [
            ("反例覆盖", "未通过", "至少存在多个历史反例尚未被当前假设解释。"),
            ("适用边界", "未通过", "将高资源地区结论直接外推到低资源地区。"),
            ("替代解释", "有条件", "政策和行为变量只被部分考虑。"),
        ],
        [
            ("适用范围过宽", "高",
             "当前假设默认不同国家都拥有近似连续的监测数据。",
             "缩小适用范围，并把数据完整度写成明确的适用条件。"),
            ("反例解释不足", "高",
             "部分历史疫情没有明显的多源前驱信号。",
             "加入反例分析，并明确哪些情形会削弱当前假设。"),
            ("人类行为因素不足", "中",
             "政策响应、公众行为变化可能改变传播速度。",
             "把政策与行为变量作为替代解释或混杂因素进入分析。"),
        ],
        [
            ("历史疫情时间序列", "用于寻找没有稳定前驱信号的反例。"),
            ("跨地区监测覆盖数据", "用于判断结论能否外推到低资源地区。"),
        ],
    )

def trace_detail(status: str = "passed") -> dict:
    if status == "failed":
        return make_gate_detail(
            "trace", "failed", 45,
            "发现至少一条核心引用无法可靠溯源。",
            "存在引用真实性或引用语义与论断不匹配的问题。",
            [
                ("引用真实性", "未通过", "至少一条核心引用无法确认出版信息。"),
                ("语义一致性", "有条件", "部分论文只支持相关性而非当前强表述。"),
                ("来源质量", "通过", "其余来源质量可接受。"),
            ],
            [
                ("核心引用无法核验", "高", "论文元数据无法匹配。", "删除或替换该引用，并重新执行溯源审查。"),
            ],
            [("文献元数据核验", "通过题名、作者、年份与 DOI/索引信息进行交叉检查。")],
        )
    return make_gate_detail(
        "trace", "passed", 94,
        "核心引用均可追溯，未发现明显虚假引用。",
        "12 篇核心引用的元数据与当前论断能够对应，且未发现明显断章取义。",
        [
            ("引用真实性", "通过", "12/12 篇核心引用可追溯到真实出版记录。"),
            ("语义一致性", "通过", "引用内容与当前论断基本一致。"),
            ("来源质量", "通过", "核心来源以同行评议论文为主。"),
        ],
        [],
        [
            ("核心引用元数据", "核对题名、作者、年份与 DOI/索引信息。"),
            ("摘要/证据片段", "检查论文实际支持的结论强度。"),
        ],
    )

def causal_detail(round_no: int, status: str) -> dict:
    if status == "passed":
        return make_gate_detail(
            "causal", "passed", 86,
            "关键因果风险已经得到控制，证据不足的关系已降级为相关性表述。",
            "当前版本明确区分预测关联与因果解释，并把混杂因素和敏感性分析纳入研究计划。",
            [
                ("混杂控制", "通过", "人口规模、政策干预、监测强度进入验证方案。"),
                ("统计显著性", "通过", "关键预测关系达到 Mock 阈值。"),
                ("因果表述强度", "通过", "证据不足的关系不再宣称直接因果。"),
            ],
            [],
            [
                ("分层回归 Mock 结果", "关键预测变量在控制主要混杂项后仍保留预测价值。"),
                ("敏感性分析方案", "用于检查结论对模型设定和缺失数据处理的稳定性。"),
            ],
        )
    if status == "conditional":
        return make_gate_detail(
            "causal", "conditional", 72,
            "预测价值存在，但直接因果解释仍不充分。",
            "可作为预测模型继续研究，但正式报告必须使用相关性/预测性语言。",
            [
                ("混杂控制", "有条件", "仍有部分不可观测混杂因素。"),
                ("统计显著性", "通过", "部分核心变量达到阈值。"),
                ("因果表述强度", "有条件", "必须避免直接因果措辞。"),
            ],
            [
                ("不可观测混杂仍存在", "中",
                 "政策强度和行为变化无法被完整量化。",
                 "最终结论保留为预测相关性，并设计进一步准实验验证。"),
            ],
            [
                ("Mock 敏感性分析", "显示方向稳定，但不能排除全部未观测混杂。"),
            ],
        )
    return make_gate_detail(
        "causal", "failed", 54 if round_no == 1 else 61,
        "当前数据不足以支持核心因果表述。",
        "航空网络与传播速度之间存在相关性，但尚不能排除人口规模、政策干预和监测强度等混杂因素。",
        [
            ("混杂控制", "未通过", "关键混杂因素尚未被充分控制。"),
            ("统计显著性", "未通过", "部分变量在独立时间窗口中不稳定。"),
            ("因果表述强度", "未通过", "当前文字把预测关联写成直接因果。"),
        ],
        [
            ("混杂因素控制不足", "高",
             "人口规模、政策干预和监测强度都可能同时影响航空流动与传播速度。",
             "加入分层/匹配/敏感性分析，并降低因果措辞。"),
            ("统计显著性不稳定", "高",
             "部分变量在独立时间窗口中没有稳定达到阈值。",
             "进行时间外验证并报告置信区间，而不是只报告单次显著性。"),
        ],
        [
            ("Mock 回归分析", "用于演示显著性和混杂控制结果。"),
            ("时间外验证窗口", "用于检查预测关系是否跨时间稳定。"),
        ],
    )

def round_plan(question_id: int, round_no: int) -> dict[str, dict]:
    # #27 is the special demo branch: 3 automatic rounds still cannot fully pass.
    if int(question_id) == 27:
        plan = {
            1: {"debate": "failed", "trace": "passed", "causal": "failed"},
            2: {"debate": "conditional", "trace": "passed", "causal": "failed"},
            3: {"debate": "conditional", "trace": "passed", "causal": "failed"},
        }[min(round_no, 3)]
    else:
        plan = {
            1: {"debate": "failed", "trace": "passed", "causal": "failed"},
            2: {"debate": "passed", "trace": "passed", "causal": "passed"},
            3: {"debate": "passed", "trace": "passed", "causal": "passed"},
        }[min(round_no, 3)]

    return {
        "debate": debate_detail(round_no, plan["debate"]),
        "trace": trace_detail(plan["trace"]),
        "causal": causal_detail(round_no, plan["causal"]),
    }

def blank_gates() -> dict:
    return {
        g: {"status": "pending", "progress": 0, "detail": None}
        for g in ("debate", "trace", "causal")
    }

def seed_history() -> None:
    init_db()
    if count_researches() > 0:
        return

    seeds = [
        ("history_dark", 45, "completed", 2, "三重审查通过"),
        ("history_mind", 27, "needs_human", 3, "自动审查 3 轮后仍需人工介入"),
        ("history_climate", 88, "completed", 2, "三重审查通过"),
        ("history_life", 117, "completed", 3, "三重审查通过"),
    ]
    for rid, qid, status, round_no, note in seeds:
        q = QUESTION_MAP[qid]
        gates = round_plan(qid, min(round_no, 3))
        stored_gates = {
            g: {
                "status": detail["status"],
                "progress": 100,
                "issues": [x["title"] for x in detail["issues"]],
                "detail": detail,
            }
            for g, detail in gates.items()
        }
        if status == "completed":
            for g in stored_gates:
                stored_gates[g]["status"] = "passed"
                stored_gates[g]["detail"] = (
                    debate_detail(2, "passed") if g == "debate"
                    else trace_detail("passed") if g == "trace"
                    else causal_detail(2, "passed")
                )

        hypothesis = {
            "title": f"关于“{q['title']}”的可验证候选科学假设",
            "summary": "这是持久化历史研究的 Mock 假设摘要。",
        }
        result = None
        if status == "completed":
            result = make_final_result(q, hypothesis, round_no, human_feedback=None)

        research = {
            "id": rid,
            "question": q,
            "status": status,
            "round": round_no,
            "stage": "completed" if status == "completed" else "human_intervention",
            "created_at": "2026-08-12T10:00:00",
            "updated_at": "2026-08-12T10:30:00",
            "note": note,
            "gates": stored_gates,
            "hypothesis": hypothesis,
            "result": result,
            "feedbacks": [],
            "revision_history": [],
            "stream_generation": 0,
        }
        save_research(research)

def list_questions(q: str = "", category: str = "") -> list[dict]:
    q_norm = (q or "").strip().lower()
    category = (category or "").strip()
    rows = []
    for item in QUESTIONS:
        if category and category != "全部" and item["category"] != category:
            continue
        hay = f"{item['id']} {item['title']} {item['category']} {item['summary']}".lower()
        if q_norm and q_norm not in hay:
            continue
        rows.append(item)
    return rows

def list_researches() -> list[dict]:
    rows = []
    for r in list_research_rows():
        rows.append({
            "id": r["id"],
            "question": r["question"],
            "status": r["status"],
            "round": r["round"],
            "stage": r["stage"],
            "note": r.get("note", ""),
            "updated_at": r["updated_at"],
        })
    return rows

def get_research(research_id: str) -> dict | None:
    r = load_research(research_id)
    return copy.deepcopy(r) if r else None

def start_research(question_id: int) -> dict:
    question = QUESTION_MAP.get(int(question_id))
    if not question:
        raise KeyError("question_not_found")
    rid = f"r_{uuid.uuid4().hex[:10]}"
    research = {
        "id": rid,
        "question": question,
        "status": "running",
        "round": 0,
        "stage": "created",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "note": "准备开始研究",
        "gates": blank_gates(),
        "hypothesis": None,
        "result": None,
        "feedbacks": [],
        "revision_history": [],
        "stream_generation": 0,
    }
    save_research(research)
    return copy.deepcopy(research)

def stop_research(research_id: str) -> dict:
    r = load_research(research_id)
    if not r:
        raise KeyError(research_id)
    r["status"] = "stopped"
    r["stage"] = "stopped"
    r["note"] = "研究已停止"
    r["updated_at"] = now_iso()
    r["stream_generation"] += 1
    save_research(r)
    return copy.deepcopy(r)

def infer_impacted_gates(message: str) -> list[str]:
    impacted = []
    if any(k in message for k in ["文献", "引用", "论文", "溯源", "来源"]):
        impacted.append("trace")
    if any(k in message for k in ["因果", "统计", "显著", "混杂", "相关", "回归"]):
        impacted.append("causal")
    if any(k in message for k in ["反例", "逻辑", "范围", "假设", "漏洞", "边界", "外推"]):
        impacted.append("debate")
    if not impacted:
        impacted = ["debate", "trace", "causal"]
    return list(dict.fromkeys(impacted))

def add_feedback(research_id: str, message: str) -> dict:
    r = load_research(research_id)
    if not r:
        raise KeyError(research_id)

    impacted = infer_impacted_gates(message.strip())
    r["feedbacks"].append({
        "message": message.strip(),
        "time": now_hm(),
        "impacted_gates": impacted,
    })
    r["status"] = "running"
    r["stage"] = "feedback_received"
    r["round"] = int(r.get("round") or 0) + 1
    r["note"] = "已收到人工意见，准备重新审查"
    r["updated_at"] = now_iso()
    r["stream_generation"] += 1
    save_research(r)
    return {
        "accepted": True,
        "research_id": research_id,
        "round": r["round"],
        "impacted_gates": impacted,
        "message": "人工意见已加入当前研究，将触发相关审查重新执行。",
    }

def _event(event_type: str, **payload) -> str:
    return f"data: {json.dumps({'type': event_type, **payload}, ensure_ascii=False)}\n\n"

async def _sleep(seconds: float = 0.72):
    await asyncio.sleep(seconds)

def _alive(research_id: str, generation: int) -> bool:
    current = load_research(research_id)
    return bool(
        current
        and current.get("stream_generation") == generation
        and current.get("status") != "stopped"
    )

def store_gate(r: dict, gate: str, detail: dict) -> None:
    r["gates"][gate] = {
        "status": detail["status"],
        "progress": 100,
        "issues": [x["title"] for x in detail["issues"]],
        "detail": detail,
    }
    r["updated_at"] = now_iso()
    save_research(r)

def revision_for_round(round_no: int, previous_hypothesis: dict) -> tuple[dict, list[str]]:
    if round_no == 2:
        changes = [
            "缩小适用范围到具备连续监测能力的地区",
            "将证据不足的因果表述降级为相关性表述",
            "加入低资源地区数据缺失作为外部验证条件",
        ]
        hypothesis = {
            "title": "受监测条件约束的多源联合早期预警假设",
            "summary": "在具备连续监测能力的地区，多源异常信号与全球流动网络可用于风险分层；对缺乏充分因果证据的关系仅保留为预测相关因素。",
            "falsifiable": "若独立地区和独立时间窗口中无法稳定获得预警提前量，则该假设被削弱。",
        }
    else:
        changes = [
            "进一步限制外推范围并加入保留意见",
            "补充替代解释与敏感性分析要求",
            "明确哪些关系只能作为预测变量而不能作因果解释",
        ]
        hypothesis = {
            "title": "带保留意见的多源风险预警假设",
            "summary": "多源异常信号可能用于风险分层，但不同地区的数据缺失、政策与行为差异使外部泛化仍存在不确定性；因果解释必须保持谨慎。",
            "falsifiable": "若跨地区验证无法复现稳定的风险分层能力，则该假设不应被推广。",
        }
    return hypothesis, changes

def make_final_result(question: dict, hypothesis: dict, round_no: int, human_feedback: str | None) -> dict:
    feedback_suffix = " 本轮进一步吸收了人工专家意见并重新执行了受影响审查。" if human_feedback else ""
    return {
        "title": hypothesis.get("title", "最终科学假设"),
        "hypothesis": hypothesis.get("summary", ""),
        "score": 90 if human_feedback else 88,
        "support_evidence": 18,
        "counter_evidence": 2,
        "citations": 12,
        "conclusion": (
            f"针对“{question['title']}”，当前证据支持在明确适用边界下继续研究该候选假设。"
            "系统没有把预测相关性自动升级为直接因果结论；无法充分验证的关系被保留为相关性或有条件结论。"
            + feedback_suffix
        ),
        "falsification": hypothesis.get(
            "falsifiable",
            "若独立地区和独立时间窗口中无法稳定复现主要预测关系，则当前假设应被削弱或证伪。"
        ),
        "limitations": [
            "低资源地区监测数据的连续性和完整性不足。",
            "政策响应与人类行为变化可能影响外部泛化能力。",
            "部分变量目前只能获得预测相关性证据。",
        ],
        "review_summary": {
            "debate": "达到可接受状态：关键反例、外推边界与替代解释已明确。",
            "trace": "通过：核心引用可追溯，未发现明显虚假引用。",
            "causal": "达到可接受状态：混杂因素进入验证方案，证据不足的因果表述已降级。",
        },
        "research_plan": [
            "建立跨地区多源监测数据集",
            "预注册主要预测变量与评价指标",
            "进行时间外验证与地区外验证",
            "对关键关联做混杂控制与敏感性分析",
        ],
        "human_feedback_applied": human_feedback,
        "review_round": round_no,
    }

async def initial_flow(research_id: str, generation: int) -> AsyncIterator[str]:
    r = load_research(research_id)
    if not r:
        return
    q = r["question"]

    yield _event("message", role="assistant", text=f"已读取 Science125 #{q['id']}：{q['title']}。我会先理解问题、准备证据并形成候选科学假设。")
    await _sleep()
    if not _alive(research_id, generation): return

    r["stage"] = "problem_understanding"; r["note"] = "问题理解完成"; r["updated_at"] = now_iso(); save_research(r)
    yield _event("progress", stage="problem_understanding", status="completed", label="问题理解")
    await _sleep()
    if not _alive(research_id, generation): return

    r["stage"] = "evidence"; r["note"] = "文献与证据准备完成"; r["updated_at"] = now_iso(); save_research(r)
    yield _event("progress", stage="evidence", status="completed", label="证据准备", documents=156, core_citations=12)
    await _sleep()
    if not _alive(research_id, generation): return

    hypothesis = {
        "title": "多源监测 × 全球流动联合早期预警假设",
        "summary": "当跨宿主异常信号、病例变化、气候异常与人口流动网络同时出现一致性前驱特征时，可在部分地区提前识别风险。",
        "falsifiable": "若在独立时间窗口与外部地区中无法稳定获得提前量，则该假设不成立。",
    }
    r["hypothesis"] = hypothesis
    r["stage"] = "hypothesis"; r["note"] = "候选假设已生成"; r["updated_at"] = now_iso(); save_research(r)
    yield _event("hypothesis", hypothesis=hypothesis)
    await _sleep()
    if not _alive(research_id, generation): return

    for round_no in range(1, MAX_AUTO_ROUNDS + 1):
        if not _alive(research_id, generation): return

        r["round"] = round_no
        r["stage"] = "review"
        r["note"] = f"第 {round_no} 轮三重审查"
        r["updated_at"] = now_iso()
        save_research(r)
        yield _event("review_started", round=round_no, max_auto_rounds=MAX_AUTO_ROUNDS)
        await _sleep(.5)

        details = round_plan(q["id"], round_no)
        failed = []
        for gate in ("debate", "trace", "causal"):
            if not _alive(research_id, generation): return
            detail = details[gate]
            for step_no, step in enumerate(audit_trace(gate, detail), start=1):
                yield _event(
                    "audit_step",
                    round=round_no,
                    gate=gate,
                    step=step_no,
                    total_steps=3,
                    stage=step["stage"],
                    label=step["label"],
                    text=step["text"],
                )
                await _sleep(.42)
                if not _alive(research_id, generation): return
            store_gate(r, gate, detail)
            if detail["status"] == "failed":
                failed.append(gate)
            yield _event(
                "gate_update",
                round=round_no,
                gate=gate,
                status=detail["status"],
                progress=100,
                issues=[x["title"] for x in detail["issues"]],
                detail=detail,
            )
            await _sleep(.55)

        if not failed:
            result = make_final_result(q, r["hypothesis"], round_no, human_feedback=None)
            r["result"] = result
            r["status"] = "completed"
            r["stage"] = "completed"
            r["note"] = "三重审查达到可接受状态"
            r["updated_at"] = now_iso()
            save_research(r)
            yield _event("final_result", round=round_no, result=result)
            yield _event("stream_end")
            return

        if round_no >= MAX_AUTO_ROUNDS:
            unresolved = []
            for gate in failed:
                d = r["gates"][gate].get("detail") or {}
                unresolved.extend([
                    {
                        "gate": gate,
                        "gate_name": gate_name(gate),
                        "title": issue["title"],
                        "severity": issue["severity"],
                        "recommendation": issue["recommendation"],
                    }
                    for issue in d.get("issues", [])
                ])
            r["status"] = "needs_human"
            r["stage"] = "human_intervention"
            r["note"] = "自动审查 3 轮后仍有未解决问题，需要人工介入"
            r["updated_at"] = now_iso()
            save_research(r)
            yield _event(
                "human_intervention_required",
                round=round_no,
                failed_gates=failed,
                unresolved=unresolved,
                message="已达到 3 轮自动审查上限。系统不会为了“过审”继续自我迎合，需要专家提供新的判断或约束。",
            )
            yield _event("stream_end")
            return

        yield _event(
            "review_failed",
            round=round_no,
            failed_gates=failed,
            revision_count=sum(len((r["gates"][g].get("detail") or {}).get("issues", [])) for g in failed),
        )
        r["stage"] = "revision"
        r["note"] = "正在自动修订候选假设"
        r["updated_at"] = now_iso()
        save_research(r)
        await _sleep(.5)

        revised, changes = revision_for_round(round_no + 1, r["hypothesis"])
        r["revision_history"].append({
            "from_round": round_no,
            "to_round": round_no + 1,
            "changes": changes,
            "time": now_hm(),
        })
        r["hypothesis"] = revised
        r["updated_at"] = now_iso()
        save_research(r)
        yield _event("revision_started", round=round_no + 1, hypothesis=revised, changes=changes)
        await _sleep(.7)

async def feedback_flow(research_id: str, generation: int) -> AsyncIterator[str]:
    r = load_research(research_id)
    if not r or not r.get("feedbacks"):
        return
    fb = r["feedbacks"][-1]
    impacted = fb["impacted_gates"]
    round_no = r["round"]

    yield _event("feedback_received", round=round_no, message=fb["message"], impacted_gates=impacted)
    await _sleep()
    if not _alive(research_id, generation): return

    yield _event(
        "message",
        role="assistant",
        text=f"已收到专家意见。本次主要影响：{'、'.join(gate_name(g) for g in impacted)}。我会先吸收意见，再重新执行受影响的审查。",
    )
    await _sleep()
    if not _alive(research_id, generation): return

    changes = [
        f"吸收人工意见：{fb['message']}",
        "重新定义受影响审查的判断边界",
        "保留原有通过项，不重复降低审查标准",
    ]
    r["stage"] = "revision"
    r["note"] = "根据人工意见修订中"
    r["revision_history"].append({
        "from_round": round_no - 1,
        "to_round": round_no,
        "changes": changes,
        "time": now_hm(),
        "human": True,
    })
    r["updated_at"] = now_iso()
    save_research(r)
    yield _event("revision_started", round=round_no, hypothesis=r["hypothesis"], changes=changes)
    await _sleep()
    if not _alive(research_id, generation): return

    r["stage"] = "review"
    r["note"] = f"人工介入后的第 {round_no} 轮审查"
    r["updated_at"] = now_iso()
    save_research(r)
    yield _event("review_started", round=round_no, reason="human_feedback", max_auto_rounds=MAX_AUTO_ROUNDS)
    await _sleep(.5)

    for gate in ("debate", "trace", "causal"):
        if not _alive(research_id, generation): return

        previous = (r["gates"].get(gate) or {}).get("detail")
        if gate in impacted:
            if gate == "debate":
                detail = debate_detail(round_no, "passed")
                detail["summary"] += " 本轮明确吸收了专家提出的新边界条件。"
            elif gate == "trace":
                detail = trace_detail("passed")
                detail["summary"] += " 人工补充意见未引入不可追溯引用。"
            else:
                detail = causal_detail(round_no, "passed")
                detail["summary"] += " 本轮按照专家意见更新了混杂控制与统计验证方案。"
        else:
            detail = previous or (
                debate_detail(round_no, "conditional") if gate == "debate"
                else trace_detail("passed") if gate == "trace"
                else causal_detail(round_no, "conditional")
            )

        for step_no, step in enumerate(audit_trace(gate, detail), start=1):
            if gate not in impacted and step_no == 1:
                step = {
                    "stage": "reuse",
                    "label": "\u590d\u6838\u8303\u56f4",
                    "text": "\u672c\u5173\u672a\u53d7\u4eba\u5de5\u610f\u89c1\u76f4\u63a5\u5f71\u54cd\uff0c\u590d\u7528\u4e0a\u8f6e\u5df2\u4fdd\u5b58\u7684\u5ba1\u67e5\u6750\u6599\u5e76\u786e\u8ba4\u5176\u9002\u7528\u6027\u3002",
                }
            yield _event(
                "audit_step",
                round=round_no,
                gate=gate,
                step=step_no,
                total_steps=3,
                stage=step["stage"],
                label=step["label"],
                text=step["text"],
                skipped=gate not in impacted,
            )
            await _sleep(.42)
            if not _alive(research_id, generation): return

        # Conditional is acceptable after explicit human review; failed is not.
        store_gate(r, gate, detail)
        yield _event(
            "gate_update",
            round=round_no,
            gate=gate,
            status=detail["status"],
            progress=100,
            issues=[x["title"] for x in detail["issues"]],
            detail=detail,
            skipped=gate not in impacted,
        )
        await _sleep(.5)

    unacceptable = [
        g for g in ("debate", "trace", "causal")
        if r["gates"][g]["status"] == "failed"
    ]
    if unacceptable:
        r["status"] = "needs_human"
        r["stage"] = "human_intervention"
        r["note"] = "人工意见尚不足以解决所有未通过项"
        r["updated_at"] = now_iso()
        save_research(r)
        yield _event(
            "human_intervention_required",
            round=round_no,
            failed_gates=unacceptable,
            unresolved=[],
            message="当前人工意见尚未覆盖全部未通过问题，请继续补充专家判断。",
        )
        yield _event("stream_end")
        return

    result = make_final_result(question=r["question"], hypothesis=r["hypothesis"], round_no=round_no, human_feedback=fb["message"])
    r["result"] = result
    r["status"] = "completed"
    r["stage"] = "completed"
    r["note"] = "人工意见吸收完成，重新审查达到可接受状态"
    r["updated_at"] = now_iso()
    save_research(r)
    yield _event("final_result", round=round_no, result=result, after_feedback=True)
    yield _event("stream_end")

def build_report(research_id: str) -> dict:
    r = load_research(research_id)
    if not r:
        raise KeyError(research_id)
    q = r["question"]
    result = r.get("result") or {}
    hypothesis = r.get("hypothesis") or {}

    summaries = {}
    for gate in ("debate", "trace", "causal"):
        detail = (r.get("gates", {}).get(gate) or {}).get("detail") or {}
        summaries[gate] = detail.get("verdict") or f"{gate_name(gate)}：暂无正式结论。"

    feedbacks = [
        {
            "time": item.get("time", ""),
            "message": item.get("message", ""),
            "impacted_gates": [gate_name(g) for g in item.get("impacted_gates", [])],
        }
        for item in r.get("feedbacks", [])
    ]

    return {
        "report_title": "AI Scientist 最终科研报告",
        "research_id": research_id,
        "generated_at": now_iso(),
        "question": q,
        "status": r.get("status"),
        "review_rounds": r.get("round", 0),
        "problem_background": q.get("summary", ""),
        "final_hypothesis": {
            "title": result.get("title") or hypothesis.get("title", ""),
            "summary": result.get("hypothesis") or hypothesis.get("summary", ""),
        },
        "metrics": {
            "score": result.get("score"),
            "support_evidence": result.get("support_evidence"),
            "counter_evidence": result.get("counter_evidence"),
            "citations": result.get("citations"),
        },
        "review_summary": summaries,
        "falsification": result.get("falsification", hypothesis.get("falsifiable", "暂无")),
        "limitations": result.get("limitations", []),
        "research_plan": result.get("research_plan", []),
        "human_feedback": feedbacks,
        "conclusion": result.get(
            "conclusion",
            "当前研究尚未形成最终结论；如果仍存在未通过审查项，应先完成人工介入和重新验证。"
        ),
    }

def report_to_markdown(report: dict) -> str:
    q = report["question"]
    h = report["final_hypothesis"]
    m = report["metrics"]

    def bullets(items):
        return "".join(f"- {x}\n" for x in items) if items else "- 暂无\n"

    feedback_lines = []
    for item in report.get("human_feedback", []):
        gates = "、".join(item.get("impacted_gates", [])) or "未指定"
        feedback_lines.append(f"- **{item.get('time','')}**：{item.get('message','')}（影响：{gates}）")
    feedback_text = "\n".join(feedback_lines) if feedback_lines else "- 本次研究无人工专家介入记录。"

    return f"""# {report['report_title']}

> Research ID: `{report['research_id']}`  
> 生成时间：{report['generated_at']}

## 01 研究问题

**Science125 #{q['id']}：{q['title']}**

领域：{q.get('category','')}

{report.get('problem_background','')}

## 02 最终科学假设

### {h.get('title','')}

{h.get('summary','')}

## 03 最终综合结论

{report.get('conclusion','')}

## 04 三重科学审查

### 思辨审查
{report['review_summary'].get('debate','')}

### 溯源审查
{report['review_summary'].get('trace','')}

### 因果审查
{report['review_summary'].get('causal','')}

## 05 研究指标

- 综合评分：{m.get('score','—')} / 100
- 支持证据：{m.get('support_evidence','—')}
- 反向证据：{m.get('counter_evidence','—')}
- 有效引用：{m.get('citations','—')}
- 审查轮次：{report.get('review_rounds','—')}

## 06 可证伪条件

{report.get('falsification','')}

## 07 研究局限

{bullets(report.get('limitations',[]))}
## 08 后续研究计划

{bullets(report.get('research_plan',[]))}
## 09 人工专家介入记录

{feedback_text}

---

本报告由 AI Scientist Mock 流程生成。正式比赛版本应使用真实模型、真实文献检索、真实审查与实际统计验证结果。
"""

async def stream_research(research_id: str, reason: str = "start") -> AsyncIterator[str]:
    r = load_research(research_id)
    if not r:
        return
    generation = r["stream_generation"]
    if reason == "feedback":
        async for chunk in feedback_flow(research_id, generation):
            yield chunk
    else:
        async for chunk in initial_flow(research_id, generation):
            yield chunk

seed_history()
