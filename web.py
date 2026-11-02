"""web.py — Flask 后端：/api/state /api/act /api/budget /api/reset。"""
from __future__ import annotations

import threading

from flask import Flask, jsonify, request, send_from_directory

import ledger

app = Flask(__name__, static_folder="static", static_url_path="/static")

_agent = None
_lock = threading.Lock()


def get_agent():
    global _agent
    if _agent is None:
        from agent import Agent

        _agent = Agent()
    return _agent


def build_state():
    """前端一次拿全：模式 + 月度统计 + 预算 + 最近账目 + 每日序列。"""
    return {
        "mode": ledger.get_mode(),
        "stats": ledger.monthly_stats(),
        "budgets": ledger.budget_status(),
        "expenses": ledger.query_expenses(limit=50)["items"],
        "daily": ledger.daily_totals(),
    }


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/state")
def state():
    return jsonify(build_state())


@app.post("/api/act")
def act():
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400
    with _lock:
        try:
            reply = get_agent().run(message)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
    return jsonify({"reply": reply, **build_state()})


@app.post("/api/budget")
def set_budget():
    data = request.get_json(force=True, silent=True) or {}
    try:
        ledger.set_budget(data.get("category"), data.get("amount"))
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400
    return jsonify(build_state())


@app.post("/api/reset")
def reset():
    ledger.reset()
    if _agent is not None:
        _agent.reset()
    return jsonify(build_state())


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    ledger.init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
