# V2 进度（progress.md）

> 状态以代码与验证证据为准，不把规划中的能力写成已有实现。

## 里程碑总览

| 里程碑 | 范围 | 状态 |
| --- | --- | --- |
| M0 基线与冻结设计 | T00 | ✅ 完成 |
| M1 数据底座 | T01–T05 | 🔨 进行中（T01/T02 完成） |
| M2 可靠执行 | T06–T13 | ⬜ 未开始 |
| M3 会话分析与界面 | T14–T19 | ⬜ 未开始 |
| M4 导入与多模态 | T20–T23 | ⬜ 未开始 |
| M5 全量验证与文档 | T25/T26 | ⬜ 未开始 |
| M6 迁移与发布 | T27 | ⬜ 未开始 |

## 工作包状态

| ID | 工作包 | 状态 | 证据 / 完成条件 |
| --- | --- | --- | --- |
| T00 | 基线核查、分支、docs/v2 | ✅ | `docs/v2/baseline_review.md`；`v2` 分支 |
| T01 | Settings/错误码/时钟/create_app | ✅ | 无导入副作用；无 Key 可启动；可注入时钟 |
| T02 | 金额日期分类模式输入模型 | ✅ | 47 个边界测试通过；拒绝非法枚举/非有限金额 |
| T03 | V2 schema、迁移 runner、Repository、UnitOfWork | ⬜ | 约束/索引/版本校验；新空库可初始化 |
| T04 | 备份/预检/转换/对账/dry-run/恢复预演 | ⬜ | 正常/异常/中断/重复四路径演练 |
| T05 | LedgerService CRUD、乐观锁、软删恢复、事件 | ⬜ | 原子写入；旧 ID 与新增 ID 正确 |
| T06–T27 | 见方案 §15.1 | ⬜ | — |

## 已完成内容

- `snarky_ledger/` 包：`config.py`（Settings）、`clock.py`（可注入时钟）、`errors.py`（统一错误码）、`__init__.py`（`create_app`）。
- `domain/`：`money.py`（Money 整数分）、`dates.py`（BusinessDate/Month 半开区间）、`category.py`（精确匹配）、`mode.py`（严格解析）。
- `tests/`：`test_money.py`、`test_dates.py`、`test_category.py`、`test_mode.py`、`test_config.py`，共 47 个用例。
- 旧入口未改动；`test_offline.py`（4 用例）仍通过。

## 变更记录

| 日期 | 内容 |
| --- | --- |
| 2026-11-05 | M0 完成；M1 的 T01/T02 完成（47 测试通过），推送 `v2` 分支 |
