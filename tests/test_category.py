"""test_category.py — 分类精确匹配，不做子串归类。"""
import unittest

from snarky_ledger.domain.category import Category
from snarky_ledger.errors import InvalidArgument


class CategoryTest(unittest.TestCase):
    def test_parse_by_name(self):
        self.assertEqual(Category.parse("餐饮").id, "food")

    def test_parse_by_id(self):
        self.assertEqual(Category.parse("food").name, "餐饮")

    def test_strip(self):
        self.assertEqual(Category.parse(" 餐饮 ").id, "food")

    def test_unknown_rejected(self):
        for v in ("奶茶", "吃喝", "foo", "吃"):
            with self.assertRaises(InvalidArgument):
                Category.parse(v)

    def test_no_substring_matching(self):
        # 「吃」是「餐饮」的子串，但不允许子串归类（方案 F06）
        with self.assertRaises(InvalidArgument):
            Category.parse("吃")

    def test_none_rejected(self):
        with self.assertRaises(InvalidArgument):
            Category.parse(None)

    def test_all_count(self):
        self.assertEqual(len(Category.all("expense")), 8)
        self.assertEqual(len(Category.all("income")), 5)


if __name__ == "__main__":
    unittest.main()
