"""test_config.py — Settings、时钟、错误码与 create_app。"""
import unittest
from datetime import date

from snarky_ledger import create_app
from snarky_ledger.clock import FrozenClock
from snarky_ledger.config import Settings
from snarky_ledger.errors import InvalidArgument, NotFound, VersionConflict


class SettingsTest(unittest.TestCase):
    def test_defaults(self):
        s = Settings.from_env({})
        self.assertEqual(s.db_path, "ledger.db")
        self.assertEqual(s.timezone, "Asia/Shanghai")
        self.assertIsNone(s.deepseek_api_key)
        self.assertEqual(s.port, 5000)

    def test_env(self):
        s = Settings.from_env({
            "LEDGER_DB": "/tmp/x.db",
            "DEEPSEEK_API_KEY": "sk-abc",
            "PORT": "8000",
            "LEDGER_IMAGE_IMPORT": "true",
        })
        self.assertEqual(s.db_path, "/tmp/x.db")
        self.assertEqual(s.deepseek_api_key, "sk-abc")
        self.assertEqual(s.port, 8000)
        self.assertTrue(s.image_import_enabled)
        self.assertFalse(s.voice_import_enabled)


class ClockTest(unittest.TestCase):
    def test_frozen(self):
        c = FrozenClock(date(2026, 11, 5))
        self.assertEqual(c.today().isoformat(), "2026-11-05")
        c.advance(2)
        self.assertEqual(c.today().isoformat(), "2026-11-07")


class ErrorsTest(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(InvalidArgument().code, "INVALID_ARGUMENT")
        self.assertEqual(InvalidArgument().http_status, 422)
        self.assertEqual(NotFound().http_status, 404)
        self.assertEqual(VersionConflict().http_status, 409)

    def test_to_dict(self):
        e = InvalidArgument("金额不能为空", field_errors=[{"field": "amount", "message": "x"}])
        d = e.to_dict()
        self.assertEqual(d["code"], "INVALID_ARGUMENT")
        self.assertEqual(d["message"], "金额不能为空")
        self.assertEqual(d["field_errors"][0]["field"], "amount")


class CreateAppTest(unittest.TestCase):
    def test_health(self):
        import os
        import tempfile
        db_path = os.path.join(tempfile.mkdtemp(), "ledger.db")
        app = create_app(Settings(db_path=db_path))
        c = app.test_client()
        r = c.get("/health/live")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
