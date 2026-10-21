"""模型：用本地 Ollama 執行的開源模型，依 case study 2.2 的三個維度判斷工單：處理路徑、急件、高風險，
並抽出出發日期、客人主張的金額，以及草擬時需要的查詢工具。

非中文由規則先判斷（rules.py），不在模型的選項內；模型仍會讀非中文工單，判斷急件與高風險。
規則的標記只能升級、不能被模型撤銷，合併在 triage.py。
工單內容只送到本機的 Ollama，不離開這台電腦（docs/case-study.md 2.7：外部 LLM 評估完成前，用內部部署的開源模型）。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from rules import Ticket

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen3:8b"
TIMEOUT_SECONDS = 180

# 處理路徑代碼：模型直接回傳代碼，輸出與程式比對都用同一組代碼
ORDER = "order"
REFUND = "refund_cancel"
POLICY = "policy"
INSUFFICIENT = "insufficient_info"
COMPLAINT = "complaint"
OTHER_DEPT = "other_department"
PRODUCT = "product"
EXTERNAL = "external_info"
SPAM = "spam"
TEST = "test"
# 每條路徑的中文名稱與定義只寫在這裡；prompt 與執行摘要都由這張表產生
PATH_DEFINITIONS = {
    ORDER: ("訂單查詢／變更", "要查詢或修改某一筆已成立的訂單"),
    REFUND: ("退款／取消", "要取消已成立的訂單、申請退款，或查詢退款進度"),
    POLICY: ("政策詢問", "詢問一般規定，未涉及特定訂單"),
    INSUFFICIENT: ("資訊不足", "看不出客人的需求，或缺少處理所需的基本資訊"),
    COMPLAINT: ("客訴與補償", "對已發生的服務或行程不滿，要求處理、道歉或補償"),
    OTHER_DEPT: ("轉其他部門", "不是旅客的來信，或屬於客服以外部門的事務（例如發票收據、會員帳號與付款、客服電話）"),
    PRODUCT: ("產品詢問", "尚未下訂，詢問商品的內容、價格或安排"),
    EXTERNAL: ("外部資訊", "答案取決於旅行社以外的規範，例如出入境、簽證、護照效期由政府決定，航班與行李規定由航空公司決定"),
    SPAM: ("垃圾信", "與本公司業務無關的廣告或群發信"),
    TEST: ("測試資料", "內部測試，不是真的客人"),
}
PATHS = list(PATH_DEFINITIONS)

# 模型可以提出的唯讀查詢工具（名稱即未來 function calling 的函式名；只宣告、未實作）。
# get_order 只回傳寄件者本人的訂單，需驗證所有權。送出退款申請等寫入動作不是工具，一律由客服執行。
GET_ORDER = "get_order"
SEARCH_POLICY = "search_policy"
TOOL_DEFINITIONS = {
    GET_ORDER: "查詢寄件者本人的訂單（依信中的訂單編號，或寄件者帳號下的訂單），包含內容、付款與退款狀態",
    SEARCH_POLICY: "查詢退改規則、手續費、天災處理等公司政策",
}
TOOLS = list(TOOL_DEFINITIONS)

_PATH_LINES = "\n".join(f"- {code}（{name}）：{desc}" for code, (name, desc) in PATH_DEFINITIONS.items())
_TOOL_LINES = "\n".join(f"- {code}：{desc}" for code, desc in TOOL_DEFINITIONS.items())

SYSTEM_PROMPT = f"""你是 T 旅遊客服的工單分流助手，只做判斷，不回覆客人。客服能查的系統只有訂單系統與政策知識。
依客人真正要解決的事判斷，不要被標題或語氣帶走。

一、處理路徑（category，選一個代碼）：依需要哪個系統或哪個單位處理來區分
{_PATH_LINES}

二、急件（urgent）：如果不在當天處理，客人就會受到損失，或事態會擴大。客人目前人在旅途中、需要當下解決的問題或抱怨（例如住宿、交通、行程安排）也算急件。

三、高風險（high_risk）：需要資深客服或主管處理的情況，也就是揚言公開或走法律途徑，或明確要求賠償。一般抱怨、退款申請、帳務問題本身不算。

四、其他欄位
- reason：30 字以內，說明選擇這個處理路徑的依據
- urgent_reason、high_risk_reason：成立時用一句話說明，不成立留空
- departure_date：客人提到的出發或使用日期（YYYY-MM-DD，年份依建單時間推斷），沒有提到就留空
- claimed_amount：客人要求退款或賠償的金額（新台幣整數），沒有提到就填 0

五、可用的查詢工具（needed_tools）：草擬回覆時需要查的資料，只選真的需要的；不需要查詢就留空。
{_TOOL_LINES}"""

# reason 放第一個：讓模型先寫依據再做判斷
SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "category": {"type": "string", "enum": PATHS},
        "urgent": {"type": "boolean"},
        "urgent_reason": {"type": "string"},
        "high_risk": {"type": "boolean"},
        "high_risk_reason": {"type": "string"},
        "departure_date": {"type": "string"},
        "claimed_amount": {"type": "integer"},
        "needed_tools": {"type": "array", "items": {"type": "string", "enum": TOOLS}},
    },
    "required": ["reason", "category", "urgent", "urgent_reason",
                 "high_risk", "high_risk_reason", "departure_date", "claimed_amount", "needed_tools"],
}


class ModelUnavailable(RuntimeError):
    pass


@dataclass
class ModelResult:
    reason: str
    category: str
    urgent: bool
    urgent_reason: str
    high_risk: bool
    high_risk_reason: str
    departure_date: str
    claimed_amount: int
    needed_tools: list[str]


def _request(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{OLLAMA_URL}{path}", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.load(resp)


def check_ready() -> None:
    try:
        models = [m["name"] for m in _request("/api/tags")["models"]]
    except (urllib.error.URLError, OSError) as e:
        raise ModelUnavailable(f"連不到 Ollama（{OLLAMA_URL}）：{e}。請先安裝並啟動 Ollama。") from e
    if MODEL not in models:
        raise ModelUnavailable(f"Ollama 裡沒有 {MODEL}。請先執行：ollama pull {MODEL}")


def classify(t: Ticket) -> ModelResult:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"建單時間：{t.created_at:%Y-%m-%d %H:%M}\n寄件者：{t.customer_name}\n"
                                        f"標題：{t.subject}\n內文：{t.body}"},
        ],
        "format": SCHEMA,
        "think": False,
        "stream": False,
        "options": {"temperature": 0, "seed": 42},
    }
    try:
        content = _request("/api/chat", payload)["message"]["content"]
    except (urllib.error.URLError, OSError) as e:
        raise ModelUnavailable(f"{t.ticket_id} 呼叫 {MODEL} 失敗：{e}") from e
    return ModelResult(**json.loads(content))
