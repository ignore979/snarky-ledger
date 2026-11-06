"""test_tools.py — 工具注册表：严格校验 + 走服务层。"""
import json
import os
import tempfile
import unittest
from datetime import date

from snarky_ledger import db as dbm
from snarky_ledger.clock import FrozenClock
from snarky_ledger.domain import Month
from snarky_ledger.repo import LedgerRepository
from snarky_ledger.services import AnalysisService, BudgetService, LedgerService
from snarky_ledger.tools import ToolRegistry


def run(tools, name, **args):
    return json.loads(tools.execute(name, args))


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "ledger.db")
        self.clock = FrozenClock(date(2026, 11, 5))
        dbm.migrate(self.db_path, self.clock)
        self.repo = LedgerRepository(self.db_path, self.clock)
        self.ledger = LedgerService(self.repo, self.clock)
        self.budget = BudgetService(self.repo)
        self.analysis = AnalysisService(self.repo, self.clock)
        self.tools = ToolRegistry(self.ledger, self.budget, self.analysis, self.clock)

    def test_add_expense_tool(self):
        r = run(self.tools, "add_expense", amount="50", category="餐饮", note="火锅")
        self.assertTrue(r["ok"])
        self.assertEqual(r["expense"]["amount_minor"], 5000)
        self.assertEqual(r["month_total_minor"], 5000)

    def test_add_invalid_amount_rejected(self):
        r = run(self.tools, "add_expense", amount="1.005", category="餐饮")
        self.assertFalse(r["ok"])
        self.assertIn("两位小数", r["error"])

    def test_add_unknown_category_rejected(self):
        r = run(self.tools, "add_expense", amount="50", category="奶茶")
        self.assertFalse(r["ok"])

    def test_add_income_tool(self):
        r = run(self.tools, "add_income", amount="5000", category="工资")
        self.assertTrue(r["ok"])
        self.assertEqual(r["income"]["amount_minor"], 500000)
        self.assertEqual(r["month_income_total_minor"], 500000)

    def test_add_income_with_expense_category_rejected(self):
        r = run(self.tools, "add_income", amount="5000", category="餐饮")
        self.assertFalse(r["ok"])

    def test_query(self):
        run(self.tools, "add_expense", amount="50", category="餐饮")
        run(self.tools, "add_expense", amount="30", category="交通")
        r = run(self.tools, "query_expenses")
        self.assertTrue(r["ok"])
        self.assertEqual(r["total_minor"], 8000)
        self.assertEqual(r["count"], 2)

    def test_monthly_stats(self):
        run(self.tools, "add_expense", amount="50", category="餐饮")
        r = run(self.tools, "monthly_stats", month="2026-11")
        self.assertTrue(r["ok"])
        self.assertEqual(r["total_minor"], 5000)

    def test_budget_flow(self):
        run(self.tools, "add_expense", amount="50", category="餐饮")
        r = run(self.tools, "set_budget", category="餐饮", amount="100")
        self.assertTrue(r["ok"])
        s = run(self.tools, "budget_status")
        self.assertEqual(s["budgets"][0]["spent_minor"], 5000)
        self.assertEqual(s["budgets"][0]["pct"], 50.0)

    def test_set_mode(self):
        r = run(self.tools, "set_mode", mode="gentle")
        self.assertTrue(r["ok"])
        self.assertEqual(self.tools.get_mode(), "gentle")
        r = run(self.tools, "set_mode", mode="bogus")
        self.assertFalse(r["ok"])

    def test_delete_soft(self):
        r = run(self.tools, "add_expense", amount="50", category="餐饮")
        eid = r["expense"]["id"]
        d = run(self.tools, "delete_expense", id=eid)
        self.assertTrue(d["ok"])
        self.assertTrue(d["deleted"])
        # 软删后不再计入
        self.assertEqual(self.analysis.monthly_facts(Month("2026-11"))["count"], 0)

    def test_unknown_tool(self):
        r = run(self.tools, "nope", x=1)
        self.assertFalse(r["ok"])

    def test_bad_args(self):
        r = run(self.tools, "add_expense")
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
