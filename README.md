# 损友账本 · Snarky Ledger

> 一个会毒舌吐槽的 AI 记账 Agent。你用自然语言记一笔账，它就损你一句；月底再给你一份「花钱人格报告」。

**实用的是功能，天马行空的是人设。** 记账、查账、统计、预算——这是实打实的个人财务工具；而替你看账的，是一个嘴贱但关心你的「损友」——吐槽具体到每一分钱，还会脑洞「这笔钱本可以干什么」。

```
你 > 今天花 50 吃火锅
账哥 > 火锅 50 已入账。你这个月已经吃 3 顿火锅了，肠胃比钱包还能扛。
```

## 为什么它是 Agent

- **记忆** = SQLite 里的账目 + 预算 + 会话 + 偏好记忆（`db.py` / `repo.py`）
- **工具** = 记账 / 查账 / 统计 / 预算 / 报告等 8 个函数 + JSON Schema（`tools.py`）
- **循环** = LLM 决定要不要调工具 → 严格校验执行 → 把结果喂回 → 直到给出最终回复（`agent.py` 的 ReAct 循环）

**同一个循环，把 `move`/`attack` 换成 `add_expense`/`query_expenses`，游戏就变成了记账管家。** 这是「工具可替换性」的活证明。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env          # 填入你的 DEEPSEEK_API_KEY
python main.py                # 终端版
python main.py --web          # 网页版（图表 + 对话），默认 http://127.0.0.1:5000
```

> 需要 DeepSeek API Key，到 [platform.deepseek.com](https://platform.deepseek.com) 申请后填入 `.env`（`.env` 已 gitignore，不会进仓库）。

## V2 特性：正确性 & 安全

| 特性 | 说明 |
| --- | --- |
| 金额整数分 | 内部以「分」为唯一计算单位，API 传十进制字符串；拒绝浮点/布尔/负/超两位小数/越界 |
| 收入与结余 | 收入（工资/兼职/理财/红包礼金/其他收入）与支出分开记录，自动算结余 |
| 软删 + 乐观锁 | 删除是软删（可恢复），编辑/删除用 `version` 乐观锁防覆盖 |
| 按月预算 | 预算按「月份 + 分类」唯一，跨月不覆盖；支持总预算 |
| 全月统计 | 最大三笔按全月取、不受分页影响；完整月环比与日均口径明确 |
| 版本迁移 | `schema_migrations` + checksum；旧库 → V2 迁移逐行金额转分并对账 |
| 安全执行 | 两步清空（预览 + 确认）；本机认证（同源 + 可选令牌）；未知分类/模式拒绝不放宽 |
| 会话与记忆 | 会话持久化；长期记忆白名单（分类别名/直记偏好等），不记病史/工资 |
| CSV 导入导出 | 候选核对后入账；导出做公式注入防护 |

## 功能与工具（9 个）

| 工具 | 参数 | 做什么 |
| --- | --- | --- |
| `add_expense` | amount, category, note?, date? | 记一笔支出（返回该分类本月累计，供吐槽） |
| `add_income` | amount, category, note?, date? | 记一笔收入（工资/兼职/理财等），返回本月收入累计 |
| `query_expenses` | start?, end?, category? | 查账：总额 + 分类占比 + 明细 |
| `monthly_stats` | month? | 月度统计 + 完整月环比 + 日均 + 最大三笔 |
| `set_budget` | category, amount | 设某分类（或 total 总预算）的月预算 |
| `budget_status` | — | 预算剩余 / 超支百分比 |
| `persona_report` | month? | 花钱人格报告数据（统计 + 最大三笔） |
| `set_mode` | mode('savage'/'gentle') | 切换毒舌 / 温柔模式 |
| `delete_expense` | id | 软删一笔账（可恢复） |

分类可省略让 agent 自己推断；推断不出才追问——这是「主动补全 + 必要时澄清」的 agent 行为展示点。

## 人设：账哥

一个嘴贱但真心关心你钱的损友，而不是冷冰冰的财务软件。语气规则（详见 `snarky_ledger/persona.py`）：

1. **具体到数字**：吐槽必须引用真实金额、次数、占比。
2. **损事不损人**：损这笔消费和它的后果，绝不攻击用户的人格、能力、家庭、收入。
3. **有梗有脑洞**：把「这笔钱本可以干什么」换算成离谱但具体的等价物。
4. **网开一面**：医疗、学习、房租、给家人的支出——不毒舌，反而给一句认可。
5. **可切温柔模式**：说「别损我，今天心情差」→ 立即 `set_mode('gentle')`。

安全边界：不评价赚多赚少、不做金钱羞辱；不鼓励报复性消费，也不鼓励极端节俭。

## 项目结构

```
snarky-ledger/
├── snarky_ledger/          # V2 主包
│   ├── domain/             # Money（整数分）/ 日期 / 分类 / 模式，严格校验
│   ├── db.py               # SQLite 连接 + schema 版本迁移
│   ├── migrate.py          # 旧库 → V2 迁移 + 对账
│   ├── repo.py             # 参数化 SQL 仓储
│   ├── services.py         # 账目 / 预算 / 分析
│   ├── advanced.py         # 会话 / 记忆 / 确认 / 报告缓存 / CSV
│   ├── tools.py            # 8 工具 + JSON Schema
│   ├── agent.py            # ReAct 编排器
│   └── api.py              # Flask API（V2 + 旧接口兼容）
├── main.py                 # 入口：REPL / --web
├── static/index.html       # 前端：对话 + 图表 + 预算 + 月份切换 + 删除
├── tests/                  # 90 个单元测试
├── docs/v2/                # 架构 / API / 迁移 / 运维 / 隐私 / 发布清单
├── requirements.txt
└── .env.example
```

## 测试

```bash
python -m unittest discover -s tests -t .   # 90 个用例：金额/日期/服务/迁移/工具/Agent/API/会话/记忆/CSV
```

## 迁移与运维

```bash
python -m snarky_ledger migrate --old <旧库> --new <新库>   # 旧库迁移（只读旧库、逐行转分、对账）
python -m snarky_ledger doctor --db <数据库>                # integrity_check / schema_version
```

## 演示

```
你 > 今天花 50 吃火锅
你 > 又买了杯 18 的奶茶
你 > 我这个月花了多少？
你 > 设个餐饮预算 1500
你 > 再记一笔：299 买耳机
你 > 发工资了，记收入 8000
你 > 别损我，今天心情差
你 > 给我看看我这个月的花钱人格
```

这段能依次展示：记账 + 吐槽 → 关联记忆 → 统计 → 预算 → 超支预警 → 记收入 → 模式切换 → 花钱人格报告。
