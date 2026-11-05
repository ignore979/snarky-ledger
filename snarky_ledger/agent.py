"""agent.py — ReAct 编排器：LLM 决定调工具 → 严格校验执行 → 结果喂回 → 最终回复。"""
from __future__ import annotations

import json

from openai import OpenAI

from .persona import build_system_prompt
from .tools import ToolRegistry

MAX_STEPS = 6
MAX_TOOLS_PER_TURN = 12


class Agent:
    def __init__(self, *, settings, clock, tools: ToolRegistry, client=None, temperature=0.8):
        self.settings = settings
        self.clock = clock
        self.tools = tools
        self.temperature = temperature
        self.model = settings.deepseek_model
        self.messages: list = []
        if client is None:
            if not settings.deepseek_api_key:
                raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在 .env 或环境变量中配置")
            client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
        self.client = client

    @property
    def mode(self):
        return self.tools.get_mode()

    def run(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        tool_count = 0
        for _ in range(MAX_STEPS):
            system = build_system_prompt(self.mode, self.clock.today().isoformat())
            msgs = [{"role": "system", "content": system}] + self.messages
            resp = self.client.chat.completions.create(
                model=self.model, messages=msgs, tools=self.tools.schemas(),
                tool_choice="auto", temperature=self.temperature,
            )
            msg = resp.choices[0].message
            if getattr(msg, "tool_calls", None):
                self.messages.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in msg.tool_calls
                    ],
                })
                for tc in msg.tool_calls:
                    tool_count += 1
                    if tool_count > MAX_TOOLS_PER_TURN:
                        self.messages.append({"role": "tool", "tool_call_id": tc.id,
                                              "content": json.dumps({"ok": False, "error": "本次操作步数已达上限"})})
                        continue
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        self.messages.append({"role": "tool", "tool_call_id": tc.id,
                                              "content": json.dumps({"ok": False, "error": "工具参数不是合法 JSON"})})
                        continue
                    result = self.tools.execute(tc.function.name, args)
                    self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                continue
            content = msg.content or ""
            self.messages.append({"role": "assistant", "content": content})
            return content
        return "（账哥卡壳了，你再说一遍？）"

    def reset(self):
        self.messages = []
