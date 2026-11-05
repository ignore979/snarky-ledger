"""migrate.py — 旧格式库 → V2 库迁移：只读旧库，写独立新库，逐行金额转分并对账。"""
from __future__ import annotations

import sqlite3
from decimal import Decimal, ROUND_HALF_UP

from . import db as dbm
from .clock import Clock, SystemClock
from .domain import BusinessDate, Category, Month
from .domain.money import MAX_MINOR


def _amount_to_minor(value, errs: list) -> int | None:
    d = Decimal(str(value))
    if not d.is_finite() or d <= 0:
        errs.append("non_finite_or_nonpositive")
        return None
    exp = d.as_tuple().exponent
    if isinstance(exp, int) and exp < -2:
        errs.append("more_than_2_decimals")
        return None
    q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    minor = int(q * 100)
    if minor > MAX_MINOR:
        errs.append("over_max")
        return None
    return minor


def _check_old_schema(old: sqlite3.Connection) -> None:
    try:
        exp_cols = {r["name"] for r in old.execute("PRAGMA table_info(expenses)")}
        bud_cols = {r["name"] for r in old.execute("PRAGMA table_info(budgets)")}
    except sqlite3.OperationalError:
        raise RuntimeError("旧库缺少 expenses/budgets 表，不是支持的旧格式")
    if not {"amount", "date", "category"}.issubset(exp_cols):
        raise RuntimeError("expenses 表结构不是支持的旧格式")
    if not {"category", "month", "amount"}.issubset(bud_cols):
        raise RuntimeError("budgets 表结构不是支持的旧格式")


def migrate_old_db(old_path: str, new_path: str, clock: Clock | None = None) -> dict:
    """把旧库迁移到独立新库。异常行不静默丢弃，进入 anomalies 并阻止切换。"""
    clock = clock or SystemClock()
    dbm.migrate(new_path, clock)
    old = sqlite3.connect(old_path)
    old.row_factory = sqlite3.Row
    new = dbm.connect(new_path)
    anomalies: list = []
    converted = []
    budget_rows = []
    old_mode = "savage"
    try:
        _check_old_schema(old)
        old_exp = old.execute("SELECT * FROM expenses ORDER BY id").fetchall()
        old_budgets = old.execute("SELECT * FROM budgets").fetchall()
        meta = {r["key"]: r["value"] for r in old.execute("SELECT key, value FROM meta")}
        old_mode = meta.get("mode", "savage")

        for r in old_exp:
            errs: list = []
            minor = _amount_to_minor(r["amount"], errs)
            try:
                cat = Category.parse(r["category"])
            except Exception:
                cat = None
                errs.append("unknown_category")
            try:
                bd = BusinessDate(r["date"])
            except Exception:
                bd = None
                errs.append("invalid_date")
            if minor is None or errs:
                anomalies.append({
                    "id": r["id"], "types": errs, "amount": str(r["amount"]),
                    "category": r["category"], "date": r["date"],
                })
                continue
            converted.append({
                "id": r["id"], "minor": minor, "category_id": cat.id,
                "note": r["note"], "spent_on": bd.iso,
            })

        now = clock.now().isoformat()
        for c in converted:
            new.execute(
                "INSERT INTO expenses(id, ledger_id, amount_minor, category_id, note, spent_on,"
                " source, created_at, updated_at, deleted_at, version) VALUES(?,?,?,?,?,?,?,?,?,NULL,1)",
                (c["id"], dbm.DEFAULT_LEDGER_ID, c["minor"], c["category_id"], c["note"],
                 c["spent_on"], "legacy", now, now),
            )

        for b in old_budgets:
            errs = []
            try:
                cat = Category.parse(b["category"])
            except Exception:
                anomalies.append({"id": f"budget:{b['category']}", "types": ["unknown_category"],
                                  "amount": str(b["amount"])})
                continue
            minor = _amount_to_minor(b["amount"], errs)
            if minor is None or errs:
                anomalies.append({"id": f"budget:{b['category']}", "types": errs, "amount": str(b["amount"])})
                continue
            period = b["month"]
            try:
                period = Month(b["month"]).iso
            except Exception:
                anomalies.append({"id": f"budget:{b['category']}", "types": ["invalid_month"], "month": str(b["month"])})
                continue
            budget_rows.append({"period": period, "scope_key": cat.id, "minor": minor})

        for b in budget_rows:
            new.execute(
                "INSERT INTO budgets(ledger_id, period, scope_key, amount_minor, version, created_at, updated_at)"
                " VALUES(?,?,?,?,1,?,?)",
                (dbm.DEFAULT_LEDGER_ID, b["period"], b["scope_key"], b["minor"], now, now),
            )

        if old_mode in ("savage", "gentle"):
            new.execute(
                "INSERT INTO preferences(ledger_id, key, value_json, updated_at) VALUES(?,?,?,?)"
                " ON CONFLICT(ledger_id, key) DO UPDATE SET value_json=excluded.value_json",
                (dbm.DEFAULT_LEDGER_ID, "mode", old_mode, now),
            )
        else:
            anomalies.append({"id": "meta:mode", "types": ["unknown_mode"], "value": str(old_mode)})

        max_id = max((c["id"] for c in converted), default=0)
        new.execute("UPDATE sqlite_sequence SET seq=? WHERE name='expenses'", (max_id,))
        new.commit()

        recon = _reconcile(old_exp, converted, budget_rows, old_mode, new)
    finally:
        old.close()
        new.close()

    return {
        "ok": len(anomalies) == 0,
        "anomalies": anomalies,
        "converted_count": len(converted),
        "reconciliation": recon,
    }


def _reconcile(old_exp, converted, budget_rows, old_mode, new: sqlite3.Connection) -> dict:
    new_count = new.execute(
        "SELECT COUNT(*) FROM expenses WHERE ledger_id=?", (dbm.DEFAULT_LEDGER_ID,)
    ).fetchone()[0]
    old_ids = {c["id"] for c in converted}
    new_ids = {r["id"] for r in new.execute(
        "SELECT id FROM expenses WHERE ledger_id=?", (dbm.DEFAULT_LEDGER_ID,)
    )}
    old_sum: dict = {}
    for c in converted:
        key = (c["spent_on"][:7], c["category_id"])
        old_sum[key] = old_sum.get(key, 0) + c["minor"]
    new_sum: dict = {}
    for r in new.execute(
        "SELECT spent_on, category_id, amount_minor FROM expenses WHERE ledger_id=?",
        (dbm.DEFAULT_LEDGER_ID,),
    ):
        key = (r["spent_on"][:7], r["category_id"])
        new_sum[key] = new_sum.get(key, 0) + r["amount_minor"]
    return {
        "old_row_count": len(old_exp),
        "converted_count": len(converted),
        "new_expense_count": new_count,
        "id_match": old_ids == new_ids,
        "sum_match": old_sum == new_sum,
        "budget_imported": len(budget_rows),
        "mode": old_mode,
    }
