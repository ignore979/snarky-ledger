# 运维（operations.md）

## 运行

```bash
python main.py            # 终端对话
python main.py --web      # 网页版 http://127.0.0.1:5000
```

## 诊断

```bash
python -m snarky_ledger doctor --db <数据库>   # integrity_check / foreign_key_check / schema_version
```

## 备份

SQLite 在线备份优先用 backup API（`sqlite3.Connection.backup`），不要裸拷正在写入的 `.db`。

## 配置（.env，已被 gitignore）

`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`LEDGER_DB`、`LEDGER_ACCESS_TOKEN`、`PORT`、`LEDGER_TIMEZONE`。

## 数据保留与清理

软删账目可恢复；清空账本走两步确认（`reset-preview` / `reset-confirm`）。原始上传与业务日志的自动清理周期尚未实现。
