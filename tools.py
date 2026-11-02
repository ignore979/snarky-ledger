"""tools.py — function calling 工具集 + JSON Schema + 分发执行。

8 个工具对应 PLAN §6，每个返回 JSON 字符串喂回给 LLM。
"""
from __future__ import annotations

import calendar
import json
from datetime import datetime

import ledger
from ledger import CATEGORIES
from persona import REPORT_STRUCTURE


def _ok(payload):
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _err(msg):
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


# --- 工具实现 ---------------------------------------------------------------

def tool_add_expense(amount, category, note="", date=None):
    rec = ledger.add_expense(amount, category, note, date)
    return _ok({"result": rec})


def tool_query_expenses(start=None, end=None, category=None):
    q = ledger.query_expenses(start=start, end=end, category=category, limit=20)
    return _ok({"result": q})


def tool_monthly_stats(month=None):
    return _ok({"result": ledger.monthly_stats(month)})


def tool_set_budget(category, amount):
    return _ok({"result": ledger.set_budget(category, amount)})


def tool_budget_status():
    return _ok({"result": ledger.budget_status()})


def tool_persona_report(month=None):
    month = month or datetime.now().strftime("%Y-%m")
    stats = ledger.monthly_stats(month)
    y, m = int(month[:4]), int(month[5:7])
    end = f"{month}-{calendar.monthrange(y, m)[1]:02d}"
    q = ledger.query_expenses(start=month + "-01", end=end, limit=200)
    top3 = sorted(q["items"], key=lambda r: r["amount"], reverse=True)[:3]
    return _ok(
        {
            "result": {
                "stats": stats,
                "top3": [
                    {"amount": r["amount"], "category": r["category"], "note": r["note"], "date": r["date"]}
                    for r in top3
                ],
            }
        }
    )


def tool_set_mode(mode):
    m = ledger.set_mode(mode)
    hint = (
        "已切换到温柔模式，接下来请温柔、不毒舌地回复。"
        if m["mode"] == "gentle"
        else "已切回毒舌模式，可以开损了，但记得损事不损人。"
    )
    return _ok({"mode": m["mode"], "hint": hint})


def tool_delete_expense(id):
    return _ok({"result": ledger.delete_expense(id)})


TOOL_FUNCTIONS = {
    "add_expense": tool_add_expense,
    "query_expenses": tool_query_expenses,
    "monthly_stats": tool_monthly_stats,
    "set_budget": tool_set_budget,
    "budget_status": tool_budget_status,
    "persona_report": tool_persona_report,
    "set_mode": tool_set_mode,
    "delete_expense": tool_delete_expense,
}


def execute_tool(name, args):
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return _err(f"未知工具：{name}")
    try:
        return fn(**args)
    except TypeError as e:
        return _err(f"参数错误：{e}")
    except Exception as e:  # noqa: BLE001
        return _err(str(e))


# --- JSON Schema（OpenAI function calling 格式） -----------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_expense",
            "description": "记一笔支出。用户报账时调用，返回该分类本月累计金额与次数，供吐槽用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "金额（元）"},
                    "category": {"type": "string", "enum": CATEGORIES, "description": "支出分类"},
                    "note": {"type": "string", "description": "备注，如「火锅」"},
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD，缺省今天"},
                },
                "required": ["amount", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_expenses",
            "description": "按日期范围/分类查账，返回总额、分类占比与明细。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "起始日期 YYYY-MM-DD，可空"},
                    "end": {"type": "string", "description": "结束日期 YYYY-MM-DD，可空"},
                    "category": {"type": "string", "enum": CATEGORIES, "description": "分类，可空"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "monthly_stats",
            "description": "月度统计：总额、分类占比、环比、日均、最大单笔、最高频分类。",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string", "description": "月份 YYYY-MM，缺省本月"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_budget",
            "description": "设置某分类的月预算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": CATEGORIES, "description": "分类"},
                    "amount": {"type": "number", "description": "月预算金额（元）"},
                },
                "required": ["category", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "budget_status",
            "description": "查询所有已设预算分类的已花/剩余/超支百分比。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "persona_report",
            "description": "生成「花钱人格报告」所需数据（月度统计 + 本月最大三笔）。" + REPORT_STRUCTURE,
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string", "description": "月份 YYYY-MM，缺省本月"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_mode",
            "description": "切换语气模式：savage=毒舌，gentle=温柔（用户说「别损了/心情不好」时用）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["savage", "gentle"], "description": "模式"},
                },
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_expense",
            "description": "删除一笔账（纠错）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "账目 id"},
                },
                "required": ["id"],
            },
        },
    },
]
