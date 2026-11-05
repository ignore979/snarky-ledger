"""config.py — 统一配置解析。密钥只由服务端读取，不进入日志（方案 §13.2）。"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str
    timezone: str = "Asia/Shanghai"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    access_token: str | None = None
    port: int = 5000
    # 能力开关：真实能力须经探测/验收后开启，多模态默认关闭
    text_agent_enabled: bool = True
    image_import_enabled: bool = False
    voice_import_enabled: bool = False
    csv_import_enabled: bool = False

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Settings":
        env = dict(os.environ if env is None else env)

        def _bool(key: str, default: bool) -> bool:
            v = env.get(key)
            if v is None:
                return default
            return str(v).strip().lower() in ("1", "true", "yes", "on")

        return cls(
            db_path=env.get("LEDGER_DB", "ledger.db"),
            timezone=env.get("LEDGER_TIMEZONE", "Asia/Shanghai"),
            deepseek_api_key=env.get("DEEPSEEK_API_KEY") or None,
            deepseek_base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=env.get("DEEPSEEK_MODEL", "deepseek-chat"),
            access_token=env.get("LEDGER_ACCESS_TOKEN") or None,
            port=int(env.get("PORT", "5000")),
            text_agent_enabled=_bool("LEDGER_TEXT_AGENT", True),
            image_import_enabled=_bool("LEDGER_IMAGE_IMPORT", False),
            voice_import_enabled=_bool("LEDGER_VOICE_IMPORT", False),
            csv_import_enabled=_bool("LEDGER_CSV_IMPORT", False),
        )
