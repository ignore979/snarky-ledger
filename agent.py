"""agent.py — ReAct 循环：LLM 决定调工具 → 执行 → 结果喂回 → 直到最终回复。

与「地牢主」同一套引擎，只是把 move/attack 换成 add_expense/query_expenses。
"""
from __future__ import annotations

import json
import os

from openai import OpenAI

import ledger
import tools
from persona import build_system_prompt

MAX_STEPS = 6


class Agent:
    def __init__(self, api_key=None, base_url=None, model=None, client=None, temperature=0.8):
        api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        base_url = base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self.model = model
        self.temperature = temperature
        self.messages = []
        if client is None and not api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在 .env 或环境变量中配置")
        # 允许注入假 client 便于离线测试
        self.client = client or OpenAI(api_key=api_key, base_url=base_url)

    @property
    def mode(self):
        return ledger.get_mode()

    def run(self, user_text):
        self.messages.append({"role": "user", "content": user_text})
        for _ in range(MAX_STEPS):
            system = build_system_prompt(self.mode)
            msgs = [{"role": "system", "content": system}] + self.messages
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=msgs,
                tools=tools.TOOLS,
                tool_choice="auto",
                temperature=self.temperature,
            )
            msg = resp.choices[0].message

            if getattr(msg, "tool_calls", None):
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = tools.execute_tool(tc.function.name, args)
                    self.messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": result}
                    )
                continue

            content = msg.content or ""
            self.messages.append({"role": "assistant", "content": content})
            return content

        return "（账哥卡壳了，你再说一遍？）"

    def reset(self):
        self.messages = []
