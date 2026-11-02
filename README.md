# 损友账本 · Snarky Ledger

> 一个会毒舌吐槽的 AI 记账 Agent。你用自然语言记一笔账，它就损你一句；月底再给你一份「花钱人格报告」。

**实用的是功能，天马行空的是人设。** 记账、查账、统计、预算——这是实打实的个人财务工具；而替你看账的，是一个嘴贱但关心你的「损友」——吐槽具体到每一分钱，还会脑洞「这笔钱本可以干什么」。

```
你 > 今天花 50 吃火锅
账哥 > 火锅 50 已入账。你这个月已经吃 3 顿火锅了，肠胃比钱包还能扛。
```

## 为什么它是 Agent

和「地牢主」是同一套引擎，只是换了一批工具：

- **记忆** = SQLite 里的账目 + 预算（`ledger.py`）
- **工具** = 记账 / 查账 / 统计 / 预算 / 报告等 8 个函数 + JSON Schema（`tools.py`）
- **循环** = LLM 决定要不要调工具 → 执行 → 把结果喂回 → 直到给出最终回复（`agent.py` 的 ReAct 循环）

**同一个循环，把 `move`/`attack` 换成 `add_expense`/`query_expenses`，游戏就变成了记账管家。** 这是「工具可替换性」的活证明。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env          # 填入你的 DEEPSEEK_API_KEY
python main.py                # 终端版
python main.py --web          # 网页版（图表 + 对话），默认 http://127.0.0.1:5000
```

> 需要 DeepSeek API Key，到 [platform.deepseek.com](https://platform.deepseek.com) 申请后填入 `.env`。

## 功能与 8 个工具

| 工具 | 参数 | 做什么 |
| --- | --- | --- |
| `add_expense` | amount, category, note?, date? | 记一笔支出（返回该分类本月累计金额/次数，供吐槽） |
| `query_expenses` | start?, end?, category? | 查账：总额 + 分类占比 + 明细 |
| `monthly_stats` | month? | 月度统计 + 环比 + 日均 + 最大单笔 |
| `set_budget` | category, amount | 设某分类的月预算 |
| `budget_status` | — | 预算剩余 / 超支百分比 |
| `persona_report` | month? | 花钱人格报告数据（统计 + 本月最大三笔） |
| `set_mode` | mode('savage'/'gentle') | 切换毒舌 / 温柔模式 |
| `delete_expense` | id | 删一笔账（纠错） |

分类可省略让 agent 自己推断；推断不出才追问——这是「主动补全 + 必要时澄清」的 agent 行为展示点。

## 人设：账哥

一个嘴贱但真心关心你钱的损友，而不是冷冰冰的财务软件。语气规则（详见 `persona.py`）：

1. **具体到数字**：吐槽必须引用真实金额、次数、占比。
2. **损事不损人**：损这笔消费和它的后果，绝不攻击用户的人格、能力、家庭、收入。
3. **有梗有脑洞**：把「这笔钱本可以干什么」换算成离谱但具体的等价物。
4. **网开一面**：医疗、学习、房租、给家人的支出——不毒舌，反而给一句认可。
5. **可切温柔模式**：说「别损我，今天心情差」→ 立即 `set_mode('gentle')`。

安全边界：不评价赚多赚少、不做金钱羞辱；不鼓励报复性消费，也不鼓励极端节俭。

## 项目结构

```
snarky-ledger/
├── ledger.py          # SQLite 数据层：建表、增删查、统计、预算、模式
├── persona.py         # 人设：系统提示词 + 语气规则 + 报告模板
├── tools.py           # 8 个工具 + JSON Schema + 分发执行
├── agent.py           # ReAct 循环
├── main.py            # 终端 REPL（--web 启动网页版）
├── web.py             # Flask 后端（/api/state /api/act /api/budget /api/reset）
├── static/index.html  # 前端：对话 + 账目表 + 柱状图 + 饼图 + 预算面板
├── test_offline.py    # 离线测试（无需 API key）
├── requirements.txt
└── .env.example
```

## 测试

无需 API key 的离线测试，覆盖数据层、工具分发与 ReAct 循环（用假 client 注入）：

```bash
python test_offline.py
```

## 演示

> [!NOTE]
> 演示截图 / GIF 待补充：拿到 `DEEPSEEK_API_KEY` 后跑一遍下面的脚本即可录屏。

```
你 > 今天花 50 吃火锅
你 > 又买了杯 18 的奶茶
你 > 我这个月花了多少？
你 > 设个餐饮预算 1500
你 > 再记一笔：299 买耳机
你 > 别损我，今天心情差
你 > 给我看看我这个月的花钱人格
```

这段能依次展示：记账 + 吐槽 → 关联记忆 → 统计 → 预算 → 超支预警 → 模式切换 → 花钱人格报告。
