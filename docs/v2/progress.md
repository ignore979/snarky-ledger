# V2 进度（progress.md）

> 状态以代码与验证证据为准，不把规划中的能力写成已有实现。

## 里程碑总览

| 里程碑 | 范围 | 状态 |
| --- | --- | --- |
| M0 基线与冻结设计 | T00 | ✅ 完成 |
| M1 数据底座 | T01–T05 | ✅ 完成 |
| M2 可靠执行 | T06–T13 | 🔨 部分（T09/T10/T13 完成；T06/T07/T08/T11/T12 待做） |
| M3 会话分析与界面 | T14–T19 | 🔨 部分（T16/T18 完成；T14/T15/T17/T19 待做） |
| M4 导入与多模态 | T20–T23 | ⬜ 未开始（真实服务凭据缺失） |
| M5 全量验证与文档 | T25/T26 | ⬜ 未开始 |
| M6 迁移与发布 | T27 | ⬜ 未开始（真实库迁移需授权） |

## 已完成（本回合）

- **T01/T02** Settings/时钟/错误码/严格 Money(整数分)/日期/分类/模式（47 用例）。
- **T03** V2 schema（整数分、软删、乐观锁 version、schema_migrations + checksum）+ 迁移 runner + 索引。
- **T04** `migrate_old_db`：只读旧库 → 独立新库，逐行金额转分（`Decimal(str(value))` ROUND_HALF_UP）、异常行阻断、逐月逐分类对账、保留旧 ID。
- **T05** `LedgerService`：增删改查 + 软删恢复 + 乐观锁（`VersionConflict`）+ 账本 revision + mutation_events。
- **T09** `BudgetService`：按月唯一（`UNIQUE(ledger_id,period,scope_key)`），跨月不覆盖；支持分类与 total 总预算。
- **T10** `ToolRegistry`：8 工具严格校验（金额/分类/日期/模式非法值拒绝），全部走服务层。
- **T13** `Agent` ReAct 编排器：工具执行 + 结果喂回 + 步数/工具数预算，可注入假 client。
- **T16** `AnalysisService`：事实包（总额/分类占比/全月 Top3/完整月环比/日均/日序列），Top3 不受分页限制（修 F09）。
- **T18** V2 API（`/api/v2/*`）+ 旧接口兼容（`/api/state|act|budget|reset` 映射回旧前端形状）；`create_app`；`main.py` 接线新后端；`python -m snarky_ledger migrate|doctor`。

**验证**：81 个测试全部通过（金额/日期/分类/模式/服务/迁移/工具/Agent/API），旧 `test_offline.py` 4 用例仍通过。

## 尚未完成（如实记录）

| 项 | 说明 |
| --- | --- |
| T06 幂等命令 | `command_requests` 表已建，未接入 turn 流程（防重试重复落账） |
| T07 一次性确认 | 删除已是软删，但未做两步确认 / 清空维护模式 + epoch |
| T08 本机认证 | 无 CSRF / Host-Origin / 访问令牌 |
| T11 Provider | 无能力探测、超时重试、假 Provider 抽象 |
| T12/T14/T15 会话/摘要/记忆 | 未持久化会话消息 |
| T17 报告 | 无报告缓存与事实核验（当前 persona_report 直接给事实包） |
| T19 前端重写 | W01–W08 未做；当前旧前端经旧接口兼容可用 |
| T20–T23 多模态/CSV | 未实现（接口占位，能力开关关闭） |
| T25–T27 | 评测集、依赖锁、发布回滚 |

## 需授权 / 凭据门槛

- **真实账本迁移**：当前只用合成库演练；迁移真实 `ledger.db` 需你授权并提供副本。
- **真实多模态识别**：图片/语音需对应服务凭据，未验收不得宣称可用。

## 变更记录

| 日期 | 内容 |
| --- | --- |
| 2026-11-05 | M0 完成；T01/T02 完成 |
| 2026-11-05 | T03–T05、T09/T10/T13/T16/T18 完成；81 测试通过 |
