"""db.py — SQLite 连接、V2 schema 版本迁移、初始化与种子数据。"""
from __future__ import annotations

import hashlib
import sqlite3

from .clock import Clock, SystemClock

DEFAULT_LEDGER_ID = "local"

CATEGORY_SEED = [
    ("food", "餐饮", 0),
    ("transport", "交通", 1),
    ("shopping", "购物", 2),
    ("study", "学习", 3),
    ("entertainment", "娱乐", 4),
    ("housing", "居住", 5),
    ("medical", "医疗", 6),
    ("other", "其他", 7),
]

# 每个版本是一组语句；应用后记录 checksum，禁止修改已应用脚本
MIGRATIONS = [
    (
        "0001_initial",
        [
            "CREATE TABLE ledgers ("
            " id TEXT PRIMARY KEY,"
            " currency TEXT NOT NULL DEFAULT 'CNY',"
            " timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',"
            " revision INTEGER NOT NULL DEFAULT 0,"
            " epoch INTEGER NOT NULL DEFAULT 1"
            ")",
            "CREATE TABLE categories ("
            " id TEXT PRIMARY KEY,"
            " ledger_id TEXT NOT NULL,"
            " name TEXT NOT NULL,"
            " sort_order INTEGER NOT NULL DEFAULT 0,"
            " UNIQUE(ledger_id, name)"
            ")",
            "CREATE TABLE expenses ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ledger_id TEXT NOT NULL,"
            " amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),"
            " category_id TEXT NOT NULL,"
            " note TEXT NOT NULL DEFAULT '',"
            " spent_on TEXT NOT NULL,"
            " source TEXT NOT NULL DEFAULT 'manual',"
            " created_at TEXT NOT NULL,"
            " updated_at TEXT NOT NULL,"
            " deleted_at TEXT,"
            " version INTEGER NOT NULL DEFAULT 1,"
            " command_id TEXT"
            ")",
            "CREATE TABLE budgets ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ledger_id TEXT NOT NULL,"
            " period TEXT NOT NULL,"
            " scope_key TEXT NOT NULL,"
            " amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),"
            " version INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL,"
            " updated_at TEXT NOT NULL,"
            " UNIQUE(ledger_id, period, scope_key)"
            ")",
            "CREATE TABLE preferences ("
            " ledger_id TEXT NOT NULL,"
            " key TEXT NOT NULL,"
            " value_json TEXT NOT NULL,"
            " updated_at TEXT NOT NULL,"
            " PRIMARY KEY(ledger_id, key)"
            ")",
            "CREATE TABLE command_requests ("
            " id TEXT PRIMARY KEY,"
            " ledger_id TEXT NOT NULL,"
            " idempotency_key TEXT NOT NULL,"
            " payload_hash TEXT NOT NULL,"
            " status TEXT NOT NULL,"
            " response_json TEXT,"
            " created_at TEXT NOT NULL,"
            " UNIQUE(ledger_id, idempotency_key)"
            ")",
            "CREATE TABLE mutation_events ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ledger_id TEXT NOT NULL,"
            " entity_type TEXT NOT NULL,"
            " entity_id TEXT NOT NULL,"
            " operation TEXT NOT NULL,"
            " occurred_at TEXT NOT NULL"
            ")",
            "CREATE INDEX idx_expenses_spent ON expenses(ledger_id, spent_on, id)",
            "CREATE INDEX idx_expenses_cat ON expenses(ledger_id, category_id, spent_on)",
            "CREATE INDEX idx_expenses_del ON expenses(ledger_id, deleted_at, spent_on)",
            "CREATE INDEX idx_budgets_period ON budgets(ledger_id, period)",
        ],
    ),
]


def connect(db_path: str, *, busy_timeout: int = 5000) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout)}")
    return conn


def _checksum(statements) -> str:
    return hashlib.sha256("\n".join(statements).encode("utf-8")).hexdigest()


def migrate(db_path: str, clock: Clock | None = None) -> None:
    """应用未执行的版本迁移，并写入默认账本与 8 个分类（幂等）。"""
    clock = clock or SystemClock()
    conn = connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        applied = {
            r["version"]: r["checksum"]
            for r in conn.execute("SELECT version, checksum FROM schema_migrations")
        }
        for version, statements in MIGRATIONS:
            expected = _checksum(statements)
            if version in applied:
                if applied[version] != expected:
                    raise RuntimeError(f"迁移 {version} 的 checksum 不一致，禁止修改已应用脚本")
                continue
            for stmt in statements:
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES(?,?,?)",
                (version, expected, clock.now().isoformat()),
            )
            conn.commit()
        _seed(conn, clock)
        conn.commit()
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection, clock: Clock) -> None:
    now = clock.now().isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO ledgers(id, currency, timezone, revision, epoch) VALUES(?,?,?,?,?)",
        (DEFAULT_LEDGER_ID, "CNY", "Asia/Shanghai", 0, 1),
    )
    for cid, name, sort in CATEGORY_SEED:
        conn.execute(
            "INSERT OR IGNORE INTO categories(id, ledger_id, name, sort_order) VALUES(?,?,?,?)",
            (cid, DEFAULT_LEDGER_ID, name, sort),
        )


def schema_version(db_path: str) -> str | None:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    finally:
        conn.close()
    return row["v"] if row and row["v"] else None
