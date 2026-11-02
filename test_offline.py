"""test_offline.py — 无 API key 的离线测试：ledger 数据层 + 工具分发 + ReAct 循环。

运行：python test_offline.py
用假 client 注入 agent，验证「LLM 决定调工具 → 执行 → 喂回 → 最终回复」的循环。
"""
from __future__ import annotations

import os
import tempfile
import types

import ledger
import tools
from agent import Agent


def setup_db():
    ledger.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
    ledger.init_db()


# --- 假 OpenAI client，按脚本依次返回响应 ------------------------------------

class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.i = 0

    def create(self, **kwargs):
        resp = self.script[self.i]
        self.i += 1
        return resp


class FakeClient:
    def __init__(self, script):
        self.chat = types.SimpleNamespace(completions=FakeCompletions(script))


def make_tool_call_msg(tool_calls):
    msg = types.SimpleNamespace(content=None, tool_calls=[])
    for name, args in tool_calls:
        msg.tool_calls.append(
            types.SimpleNamespace(
                id="call_1",
                type="function",
                function=types.SimpleNamespace(name=name, arguments=args),
            )
        )
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def make_text_msg(text):
    msg = types.SimpleNamespace(content=text, tool_calls=None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


# --- 测试 -------------------------------------------------------------------

def test_ledger():
    setup_db()
    ledger.add_expense(50, "餐饮", "火锅")
    ledger.add_expense(18, "餐饮", "奶茶")
    ledger.add_expense(299, "购物", "耳机")
    assert ledger.monthly_stats()["total"] == 367.0
    assert ledger.query_expenses()["count"] == 3
    ledger.set_budget("餐饮", 100)
    st = ledger.budget_status()["budgets"][0]
    assert st["spent"] == 68.0 and st["pct"] == 68.0
    print("  [ok] ledger")


def test_execute_tool():
    setup_db()
    assert '"ok": true' in tools.execute_tool(
        "add_expense", {"amount": 50, "category": "餐饮", "note": "火锅"}
    )
    assert '"ok": false' in tools.execute_tool("add_expense", {"amount": 0, "category": "餐饮"})
    assert '"ok": false' in tools.execute_tool("nope", {})
    print("  [ok] execute_tool")


def test_agent_loop():
    setup_db()
    script = [
        make_tool_call_msg([("add_expense", '{"amount": 50, "category": "餐饮", "note": "火锅"}')]),
        make_text_msg("火锅 50 已入账，本月餐饮 50，你肠胃比钱包能扛。"),
    ]
    agent = Agent(client=FakeClient(script))
    reply = agent.run("今天花 50 吃火锅")
    assert reply == "火锅 50 已入账，本月餐饮 50，你肠胃比钱包能扛。"
    assert ledger.query_expenses()["total"] == 50.0
    print("  [ok] agent loop (add_expense -> 最终回复)")


def test_agent_mode_switch():
    setup_db()
    script = [
        make_tool_call_msg([("set_mode", '{"mode": "gentle"}')]),
        make_text_msg("行，今天不损你。"),
    ]
    agent = Agent(client=FakeClient(script))
    reply = agent.run("别损我，今天心情差")
    assert reply == "行，今天不损你。"
    assert ledger.get_mode() == "gentle"
    print("  [ok] agent loop (set_mode gentle)")


if __name__ == "__main__":
    print("running offline tests...")
    test_ledger()
    test_execute_tool()
    test_agent_loop()
    test_agent_mode_switch()
    print("ALL OFFLINE TESTS PASSED")
