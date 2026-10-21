"""執行摘要（summary.md）：題目要求的類別分佈、需人工比例與資料問題。只負責格式化，不影響分流結果。"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import llm
from rules import NON_ZH, Ticket
from triage import ARCHIVED, FLAG_DEFINITIONS, NEXT_STEP_DEFINITIONS, PII, URGENT, Triage

# 摘要裡 category 的說明：模型的路徑定義加上規則判斷的非中文
CATEGORY_DEFINITIONS = {
    **{code: f"{name}：{desc}" for code, (name, desc) in llm.PATH_DEFINITIONS.items()},
    NON_ZH: "非中文：主要不是用中文寫的工單，由規則依中文字元比例判斷",
}
NO_TOOLS = "（無）"


def _ids(items) -> str:
    return "、".join(x.ticket_id for x in items) or "無"


def _notes(definitions: dict[str, str], codes) -> list[str]:
    """表格下方的值說明，只列表格裡出現的值。"""
    return ["", *[f"- `{c}`：{definitions[c]}" for c in codes if c in definitions]]


def _route_of(results: list[Triage]) -> str:
    """同一個 category 通常只有一種 route；高風險會蓋過路徑，所以混合時列出各自筆數。"""
    routes = Counter(r.route for r in results)
    return next(iter(routes)) if len(routes) == 1 else "、".join(f"{k} {v} 筆" for k, v in routes.most_common())


def _model_only(r: Triage, prefix: str) -> bool:
    """某個旗標的所有來源都標著（模型），代表規則與程式計算都沒有命中，值得人工多看一眼。"""
    sources = [x for x in r.reasons if x.startswith(prefix)]
    return bool(sources) and all(x.endswith("（模型）") for x in sources)


def write_summary(results: list[Triage], tickets: list[Ticket], source: Path, path: Path) -> None:
    n = len(results)
    archived = [r for r in results if r.category in ARCHIVED]
    in_process = [r for r in results if r.category not in ARCHIVED]
    human = [r for r in in_process if r.route == "human"]

    lines = [
        "# 執行摘要",
        "",
        f"- 輸入：`{source.name}`，共 {n} 筆；處理路徑由本地模型 `{llm.MODEL}` 判斷（非中文由規則判斷）",
        f"- 封存、不進客服流程：{len(archived)} 筆（{_ids(archived)}）；PoC 與試營運期間，每筆封存與轉其他部門都要人工確認",
        f"- 進客服流程：{len(in_process)} 筆，其中 route=human {len(human)} 筆（{len(human) / len(in_process):.0%}），"
        f"route=auto {len(in_process) - len(human)} 筆",
        "",
        "route=auto 代表 AI 可查資料並草擬，**客服確認後才送出**，不是自動寄出；route=human 代表 AI 不草擬，由人處理。",
        "",
        "## 處理路徑",
        "",
        "| category | 筆數 | 占比 | route |",
        "|---|---:|---:|---|",
    ]
    categories = Counter(r.category for r in results).most_common()
    for cat, k in categories:
        lines.append(f"| `{cat}` | {k} | {k / n:.0%} | {_route_of([r for r in results if r.category == cat])} |")
    lines += _notes(CATEGORY_DEFINITIONS, [c for c, _ in categories])

    steps = Counter(r.next_step for r in results).most_common()
    lines += ["", "## 下一步", "", "| next_step | 筆數 | 占比 |", "|---|---:|---:|"]
    lines += [f"| `{s}` | {k} | {k / n:.0%} |" for s, k in steps]
    lines += _notes(NEXT_STEP_DEFINITIONS, [s for s, _ in steps])

    drafted = [r for r in results if r.ai_draft]
    tools = Counter(";".join(r.allowed_tools) or NO_TOOLS for r in drafted).most_common()
    lines += ["", "## AI 可用的查詢工具（AI 草擬的工單）", "", "| allowed_tools | 筆數 | 占比 |", "|---|---:|---:|"]
    lines += [f"| `{t}` | {k} | {k / len(drafted):.0%} |" for t, k in tools]
    lines += _notes({**llm.TOOL_DEFINITIONS, NO_TOOLS: "不需要查詢就能草擬，或模型沒有請求工具"},
                    [*llm.TOOLS, NO_TOOLS] if any(t == NO_TOOLS for t, _ in tools) else llm.TOOLS)
    lines.append("- 多個工具以 `;` 分隔；實際開放的工具是模型的請求與該路徑上限的交集")

    urgent = [r for r in results if r.priority == URGENT]
    flag_counts = Counter(f for r in results for f in r.risk_flags).most_common()
    lines += ["", "## 優先級與風險旗標", "", f"- `{URGENT}`：{len(urgent)} 筆（{_ids(urgent)}）"]
    lines += [f"- `{f}`：{k} 筆（{_ids([r for r in results if f in r.risk_flags])}）" for f, k in flag_counts]
    lines.append(f"- 只由模型判定的急件：{_ids([r for r in results if _model_only(r, '急件：')])}")
    lines.append(f"- 只由模型判定的高風險：{_ids([r for r in results if _model_only(r, '高風險：')])}")
    lines += _notes(FLAG_DEFINITIONS, [URGENT, *[f for f, _ in flag_counts]])

    # 資料問題分兩組，與 README 的資料雜訊表一致
    by_customer: dict[str, list[Ticket]] = {}
    for t in tickets:
        by_customer.setdefault(t.customer_name.strip(), []).append(t)
    repeats = "；".join(_ids(ts).replace("、", "／") for ts in by_customer.values() if len(ts) > 1) or "無"
    lines += [
        "",
        "## 資料問題",
        "",
        "### 前處理雜訊（不修改原始資料）",
        "",
        f"- 測試資料與垃圾信，由模型判斷後封存：{_ids(archived)}",
        f"- 同一位客人多張工單，不合併、各自分流（設計上會串接未結工單，PoC 未實作）：{repeats}",
        "- HTML 與簽名檔、全形字元、連續空白、重複標點：不處理，不影響模型判讀（見 README）",
        "",
        "### 看起來像雜訊、其實是業務情況，交給分類處理",
        "",
        f"- 內文過短 → `{llm.INSUFFICIENT}`：{_ids([r for r in results if r.category == llm.INSUFFICIENT])}",
        f"- 非中文 → `{NON_ZH}`（規則判斷）：{_ids([r for r in results if r.category == NON_ZH])}",
        f"- 內文含結構化個資 → `{PII}` 旗標：{_ids([r for r in results if PII in r.risk_flags])}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
