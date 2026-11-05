"""test_agent.py — ReAct 编排器：假 client 注入，验证工具执行与最终回复。"""
import os
import tempfile
import types
import unittest
from datetime import date

from snarky_ledger import db as dbm
from snarky_ledger.agent import Agent
from snarky_ledger.clock import FrozenClock
from snarky_ledger.config import Settings
from snarky_ledger.domain import Month
from snarky_ledger.repo import LedgerRepository
from snarky_ledger.services import AnalysisService, BudgetService, LedgerService
from snarky_ledger.tools import ToolRegistry


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.i = 0

    def create(self, **kw):
        r = self.script[self.i]
        self.i += 1
        return r


class FakeClient:
    def __init__(self, script):
        self.chat = types.SimpleNamespace(completions=FakeCompletions(script))


def tool_msg(calls):
    msg = types.SimpleNamespace(content=None, tool_calls=[])
    for name, args in calls:
        msg.tool_calls.append(types.SimpleNamespace(
            id="c1", type="function",
            function=types.SimpleNamespace(name=name, arguments=args),
        ))
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def text_msg(t):
    return types.SimpleNamespace(choices=[
        types.SimpleNamespace(message=types.SimpleNamespace(content=t, tool_calls=None))
    ])


class AgentTest(unittest.TestCase):
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
        self.settings = Settings(db_path=self.db_path, deepseek_api_key="sk-test")

    def test_loop_add_expense(self):
        agent = Agent(settings=self.settings, clock=self.clock, tools=self.tools,
                      client=FakeClient([
                          tool_msg([("add_expense", '{"amount":"50","category":"餐饮","note":"火锅"}')]),
                          text_msg("火锅 50 已入账，本月餐饮 50。"),
                      ]))
        reply = agent.run("今天花 50 吃火锅")
        self.assertEqual(reply, "火锅 50 已入账，本月餐饮 50。")
        self.assertEqual(self.analysis.monthly_facts(Month("2026-11"))["total_minor"], 5000)

    def test_loop_set_mode(self):
        agent = Agent(settings=self.settings, clock=self.clock, tools=self.tools,
                      client=FakeClient([
                          tool_msg([("set_mode", '{"mode":"gentle"}')]),
                          text_msg("行，今天不损你。"),
                      ]))
        reply = agent.run("别损我，今天心情差")
        self.assertEqual(reply, "行，今天不损你。")
        self.assertEqual(self.tools.get_mode(), "gentle")

    def test_loop_bad_json_tool_args(self):
        # 畸形 JSON 不导致副作用
        agent = Agent(settings=self.settings, clock=self.clock, tools=self.tools,
                      client=FakeClient([
                          tool_msg([("add_expense", '{not json')]),
                          text_msg("没记上，重说一遍？"),
                      ]))
        reply = agent.run("记一笔")
        self.assertEqual(reply, "没记上，重说一遍？")
        self.assertEqual(self.analysis.monthly_facts(Month("2026-11"))["count"], 0)


if __name__ == "__main__":
    unittest.main()
