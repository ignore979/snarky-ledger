"""snarky_ledger 维护入口：python -m snarky_ledger migrate|doctor。"""
from __future__ import annotations

import sys


def _migrate(args):
    old = new = None
    for i, a in enumerate(args):
        if a == "--old" and i + 1 < len(args):
            old = args[i + 1]
        if a == "--new" and i + 1 < len(args):
            new = args[i + 1]
    if not old or not new:
        print("需要 --old <旧库路径> --new <新库路径>")
        return 1
    import json

    from .migrate import migrate_old_db

    res = migrate_old_db(old, new)
    print(json.dumps(
        {"ok": res["ok"], "converted_count": res["converted_count"],
         "anomalies": res["anomalies"], "reconciliation": res["reconciliation"]},
        ensure_ascii=False, indent=2,
    ))
    return 0 if res["ok"] else 2


def _doctor(args):
    db_path = None
    for i, a in enumerate(args):
        if a == "--db" and i + 1 < len(args):
            db_path = args[i + 1]
    if not db_path:
        print("需要 --db <数据库路径>")
        return 1
    import sqlite3

    from .api import detect_format
    from .db import schema_version

    print("format:", detect_format(db_path))
    print("schema_version:", schema_version(db_path))
    conn = sqlite3.connect(db_path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity_check:", integrity)
        print("foreign_key_violations:", len(fk))
    finally:
        conn.close()
    return 0


def main():
    args = sys.argv[1:]
    if not args:
        print("用法：python -m snarky_ledger migrate --old <旧库> --new <新库>")
        print("      python -m snarky_ledger doctor --db <数据库>")
        return 1
    if args[0] == "migrate":
        return _migrate(args[1:])
    if args[0] == "doctor":
        return _doctor(args[1:])
    print(f"未知命令：{args[0]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
