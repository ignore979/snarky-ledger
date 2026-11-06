"""repo.py — SQL 数据访问。写操作由服务层在短事务内组合，本层只做参数化 SQL。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from .clock import Clock, SystemClock
from .db import DEFAULT_LEDGER_ID, connect


def _row_dict(row) -> dict:
    return dict(row) if row is not None else None


class LedgerRepository:
    def __init__(self, db_path: str, clock: Clock | None = None):
        self.db_path = db_path
        self.clock = clock or SystemClock()

    def now(self) -> str:
        return self.clock.now().isoformat()

    @contextmanager
    def transaction(self):
        conn = connect(self.db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- 账本版本 ---
    def revision(self, conn) -> int:
        return conn.execute(
            "SELECT revision FROM ledgers WHERE id=?", (DEFAULT_LEDGER_ID,)
        ).fetchone()["revision"]

    def bump_revision(self, conn) -> int:
        conn.execute(
            "UPDATE ledgers SET revision = revision + 1 WHERE id=?", (DEFAULT_LEDGER_ID,)
        )
        return self.revision(conn)

    def add_event(self, conn, entity_type: str, entity_id: str, operation: str) -> None:
        conn.execute(
            "INSERT INTO mutation_events(ledger_id, entity_type, entity_id, operation, occurred_at)"
            " VALUES(?,?,?,?,?)",
            (DEFAULT_LEDGER_ID, entity_type, entity_id, operation, self.now()),
        )

    # --- 账目 ---
    def insert_expense(self, conn, *, amount_minor, category_id, note, spent_on, source, command_id) -> dict:
        now = self.now()
        cur = conn.execute(
            "INSERT INTO expenses(ledger_id, amount_minor, category_id, note, spent_on, source,"
            " created_at, updated_at, deleted_at, version, command_id)"
            " VALUES(?,?,?,?,?,?,?,?,NULL,1,?)",
            (DEFAULT_LEDGER_ID, amount_minor, category_id, note, spent_on, source, now, now, command_id),
        )
        return _row_dict(self.get_expense(conn, cur.lastrowid))

    def get_expense(self, conn, expense_id: int) -> dict | None:
        return _row_dict(
            conn.execute("SELECT * FROM expenses WHERE id=? AND ledger_id=?", (expense_id, DEFAULT_LEDGER_ID)).fetchone()
        )

    def update_expense(self, conn, expense_id, version, *, amount_minor, category_id, note, spent_on) -> dict | None:
        cur = conn.execute(
            "UPDATE expenses SET amount_minor=?, category_id=?, note=?, spent_on=?, updated_at=?, version=version+1"
            " WHERE id=? AND ledger_id=? AND version=? AND deleted_at IS NULL",
            (amount_minor, category_id, note, spent_on, self.now(), expense_id, DEFAULT_LEDGER_ID, version),
        )
        if cur.rowcount == 0:
            return None
        return _row_dict(self.get_expense(conn, expense_id))

    def set_deleted(self, conn, expense_id, version, deleted_at: str | None) -> dict | None:
        cur = conn.execute(
            "UPDATE expenses SET deleted_at=?, updated_at=?, version=version+1"
            " WHERE id=? AND ledger_id=? AND version=?",
            (deleted_at, self.now(), expense_id, DEFAULT_LEDGER_ID, version),
        )
        if cur.rowcount == 0:
            return None
        return _row_dict(self.get_expense(conn, expense_id))

    def list_expenses(self, conn, *, start=None, end=None, category_id=None, include_deleted=False,
                      limit=50, after_id=None) -> list:
        where = ["ledger_id=?"]
        params = [DEFAULT_LEDGER_ID]
        if not include_deleted:
            where.append("deleted_at IS NULL")
        if start:
            where.append("spent_on >= ?")
            params.append(start)
        if end:
            where.append("spent_on < ?")
            params.append(end)
        if category_id:
            where.append("category_id = ?")
            params.append(category_id)
        if after_id:
            where.append("id < ?")
            params.append(after_id)
        sql = f"SELECT * FROM expenses WHERE {' AND '.join(where)} ORDER BY spent_on DESC, id DESC LIMIT ?"
        return [_row_dict(r) for r in conn.execute(sql, params + [limit])]

    def aggregate(self, conn, *, start=None, end=None, category_id=None) -> dict:
        where = ["ledger_id=?", "deleted_at IS NULL"]
        params = [DEFAULT_LEDGER_ID]
        if start:
            where.append("spent_on >= ?")
            params.append(start)
        if end:
            where.append("spent_on < ?")
            params.append(end)
        if category_id:
            where.append("category_id = ?")
            params.append(category_id)
        base = f"FROM expenses WHERE {' AND '.join(where)}"
        total, count = conn.execute(f"SELECT COALESCE(SUM(amount_minor),0), COUNT(*) {base}", params).fetchone()
        by_cat = {
            r["category_id"]: r["t"]
            for r in conn.execute(f"SELECT category_id, SUM(amount_minor) AS t {base} GROUP BY category_id", params)
        }
        return {"total_minor": total, "count": count, "by_category": by_cat}

    def top_expenses(self, conn, *, start=None, end=None, n=3) -> list:
        where = ["ledger_id=?", "deleted_at IS NULL"]
        params = [DEFAULT_LEDGER_ID]
        if start:
            where.append("spent_on >= ?")
            params.append(start)
        if end:
            where.append("spent_on < ?")
            params.append(end)
        sql = (
            f"SELECT * FROM expenses WHERE {' AND '.join(where)}"
            " ORDER BY amount_minor DESC, spent_on DESC, id DESC LIMIT ?"
        )
        return [_row_dict(r) for r in conn.execute(sql, params + [n])]

    def daily_totals(self, conn, month_start: str, month_end: str) -> list:
        rows = conn.execute(
            "SELECT spent_on, SUM(amount_minor) AS t FROM expenses"
            " WHERE ledger_id=? AND deleted_at IS NULL AND spent_on>=? AND spent_on<?"
            " GROUP BY spent_on ORDER BY spent_on",
            (DEFAULT_LEDGER_ID, month_start, month_end),
        ).fetchall()
        return {r["spent_on"]: r["t"] for r in rows}

    def category_counts(self, conn, *, start=None, end=None) -> dict:
        where = ["ledger_id=?", "deleted_at IS NULL"]
        params = [DEFAULT_LEDGER_ID]
        if start:
            where.append("spent_on >= ?")
            params.append(start)
        if end:
            where.append("spent_on < ?")
            params.append(end)
        return {
            r["category_id"]: r["c"]
            for r in conn.execute(
                f"SELECT category_id, COUNT(*) AS c FROM expenses WHERE {' AND '.join(where)} GROUP BY category_id",
                params,
            )
        }

    # --- 预算 ---
    def upsert_budget(self, conn, *, period, scope_key, amount_minor) -> dict:
        now = self.now()
        conn.execute(
            "INSERT INTO budgets(ledger_id, period, scope_key, amount_minor, version, created_at, updated_at)"
            " VALUES(?,?,?,?,1,?,?)"
            " ON CONFLICT(ledger_id, period, scope_key) DO UPDATE SET"
            " amount_minor=excluded.amount_minor, version=version+1, updated_at=excluded.updated_at",
            (DEFAULT_LEDGER_ID, period, scope_key, amount_minor, now, now),
        )
        return _row_dict(
            conn.execute(
                "SELECT * FROM budgets WHERE ledger_id=? AND period=? AND scope_key=?",
                (DEFAULT_LEDGER_ID, period, scope_key),
            ).fetchone()
        )

    def list_budgets(self, conn, period: str) -> list:
        return [
            _row_dict(r)
            for r in conn.execute(
                "SELECT * FROM budgets WHERE ledger_id=? AND period=? ORDER BY scope_key",
                (DEFAULT_LEDGER_ID, period),
            )
        ]

    # --- 偏好 ---
    def get_preference(self, conn, key: str) -> str | None:
        row = conn.execute(
            "SELECT value_json FROM preferences WHERE ledger_id=? AND key=?",
            (DEFAULT_LEDGER_ID, key),
        ).fetchone()
        return row["value_json"] if row else None

    def set_preference(self, conn, key: str, value_json: str) -> None:
        conn.execute(
            "INSERT INTO preferences(ledger_id, key, value_json, updated_at) VALUES(?,?,?,?)"
            " ON CONFLICT(ledger_id, key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            (DEFAULT_LEDGER_ID, key, value_json, self.now()),
        )

    # --- 幂等命令 ---
    def create_command(self, conn, *, command_id, idempotency_key, payload_hash, status) -> dict:
        conn.execute(
            "INSERT INTO command_requests(id, ledger_id, idempotency_key, payload_hash, status, response_json, created_at)"
            " VALUES(?,?,?,?,?,NULL,?)",
            (command_id, DEFAULT_LEDGER_ID, idempotency_key, payload_hash, status, self.now()),
        )
        return _row_dict(
            conn.execute("SELECT * FROM command_requests WHERE id=?", (command_id,)).fetchone()
        )

    def get_command_by_idempotency(self, conn, idempotency_key: str) -> dict | None:
        return _row_dict(
            conn.execute(
                "SELECT * FROM command_requests WHERE ledger_id=? AND idempotency_key=?",
                (DEFAULT_LEDGER_ID, idempotency_key),
            ).fetchone()
        )

    def finish_command(self, conn, command_id: str, status: str, response_json: str) -> None:
        conn.execute(
            "UPDATE command_requests SET status=?, response_json=? WHERE id=?",
            (status, response_json, command_id),
        )

    # --- 会话与消息 ---
    def create_session(self, conn, *, session_id, title="") -> dict:
        now = self.now()
        conn.execute(
            "INSERT INTO sessions(id, ledger_id, title, summary, summary_until_seq, created_at, updated_at)"
            " VALUES(?,?,?,NULL,0,?,?)",
            (session_id, DEFAULT_LEDGER_ID, title, now, now),
        )
        return _row_dict(conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone())

    def get_session(self, conn, session_id) -> dict | None:
        return _row_dict(conn.execute(
            "SELECT * FROM sessions WHERE id=? AND ledger_id=?", (session_id, DEFAULT_LEDGER_ID)).fetchone())

    def list_sessions(self, conn, limit=50) -> list:
        return [_row_dict(r) for r in conn.execute(
            "SELECT * FROM sessions WHERE ledger_id=? ORDER BY updated_at DESC LIMIT ?",
            (DEFAULT_LEDGER_ID, limit))]

    def next_seq(self, conn, session_id) -> int:
        r = conn.execute("SELECT COALESCE(MAX(seq),0) AS m FROM messages WHERE session_id=?", (session_id,)).fetchone()
        return r["m"] + 1

    def add_message(self, conn, *, message_id, session_id, seq, role, content_json, request_id=None) -> dict:
        conn.execute(
            "INSERT INTO messages(id, session_id, seq, role, content_json, request_id, created_at) VALUES(?,?,?,?,?,?,?)",
            (message_id, session_id, seq, role, content_json, request_id, self.now()),
        )
        conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (self.now(), session_id))
        return _row_dict(conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone())

    def list_messages(self, conn, session_id, limit=100) -> list:
        return [_row_dict(r) for r in conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY seq ASC LIMIT ?", (session_id, limit))]

    def update_summary(self, conn, session_id, summary, summary_until_seq) -> None:
        conn.execute("UPDATE sessions SET summary=?, summary_until_seq=?, updated_at=? WHERE id=?",
                     (summary, summary_until_seq, self.now(), session_id))

    # --- 记忆 ---
    def add_memory(self, conn, *, memory_id, kind, value_json, source_message_id=None, expires_at=None) -> dict:
        conn.execute(
            "INSERT INTO memories(id, ledger_id, kind, value_json, source_message_id, consent_at, expires_at, deleted_at)"
            " VALUES(?,?,?,?,?,?,?,NULL)",
            (memory_id, DEFAULT_LEDGER_ID, kind, value_json, source_message_id, self.now(), expires_at),
        )
        return _row_dict(conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone())

    def list_memories(self, conn, *, include_deleted=False) -> list:
        where = "ledger_id=?" if include_deleted else "ledger_id=? AND deleted_at IS NULL"
        return [_row_dict(r) for r in conn.execute(
            f"SELECT * FROM memories WHERE {where} ORDER BY consent_at DESC", (DEFAULT_LEDGER_ID,))]

    def soft_delete_memory(self, conn, memory_id) -> bool:
        cur = conn.execute("UPDATE memories SET deleted_at=? WHERE id=? AND ledger_id=?",
                           (self.now(), memory_id, DEFAULT_LEDGER_ID))
        return cur.rowcount > 0

    # --- 待确认动作 ---
    def create_pending_action(self, conn, *, action_id, action_type, payload_json, payload_hash, expires_at) -> dict:
        conn.execute(
            "INSERT INTO pending_actions(id, ledger_id, action_type, payload_json, payload_hash, status, created_at, expires_at, consumed_at)"
            " VALUES(?,?,?,?,?,?,?,?,NULL)",
            (action_id, DEFAULT_LEDGER_ID, action_type, payload_json, payload_hash, "pending", self.now(), expires_at),
        )
        return _row_dict(conn.execute("SELECT * FROM pending_actions WHERE id=?", (action_id,)).fetchone())

    def get_pending_action(self, conn, action_id) -> dict | None:
        return _row_dict(conn.execute(
            "SELECT * FROM pending_actions WHERE id=? AND ledger_id=?", (action_id, DEFAULT_LEDGER_ID)).fetchone())

    def consume_pending_action(self, conn, action_id) -> dict | None:
        cur = conn.execute(
            "UPDATE pending_actions SET status='consumed', consumed_at=? WHERE id=? AND ledger_id=? AND status='pending'",
            (self.now(), action_id, DEFAULT_LEDGER_ID),
        )
        if cur.rowcount == 0:
            return None
        return _row_dict(conn.execute("SELECT * FROM pending_actions WHERE id=?", (action_id,)).fetchone())

    # --- 报告缓存 ---
    def get_report_cache(self, conn, period) -> dict | None:
        return _row_dict(conn.execute(
            "SELECT * FROM report_cache WHERE ledger_id=? AND period=?", (DEFAULT_LEDGER_ID, period)).fetchone())

    def set_report_cache(self, conn, *, period, metric_version, ledger_revision, facts_json) -> None:
        conn.execute(
            "INSERT INTO report_cache(ledger_id, period, metric_version, ledger_revision, facts_json, created_at)"
            " VALUES(?,?,?,?,?,?)"
            " ON CONFLICT(ledger_id, period) DO UPDATE SET metric_version=excluded.metric_version,"
            " ledger_revision=excluded.ledger_revision, facts_json=excluded.facts_json, created_at=excluded.created_at",
            (DEFAULT_LEDGER_ID, period, metric_version, ledger_revision, facts_json, self.now()),
        )
