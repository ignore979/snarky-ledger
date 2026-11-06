# 架构（architecture.md）

单进程模块化单体：Flask + SQLite + 原生前端，不引入微服务、ORM、向量库。

## 分层

| 模块 | 职责 |
| --- | --- |
| `domain/` | Money（整数分）、BusinessDate/Month、Category、Mode 值对象，严格校验 |
| `db.py` | SQLite 连接、版本迁移（`schema_migrations` + checksum）、种子 |
| `migrate.py` | 旧库 → V2 迁移（只读旧库、逐行转分、对账） |
| `repo.py` | 参数化 SQL 仓储，短事务 |
| `services.py` | LedgerService / BudgetService / AnalysisService |
| `advanced.py` | SessionService / MemoryService / ConfirmationService / ReportService / CSV |
| `tools.py` | ToolRegistry 8 工具，严格校验，走服务层 |
| `agent.py` | ReAct 编排器（可注入假 client） |
| `api.py` | Flask 应用：V2 + 旧接口兼容 + 本机认证 |

## 数据流

```
网页 / CLI → Flask API / 工具 → 服务层 → 仓储 → SQLite
                ↑
模型只调用受控工具；Repository 不依赖 LLM；分析由后端确定性计算
```

## 关键不变量

- 金额以整数分（`amount_minor`）为唯一存储与计算单位；API 传十进制字符串。
- 软删 + 乐观锁 `version`；写操作同事务更新 `ledger_revision` 并写 `mutation_events`。
- 清空账本走两步确认（`reset-preview` / `reset-confirm`）；旧 `/api/reset` 返回 409。
- 未知分类/非法模式/非有限金额一律拒绝，不静默放宽。
