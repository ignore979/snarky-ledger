"""money.py — Money 金额值对象：整数分存储，严格解析，不先 float。

规则（方案 §5.1）：
- API 内传十进制字符串；领域层 Decimal 解析；数据库存 amount_minor INTEGER（分）。
- 拒绝非有限数、布尔、负数、零、超过两位小数与越界数。
- 两位以上小数直接拒绝，不静默四舍五入。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from ..errors import InvalidArgument

MAX_AMOUNT_YUAN = Decimal("100000")  # 单笔上限 ¥100,000（方案 §3.2 建议值）
MAX_MINOR = 10000000  # 100000 * 100


class Money:
    __slots__ = ("_minor",)

    def __init__(self, minor: int):
        if isinstance(minor, bool) or not isinstance(minor, int):
            raise InvalidArgument("金额分值必须是整数")
        if minor <= 0:
            raise InvalidArgument("金额必须大于 0")
        if minor > MAX_MINOR:
            raise InvalidArgument(f"单笔金额不能超过 {MAX_AMOUNT_YUAN} 元")
        self._minor = minor

    @property
    def minor(self) -> int:
        return self._minor

    @property
    def yuan(self) -> Decimal:
        return Decimal(self._minor) / Decimal(100)

    def to_yuan_str(self) -> str:
        return f"{self._minor // 100}.{self._minor % 100:02d}"

    @classmethod
    def from_minor(cls, minor: int) -> "Money":
        return cls(minor)

    @classmethod
    def parse(cls, value) -> "Money":
        if value is None or isinstance(value, bool):
            raise InvalidArgument("金额不能为空或布尔值")
        if isinstance(value, float):
            raise InvalidArgument("金额请用十进制字符串或整数，不要用浮点数")
        if isinstance(value, int):
            return cls(value * 100)
        if isinstance(value, Decimal):
            d = value
        elif isinstance(value, str):
            s = value.strip()
            if s == "":
                raise InvalidArgument("金额不能为空")
            try:
                d = Decimal(s)
            except InvalidOperation:
                raise InvalidArgument(f"金额格式不正确：{value!r}")
        else:
            raise InvalidArgument("金额类型不支持")

        if not d.is_finite():
            raise InvalidArgument("金额必须是有限数值")
        if d <= 0:
            raise InvalidArgument("金额必须大于 0")

        # Decimal 指数为负表示小数位数；只允许最多两位小数，不静默舍入
        exp = d.as_tuple().exponent
        if isinstance(exp, int) and exp < -2:
            raise InvalidArgument("金额最多两位小数")

        cents = int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))
        return cls(cents)

    def __eq__(self, other):
        if isinstance(other, Money):
            return self._minor == other._minor
        return NotImplemented

    def __hash__(self):
        return hash(self._minor)

    def __repr__(self):
        return f"Money('{self.to_yuan_str()}')"
