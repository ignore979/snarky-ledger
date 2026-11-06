# 迁移（migration.md）

## 命令

```bash
python -m snarky_ledger migrate --old <旧库路径> --new <新库路径>
python -m snarky_ledger doctor --db <数据库路径>
```

## 原则

- 旧库是只读来源，新库另建文件；不在唯一生产库上改表。
- 金额逐行 `Decimal(str(value))` 量化到 0.01 元再乘 100 转整数分，不用 `int(float*100)`。
- 异常行（超过两位小数、非有限、≤0、越界、未知分类、非法日期）进入 `anomalies`，`ok=False` 阻止正式切换，不静默丢弃。
- 保留旧支出 ID；迁移后 `sqlite_sequence` 置为最大旧 ID，新增不冲突。
- 对账输出 `id_match` / `sum_match`（逐月逐分类旧量化值 vs 新整数分）。

## 结果

返回 `{ok, anomalies, converted_count, reconciliation}`；`ok=False` 表示存在需核对异常。
