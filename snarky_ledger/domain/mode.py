"""mode.py — 语气模式：savage/gentle，严格解析，非法值拒绝而非静默转 savage。"""
from __future__ import annotations

from ..errors import InvalidArgument


class Mode:
    SAVAGE = "savage"
    GENTLE = "gentle"
    _VALUES = (SAVAGE, GENTLE)

    @classmethod
    def parse(cls, value) -> str:
        if value is None:
            raise InvalidArgument("模式不能为空")
        s = value.strip() if isinstance(value, str) else str(value)
        if s in cls._VALUES:
            return s
        raise InvalidArgument(f"未知模式：{value!r}（只能是 savage 或 gentle）")

    @classmethod
    def values(cls) -> list:
        return list(cls._VALUES)
