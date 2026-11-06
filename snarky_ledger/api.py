"""api.py — Flask API：V2 端点 + 旧接口兼容，全部走同一服务层。"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading

from flask import Blueprint, Flask, jsonify, request, send_from_directory

from . import db as dbm
from .advanced import (
    ConfirmationService,
    MemoryService,
    ReportService,
    SessionService,
    _id,
    export_expenses_csv,
    parse_expenses_csv,
)
from .clock import Clock, SystemClock
from .config import Settings
from .domain import BusinessDate, Category, Money, Mode, Month
from .errors import InvalidArgument, LedgerError, ProviderUnavailable
from .repo import LedgerRepository
from .services import AnalysisService, BudgetService, LedgerService
from .tools import ToolRegistry

DEFAULT_LEDGER = dbm.DEFAULT_LEDGER_ID


def detect_format(db_path: str) -> str:
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return "empty"
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone():
            return "v2"
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(expenses)")}
        if "amount" in cols and "date" in cols:
            return "v1"
        return "unknown"
    finally:
        conn.close()


def ensure_db(db_path: str, clock: Clock) -> None:
    fmt = detect_format(db_path)
    if fmt in ("empty", "v2"):
        dbm.migrate(db_path, clock)
    elif fmt == "v1":
        raise RuntimeError("检测到旧格式账本，请先迁移：python -m snarky_ledger.migrate（见 docs/v2）")
    else:
        raise RuntimeError("数据库格式无法识别")


def build_services(settings: Settings, clock: Clock):
    repo = LedgerRepository(settings.db_path, clock)
    ledger = LedgerService(repo, clock)
    budget = BudgetService(repo)
    analysis = AnalysisService(repo, clock)
    tools = ToolRegistry(ledger, budget, analysis, clock)
    return repo, ledger, budget, analysis, tools


def reset_ledger(repo: LedgerRepository) -> dict:
    with repo.transaction() as conn:
        conn.execute("DELETE FROM expenses")
        conn.execute("DELETE FROM budgets")
        conn.execute("DELETE FROM mutation_events")
        conn.execute(f"UPDATE ledgers SET epoch=epoch+1, revision=0 WHERE id='{DEFAULT_LEDGER}'")
        repo.set_preference(conn, "mode", "savage")
    return {"reset": True}


def build_app(settings: Settings | None = None, clock: Clock | None = None):
    settings = settings or Settings.from_env()
    clock = clock or SystemClock()
    ensure_db(settings.db_path, clock)
    repo, ledger, budget, analysis, tools = build_services(settings, clock)
    sessions = SessionService(repo)
    memories = MemoryService(repo)
    confirmations = ConfirmationService(repo, ledger, clock)
    reports = ReportService(repo, analysis)

    app = Flask(__name__)
    app.static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
    app.config["LEDGER_SETTINGS"] = settings
    app.config["LEDGER_CLOCK"] = clock
    app.config["LEDGER_SERVICES"] = (repo, ledger, budget, analysis, tools)
    _agents: dict = {}
    _lock = threading.Lock()

    def get_agent(session_id="default"):
        if session_id not in _agents:
            from .agent import Agent
            if not settings.deepseek_api_key:
                raise ProviderUnavailable("未配置 DEEPSEEK_API_KEY，自然语言记账不可用")
            _agents[session_id] = Agent(settings=settings, clock=clock, tools=tools)
        return _agents[session_id]

    @app.errorhandler(LedgerError)
    def on_error(e: LedgerError):
        return jsonify({"error": e.to_dict()}), e.http_status

    # 本机安全：同源 + 可选访问令牌（方案 §13.1）
    def _authorized() -> bool:
        if settings.access_token:
            token = request.headers.get("X-Ledger-Token") or request.cookies.get("ledger_token")
            if token != settings.access_token:
                return False
        host = request.host or ""
        if not host.startswith(("127.0.0.1", "localhost", "::1", "[::1]")):
            return False
        origin = request.headers.get("Origin")
        if origin and request.host not in origin:
            return False
        return True

    @app.before_request
    def _guard():
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _authorized():
            raise InvalidArgument("请求来源或访问令牌校验失败")

    def _state(month: Month):
        facts = reports.get_or_compute(month)
        start, end = month.half_open_range()
        with repo.transaction() as conn:
            items = repo.list_expenses(conn, start=start, end=end, limit=50)
        return {
            "mode": tools.get_mode(),
            "facts": facts,
            "budgets": budget.status(month),
            "expenses": [
                {"id": r["id"], "amount": Money.from_minor(r["amount_minor"]).to_yuan_str(),
                 "category_id": r["category_id"], "note": r["note"],
                 "spent_on": r["spent_on"], "version": r["version"], "deleted_at": r["deleted_at"],
                 "kind": r["kind"]}
                for r in items
            ],
        }

    def _old_state(month: Month):
        facts = reports.get_or_compute(month)
        bs = budget.status(month)
        with repo.transaction() as conn:
            items = repo.list_expenses(conn, start=month.first_day, end=month.next_month.first_day, limit=50)
        by_name = {Category.parse(cid).name: round(v["amount_minor"] / 100, 2) for cid, v in facts["by_category"].items()}
        daily = [{"date": d["date"], "total": round(d["amount_minor"] / 100, 2)} for d in facts["daily"]]
        budget_rows = [{
            "category": "总预算" if b["scope_key"] == "total" else Category.parse(b["scope_key"]).name,
            "budget": round(b["budget_minor"] / 100, 2),
            "spent": round(b["spent_minor"] / 100, 2),
            "remaining": round(b["remaining_minor"] / 100, 2),
            "pct": b["pct"],
        } for b in bs["budgets"]]
        expenses = [{
            "id": r["id"], "amount": round(r["amount_minor"] / 100, 2),
            "category": Category.parse(r["category_id"]).name, "category_id": r["category_id"],
            "note": r["note"], "date": r["spent_on"], "version": r["version"], "kind": r["kind"],
        } for r in items]
        return {
            "mode": tools.get_mode(),
            "stats": {
                "month": month.iso, "total": round(facts["total_minor"] / 100, 2), "count": facts["count"],
                "income_total": round(facts["income_total_minor"] / 100, 2),
                "income_count": facts["income_count"],
                "net": round(facts["net_minor"] / 100, 2),
                "by_category": by_name, "mom_change_pct": facts["mom_full"]["change_pct"],
                "avg_daily": round(facts["avg_daily"]["amount_minor"] / 100, 2),
                "top_category": Category.parse(facts["top_category"]["category_id"]).name if facts["top_category"] else None,
            },
            "budgets": {"month": month.iso, "budgets": budget_rows},
            "expenses": expenses,
            "daily": daily,
        }

    def _run_turn(session_id, message, request_id=None):
        # 幂等：同 request_id 返回已有结果
        if request_id:
            with repo.transaction() as conn:
                existing = repo.get_command_by_idempotency(conn, request_id)
            if existing and existing["status"] == "completed" and existing["response_json"]:
                return json.loads(existing["response_json"]), True
        with _lock:
            reply = get_agent(session_id).run(message)
        result = {"reply": reply, "state": _state(Month.current(clock))}
        if request_id:
            with repo.transaction() as conn:
                cmd = repo.get_command_by_idempotency(conn, request_id)
                if cmd is None:
                    repo.create_command(conn, command_id=request_id, idempotency_key=request_id,
                                        payload_hash=hashlib.sha256(message.encode("utf-8")).hexdigest(),
                                        status="completed")
                repo.finish_command(conn, request_id, "completed", json.dumps(result, ensure_ascii=False))
        return result, False

    # --- 健康 ---
    @app.get("/health/live")
    def health_live():
        return jsonify({"status": "ok"})

    @app.get("/health/ready")
    def health_ready():
        with repo.transaction() as conn:
            rev = repo.revision(conn)
        return jsonify({"status": "ok", "ledger_revision": rev})

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    # --- V2 ---
    v2 = Blueprint("v2", __name__, url_prefix="/api/v2")

    @v2.get("/capabilities")
    def capabilities():
        return jsonify({"data": {
            "text_agent": bool(settings.deepseek_api_key) and settings.text_agent_enabled,
            "image_import": False, "voice_import": False, "csv_import": True,
        }})

    @v2.get("/state")
    def state():
        month = Month(request.args["month"]) if request.args.get("month") else Month.current(clock)
        return jsonify({"data": _state(month)})

    @v2.post("/expenses")
    def add_expense():
        body = request.get_json(force=True, silent=True) or {}
        amount = Money.parse(body.get("amount"))
        category = Category.parse(body.get("category"))
        spent_on = BusinessDate(body["spent_on"]) if body.get("spent_on") else BusinessDate.today(clock)
        kind = body.get("kind", "expense")
        rec = ledger.add(amount=amount, category=category, spent_on=spent_on,
                         note=body.get("note", ""), source="manual", kind=kind)
        return jsonify({"data": rec}), 201

    @v2.get("/expenses")
    def list_expenses():
        start = request.args.get("start")
        end = request.args.get("end")
        cat = request.args.get("category_id")
        s = BusinessDate(start).iso if start else None
        e = BusinessDate(end).iso if end else None
        if s and e and s > e:
            raise InvalidArgument("起始日期不能晚于结束日期")
        limit = min(int(request.args.get("limit", 50)), 100)
        with repo.transaction() as conn:
            items = repo.list_expenses(conn, start=s, end=e, category_id=cat, limit=limit)
            agg = repo.aggregate(conn, start=s, end=e, category_id=cat)
        return jsonify({"data": {
            "total_minor": agg["total_minor"], "count": agg["count"],
            "items": [
                {"id": r["id"], "amount_minor": r["amount_minor"], "amount": Money.from_minor(r["amount_minor"]).to_yuan_str(),
                 "category_id": r["category_id"], "note": r["note"], "spent_on": r["spent_on"], "version": r["version"]}
                for r in items
            ],
        }})

    @v2.patch("/expenses/<int:eid>")
    def edit_expense(eid):
        body = request.get_json(force=True, silent=True) or {}
        version = int(body.get("version", 0))
        amount = Money.parse(body["amount"])
        category = Category.parse(body["category"])
        spent_on = BusinessDate(body["spent_on"])
        return jsonify({"data": ledger.edit(eid, version, amount=amount, category=category, spent_on=spent_on, note=body.get("note", ""))})

    @v2.delete("/expenses/<int:eid>")
    def delete_expense(eid):
        body = request.get_json(force=True, silent=True) or {}
        version = int(body.get("version", 0))
        return jsonify({"data": ledger.soft_delete(eid, version)})

    @v2.post("/expenses/<int:eid>/restore")
    def restore_expense(eid):
        body = request.get_json(force=True, silent=True) or {}
        version = int(body.get("version", 0))
        return jsonify({"data": ledger.restore(eid, version)})

    @v2.put("/budgets/<period>/<scope_key>")
    def set_budget(period, scope_key):
        body = request.get_json(force=True, silent=True) or {}
        amount = Money.parse(body.get("amount"))
        return jsonify({"data": budget.set(period=Month(period), scope_key=scope_key, amount=amount)})

    @v2.get("/analysis")
    def analysis_view():
        month = Month(request.args["month"]) if request.args.get("month") else Month.current(clock)
        return jsonify({"data": reports.get_or_compute(month)})

    @v2.get("/reports")
    def report_view():
        month = Month(request.args["month"]) if request.args.get("month") else Month.current(clock)
        return jsonify({"data": {"facts": reports.get_or_compute(month), "metric_version": "1"}})

    @v2.post("/sessions")
    def create_session():
        body = request.get_json(force=True, silent=True) or {}
        return jsonify({"data": sessions.create(body.get("title", ""))}), 201

    @v2.get("/sessions")
    def list_sessions():
        return jsonify({"data": sessions.list()})

    @v2.get("/sessions/<sid>/messages")
    def session_messages(sid):
        return jsonify({"data": sessions.history(sid)})

    @v2.post("/sessions/<sid>/turns")
    def session_turn(sid):
        body = request.get_json(force=True, silent=True) or {}
        message = (body.get("message") or "").strip()
        if not message:
            raise InvalidArgument("消息不能为空")
        result, cached = _run_turn(sid, message, body.get("request_id"))
        if not cached:
            sessions.add_turn(sid, message, result["reply"], body.get("request_id"))
        return jsonify({"data": result, "cached": cached})

    @v2.post("/turns")
    def turns():
        body = request.get_json(force=True, silent=True) or {}
        message = (body.get("message") or "").strip()
        if not message:
            raise InvalidArgument("消息不能为空")
        result, _ = _run_turn("default", message, body.get("request_id"))
        return jsonify({"data": result})

    @v2.get("/preferences")
    def get_preferences():
        return jsonify({"data": {"mode": tools.get_mode()}})

    @v2.patch("/preferences")
    def patch_preferences():
        body = request.get_json(force=True, silent=True) or {}
        mode = Mode.parse(body.get("mode"))
        with repo.transaction() as conn:
            repo.set_preference(conn, "mode", mode)
        return jsonify({"data": {"mode": mode}})

    @v2.get("/memories")
    def list_memories():
        return jsonify({"data": memories.list()})

    @v2.post("/memories")
    def add_memory():
        body = request.get_json(force=True, silent=True) or {}
        return jsonify({"data": memories.add(body.get("kind"), body.get("value"))}), 201

    @v2.delete("/memories/<mid>")
    def delete_memory(mid):
        return jsonify({"data": memories.delete(mid)})

    @v2.post("/maintenance/reset-preview")
    def reset_preview():
        return jsonify({"data": confirmations.reset_preview()})

    @v2.post("/maintenance/reset-confirm")
    def reset_confirm():
        body = request.get_json(force=True, silent=True) or {}
        result = confirmations.confirm(body.get("action_id"))
        _agents.clear()
        return jsonify({"data": result})

    @v2.get("/exports/expenses.csv")
    def export_csv():
        start = request.args.get("start")
        end = request.args.get("end")
        s = BusinessDate(start).iso if start else None
        e = BusinessDate(end).iso if end else None
        with repo.transaction() as conn:
            rows = repo.list_expenses(conn, start=s, end=e, limit=10000)
        from flask import Response
        return Response(export_expenses_csv(rows), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=expenses.csv"})

    @v2.post("/imports/csv")
    def import_csv_parse():
        body = request.get_json(force=True, silent=True) or {}
        text = body.get("csv_text") or ""
        if not text.strip():
            raise InvalidArgument("CSV 内容为空")
        return jsonify({"data": parse_expenses_csv(text)})

    @v2.post("/imports/csv/confirm")
    def import_csv_confirm():
        body = request.get_json(force=True, silent=True) or {}
        candidates = body.get("candidates") or []
        added = []
        for c in candidates:
            rec = ledger.add(amount=Money.parse(c.get("amount")), category=Category.parse(c.get("category_id")),
                             spent_on=BusinessDate(c.get("spent_on")), note=c.get("note", ""), source="import")
            added.append(rec["id"])
        return jsonify({"data": {"added": added, "count": len(added)}}), 201

    app.register_blueprint(v2)

    # --- 旧接口兼容 ---
    @app.post("/api/state")
    def old_state():
        data = request.get_json(force=True, silent=True) or {}
        month = Month(data["month"]) if data.get("month") else Month.current(clock)
        return jsonify(_old_state(month))

    @app.post("/api/act")
    def old_act():
        data = request.get_json(force=True, silent=True) or {}
        message = (data.get("message") or "").strip()
        if not message:
            raise InvalidArgument("消息不能为空")
        result, _ = _run_turn("default", message, data.get("request_id"))
        return jsonify({"reply": result["reply"], **_old_state(Month.current(clock))})

    @app.post("/api/budget")
    def old_budget():
        data = request.get_json(force=True, silent=True) or {}
        scope = "total" if str(data.get("category", "")).strip() in ("total", "总") else Category.parse(data.get("category")).id
        budget.set(period=Month.current(clock), scope_key=scope, amount=Money.parse(data.get("amount")))
        return jsonify(_old_state(Month.current(clock)))

    @app.post("/api/reset")
    def old_reset():
        # 安全不兼容：无确认清库 → 返回确认信息 + 预览 + action_id
        preview = confirmations.reset_preview()
        return jsonify({
            "error": {"code": "CONFIRMATION_REQUIRED",
                      "message": "清空账本需要确认，请调用 /api/v2/maintenance/reset-confirm",
                      "action_id": preview["action_id"], "preview": preview["preview"]},
        }), 409

    return app
