"""snarky_ledger — 损友账本 V2 应用包。"""
from __future__ import annotations

from .config import Settings


def create_app(settings: Settings | None = None):
    """组装 Flask 应用；导入无副作用，无 Key 也可启动基础账本。

    数据库就绪检查 /health/ready 与业务蓝图在 T03/T18 接入。
    """
    from flask import Flask, jsonify

    app = Flask(__name__)
    app.config["LEDGER_SETTINGS"] = settings or Settings.from_env()

    @app.get("/health/live")
    def health_live():
        return jsonify({"status": "ok"})

    return app


__all__ = ["create_app", "Settings"]
