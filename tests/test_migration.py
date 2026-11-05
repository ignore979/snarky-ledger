"""test_migration.py — 旧库 → V2 迁移：逐行金额转分、异常阻断、对账。"""
import os
import sqlite3
import tempfile
import unittest
from datetime import date

from snarky_ledger import db as dbm
from snarky_ledger.clock import FrozenClock
from snarky_ledger.migrate import migrate_old_db


def build_old_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL NOT NULL,"
        " category TEXT NOT NULL, note TEXT DEFAULT '', date TEXT NOT NULL,"
        " created_at TEXT DEFAULT (datetime('now','localtime')));"
        "CREATE TABLE budgets (category TEXT PRIMARY KEY, amount REAL NOT NULL, month TEXT NOT NULL);"
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
    )
    return conn


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.path.join(self.tmp, "old.db")
        self.new = os.path.join(self.tmp, "new.db")
        self.clock = FrozenClock(date(2026, 11, 5))

    def test_clean_migration(self):
        conn = build_old_db(self.old)
        conn.execute("INSERT INTO expenses(amount, category, note, date) VALUES(50.0,'餐饮','火锅','2026-11-02')")
        conn.execute("INSERT INTO expenses(amount, category, note, date) VALUES(18.0,'餐饮','奶茶','2026-11-03')")
        conn.execute("INSERT INTO budgets(category, amount, month) VALUES('餐饮', 1500.0, '2026-11')")
        conn.execute("INSERT INTO meta(key, value) VALUES('mode','gentle')")
        conn.commit()
        conn.close()

        res = migrate_old_db(self.old, self.new, self.clock)
        self.assertTrue(res["ok"])
        self.assertEqual(res["converted_count"], 2)
        self.assertTrue(res["reconciliation"]["id_match"])
        self.assertTrue(res["reconciliation"]["sum_match"])
        self.assertEqual(res["reconciliation"]["budget_imported"], 1)
        self.assertEqual(res["reconciliation"]["mode"], "gentle")

        nc = dbm.connect(self.new)
        rows = nc.execute("SELECT amount_minor FROM expenses ORDER BY id").fetchall()
        self.assertEqual([r["amount_minor"] for r in rows], [5000, 1800])
        nc.execute(
            "INSERT INTO expenses(ledger_id, amount_minor, category_id, note, spent_on,"
            " source, created_at, updated_at, version) VALUES('local',100,'food','','2026-11-05','manual','x','x',1)"
        )
        new_id = nc.execute("SELECT id FROM expenses ORDER BY id DESC LIMIT 1").fetchone()["id"]
        self.assertEqual(new_id, 3)
        nc.close()

    def test_anomalies_block(self):
        conn = build_old_db(self.old)
        conn.execute("INSERT INTO expenses(amount, category, note, date) VALUES(1.005,'餐饮','bad','2026-11-04')")
        conn.execute("INSERT INTO expenses(amount, category, note, date) VALUES(-10.0,'餐饮','neg','2026-11-04')")
        conn.execute("INSERT INTO expenses(amount, category, note, date) VALUES(20.0,'不存在','bad','2026-11-04')")
        conn.execute("INSERT INTO expenses(amount, category, note, date) VALUES(30.0,'餐饮','ok','2026-11-04')")
        conn.commit()
        conn.close()

        res = migrate_old_db(self.old, self.new, self.clock)
        self.assertFalse(res["ok"])
        self.assertEqual(res["converted_count"], 1)
        self.assertEqual(len(res["anomalies"]), 3)

    def test_reject_wrong_schema(self):
        conn = sqlite3.connect(self.old)
        conn.execute("CREATE TABLE expenses (id INTEGER PRIMARY KEY, foo TEXT)")
        conn.commit()
        conn.close()
        with self.assertRaises(RuntimeError):
            migrate_old_db(self.old, self.new, self.clock)


if __name__ == "__main__":
    unittest.main()
