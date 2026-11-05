"""test_dates.py — BusinessDate / Month 严格解析与半开区间。"""
import unittest
from datetime import date as _date

from snarky_ledger.clock import FrozenClock
from snarky_ledger.domain.dates import BusinessDate, Month
from snarky_ledger.errors import InvalidArgument


class BusinessDateTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(BusinessDate("2026-11-05").iso, "2026-11-05")

    def test_non_canonical_rejected(self):
        for v in ("2026-11-5", "2026-1-05", "20261105"):
            with self.assertRaises(InvalidArgument):
                BusinessDate(v)

    def test_invalid_rejected(self):
        for v in ("2026-13-01", "2026-02-30", "abc", "", "2026/11/05"):
            with self.assertRaises(InvalidArgument):
                BusinessDate(v)

    def test_leap_year(self):
        self.assertEqual(BusinessDate("2024-02-29").iso, "2024-02-29")
        with self.assertRaises(InvalidArgument):
            BusinessDate("2023-02-29")

    def test_month_property(self):
        self.assertEqual(BusinessDate("2026-11-05").month.iso, "2026-11")

    def test_future(self):
        clock = FrozenClock(_date(2026, 11, 5))
        self.assertFalse(BusinessDate("2026-11-05").is_future(clock))
        self.assertTrue(BusinessDate("2026-11-06").is_future(clock))


class MonthTest(unittest.TestCase):
    def test_valid(self):
        m = Month("2026-11")
        self.assertEqual(m.iso, "2026-11")
        self.assertEqual(m.first_day, "2026-11-01")
        self.assertEqual(m.last_day, "2026-11-30")
        self.assertEqual(m.days_in_month, 30)

    def test_leap_feb(self):
        self.assertEqual(Month("2024-02").days_in_month, 29)
        self.assertEqual(Month("2026-02").days_in_month, 28)

    def test_next_month(self):
        self.assertEqual(Month("2026-11").next_month.iso, "2026-12")
        self.assertEqual(Month("2026-12").next_month.iso, "2027-01")

    def test_half_open_range(self):
        self.assertEqual(Month("2026-11").half_open_range(), ("2026-11-01", "2026-12-01"))

    def test_invalid_rejected(self):
        for v in ("2026-13", "2026-00", "2026-1", "abc", "2026/11", ""):
            with self.assertRaises(InvalidArgument):
                Month(v)


if __name__ == "__main__":
    unittest.main()
