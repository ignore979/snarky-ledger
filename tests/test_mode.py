"""test_mode.py — 模式严格解析，非法值拒绝而非静默转 savage。"""
import unittest

from snarky_ledger.domain.mode import Mode
from snarky_ledger.errors import InvalidArgument


class ModeTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(Mode.parse("savage"), "savage")
        self.assertEqual(Mode.parse("gentle"), "gentle")

    def test_strip(self):
        self.assertEqual(Mode.parse(" gentle "), "gentle")

    def test_invalid_rejected(self):
        for v in ("Savage", "GENTLE", "normal", "", "1", True):
            with self.assertRaises(InvalidArgument):
                Mode.parse(v)

    def test_none_rejected(self):
        with self.assertRaises(InvalidArgument):
            Mode.parse(None)


if __name__ == "__main__":
    unittest.main()
