# API（api.md）

统一错误格式：`{"error": {"code", "message", "field_errors", "retryable"}}`。
本机安全：Host 须为 `127.0.0.1` / `localhost`；可配 `LEDGER_ACCESS_TOKEN`。

## V2（/api/v2）

| 方法与路径 | 用途 |
| --- | --- |
| GET /capabilities | 能力开关状态（text_agent / csv_import …） |
| GET /state?month=YYYY-MM | 一致快照（mode / facts / budgets / expenses） |
| POST /expenses | 手工记账（amount 为字符串） |
| GET /expenses | 分页列表（start/end/category_id/limit） |
| PATCH /expenses/{id} | 编辑（version 乐观锁） |
| DELETE /expenses/{id} | 软删（version） |
| POST /expenses/{id}/restore | 恢复 |
| PUT /budgets/{period}/{scope_key} | 月预算（scope_key = total 或分类 id） |
| GET /analysis、/reports | 确定性事实包（带缓存） |
| POST /sessions、GET /sessions、GET /sessions/{id}/messages、POST /sessions/{id}/turns | 会话与消息 |
| POST /turns | 默认会话自然语言 turn（支持 request_id 幂等） |
| GET/PATCH /preferences | 模式等偏好 |
| GET/POST/DELETE /memories | 记忆白名单 |
| POST /maintenance/reset-preview、/reset-confirm | 两步清空 |
| GET /exports/expenses.csv | 导出（公式注入防护） |
| POST /imports/csv、/imports/csv/confirm | CSV 候选核对 + 确认入账 |

## 旧接口兼容

`/api/state`、`/api/act`、`/api/budget` 保留，返回旧字段形状（金额转只读数字）。
`/api/reset` 不再直接清空，返回 `409 CONFIRMATION_REQUIRED` + `action_id` + 预览。
