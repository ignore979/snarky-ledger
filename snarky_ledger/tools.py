"""tools.py — 工具注册表 + 严格校验 + 8 个工具（全部走服务层，无旁路 SQL）。"""
from __future__ import annotations

import json
from datetime import timedelta

from .domain import BusinessDate, Category, Money, Mode, Month
from .errors import InvalidArgument, LedgerError, NotFound
from .services import AnalysisService, BudgetService, LedgerService, fmt


def _ok(payload):
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _err(msg):
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _end_exclusive(end_str):
    return (BusinessDate(end_str).to_date() + timedelta(days=1)).isoformat()


class ToolRegistry:
    def __init__(self, ledger: LedgerService, budget: BudgetService,
                 analysis: AnalysisService, clock):
        self.ledger = ledger
        self.budget = budget
        self.analysis = analysis
        self.clock = clock
        self._repo = ledger.repo

    def get_mode(self) -> str:
        with self._repo.transaction() as conn:
            v = self._repo.get_preference(conn, "mode")
        return v if v in ("savage", "gentle") else "savage"

    # --- 工具实现 ---
    def add_expense(self, amount, category, note="", date=None):
        m = Money.parse(amount)
        c = Category.parse(category)
        d = BusinessDate(date) if date else BusinessDate.today(self.clock)
        rec = self.ledger.add(amount=m, category=c, spent_on=d, note=note, source="agent")
        facts = self.analysis.monthly_facts(d.month)
        return _ok({
            "expense": rec,
            "month_total_minor": facts["total_minor"],
            "month_total": facts["total"],
            "month_category_total_minor": facts["by_category"].get(c.id, {}).get("amount_minor", 0),
        })

    def add_income(self, amount, category, note="", date=None):
        m = Money.parse(amount)
        c = Category.parse(category)
        if c.kind != "income":
            raise InvalidArgument(f"分类「{c.name}」不是收入分类")
        d = BusinessDate(date) if date else BusinessDate.today(self.clock)
        rec = self.ledger.add(amount=m, category=c, spent_on=d, note=note, source="agent", kind="income")
        facts = self.analysis.monthly_facts(d.month)
        return _ok({
            "income": rec,
            "month_income_total_minor": facts["income_total_minor"],
            "month_income_total": facts["income_total"],
        })

    def query_expenses(self, start=None, end=None, category=None):
        cat = Category.parse(category) if category else None
        s = BusinessDate(start).iso if start else None
        e = _end_exclusive(end) if end else None
        if start and end and BusinessDate(start) > BusinessDate(end):
            raise InvalidArgument("起始日期不能晚于结束日期")
        with self._repo.transaction() as conn:
            items = self._repo.list_expenses(
                conn, start=s, end=e, category_id=(cat.id if cat else None), limit=20)
            agg = self._repo.aggregate(conn, start=s, end=e, category_id=(cat.id if cat else None))
        return _ok({
            "total": fmt(agg["total_minor"]), "total_minor": agg["total_minor"], "count": agg["count"],
            "by_category": {k: {"amount": fmt(v)} for k, v in agg["by_category"].items()},
            "items": [self._item(i) for i in items],
        })

    def monthly_stats(self, month=None):
        m = Month(month) if month else Month.current(self.clock)
        return _ok(self.analysis.monthly_facts(m))

    def set_budget(self, category, amount):
        m = Money.parse(amount)
        scope = "total" if str(category).strip() in ("total", "总", "全部") else Category.parse(category).id
        period = Month.current(self.clock)
        return _ok(self.budget.set(period=period, scope_key=scope, amount=m))

    def budget_status(self):
        return _ok(self.budget.status(Month.current(self.clock)))

    def persona_report(self, month=None):
        m = Month(month) if month else Month.current(self.clock)
        return _ok({"facts": self.analysis.monthly_facts(m)})

    def set_mode(self, mode):
        m = Mode.parse(mode)
        with self._repo.transaction() as conn:
            self._repo.set_preference(conn, "mode", m)
        hint = "已切到温柔模式，接下来温柔、不毒舌。" if m == "gentle" else "已切回毒舌模式，损事不损人。"
        return _ok({"mode": m, "hint": hint})

    def delete_expense(self, id):
        eid = int(id)
        with self._repo.transaction() as conn:
            row = self._repo.get_expense(conn, eid)
        if row is None:
            raise NotFound(f"账目不存在：{eid}")
        if row["deleted_at"]:
            raise InvalidArgument("该账目已删除")
        return _ok(self.ledger.soft_delete(eid, row["version"]))

    @staticmethod
    def _item(r):
        return {"id": r["id"], "amount": fmt(r["amount_minor"]), "category_id": r["category_id"],
                "note": r["note"], "spent_on": r["spent_on"]}

    # --- 分发 ---
    def execute(self, name, args):
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_"):
            return _err(f"未知工具：{name}")
        try:
            return fn(**args)
        except TypeError as e:
            return _err(f"参数错误：{e}")
        except LedgerError as e:
            return _err(e.message)
        except Exception as e:  # noqa: BLE001
            return _err(str(e))

    # --- function calling schema ---
    def schemas(self):
        exp_names = [c.name for c in Category.all("expense")]
        inc_names = [c.name for c in Category.all("income")]
        return [
            {"type": "function", "function": {
                "name": "add_expense", "description": "记一笔支出，返回本月/该分类累计金额供吐槽。",
                "parameters": {"type": "object", "properties": {
                    "amount": {"type": "string", "description": "金额（元），十进制字符串，如 \"50\""},
                    "category": {"type": "string", "enum": exp_names, "description": "分类"},
                    "note": {"type": "string", "description": "备注"},
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD，缺省今天"},
                }, "required": ["amount", "category"]},
            }},
            {"type": "function", "function": {
                "name": "add_income", "description": "记一笔收入（工资/兼职/理财等），返回本月收入累计。",
                "parameters": {"type": "object", "properties": {
                    "amount": {"type": "string", "description": "金额（元），十进制字符串，如 \"5000\""},
                    "category": {"type": "string", "enum": inc_names, "description": "收入分类"},
                    "note": {"type": "string", "description": "备注"},
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD，缺省今天"},
                }, "required": ["amount", "category"]},
            }},
            {"type": "function", "function": {
                "name": "query_expenses", "description": "按日期范围/分类查账，返回总额、分类占比与明细。",
                "parameters": {"type": "object", "properties": {
                    "start": {"type": "string", "description": "起始日期 YYYY-MM-DD，可空"},
                    "end": {"type": "string", "description": "结束日期 YYYY-MM-DD（含），可空"},
                    "category": {"type": "string", "enum": exp_names, "description": "分类，可空"},
                }},
            }},
            {"type": "function", "function": {
                "name": "monthly_stats", "description": "月度统计：总额、分类占比、完整月环比、日均、最大三笔、最高频分类。",
                "parameters": {"type": "object", "properties": {
                    "month": {"type": "string", "description": "月份 YYYY-MM，缺省本月"},
                }},
            }},
            {"type": "function", "function": {
                "name": "set_budget", "description": "设置某分类（或 total 总预算）的月预算。",
                "parameters": {"type": "object", "properties": {
                    "category": {"type": "string", "description": "分类名或 total"},
                    "amount": {"type": "string", "description": "月预算金额（元），十进制字符串"},
                }, "required": ["category", "amount"]},
            }},
            {"type": "function", "function": {
                "name": "budget_status", "description": "查询所有已设预算的已花/剩余/超支百分比。",
                "parameters": {"type": "object", "properties": {}},
            }},
            {"type": "function", "function": {
                "name": "persona_report",
                "description": "生成「花钱人格报告」所需数据（月度统计 + 最大三笔）。",
                "parameters": {"type": "object", "properties": {
                    "month": {"type": "string", "description": "月份 YYYY-MM，缺省本月"},
                }},
            }},
            {"type": "function", "function": {
                "name": "set_mode", "description": "切换语气模式：savage=毒舌，gentle=温柔。",
                "parameters": {"type": "object", "properties": {
                    "mode": {"type": "string", "enum": ["savage", "gentle"]},
                }, "required": ["mode"]},
            }},
            {"type": "function", "function": {
                "name": "delete_expense", "description": "软删除一笔账（可恢复）。",
                "parameters": {"type": "object", "properties": {
                    "id": {"type": "integer", "description": "账目 id"},
                }, "required": ["id"]},
            }},
        ]
