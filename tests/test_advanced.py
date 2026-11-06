"""test_advanced.py — 会话、记忆、确认、CSV 导入导出。"""
import os
import tempfile
import unittest
from datetime import date

from snarky_ledger import db as dbm
from snarky_ledger.advanced import (
    ConfirmationService, MemoryService, SessionService,
    export_expenses_csv, parse_expenses_csv,
)
from snarky_ledger.clock import FrozenClock
from snarky_ledger.domain import BusinessDate, Category, Money
from snarky_ledger.errors import InvalidArgument, NotFound
from snarky_ledger.repo import LedgerRepository
from snarky_ledger.services import LedgerService


class AdvancedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "ledger.db")
        self.clock = FrozenClock(date(2026, 11, 5))
        dbm.migrate(self.db_path, self.clock)
        self.repo = LedgerRepository(self.db_path, self.clock)
        self.ledger = LedgerService(self.repo, self.clock)
        self.sessions = SessionService(self.repo)
        self.memories = MemoryService(self.repo)
        self.confirm = ConfirmationService(self.repo, self.ledger, self.clock)

    def _add(self, amount="50", category="餐饮", spent="2026-11-02", note=""):
        return self.ledger.add(amount=Money.parse(amount), category=Category.parse(category),
                               spent_on=BusinessDate(spent), note=note)


class SessionTest(AdvancedTest):
    def test_create_and_history(self):
        s = self.sessions.create("测试会话")
        self.sessions.add_turn(s["id"], "今天花 50 吃火锅", "火锅 50 已入账", "req-1")
        hist = self.sessions.history(s["id"])
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0]["role"], "user")
        self.assertEqual(hist[1]["role"], "assistant")
        self.assertEqual(hist[1]["content"], "火锅 50 已入账")
        self.assertGreaterEqual(len(self.sessions.list()), 1)

    def test_missing_session(self):
        with self.assertRaises(NotFound):
            self.sessions.add_turn("nope", "hi", "yo")


class MemoryTest(AdvancedTest):
    def test_add_list_delete(self):
        self.memories.add("category_alias", {"alias": "奶茶", "category_id": "food"})
        items = self.memories.list()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "category_alias")
        self.assertEqual(items[0]["value"]["alias"], "奶茶")
        self.memories.delete(items[0]["id"])
        self.assertEqual(len(self.memories.list()), 0)

    def test_invalid_kind_rejected(self):
        with self.assertRaises(InvalidArgument):
            self.memories.add("salary", {"amount": 10000})


class ConfirmationTest(AdvancedTest):
    def test_reset_two_step(self):
        self._add("50")
        self._add("30", "交通")
        preview = self.confirm.reset_preview()
        self.assertEqual(preview["preview"]["expense_count"], 2)
        self.assertIn("action_id", preview)
        self.confirm.confirm(preview["action_id"])
        with self.repo.transaction() as conn:
            self.assertEqual(self.repo.aggregate(conn)["count"], 0)

    def test_confirm_twice_rejected(self):
        self._add("50")
        preview = self.confirm.reset_preview()
        self.confirm.confirm(preview["action_id"])
        with self.assertRaises(InvalidArgument):
            self.confirm.confirm(preview["action_id"])


class CsvTest(AdvancedTest):
    def test_export_and_parse_roundtrip(self):
        self._add("50", "餐饮", "2026-11-02", "火锅")
        self._add("30", "交通", "2026-11-03", "地铁")
        with self.repo.transaction() as conn:
            rows = self.repo.list_expenses(conn, limit=10)
        csv_text = export_expenses_csv(rows)
        self.assertIn("date,amount,category,note", csv_text)
        parsed = parse_expenses_csv(csv_text)
        self.assertEqual(len(parsed["candidates"]), 2)
        self.assertEqual(parsed["total_minor"], 8000)

    def test_parse_invalid_rows(self):
        csv_text = "date,amount,category,note\n2026-11-02,1.005,餐饮,坏\n2026-11-03,30,不存在,坏\n"
        parsed = parse_expenses_csv(csv_text)
        self.assertEqual(len(parsed["errors"]), 2)
        self.assertEqual(len(parsed["candidates"]), 0)

    def test_formula_injection_guarded(self):
        self._add("50", "餐饮", "2026-11-02", "=cmd()")
        with self.repo.transaction() as conn:
            rows = self.repo.list_expenses(conn, limit=10)
        csv_text = export_expenses_csv(rows)
        self.assertIn("'=cmd()", csv_text)


if __name__ == "__main__":
    unittest.main()
