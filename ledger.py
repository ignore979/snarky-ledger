"""ledger.py — SQLite 数据层：建表、增删查、统计、预算、模式、重置。

纯函数、无 LLM 依赖，供 tools.py 与单元测试直接调用。
所有函数返回可 JSON 序列化的 dict，方便喂回给 LLM。
"""
from __future__ import annotations

import calendar
import os
import sqlite3
from datetime import date, datetime, timedelta

DB_PATH = os.environ.get("LEDGER_DB", os.path.join(os.path.dirname(__file__), "ledger.db"))

# 分类枚举（PLAN §5）
CATEGORIES = ["餐饮", "交通", "购物", "学习", "娱乐", "居住", "医疗", "其他"]

# 网开一面：这些分类不毒舌（PLAN §7 语气规则 4）
SOFT_CATEGORIES = {"学习", "医疗", "居住"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    note TEXT DEFAULT '',
    date TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS budgets (
    category TEXT PRIMARY KEY,
    amount REAL NOT NULL,
    month TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _conn(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建表 + 写入默认模式（幂等）。"""
    conn = _conn()
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('mode', 'savage')")
    conn.commit()
    conn.close()


def reset():
    """清空账目与预算，模式回默认。"""
    conn = _conn()
    conn.execute("DELETE FROM expenses")
    conn.execute("DELETE FROM budgets")
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('mode', 'savage') "
        "ON CONFLICT(key) DO UPDATE SET value='savage'"
    )
    conn.commit()
    conn.close()
    return {"reset": True}


def _today() -> str:
    return date.today().isoformat()


def _this_month() -> str:
    return _today()[:7]


def normalize_category(category):
    """把用户/LLM 给的分类归一到枚举；无法识别则返回 None。"""
    if not category:
        return None
    cat = str(category).strip()
    for c in CATEGORIES:
        if cat == c or c in cat or cat in c:
            return c
    return None


def add_expense(amount, category, note="", date_str=None):
    """记一笔支出，返回新记录 + 关联记忆（本月总额/该分类额/该分类次数/该备注次数）。"""
    amount = float(amount)
    if amount <= 0:
        raise ValueError("金额必须大于 0")
    cat = normalize_category(category)
    if cat is None:
        raise ValueError(f"无法识别的分类：{category}（可选：{'/'.join(CATEGORIES)}）")
    d = date_str or _today()

    conn = _conn()
    cur = conn.execute(
        "INSERT INTO expenses(amount, category, note, date) VALUES(?,?,?,?)",
        (amount, cat, note or "", d),
    )
    new_id = cur.lastrowid
    conn.commit()

    month = d[:7]
    month_total = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE date LIKE ?", (month + "%",)
    ).fetchone()[0]
    cat_total = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE category=? AND date LIKE ?",
        (cat, month + "%"),
    ).fetchone()[0]
    cat_count = conn.execute(
        "SELECT COUNT(*) FROM expenses WHERE category=? AND date LIKE ?",
        (cat, month + "%"),
    ).fetchone()[0]
    note_count = conn.execute(
        "SELECT COUNT(*) FROM expenses WHERE note=? AND date LIKE ?",
        (note or "", month + "%"),
    ).fetchone()[0]
    conn.close()

    return {
        "id": new_id,
        "amount": round(amount, 2),
        "category": cat,
        "note": note or "",
        "date": d,
        "month_total": round(month_total, 2),
        "month_total_for_category": round(cat_total, 2),
        "month_count_for_category": cat_count,
        "month_count_for_note": note_count,
    }


def query_expenses(start=None, end=None, category=None, limit=200):
    """按日期范围/分类查账：汇总基于全部命中，明细只回最近 limit 条。"""
    where = " WHERE 1=1"
    params = []
    if start:
        where += " AND date >= ?"
        params.append(start)
    if end:
        where += " AND date <= ?"
        params.append(end)
    if category:
        cat = normalize_category(category)
        if cat:
            where += " AND category = ?"
            params.append(cat)

    conn = _conn()
    agg = conn.execute(
        f"SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS t FROM expenses{where}", params
    ).fetchone()
    by_rows = conn.execute(
        f"SELECT category, COALESCE(SUM(amount),0) AS t FROM expenses{where} GROUP BY category",
        params,
    ).fetchall()
    rows = conn.execute(
        f"SELECT * FROM expenses{where} ORDER BY date DESC, id DESC LIMIT ?", params + [limit]
    ).fetchall()
    conn.close()

    return {
        "count": agg["c"],
        "total": round(agg["t"], 2),
        "by_category": {r["category"]: round(r["t"], 2) for r in by_rows},
        "items": [dict(r) for r in rows],
    }


def monthly_stats(month=None):
    """月度统计：总额、分类占比、环比、日均、最大单笔、最高频分类。"""
    month = month or _this_month()
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE date LIKE ? ORDER BY date ASC", (month + "%",)
    ).fetchall()
    total = round(sum(r["amount"] for r in rows), 2)
    by_category = {}
    for r in rows:
        by_category[r["category"]] = round(by_category.get(r["category"], 0) + r["amount"], 2)

    # 上月总额 + 环比
    ym = datetime.strptime(month + "-01", "%Y-%m-%d")
    prev = (ym.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    prev_total = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE date LIKE ?", (prev + "%",)
    ).fetchone()[0]
    conn.close()

    mom_change_pct = None
    if prev_total > 0:
        mom_change_pct = round((total - prev_total) / prev_total * 100, 1)

    highest = max(rows, key=lambda r: r["amount"]) if rows else None
    freq = {}
    for r in rows:
        freq[r["category"]] = freq.get(r["category"], 0) + 1
    top_category = max(freq, key=freq.get) if freq else None

    days_elapsed = date.today().day if month == _this_month() else calendar.monthrange(
        int(month[:4]), int(month[5:7])
    )[1]
    avg_daily = round(total / max(days_elapsed, 1), 2) if total else 0.0

    return {
        "month": month,
        "total": total,
        "count": len(rows),
        "by_category": by_category,
        "previous_month": prev,
        "previous_month_total": round(prev_total, 2),
        "mom_change_pct": mom_change_pct,
        "avg_daily": avg_daily,
        "highest_single": (
            {
                "amount": round(highest["amount"], 2),
                "note": highest["note"],
                "category": highest["category"],
                "date": highest["date"],
            }
            if highest
            else None
        ),
        "top_category": top_category,
    }


def daily_totals(month=None):
    """按月返回每天支出序列（缺的日期补 0），供网页柱状图。"""
    month = month or _this_month()
    conn = _conn()
    rows = conn.execute(
        "SELECT date, SUM(amount) AS total FROM expenses WHERE date LIKE ? GROUP BY date",
        (month + "%",),
    ).fetchall()
    conn.close()
    totals = {r["date"]: round(r["total"], 2) for r in rows}
    y, m = int(month[:4]), int(month[5:7])
    return [
        {"date": f"{month}-{d:02d}", "total": totals.get(f"{month}-{d:02d}", 0)}
        for d in range(1, calendar.monthrange(y, m)[1] + 1)
    ]


def set_budget(category, amount, month=None):
    """设置某分类的月预算（同分类覆盖）。"""
    cat = normalize_category(category)
    if cat is None:
        raise ValueError(f"无法识别的分类：{category}")
    amount = float(amount)
    if amount <= 0:
        raise ValueError("预算金额必须大于 0")
    month = month or _this_month()
    conn = _conn()
    conn.execute(
        "INSERT INTO budgets(category, amount, month) VALUES(?,?,?) "
        "ON CONFLICT(category) DO UPDATE SET amount=excluded.amount, month=excluded.month",
        (cat, amount, month),
    )
    conn.commit()
    conn.close()
    return {"category": cat, "amount": round(amount, 2), "month": month}


def budget_status(month=None):
    """每个已设预算分类的已花/剩余/占比。"""
    month = month or _this_month()
    conn = _conn()
    budgets = conn.execute("SELECT * FROM budgets").fetchall()
    result = []
    for b in budgets:
        spent = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE category=? AND date LIKE ?",
            (b["category"], month + "%"),
        ).fetchone()[0]
        result.append(
            {
                "category": b["category"],
                "budget": round(b["amount"], 2),
                "spent": round(spent, 2),
                "remaining": round(b["amount"] - spent, 2),
                "pct": round(spent / b["amount"] * 100, 1) if b["amount"] > 0 else 0,
            }
        )
    conn.close()
    return {"month": month, "budgets": result}


def delete_expense(expense_id):
    """删除一笔账（纠错）。"""
    conn = _conn()
    cur = conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
    conn.commit()
    conn.close()
    return {"id": expense_id, "deleted": cur.rowcount > 0}


def get_mode():
    conn = _conn()
    row = conn.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
    conn.close()
    return row["value"] if row else "savage"


def set_mode(mode):
    """切换毒舌(savage)/温柔(gentle)模式。"""
    mode = "gentle" if str(mode).strip() == "gentle" else "savage"
    conn = _conn()
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('mode', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (mode,),
    )
    conn.commit()
    conn.close()
    return {"mode": mode}
