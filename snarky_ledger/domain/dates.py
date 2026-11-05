"""dates.py — BusinessDate 与 Month：严格解析、半开区间、口径标记。"""
from __future__ import annotations

import calendar
from datetime import date
from functools import total_ordering

from ..errors import InvalidArgument


@total_ordering
class BusinessDate:
    """业务日期：本地日历 ISO 日期 YYYY-MM-DD，严格解析，非标准格式拒绝。"""

    __slots__ = ("_date",)

    def __init__(self, iso: str):
        if not isinstance(iso, str):
            raise InvalidArgument("日期必须是 YYYY-MM-DD 字符串")
        try:
            d = date.fromisoformat(iso)
        except (ValueError, TypeError):
            raise InvalidArgument(f"日期格式不正确：{iso!r}")
        if d.isoformat() != iso:
            raise InvalidArgument(f"日期格式不正确：{iso!r}")
        self._date = d

    @property
    def iso(self) -> str:
        return self._date.isoformat()

    def to_date(self) -> date:
        return self._date

    @property
    def month(self) -> "Month":
        return Month(self._date.strftime("%Y-%m"))

    @classmethod
    def today(cls, clock) -> "BusinessDate":
        return cls(clock.today().isoformat())

    def is_future(self, clock) -> bool:
        return self._date > clock.today()

    def __eq__(self, other):
        if isinstance(other, BusinessDate):
            return self._date == other._date
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, BusinessDate):
            return self._date < other._date
        return NotImplemented

    def __hash__(self):
        return hash(self._date)

    def __repr__(self):
        return f"BusinessDate('{self.iso}')"


@total_ordering
class Month:
    """月份 YYYY-MM：提供首末、天数、次月与半开区间 [first, next_month.first)。"""

    __slots__ = ("_first",)

    def __init__(self, iso: str):
        if not isinstance(iso, str) or len(iso) != 7 or iso[4] != "-":
            raise InvalidArgument(f"月份格式不正确：{iso!r}（应为 YYYY-MM）")
        try:
            y, m = int(iso[:4]), int(iso[5:7])
            self._first = date(y, m, 1)
        except (ValueError, TypeError):
            raise InvalidArgument(f"月份格式不正确：{iso!r}（应为 YYYY-MM）")

    @property
    def iso(self) -> str:
        return self._first.strftime("%Y-%m")

    @property
    def first_day(self) -> str:
        return self._first.isoformat()

    @property
    def last_day(self) -> str:
        return date(self._first.year, self._first.month, self.days_in_month).isoformat()

    @property
    def days_in_month(self) -> int:
        return calendar.monthrange(self._first.year, self._first.month)[1]

    @property
    def next_month(self) -> "Month":
        y, m = self._first.year, self._first.month
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
        return Month(f"{y:04d}-{m:02d}")

    def half_open_range(self) -> tuple:
        """[first_day, next_month.first_day) 半开区间，避免 LIKE 跨月边界。"""
        return (self.first_day, self.next_month.first_day)

    @classmethod
    def current(cls, clock) -> "Month":
        return cls(clock.today().strftime("%Y-%m"))

    def __eq__(self, other):
        if isinstance(other, Month):
            return self._first == other._first
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, Month):
            return self._first < other._first
        return NotImplemented

    def __hash__(self):
        return hash(self._first)

    def __repr__(self):
        return f"Month('{self.iso}')"
