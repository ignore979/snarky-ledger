"""services.py — 应用服务：账目、预算、分析。写操作走服务层，同一业务规则。"""
from __future__ import annotations

from datetime import date, timedelta

from .clock import Clock
from .db import DEFAULT_LEDGER_ID
from .domain import BusinessDate, Category, Money, Month
from .errors import InvalidArgument, NotFound, VersionConflict
from .repo import LedgerRepository


def fmt(minor: int) -> str:
    sign = "-" if minor < 0 else ""
    a = abs(minor)
    return f"{sign}{a // 100}.{a % 100:02d}"


class LedgerService:
    def __init__(self, repo: LedgerRepository, clock: Clock | None = None):
        self.repo = repo
        self.clock = clock or repo.clock

    def _check(self, amount: Money, spent_on: BusinessDate, note: str) -> str:
        if spent_on.is_future(self.clock):
            raise InvalidArgument(f"未来日期不能记作已发生支出：{spent_on.iso}")
        note = (note or "").strip()
        if len(note) > 200:
            raise InvalidArgument("备注过长（最多 200 字）")
        return note

    def add(self, *, amount: Money, category: Category, spent_on: BusinessDate,
            note="", source="manual", command_id=None) -> dict:
        note = self._check(amount, spent_on, note)
        with self.repo.transaction() as conn:
            row = self.repo.insert_expense(
                conn, amount_minor=amount.minor, category_id=category.id,
                note=note, spent_on=spent_on.iso, source=source, command_id=command_id,
            )
            self.repo.add_event(conn, "expense", str(row["id"]), "created")
            rev = self.repo.bump_revision(conn)
        return self._dto(row, rev)

    def edit(self, expense_id: int, expected_version: int, *, amount: Money,
             category: Category, spent_on: BusinessDate, note="") -> dict:
        note = self._check(amount, spent_on, note)
        with self.repo.transaction() as conn:
            row = self.repo.update_expense(
                conn, expense_id, expected_version,
                amount_minor=amount.minor, category_id=category.id,
                note=note, spent_on=spent_on.iso,
            )
            if row is None:
                self._raise_conflict(conn, expense_id)
            self.repo.add_event(conn, "expense", str(expense_id), "updated")
            rev = self.repo.bump_revision(conn)
        return self._dto(row, rev)

    def soft_delete(self, expense_id: int, expected_version: int) -> dict:
        with self.repo.transaction() as conn:
            row = self.repo.set_deleted(conn, expense_id, expected_version, self.repo.now())
            if row is None:
                self._raise_conflict(conn, expense_id)
            self.repo.add_event(conn, "expense", str(expense_id), "deleted")
            rev = self.repo.bump_revision(conn)
        return {"id": expense_id, "deleted": True, "ledger_revision": rev}

    def restore(self, expense_id: int, expected_version: int) -> dict:
        with self.repo.transaction() as conn:
            row = self.repo.set_deleted(conn, expense_id, expected_version, None)
            if row is None:
                self._raise_conflict(conn, expense_id)
            self.repo.add_event(conn, "expense", str(expense_id), "restored")
            rev = self.repo.bump_revision(conn)
        return self._dto(row, rev)

    def _raise_conflict(self, conn, expense_id: int):
        exists = conn.execute(
            "SELECT 1 FROM expenses WHERE id=? AND ledger_id=?",
            (expense_id, DEFAULT_LEDGER_ID),
        ).fetchone()
        if exists is None:
            raise NotFound(f"账目不存在：{expense_id}")
        raise VersionConflict("数据已被修改，请刷新后重试")

    @staticmethod
    def _dto(row, rev) -> dict:
        return {
            "id": row["id"],
            "amount_minor": row["amount_minor"],
            "amount": fmt(row["amount_minor"]),
            "category_id": row["category_id"],
            "note": row["note"],
            "spent_on": row["spent_on"],
            "version": row["version"],
            "deleted_at": row["deleted_at"],
            "ledger_revision": rev,
        }


class BudgetService:
    def __init__(self, repo: LedgerRepository):
        self.repo = repo

    def set(self, *, period: Month, scope_key: str, amount: Money) -> dict:
        # scope_key：'total' 或分类稳定 id；非法 id 拒绝，不静默放宽
        if scope_key != "total":
            Category.parse(scope_key)
        with self.repo.transaction() as conn:
            row = self.repo.upsert_budget(
                conn, period=period.iso, scope_key=scope_key, amount_minor=amount.minor
            )
            rev = self.repo.bump_revision(conn)
        return {
            "period": period.iso,
            "scope_key": scope_key,
            "amount_minor": row["amount_minor"],
            "amount": fmt(row["amount_minor"]),
            "version": row["version"],
            "ledger_revision": rev,
        }

    def status(self, period: Month) -> dict:
        start, end = period.half_open_range()
        with self.repo.transaction() as conn:
            budgets = self.repo.list_budgets(conn, period.iso)
            by_cat = self.repo.aggregate(conn, start=start, end=end)["by_category"]
            total_spent = sum(by_cat.values())
            result = []
            for b in budgets:
                spent = total_spent if b["scope_key"] == "total" else by_cat.get(b["scope_key"], 0)
                rem = b["amount_minor"] - spent
                result.append({
                    "scope_key": b["scope_key"],
                    "budget_minor": b["amount_minor"],
                    "budget": fmt(b["amount_minor"]),
                    "spent_minor": spent,
                    "spent": fmt(spent),
                    "remaining_minor": rem,
                    "remaining": fmt(rem),
                    "pct": round(spent / b["amount_minor"] * 100, 1) if b["amount_minor"] > 0 else 0,
                })
        return {"period": period.iso, "budgets": result}


class AnalysisService:
    def __init__(self, repo: LedgerRepository, clock: Clock | None = None):
        self.repo = repo
        self.clock = clock or repo.clock

    @staticmethod
    def _prev(period: Month) -> Month:
        first = date(int(period.iso[:4]), int(period.iso[5:7]), 1)
        return Month((first - timedelta(days=1)).strftime("%Y-%m"))

    def monthly_facts(self, period: Month) -> dict:
        start, end = period.half_open_range()
        prev = self._prev(period)
        with self.repo.transaction() as conn:
            agg = self.repo.aggregate(conn, start=start, end=end)
            top3 = self.repo.top_expenses(conn, start=start, end=end, n=3)
            counts = self.repo.category_counts(conn, start=start, end=end)
            daily_map = self.repo.daily_totals(conn, start, end)
            prev_agg = self.repo.aggregate(conn, start=prev.first_day, end=prev.next_month.first_day)
            rev = self.repo.revision(conn)

        by_category = {
            cid: {"amount_minor": m, "amount": fmt(m)} for cid, m in agg["by_category"].items()
        }
        top_cat = max(counts, key=counts.get) if counts else None
        days = period.days_in_month
        daily = [
            {"date": f"{period.iso}-{d:02d}", "amount_minor": daily_map.get(f"{period.iso}-{d:02d}", 0),
             "amount": fmt(daily_map.get(f"{period.iso}-{d:02d}", 0))}
            for d in range(1, days + 1)
        ]

        prev_total = prev_agg["total_minor"]
        mom = round((agg["total_minor"] - prev_total) / prev_total * 100, 1) if prev_total > 0 else None

        current_month = self.clock.today().strftime("%Y-%m") == period.iso
        elapsed = self.clock.today().day if current_month else days
        note = f"本月至今 {elapsed} 天" if current_month else f"完整月 {days} 天"
        avg = round(agg["total_minor"] / elapsed) if elapsed else 0

        return {
            "period": period.iso,
            "currency": "CNY",
            "ledger_revision": rev,
            "total_minor": agg["total_minor"],
            "total": fmt(agg["total_minor"]),
            "count": agg["count"],
            "by_category": by_category,
            "top3": [
                {"id": r["id"], "amount_minor": r["amount_minor"], "amount": fmt(r["amount_minor"]),
                 "category_id": r["category_id"], "note": r["note"], "spent_on": r["spent_on"]}
                for r in top3
            ],
            "top_category": {"category_id": top_cat, "count": counts[top_cat]} if top_cat else None,
            "mom_full": {
                "previous_month": prev.iso,
                "previous_total_minor": prev_total,
                "previous_total": fmt(prev_total),
                "change_pct": mom,
            },
            "avg_daily": {"amount_minor": avg, "amount": fmt(avg), "note": note},
            "daily": daily,
        }
