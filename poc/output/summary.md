# 執行摘要

- 輸入：`sample_tickets.xlsx`，共 48 筆；處理路徑由本地模型 `qwen3:8b` 判斷（非中文由規則判斷）
- 封存、不進客服流程：2 筆（TK-1008、TK-1041）；PoC 與試營運期間，每筆封存與轉其他部門都要人工確認
- 進客服流程：46 筆，其中 route=human 23 筆（50%），route=auto 23 筆

route=auto 代表 AI 可查資料並草擬，**客服確認後才送出**，不是自動寄出；route=human 代表 AI 不草擬，由人處理。

## 處理路徑

| category | 筆數 | 占比 | route |
|---|---:|---:|---|
| `refund_cancel` | 8 | 17% | auto |
| `other_department` | 8 | 17% | human |
| `order` | 7 | 15% | auto |
| `policy` | 7 | 15% | auto |
| `product` | 7 | 15% | human |
| `complaint` | 5 | 10% | human |
| `external_info` | 2 | 4% | human |
| `spam` | 1 | 2% | auto |
| `non_chinese` | 1 | 2% | human |
| `insufficient_info` | 1 | 2% | auto |
| `test` | 1 | 2% | auto |

- `refund_cancel`：退款／取消：要取消已成立的訂單、申請退款，或查詢退款進度
- `other_department`：轉其他部門：不是旅客的來信，或屬於客服以外部門的事務（例如發票收據、會員帳號與付款、客服電話）
- `order`：訂單查詢／變更：要查詢或修改某一筆已成立的訂單
- `policy`：政策詢問：詢問一般規定，未涉及特定訂單
- `product`：產品詢問：尚未下訂，詢問商品的內容、價格或安排
- `complaint`：客訴與補償：對已發生的服務或行程不滿，要求處理、道歉或補償
- `external_info`：外部資訊：答案取決於旅行社以外的規範，例如出入境、簽證、護照效期由政府決定，航班與行李規定由航空公司決定
- `spam`：垃圾信：與本公司業務無關的廣告或群發信
- `non_chinese`：非中文：主要不是用中文寫的工單，由規則依中文字元比例判斷
- `insufficient_info`：資訊不足：看不出客人的需求，或缺少處理所需的基本資訊
- `test`：測試資料：內部測試，不是真的客人

## 下一步

| next_step | 筆數 | 占比 |
|---|---:|---:|
| `agent_review_then_send` | 22 | 46% |
| `agent_handles` | 12 | 25% |
| `forward_to_department` | 8 | 17% |
| `senior_agent_handles` | 3 | 6% |
| `archive` | 2 | 4% |
| `agent_review_then_supervisor` | 1 | 2% |

- `agent_review_then_send`：AI 查資料並草擬，客服確認後送出
- `agent_handles`：客服人工處理，AI 不草擬
- `forward_to_department`：轉給客服以外的部門處理
- `senior_agent_handles`：高風險，由資深客服或主管全程處理，AI 不草擬
- `archive`：垃圾信或測試資料，封存、不回覆
- `agent_review_then_supervisor`：AI 查資料並草擬，客服確認、主管簽核後送出

## AI 可用的查詢工具（AI 草擬的工單）

| allowed_tools | 筆數 | 占比 |
|---|---:|---:|
| `get_order` | 10 | 43% |
| `search_policy` | 7 | 30% |
| `get_order;search_policy` | 5 | 22% |
| `（無）` | 1 | 4% |

- `get_order`：查詢寄件者本人的訂單（依信中的訂單編號，或寄件者帳號下的訂單），包含內容、付款與退款狀態
- `search_policy`：查詢退改規則、手續費、天災處理等公司政策
- `（無）`：不需要查詢就能草擬，或模型沒有請求工具
- 多個工具以 `;` 分隔；實際開放的工具是模型的請求與該路徑上限的交集

## 優先級與風險旗標

- `urgent`：12 筆（TK-1002、TK-1004、TK-1010、TK-1011、TK-1013、TK-1019、TK-1021、TK-1028、TK-1029、TK-1031、TK-1037、TK-1042）
- `high_risk`：3 筆（TK-1011、TK-1019、TK-1029）
- `supervisor_approval`：2 筆（TK-1015、TK-1029）
- `pii`：1 筆（TK-1023）
- 只由模型判定的急件：TK-1002、TK-1004、TK-1010、TK-1028、TK-1029
- 只由模型判定的高風險：無

- `urgent`：急件：不當天處理就會造成損失或事態擴大，排在佇列最前面
- `high_risk`：高風險：揚言公開或走法律途徑，或明確要求賠償
- `supervisor_approval`：需主管簽核（提示）：客人主張的退款或賠償金額超過 30,000 元；正式判斷在查訂單後
- `pii`：含個資：內文有身分證、手機、銀行帳號或信用卡號的格式

## 資料問題

### 前處理雜訊（不修改原始資料）

- 測試資料與垃圾信，由模型判斷後封存：TK-1008、TK-1041
- 同一位客人多張工單，不合併、各自分流（設計上會串接未結工單，PoC 未實作）：TK-1013／TK-1031
- HTML 與簽名檔、全形字元、連續空白、重複標點：不處理，不影響模型判讀（見 README）

### 看起來像雜訊、其實是業務情況，交給分類處理

- 內文過短 → `insufficient_info`：TK-1033
- 非中文 → `non_chinese`（規則判斷）：TK-1012
- 內文含結構化個資 → `pii` 旗標：TK-1023
