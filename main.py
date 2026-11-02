"""main.py — 终端 REPL。

用法：
    python main.py               # 终端对话
    python main.py --web         # 启动网页版
    python main.py --web --port 8000
"""
from __future__ import annotations

import os
import sys


def _fix_encoding():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


BANNER = """
╔══════════════════════════════════════════╗
║        损友账本 · Snarky Ledger          ║
║   一个会毒舌吐槽你花钱的记账 Agent        ║
╚══════════════════════════════════════════╝
"""


def run_repl():
    from dotenv import load_dotenv

    load_dotenv()
    import ledger

    ledger.init_db()
    from agent import Agent

    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("缺少 DEEPSEEK_API_KEY：请先 `cp .env.example .env` 并填入你的 key，或写入环境变量。")
        return

    agent = Agent()
    print(BANNER)
    print("直接说人话记账 / 查账 / 统计 / 设预算。")
    print("/mode gentle 切温柔  /mode savage 切毒舌  /reset 清空  /exit 退出")
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
        if text == "/reset":
            ledger.reset()
            agent.reset()
            print("账哥 > 账本清空了，希望这次你是认真的。")
            continue
        if text.startswith("/mode"):
            m = "gentle" if "gentle" in text else "savage"
            ledger.set_mode(m)
            print(f"账哥 > 模式已切到 {'温柔' if m == 'gentle' else '毒舌'}。")
            continue
        try:
            reply = agent.run(text)
        except Exception as e:  # noqa: BLE001
            reply = f"（出错了：{e}）"
        print(f"账哥 > {reply}")


def run_web(port=None):
    from dotenv import load_dotenv

    load_dotenv()
    import ledger

    ledger.init_db()
    from web import app

    port = port or int(os.environ.get("PORT", 5000))
    print(f"网页版启动：http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


def main():
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
