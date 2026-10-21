"""合併規則與模型的結果，再依 case study 4.1 的流程對應出 route、可用工具、是否草擬、下一步。

分工：
- 模型（llm.py）：處理路徑、急件、高風險，以及出發日期、客人主張的金額、需要的查詢工具
- 規則（rules.py）：非中文（直接決定處理路徑）、高風險與止付的地板（明確字眼）、結構化個資
- 本檔：急件與高風險取模型與規則的聯集（規則的標記不會被模型撤銷），出發日是否在 3 天內由程式計算，
  route 等欄位查表決定，可用工具是模型的要求再套上各路徑的上限

輸出的結構化欄位一律用英文代碼，方便後續程式比對；reason 是給客服看的說明，維持中文。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import llm
from rules import NON_ZH, RuleResult, Ticket, apply_rules

URGENT = "urgent"
NORMAL = "normal"
HIGH_RISK = "high_risk"
SUPERVISOR = "supervisor_approval"
PII = "pii"

AGENT_REVIEW_SEND = "agent_review_then_send"
AGENT_REVIEW_SUPERVISOR = "agent_review_then_supervisor"
SENIOR_HANDLES = "senior_agent_handles"
AGENT_HANDLES = "agent_handles"
FORWARD = "forward_to_department"
ARCHIVE = "archive"

# 優先級、旗標、下一步的意義只寫在這裡，執行摘要由這兩張表產生說明
FLAG_DEFINITIONS = {
    URGENT: "急件：不當天處理就會造成損失或事態擴大，排在佇列最前面",
    HIGH_RISK: "高風險：揚言公開或走法律途徑，或明確要求賠償",
    SUPERVISOR: "需主管簽核（提示）：客人主張的退款或賠償金額超過 30,000 元；正式判斷在查訂單後",
    PII: "含個資：內文有身分證、手機、銀行帳號或信用卡號的格式",
}
NEXT_STEP_DEFINITIONS = {
    AGENT_REVIEW_SEND: "AI 查資料並草擬，客服確認後送出",
    AGENT_REVIEW_SUPERVISOR: "AI 查資料並草擬，客服確認、主管簽核後送出",
    SENIOR_HANDLES: "高風險，由資深客服或主管全程處理，AI 不草擬",
    AGENT_HANDLES: "客服人工處理，AI 不草擬",
    FORWARD: "轉給客服以外的部門處理",
    ARCHIVE: "垃圾信或測試資料，封存、不回覆",
}

URGENT_WITHIN_DAYS = 3
REFUND_APPROVAL_THRESHOLD = 30_000

ARCHIVED = {llm.SPAM, llm.TEST}
# 各 auto 路徑的查詢工具上限，由程式決定、不由模型決定；不在表內的路徑轉人工、不開放工具。
# 模型提出需要的工具，實際只開放與上限的交集。
TOOL_CEILING = {
    llm.ORDER: {llm.GET_ORDER, llm.SEARCH_POLICY},
    llm.REFUND: {llm.GET_ORDER, llm.SEARCH_POLICY},
    llm.POLICY: {llm.SEARCH_POLICY},
    # 先從寄件者本人的訂單補資訊，仍不足才請客人補充
    llm.INSUFFICIENT: {llm.GET_ORDER},
}
HUMAN_NEXT_STEP = {
    llm.COMPLAINT: AGENT_HANDLES,
    llm.OTHER_DEPT: FORWARD,
    llm.PRODUCT: AGENT_HANDLES,
    llm.EXTERNAL: AGENT_HANDLES,
    NON_ZH: AGENT_HANDLES,
}


@dataclass
class Triage:
    ticket_id: str
    category: str
    priority: str
    risk_flags: list[str]
    route: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    ai_draft: bool = False
    next_step: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        return "；".join(self.reasons)


def _route(r: Triage, requested: list[str]) -> None:
    ceiling, scope = set(), r.category
    if r.category in ARCHIVED:
        r.route, r.ai_draft, r.next_step = "auto", False, ARCHIVE
    elif HIGH_RISK in r.risk_flags:
        r.route, r.ai_draft, r.next_step, scope = "human", False, SENIOR_HANDLES, HIGH_RISK
    elif r.category in TOOL_CEILING:
        ceiling = TOOL_CEILING[r.category]
        r.route, r.ai_draft = "auto", True
        r.next_step = AGENT_REVIEW_SUPERVISOR if SUPERVISOR in r.risk_flags else AGENT_REVIEW_SEND
    else:
        r.route, r.ai_draft, r.next_step = "human", False, HUMAN_NEXT_STEP[r.category]

    r.allowed_tools = [t for t in llm.TOOLS if t in requested and t in ceiling]
    r.reasons += [f"擋下：{t} 不在 {scope} 的上限內" for t in llm.TOOLS if t in requested and t not in ceiling]


def _days_until_departure(departure: str, t: Ticket) -> int | None:
    try:
        return (date.fromisoformat(departure) - t.created_at.date()).days
    except ValueError:
        return None


def merge(t: Ticket, rules: RuleResult, model: llm.ModelResult) -> Triage:
    """急件與高風險都是聯集：模型、規則、程式計算任一成立就成立，每個來源都寫進 reasons。"""
    urgent, high_risk = [], []

    if model.urgent:
        urgent.append(f"{model.urgent_reason or '模型判斷'}（模型）")
    days = _days_until_departure(model.departure_date, t)
    if days is not None and 0 <= days <= URGENT_WITHIN_DAYS:
        urgent.append(f"出發日 {model.departure_date} 距建單 {days} 天（程式計算）")
    if rules.chargeback:
        urgent.append(f"揚言止付／爭議款（規則：{'、'.join(rules.chargeback)}）")
    if rules.public_threat:
        urgent.append(f"公開或法律威脅（規則：{'、'.join(rules.public_threat)}）")

    if model.high_risk:
        high_risk.append(f"{model.high_risk_reason or '模型判斷'}（模型）")
    if rules.public_threat:
        high_risk.append(f"公開或法律威脅（規則：{'、'.join(rules.public_threat)}）")
    if rules.compensation:
        high_risk.append(f"要求賠償（規則：{'、'.join(rules.compensation)}）")

    # reason 開頭標明處理路徑由誰判斷；冒號後面是模型自己寫的依據，或規則的計算結果
    if rules.non_chinese:
        category, reasons = NON_ZH, [f"規則判路徑：非中文（{rules.non_chinese}）"]
    else:
        category, reasons = model.category, [f"模型判路徑：{model.reason}"]

    flags = []
    reasons += [f"急件：{x}" for x in urgent]
    reasons += [f"高風險：{x}" for x in high_risk]
    if high_risk:
        flags.append(HIGH_RISK)
    if model.claimed_amount > REFUND_APPROVAL_THRESHOLD:
        flags.append(SUPERVISOR)
        reasons.append(f"需主管簽核（提示）：客人主張 {model.claimed_amount:,} 元 > {REFUND_APPROVAL_THRESHOLD:,}，"
                       "正式判斷在查訂單後")
    if rules.pii:
        flags.append(PII)
        reasons.append(f"含個資：{'、'.join(rules.pii)}格式")

    r = Triage(t.ticket_id, category, URGENT if urgent else NORMAL, flags, reasons=reasons)
    _route(r, model.needed_tools)
    return r


def triage(t: Ticket) -> Triage:
    return merge(t, apply_rules(t), llm.classify(t))
