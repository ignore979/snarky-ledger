"""test_api.py — Flask API：V2 端点 + 旧接口兼容 + 错误映射。"""
import os
import tempfile
import unittest
from datetime import date

from snarky_ledger import create_app
from snarky_ledger.clock import FrozenClock
from snarky_ledger.config import Settings


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "ledger.db")
        self.clock = FrozenClock(date(2026, 11, 5))
        app = create_app(Settings(db_path=self.db_path, deepseek_api_key=None), self.clock)
        app.testing = True
        self.client = app.test_client()

    def test_health(self):
        self.assertEqual(self.client.get("/health/live").status_code, 200)
        self.assertEqual(self.client.get("/health/ready").status_code, 200)

    def test_add_and_state(self):
        r = self.client.post("/api/v2/expenses",
                             json={"amount": "50", "category": "餐饮", "note": "火锅"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["data"]["amount_minor"], 5000)
        s = self.client.get("/api/v2/state?month=2026-11").get_json()["data"]
        self.assertEqual(s["facts"]["total_minor"], 5000)
        self.assertEqual(len(s["expenses"]), 1)

    def test_invalid_amount_422(self):
        r = self.client.post("/api/v2/expenses", json={"amount": "1.005", "category": "餐饮"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.get_json()["error"]["code"], "INVALID_ARGUMENT")

    def test_edit_and_conflict(self):
        rid = self.client.post("/api/v2/expenses",
                               json={"amount": "50", "category": "餐饮"}).get_json()["data"]["id"]
        r = self.client.patch(f"/api/v2/expenses/{rid}",
                              json={"version": 1, "amount": "60", "category": "餐饮", "spent_on": "2026-11-02"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["data"]["amount_minor"], 6000)
        # 旧版本再改 → 409
        r2 = self.client.patch(f"/api/v2/expenses/{rid}",
                               json={"version": 1, "amount": "70", "category": "餐饮", "spent_on": "2026-11-02"})
        self.assertEqual(r2.status_code, 409)

    def test_delete_restore(self):
        rid = self.client.post("/api/v2/expenses",
                               json={"amount": "50", "category": "餐饮"}).get_json()["data"]["id"]
        d = self.client.delete(f"/api/v2/expenses/{rid}", json={"version": 1})
        self.assertEqual(d.status_code, 200)
        s = self.client.get("/api/v2/state?month=2026-11").get_json()["data"]
        self.assertEqual(s["facts"]["count"], 0)
        self.client.post(f"/api/v2/expenses/{rid}/restore", json={"version": 2})
        s = self.client.get("/api/v2/state?month=2026-11").get_json()["data"]
        self.assertEqual(s["facts"]["count"], 1)

    def test_budget(self):
        self.client.post("/api/v2/expenses", json={"amount": "50", "category": "餐饮"})
        r = self.client.put("/api/v2/budgets/2026-11/food", json={"amount": "100"})
        self.assertEqual(r.status_code, 200)
        s = self.client.get("/api/v2/state?month=2026-11").get_json()["data"]
        self.assertEqual(s["budgets"]["budgets"][0]["spent_minor"], 5000)

    def test_old_state_compat(self):
        # 旧前端期望旧字段形状（stats/daily/expenses 含 date+category+note+amount）
        self.client.post("/api/v2/expenses", json={"amount": "50", "category": "餐饮"})
        r = self.client.post("/api/state")
        d = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertIn("stats", d)
        self.assertIn("daily", d)
        self.assertEqual(d["stats"]["total"], 50.0)
        self.assertEqual(d["expenses"][0]["category"], "餐饮")
        self.assertEqual(d["expenses"][0]["amount"], 50.0)

    def test_turn_requires_key(self):
        # 未配置 key，自然语言入口返回 503，不崩溃
        r = self.client.post("/api/v2/turns", json={"message": "今天花 50 吃火锅"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json()["error"]["code"], "PROVIDER_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
