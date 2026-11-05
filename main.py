"""main.py — 入口。

用法：
    python main.py                # 终端对话（自然语言记账）
    python main.py --web          # 网页版（默认 http://127.0.0.1:5000）
    python main.py --web --port 8000
"""
from __future__ import annotations

import sys

from dotenv import load_dotenv


def _fix_encoding():
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")


BANNER = """
╔══════════════════════════════════════════╗
║        损友账本 · Snarky Ledger          ║
║   一个会毒舌吐槽你花钱的记账 Agent        ║
╚══════════════════════════════════════════╝
"""


def _services():
    from snarky_ledger import Settings, SystemClock
    from snarky_ledger.api import build_services, ensure_db

    settings = Settings.from_env()
    clock = SystemClock()
    ensure_db(settings.db_path, clock)
    repo, ledger, budget, analysis, tools = build_services(settings, clock)
    return settings, clock, tools


def run_repl():
    from snarky_ledger.agent import Agent

    settings, clock, tools = _services()
    if not settings.deepseek_api_key:
        print("缺少 DEEPSEEK_API_KEY：请先 `cp .env.example .env` 并填入 key。")
        return

    agent = Agent(settings=settings, clock=clock, tools=tools)
    print(BANNER)
    print("直接说人话记账 / 查账 / 统计 / 设预算。")
    print("/mode gentle 切温柔  /mode savage 切毒舌  /exit 退出")
    print("-" * 60)

    while True:
        try:
            text = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n账哥 > 走了？行，账本我帮你盯着。")
            break
        if not text:
            continue
        if text in ("/exit", "/quit", "退出", "quit", "exit"):
            print("账哥 > 走了？行，账本我帮你盯着。")
            break
        if text.startswith("/mode"):
            m = "gentle" if "gentle" in text else "savage"
            tools.set_mode(m)
            print(f"账哥 > 已切到 {'温柔' if m == 'gentle' else '毒舌'}模式。")
            continue
        try:
            reply = agent.run(text)
        except Exception as e:  # noqa: BLE001
            reply = f"（出错了：{e}）"
        print(f"账哥 > {reply}")


def run_web(port=None):
    from snarky_ledger import Settings, create_app

    settings = Settings.from_env()
    app = create_app(settings)
    port = port or settings.port
    print(f"网页版启动：http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


def main():
    load_dotenv()
    _fix_encoding()
    args = sys.argv[1:]
    if "--web" in args:
        port = None
        for i, a in enumerate(args):
            if a == "--port" and i + 1 < len(args):
                port = int(args[i + 1])
        run_web(port)
    else:
        run_repl()


if __name__ == "__main__":
    main()
