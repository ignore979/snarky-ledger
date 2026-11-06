"""kind.py — 收支类型：expense / income，严格解析。"""
from __future__ import annotations

from ..errors import InvalidArgument


class Kind:
    EXPENSE = "expense"
    INCOME = "income"
    _VALUES = (EXPENSE, INCOME)

    @classmethod
    def parse(cls, value) -> str:
        if value is None:
            raise InvalidArgument("收支类型不能为空")
        s = value.strip() if isinstance(value, str) else str(value)
        if s not in cls._VALUES:
            raise InvalidArgument(f"收支类型只能是 expense 或 income，得到：{value!r}")
        return s
