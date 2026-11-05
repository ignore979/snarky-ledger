"""test_services.py — 账目/预算/分析服务与软删、乐观锁、环比。"""
import os
import tempfile
import unittest
from datetime import date

from snarky_ledger import db as dbm
from snarky_ledger.clock import FrozenClock
from snarky_ledger.domain import BusinessDate, Category, Money, Month
from snarky_ledger.errors import InvalidArgument, NotFound, VersionConflict
from snarky_ledger.repo import LedgerRepository
from snarky_ledger.services import AnalysisService, BudgetService, LedgerService


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "ledger.db")
        self.clock = FrozenClock(date(2026, 11, 5))
        dbm.migrate(self.db_path, self.clock)
        self.repo = LedgerRepository(self.db_path, self.clock)
        self.ledger = LedgerService(self.repo, self.clock)
        self.budget = BudgetService(self.repo)
        self.analysis = AnalysisService(self.repo, self.clock)

    def _add(self, amount, category="餐饮", spent="2026-11-02", note=""):
        return self.ledger.add(
            amount=Money.parse(amount), category=Category.parse(category),
            spent_on=BusinessDate(spent), note=note,
        )

    def test_add_and_revision(self):
        r1 = self._add("50")
        self.assertEqual(r1["amount_minor"], 5000)
        self.assertEqual(r1["category_id"], "food")
        r2 = self._add("18", note="奶茶")
        self.assertGreater(r2["ledger_revision"], r1["ledger_revision"])

    def test_future_date_rejected(self):
        with self.assertRaises(InvalidArgument):
            self._add("50", spent="2026-11-06")

    def test_edit(self):
        r = self._add("50")
        e = self.ledger.edit(r["id"], r["version"], amount=Money.parse("60"),
                             category=Category.parse("餐饮"), spent_on=BusinessDate("2026-11-02"), note="加菜")
        self.assertEqual(e["amount_minor"], 6000)
        self.assertEqual(e["version"], r["version"] + 1)

    def test_edit_version_conflict(self):
        r = self._add("50")
        self.ledger.edit(r["id"], r["version"], amount=Money.parse("60"),
                         category=Category.parse("餐饮"), spent_on=BusinessDate("2026-11-02"))
        with self.assertRaises(VersionConflict):
            self.ledger.edit(r["id"], r["version"], amount=Money.parse("70"),
                             category=Category.parse("餐饮"), spent_on=BusinessDate("2026-11-02"))

    def test_soft_delete_restore(self):
        r = self._add("50")
        d = self.ledger.soft_delete(r["id"], r["version"])
        self.assertTrue(d["deleted"])
        self.assertEqual(self.analysis.monthly_facts(Month("2026-11"))["count"], 0)
        restored = self.ledger.restore(r["id"], r["version"] + 1)
        self.assertIsNone(restored["deleted_at"])
        self.assertEqual(self.analysis.monthly_facts(Month("2026-11"))["count"], 1)

    def test_not_found(self):
        with self.assertRaises(NotFound):
            self.ledger.soft_delete(999, 1)

    def test_budget_multi_month_not_overwritten(self):
        self._add("50", spent="2026-10-05")
        self._add("20", spent="2026-11-05")
        self.budget.set(period=Month("2026-10"), scope_key="food", amount=Money.parse("100"))
        self.budget.set(period=Month("2026-11"), scope_key="food", amount=Money.parse("200"))
        s10 = self.budget.status(Month("2026-10"))
        s11 = self.budget.status(Month("2026-11"))
        self.assertEqual(s10["budgets"][0]["budget_minor"], 10000)
        self.assertEqual(s11["budgets"][0]["budget_minor"], 20000)
        self.assertEqual(s11["budgets"][0]["spent_minor"], 2000)

    def test_budget_unknown_scope_rejected(self):
        with self.assertRaises(InvalidArgument):
            self.budget.set(period=Month("2026-11"), scope_key="nope", amount=Money.parse("100"))

    def test_analysis_top3_full_month(self):
        # 超过 200 笔：最早一笔最大额也必须进 Top3（方案 F09）
        month = "2026-10"
        for i in range(1, 201):
            self._add("10", spent=f"{month}-{i % 28 + 1:02d}", note=f"n{i}")
        self._add("999", spent=f"{month}-01", note="最早最大")
        facts = self.analysis.monthly_facts(Month(month))
        self.assertEqual(facts["count"], 201)
        self.assertEqual(facts["top3"][0]["note"], "最早最大")
        self.assertEqual(facts["top3"][0]["amount_minor"], 99900)

    def test_analysis_mom(self):
        self._add("100", spent="2026-10-01")
        self._add("150", spent="2026-11-01")
        facts = self.analysis.monthly_facts(Month("2026-11"))
        self.assertEqual(facts["mom_full"]["change_pct"], 50.0)
        self.assertEqual(facts["mom_full"]["previous_total_minor"], 10000)


if __name__ == "__main__":
    unittest.main()
