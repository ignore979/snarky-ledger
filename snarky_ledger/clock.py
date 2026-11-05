"""clock.py — 可注入时钟：业务代码不直接读系统时间，测试可冻结。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


class Clock:
    def now(self) -> datetime:
        raise NotImplementedError

    def today(self) -> date:
        raise NotImplementedError


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def today(self) -> date:
        # 业务日期使用本地日历日，具体时区由 Settings.timezone 决定（后续 T03 接入）
        return datetime.now().date()


class FrozenClock(Clock):
    """测试用：固定时间，可推进。"""

    def __init__(self, today: date | None = None, now: datetime | None = None):
        self._today = today or date(2026, 11, 5)
        self._now = now or datetime(2026, 11, 5, 12, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def today(self) -> date:
        return self._today

    def advance(self, days: int = 1) -> None:
        self._today += timedelta(days=days)
        self._now += timedelta(days=days)
