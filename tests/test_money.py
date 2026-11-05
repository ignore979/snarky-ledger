"""test_money.py — Money 金额边界测试（方案 §7.3 / §14.1）。"""
import unittest
from decimal import Decimal

from snarky_ledger.domain.money import MAX_MINOR, Money
from snarky_ledger.errors import InvalidArgument


class MoneyParseTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(Money.parse("12.34").minor, 1234)
        self.assertEqual(Money.parse("12.34").to_yuan_str(), "12.34")

    def test_zero_padded(self):
        self.assertEqual(Money.parse("0.10").minor, 10)
        self.assertEqual(Money.parse("0.1").minor, 10)
        self.assertEqual(Money.parse("0.29").minor, 29)

    def test_integer_yuan(self):
        self.assertEqual(Money.parse(12).minor, 1200)

    def test_decimal_input(self):
        self.assertEqual(Money.parse(Decimal("0.30")).minor, 30)

    def test_strip(self):
        self.assertEqual(Money.parse("  12.34  ").minor, 1234)

    def test_max_allowed(self):
        self.assertEqual(Money.parse("100000.00").minor, MAX_MINOR)

    def test_over_max_rejected(self):
        with self.assertRaises(InvalidArgument):
            Money.parse("100000.01")

    def test_three_decimals_rejected(self):
        with self.assertRaises(InvalidArgument):
            Money.parse("1.005")

    def test_many_decimals_rejected(self):
        with self.assertRaises(InvalidArgument):
            Money.parse("0.001")

    def test_zero_rejected(self):
        for v in ("0", "0.00", 0, Decimal("0")):
            with self.assertRaises(InvalidArgument):
                Money.parse(v)

    def test_negative_rejected(self):
        for v in ("-5", "-0.01", -5):
            with self.assertRaises(InvalidArgument):
                Money.parse(v)

    def test_bool_rejected(self):
        for v in (True, False):
            with self.assertRaises(InvalidArgument):
                Money.parse(v)

    def test_none_rejected(self):
        with self.assertRaises(InvalidArgument):
            Money.parse(None)

    def test_float_rejected(self):
        with self.assertRaises(InvalidArgument):
            Money.parse(3.14)

    def test_non_finite_rejected(self):
        for v in ("nan", "NaN", "inf", "-inf", "Infinity"):
            with self.assertRaises(InvalidArgument):
                Money.parse(v)

    def test_empty_rejected(self):
        for v in ("", "   "):
            with self.assertRaises(InvalidArgument):
                Money.parse(v)

    def test_garbage_rejected(self):
        for v in ("abc", "12.3.4", "¥50"):
            with self.assertRaises(InvalidArgument):
                Money.parse(v)

    def test_sum_accuracy(self):
        # 0.1 + 0.2 在浮点下为 0.30000000000000004；整数分无此误差
        total_minor = Money.parse("0.1").minor + Money.parse("0.2").minor
        self.assertEqual(total_minor, 30)
        self.assertEqual(Money.from_minor(total_minor).to_yuan_str(), "0.30")

    def test_equality_and_hash(self):
        self.assertEqual(Money.parse("12.34"), Money.parse("12.34"))
        self.assertEqual(hash(Money.parse("1.00")), hash(Money.parse("1.0")))


if __name__ == "__main__":
    unittest.main()
