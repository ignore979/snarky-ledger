"""advanced.py — 会话、记忆、确认、报告缓存与 CSV 导入导出。"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import timedelta

from .clock import Clock
from .domain import BusinessDate, Category, Money, Month
from .errors import InvalidArgument, NotFound, VersionConflict
from .repo import LedgerRepository
from .services import AnalysisService, LedgerService, fmt

METRIC_VERSION = "1"
# 记忆白名单（方案 §9.3）：不得记忆病史/亲友/工资/债务/情绪/人格标签
MEMORY_KINDS = {"category_alias", "auto_add", "default_month_view", "budget_preference"}


def _id(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


class SessionService:
    def __init__(self, repo: LedgerRepository):
        self.repo = repo

    def create(self, title="") -> dict:
        sid = _id("sess")
        with self.repo.transaction() as conn:
            return self.repo.create_session(conn, session_id=sid, title=title)

    def list(self, limit=50):
        with self.repo.transaction() as conn:
            return self.repo.list_sessions(conn, limit)

    def add_turn(self, session_id, user_text, reply, request_id=None):
        with self.repo.transaction() as conn:
            if self.repo.get_session(conn, session_id) is None:
                raise NotFound(f"会话不存在：{session_id}")
            seq = self.repo.next_seq(conn, session_id)
            self.repo.add_message(conn, message_id=_id("msg"), session_id=session_id, seq=seq,
                                  role="user", content_json=json.dumps({"text": user_text}, ensure_ascii=False),
                                  request_id=request_id)
            self.repo.add_message(conn, message_id=_id("msg"), session_id=session_id, seq=seq + 1,
                                  role="assistant", content_json=json.dumps({"text": reply}, ensure_ascii=False))
            return {"session_id": session_id, "seq": seq + 1}

    def history(self, session_id, limit=100):
        with self.repo.transaction() as conn:
            rows = self.repo.list_messages(conn, session_id, limit)
        return [
            {"seq": r["seq"], "role": r["role"], "content": json.loads(r["content_json"]).get("text", "")}
            for r in rows
        ]


class MemoryService:
    def __init__(self, repo: LedgerRepository):
        self.repo = repo

    def add(self, kind, value, *, source_message_id=None, expires_at=None):
        if kind not in MEMORY_KINDS:
            raise InvalidArgument(f"不支持的记忆类型：{kind}（可选：{'/'.join(sorted(MEMORY_KINDS))}）")
        with self.repo.transaction() as conn:
            return self.repo.add_memory(
                conn, memory_id=_id("mem"), kind=kind,
                value_json=json.dumps(value, ensure_ascii=False),
                source_message_id=source_message_id, expires_at=expires_at,
            )

    def list(self):
        with self.repo.transaction() as conn:
            rows = self.repo.list_memories(conn)
        return [
            {"id": r["id"], "kind": r["kind"], "value": json.loads(r["value_json"]),
             "consent_at": r["consent_at"], "expires_at": r["expires_at"]}
            for r in rows
        ]

    def delete(self, memory_id):
        with self.repo.transaction() as conn:
            ok = self.repo.soft_delete_memory(conn, memory_id)
        if not ok:
            raise NotFound(f"记忆不存在：{memory_id}")
        return {"id": memory_id, "deleted": True}


class ConfirmationService:
    """破坏性/影响已有数据的操作：先生成待确认动作，确认后一次性消费。"""

    def __init__(self, repo: LedgerRepository, ledger: LedgerService, clock: Clock):
        self.repo = repo
        self.ledger = ledger
        self.clock = clock

    def _create(self, action_type, payload) -> dict:
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        action_id = _id("act")
        expires = (self.clock.now() + timedelta(minutes=10)).isoformat()
        with self.repo.transaction() as conn:
            self.repo.create_pending_action(
                conn, action_id=action_id, action_type=action_type,
                payload_json=payload_json,
                payload_hash=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                expires_at=expires,
            )
        return {"action_id": action_id, "action_type": action_type, "expires_at": expires, "payload": payload}

    def confirm(self, action_id) -> dict:
        with self.repo.transaction() as conn:
            act = self.repo.get_pending_action(conn, action_id)
            if act is None:
                raise NotFound(f"确认动作不存在：{action_id}")
            if act["status"] != "pending" or act["expires_at"] < self.clock.now().isoformat():
                raise InvalidArgument("确认动作已过期或已使用")
            payload = json.loads(act["payload_json"])
            result = self._execute(conn, act["action_type"], payload)
            self.repo.consume_pending_action(conn, action_id)
            return {"action_id": action_id, "result": result}

    def _execute(self, conn, action_type, payload):
        # 只执行已知类型；清空等维护操作不在 LLM 工具白名单内
        if action_type == "reset":
            from .api import reset_ledger
            return reset_ledger(self.repo)
        if action_type == "delete_expense":
            eid = int(payload["expense_id"])
            row = self.repo.get_expense(conn, eid)
            if row is None:
                raise NotFound(f"账目不存在：{eid}")
            return self.ledger.soft_delete(eid, row["version"])
        raise InvalidArgument(f"未知确认动作类型：{action_type}")

    def reset_preview(self) -> dict:
        with self.repo.transaction() as conn:
            agg = self.repo.aggregate(conn)
        payload = {"action": "reset"}
        return {**self._create("reset", payload), "preview": {"expense_count": agg["count"]}}


class ReportService:
    def __init__(self, repo: LedgerRepository, analysis: AnalysisService):
        self.repo = repo
        self.analysis = analysis

    def get_or_compute(self, period: Month) -> dict:
        with self.repo.transaction() as conn:
            rev = self.repo.revision(conn)
            cached = self.repo.get_report_cache(conn, period.iso)
        if cached and cached["ledger_revision"] == rev and cached["metric_version"] == METRIC_VERSION:
            return json.loads(cached["facts_json"])
        facts = self.analysis.monthly_facts(period)
        with self.repo.transaction() as conn:
            self.repo.set_report_cache(conn, period=period.iso, metric_version=METRIC_VERSION,
                                       ledger_revision=rev, facts_json=json.dumps(facts, ensure_ascii=False))
        return facts


def _csv_safe(s: str) -> str:
    # 公式注入防护：以 = + - @ 开头的字段前加单引号
    if s and s[0] in "=+-@":
        return "'" + s
    return s


def export_expenses_csv(rows: list) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "amount", "category", "note"])
    for r in rows:
        w.writerow([
            r["spent_on"],
            Money.from_minor(r["amount_minor"]).to_yuan_str(),
            Category.parse(r["category_id"]).name,
            _csv_safe(r["note"]),
        ])
    return buf.getvalue()


def parse_expenses_csv(text: str) -> dict:
    reader = csv.DictReader(io.StringIO(text))
    candidates = []
    errors = []
    for i, row in enumerate(reader, start=2):
        errs = []
        try:
            money = Money.parse((row.get("amount") or "").strip())
        except Exception:
            money = None
            errs.append("invalid_amount")
        try:
            cat = Category.parse(row.get("category"))
        except Exception:
            cat = None
            errs.append("invalid_category")
        try:
            spent = BusinessDate(row.get("date"))
        except Exception:
            spent = None
            errs.append("invalid_date")
        if errs or money is None:
            errors.append({"row": i, "types": errs, "raw": row})
            continue
        candidates.append({
            "amount": money.to_yuan_str(), "amount_minor": money.minor,
            "category_id": cat.id, "note": (row.get("note") or "").strip(),
            "spent_on": spent.iso,
        })
    return {"candidates": candidates, "errors": errors, "total_minor": sum(c["amount_minor"] for c in candidates)}
