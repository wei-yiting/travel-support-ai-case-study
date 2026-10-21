"""規則（程式）：只做三件事。

1. 高風險與止付的地板：只認明確字眼。模型可以再升級，不能撤銷（docs/case-study.md 4.2：規則的標記 AI 只能升級）。
2. 結構化個資的格式驗證：證號、手機、帳號、卡號有固定格式，格式比對比模型準。
3. 非中文：算中文字元的比例，是固定的計算，不需要理解語意。
其餘需要理解語意的判斷（處理路徑、出發日期、退款金額）都交給模型。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

NON_ZH = "non_chinese"
NON_ZH_MAX_CJK_SHARE = 0.5

# 公開或法律威脅：高風險＋急件
PUBLIC_THREAT_KEYWORDS = ["消保官", "消基會", "爆料", "律師", "提告"]
# 「媒體」單獨出現不算（記者邀訪不是威脅），要搭配威脅動詞
PUBLIC_THREAT_PATTERNS = [
    re.compile(r"(找|聯絡|投訴)\S{0,4}媒體"),
    re.compile(r"(社團|網路|臉書|PTT|Dcard)\S{0,3}公開"),
]
# 要求賠償：只算高風險
COMPENSATION_KEYWORDS = ["賠償"]
# 揚言止付或爭議款：急件
CHARGEBACK_KEYWORDS = ["止付", "爭議款", "拒付"]

# 前後不能接英數字，避免把訂單編號 LT2026… 誤判成身分證字號
PII_PATTERNS = {
    "身分證字號": re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?!\d)"),
    "手機號碼": re.compile(r"(?<!\d)09\d{2}-?\d{3}-?\d{3}(?!\d)"),
    "銀行帳號": re.compile(r"(?<!\d)\d{3}-\d{8,14}(?!\d)"),
    "信用卡號": re.compile(r"(?<!\d)\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}(?!\d)"),
}


@dataclass
class Ticket:
    ticket_id: str
    created_at: datetime
    channel: str
    customer_name: str
    subject: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.subject}\n{self.body}"


@dataclass
class RuleResult:
    """每個欄位是命中的字眼或個資類型；空值代表沒命中。non_chinese 有值時，處理路徑直接定為非中文。"""
    non_chinese: str = ""
    public_threat: list[str] = field(default_factory=list)
    compensation: list[str] = field(default_factory=list)
    chargeback: list[str] = field(default_factory=list)
    pii: list[str] = field(default_factory=list)


def _hits(text: str, keywords: list[str]) -> list[str]:
    return [k for k in keywords if k in text]


def _non_chinese(text: str) -> str:
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if latin and cjk / (cjk + latin) < NON_ZH_MAX_CJK_SHARE:
        return f"中文字元占比 {cjk / (cjk + latin):.0%} < {NON_ZH_MAX_CJK_SHARE:.0%}"
    return ""


def apply_rules(t: Ticket) -> RuleResult:
    text = t.text
    return RuleResult(
        non_chinese=_non_chinese(text),
        public_threat=_hits(text, PUBLIC_THREAT_KEYWORDS) + [m.group(0) for p in PUBLIC_THREAT_PATTERNS if (m := p.search(text))],
        compensation=_hits(text, COMPENSATION_KEYWORDS),
        chargeback=_hits(text, CHARGEBACK_KEYWORDS),
        pii=[name for name, p in PII_PATTERNS.items() if p.search(text)],
    )
