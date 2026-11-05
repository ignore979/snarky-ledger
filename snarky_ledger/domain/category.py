"""category.py — 稳定分类：id 稳定、name 展示；只做精确匹配，不做子串归类。"""
from __future__ import annotations

from ..errors import InvalidArgument


class Category:
    _by_id: dict = {}
    _by_name: dict = {}
    _order: list = []

    __slots__ = ("id", "name")

    def __init__(self, id: str, name: str):
        self.id = id
        self.name = name

    @classmethod
    def register(cls, id: str, name: str) -> "Category":
        c = cls(id, name)
        cls._by_id[id] = c
        cls._by_name[name] = c
        cls._order.append(c)
        return c

    @classmethod
    def parse(cls, value) -> "Category":
        if isinstance(value, cls):
            return value
        if value is None:
            raise InvalidArgument("分类不能为空")
        s = str(value).strip()
        if s in cls._by_id:
            return cls._by_id[s]
        if s in cls._by_name:
            return cls._by_name[s]
        raise InvalidArgument(
            f"未知分类：{value!r}（可选：{'/'.join(c.name for c in cls._order)}）"
        )

    @classmethod
    def all(cls) -> list:
        return list(cls._order)

    def __eq__(self, other):
        if isinstance(other, Category):
            return self.id == other.id
        return NotImplemented

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"Category('{self.id}', '{self.name}')"


# 初始 8 类（稳定 ID，方案 §5.2）
Category.register("food", "餐饮")
Category.register("transport", "交通")
Category.register("shopping", "购物")
Category.register("study", "学习")
Category.register("entertainment", "娱乐")
Category.register("housing", "居住")
Category.register("medical", "医疗")
Category.register("other", "其他")
