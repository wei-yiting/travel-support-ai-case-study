"""規則、合併與查表邏輯的單元測試（不呼叫模型），以及對已產出結果檔的檢查。"""
from __future__ import annotations

import csv
import unittest
from datetime import datetime

import llm
from rules import NON_ZH, Ticket, apply_rules
from run_triage import HERE, load_tickets
import triage
from triage import HIGH_RISK, NORMAL, PII, SUPERVISOR, URGENT, merge

RESULT = HERE / "output" / "triage_result.csv"


def ticket(body: str) -> Ticket:
    return Ticket("TK-T", datetime(2026, 6, 22, 9, 0), "email", "客人", "詢問", body)


def model(category=llm.ORDER, urgent=False, high_risk=False, departure_date="", claimed_amount=0, needed_tools=()):
    return llm.ModelResult("測試", category, urgent, "模型的急件理由" if urgent else "",
                           high_risk, "模型的高風險理由" if high_risk else "", departure_date, claimed_amount,
                           list(needed_tools))


def run(body: str, m: llm.ModelResult | None = None):
    t = ticket(body)
    return merge(t, apply_rules(t), m or model())


class Rules(unittest.TestCase):
    def test_public_threat_is_high_risk_and_urgent(self):
        r = run("再不處理我就找消保官")
        self.assertIn(HIGH_RISK, r.risk_flags)
        self.assertEqual(r.priority, URGENT)

    def test_compensation_is_high_risk_only(self):
        r = run("要求貴公司全額賠償")
        self.assertIn(HIGH_RISK, r.risk_flags)
        self.assertEqual(r.priority, NORMAL)

    def test_chargeback_is_urgent_only(self):
        r = run("今天再不回覆我直接請銀行止付")
        self.assertEqual(r.priority, URGENT)
        self.assertNotIn(HIGH_RISK, r.risk_flags)

    def test_media_mention_without_threat_is_not_high_risk(self):
        self.assertNotIn(HIGH_RISK, run("我是財經媒體記者，想邀請貴公司受訪").risk_flags)

    def test_order_number_is_not_pii_but_national_id_is(self):
        self.assertNotIn(PII, run("訂單編號 LT20260611567 想加購").risk_flags)
        self.assertIn(PII, run("退款，身分證 A123456789").risk_flags)


class Merge(unittest.TestCase):
    def test_model_cannot_downgrade_rule_flags(self):
        r = run("再不處理就找消保官", model(urgent=False, high_risk=False))
        self.assertEqual(r.priority, URGENT)
        self.assertIn(HIGH_RISK, r.risk_flags)
        self.assertEqual((r.route, r.next_step), ("human", "senior_agent_handles"))

    def test_model_can_upgrade(self):
        r = run("我要讓大家知道你們有多爛", model(llm.COMPLAINT, urgent=True, high_risk=True))
        self.assertEqual(r.priority, URGENT)
        self.assertIn(HIGH_RISK, r.risk_flags)

    def test_departure_within_three_days_is_urgent(self):
        self.assertEqual(run("明天出發", model(departure_date="2026-06-23")).priority, URGENT)
        self.assertEqual(run("下個月出發", model(departure_date="2026-07-20")).priority, NORMAL)
        self.assertEqual(run("出發日不明", model(departure_date="不知道")).priority, NORMAL)

    def test_model_urgent_alone_is_urgent_and_sourced(self):
        r = run("人還在飯店，房間有蟑螂", model(llm.COMPLAINT, urgent=True))
        self.assertEqual(r.priority, URGENT)
        self.assertIn("急件：模型的急件理由（模型）", r.reasons)


class Route(unittest.TestCase):
    def test_non_chinese_is_decided_by_rule(self):
        r = run("Could you change my pickup hotel for the Taroko tour?", model(llm.ORDER))
        self.assertEqual((r.category, r.route, r.ai_draft, r.next_step), (NON_ZH, "human", False, "agent_handles"))

    def test_claimed_refund_over_30k_stays_auto_and_goes_to_supervisor(self):
        r = run("申請全額退費", model(llm.REFUND, claimed_amount=186_000, needed_tools=["get_order"]))
        self.assertIn(SUPERVISOR, r.risk_flags)
        self.assertEqual((r.route, r.allowed_tools, r.ai_draft, r.next_step),
                         ("auto", ["get_order"], True, "agent_review_then_supervisor"))

    def test_tools_are_model_request_capped_by_path(self):
        r = run("想改期，差價怎麼算", model(llm.ORDER, needed_tools=["get_order", "search_policy"]))
        self.assertEqual(r.allowed_tools, ["get_order", "search_policy"])

    def test_tool_outside_ceiling_is_blocked_and_recorded(self):
        r = run("取消手續費怎麼算", model(llm.POLICY, needed_tools=["get_order", "search_policy"]))
        self.assertEqual(r.allowed_tools, ["search_policy"])
        self.assertIn("擋下：get_order 不在 policy 的上限內", r.reasons)

    def test_insufficient_info_may_only_look_up_own_orders(self):
        r = run("可以退嗎", model(llm.INSUFFICIENT, needed_tools=["get_order", "search_policy"]))
        self.assertEqual((r.route, r.allowed_tools, r.ai_draft), ("auto", ["get_order"], True))
        self.assertIn("擋下：search_policy 不在 insufficient_info 的上限內", r.reasons)

    def test_human_paths_do_not_draft(self):
        r = run("請問簽證要怎麼辦", model(llm.EXTERNAL, needed_tools=["search_policy"]))
        self.assertEqual((r.route, r.allowed_tools, r.ai_draft, r.next_step), ("human", [], False, "agent_handles"))

    def test_spam_is_archived(self):
        r = run("加賴領取體驗金", model(llm.SPAM))
        self.assertEqual((r.route, r.ai_draft, r.next_step), ("auto", False, "archive"))


@unittest.skipUnless(RESULT.exists(), "先執行 run_triage.py 產出結果")
class Output(unittest.TestCase):
    def test_all_rows_present(self):
        tickets = load_tickets(HERE / "data" / "sample_tickets.xlsx")
        rows = list(csv.DictReader(RESULT.read_text(encoding="utf-8-sig").splitlines()))
        self.assertEqual([r["ticket_id"] for r in rows], [t.ticket_id for t in tickets])
        self.assertTrue(all(r["route"] in {"auto", "human"} and r["next_step"] for r in rows))

    def test_structured_columns_use_english_codes(self):
        rows = list(csv.DictReader(RESULT.read_text(encoding="utf-8-sig").splitlines()))
        flags = {HIGH_RISK, SUPERVISOR, PII}
        next_steps = {triage.AGENT_REVIEW_SEND, triage.AGENT_REVIEW_SUPERVISOR, triage.SENIOR_HANDLES,
                      triage.AGENT_HANDLES, triage.FORWARD, triage.ARCHIVE}
        for r in rows:
            self.assertIn(r["category"], set(llm.PATHS) | {NON_ZH})
            self.assertIn(r["priority"], {URGENT, NORMAL})
            self.assertIn(r["ai_draft"], {"true", "false"})
            self.assertIn(r["next_step"], next_steps)
            self.assertTrue(set(filter(None, r["risk_flags"].split(";"))) <= flags)
            self.assertTrue(set(filter(None, r["allowed_tools"].split(";"))) <= set(llm.TOOLS))


if __name__ == "__main__":
    unittest.main()
