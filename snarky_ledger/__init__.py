"""snarky_ledger — 损友账本 V2 应用包。"""
from __future__ import annotations

from .api import build_app
from .clock import Clock, FrozenClock, SystemClock
from .config import Settings

__all__ = ["Settings", "Clock", "SystemClock", "FrozenClock", "build_app"]


def create_app(settings: Settings | None = None, clock: Clock | None = None):
    """组装完整应用（迁移 + 服务 + V2 API + 旧接口兼容）。无 Key 也可启动基础账本。"""
    return build_app(settings, clock)
