# Multi-Agent Debate 系统 Prompt 工程

## 架构总览

TradingAgents-Astock 的辩论系统由两个独立辩论 + 两个裁判 + 一个最终交易员组成：

```
7-8 Analyst Reports (数据输入)
        │
        ▼
┌──────────────────────────┐
│  ① Bull Bear Debate      │  ← 3轮 Bull ↔ Bear 互驳
│  (investment_debate)     │
│        │                 │
│        ▼                 │
│  Research Manager (裁判)  │  → judge_decision + rating
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Trader (交易员)          │  → trader_investment_plan
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  ② Risk Debate           │  ← Aggressive ↔ Conservative ↔ Neutral
│  (risk_debate)           │     3方辩论
│        │                 │
│        ▼                 │
│  Portfolio Manager (裁判) │  → final_trade_decision
└────────┬─────────────────┘
         │
         ▼
   最终输出：signal + decision
```

## 文件结构与角色映射

### 第一阶段：多空辩论 (Investment Debate)

| 文件 | 角色 |
|------|------|
| `agents/researchers/bull_researcher.py` | **Bull Analyst** |
| `agents/researchers/bear_researcher.py` | **Bear Analyst** |
| `agents/managers/research_manager.py` | **Research Manager (裁判)** |

### 第二阶段：交易员 (Trader)

| 文件 | 角色 |
|------|------|
| `agents/trader/trader.py` | **Trader** — 读所有Analyst reports + Research Manager计划，输出价格/仓位/止损建议 |

### 第三阶段：风险辩论 (Risk Debate)

| 文件 | 角色 |
|------|------|
| `agents/risk_mgmt/aggressive_debator.py` | **Aggressive Analyst** |
| `agents/risk_mgmt/conservative_debator.py` | **Conservative Analyst** |
| `agents/risk_mgmt/neutral_debator.py` | **Neutral Analyst** |
| `agents/managers/portfolio_manager.py` | **Portfolio Manager (裁判)** — 最终决策者 |

### 数据流：State 结构

```python
# 分析师报告（共享）
market_report, sentiment_report, news_report, fundamentals_report,
policy_report, hot_money_report, lockup_report, chanlun_report

# 投资辩论状态
investment_debate_state: {
    "history": str, "bull_history": str, "bear_history": str,
    "current_response": str, "judge_decision": str, "count": int
}
trader_investment_plan: str
investment_plan: str

# 风险辩论状态
risk_debate_state: {
    "history": str,
    "aggressive_history": str, "conservative_history": str, "neutral_history": str,
    "latest_speaker": str,
    "current_aggressive_response": str, "current_conservative_response": str, "current_neutral_response": str,
    "judge_decision": str, "count": int
}
final_trade_decision: str
```

---

## ⭐ 游资大师实战框架注入（2026-06-08 重大升级）

### 设计理念

不满足于"游资报告作为可选数据输入"——而是把**游资大师的实战心法、判断框架、决策逻辑**直接嵌入到每个辩论角色的prompt中。让Bull不是"引用龙虎榜数据"，而是**用养家心法论证为什么这是"大众情人"**；让Bear不是"说游资在退"，而是**用闻少的退潮期信号和退学炒股的小明陷阱来拆解Bull的逻辑**。

### 7个文件、各角色的游资大师分配

| 角色 | 注入的大师 | 核心用途 |
|------|-----------|---------|
| **Bull Researcher** 🐂 | 养家、赵老哥、92科比 | Bull必须用大师框架论证上涨逻辑 |
| **Bear Researcher** 🐻 | 闻少、退学炒股、涅槃重升 | Bear必须用大师框架揭示风险 |
| **Research Manager** ⚖️ | 养家、92科比、涅槃重升 | 裁判用养家周期评判辩论 |
| **Aggressive Debater** 🔥 | 赵老哥、Asking、养家 | 用龙头接力+绝望中诞生框架支持激进 |
| **Conservative Debater** 🛡️ | 北京炒家、涅槃重升、退学炒股 | 用分仓原则+回撤威慑压制激进 |
| **Neutral Debater** ⚪ | 92科比、闻少、养家 | 用周期定位+盘口语言仲裁多空 |
| **Portfolio Manager** 🏆 | 养家、北京炒家、涅槃重升 | 用仓位体系+分仓原则定最终决策 |

### 具体注入内容

#### 1️⃣ Bull Researcher — 养家/赵老哥/92科比框架

**养家心法（情绪周期派）**：
- **"要做就做最强，选股选大众情人"** — 龙头溢价论证
- **"行情好多做，行情不好少做"** — 择时合理性
- **"买入机会，卖出风险"** — 当前风险已定价论证
- **"强势阶段做最强个股主升浪"** — 持有/加仓信号
- **"赚钱效应决定方向"** — 板块共振论证

**赵老哥模式（龙头接力）**：
- 三个确认信号：① 题材强度 ② 分歧转一致蜡烛 ③ 万亿大单封板
- **龙头战法核心**：最能带动板块、涨幅最大/最先涨停、换手充分、有题材支撑、盘子适中、人气最旺

**92科比情绪周期**：
- ⭐ **MANDATORY**: Bull必须声明当前在哪个周期阶段（启动→发酵→高潮→衰退），并以此作为论证基础

#### 2️⃣ Bear Researcher — 闻少/退学炒股/涅槃重升框架

**闻少体系（情绪周期+盘口）**：
- **退潮期识别信号**：连板断裂、炸板率上升、昨涨停今低开无溢价
- **"分歧转一致失败"** — 放量长上影 = 强Bear信号
- **盘口语言**：缩量无法创新高 = 主力在出货

**退学炒股（"我和小明"）**：
- ⭐ **MANDATORY**: Bear必须指出Bull陷入了哪种小明陷阱
- "这次不一样" = narrative-driven 小明
- "再不买就来不及了" = FOMO-driven 小明
- "基本面已经改善了" = valuation-ignoring 小明

**涅槃重升（控制回撤）**：
- **"控制回撤比追求盈利更重要"**
- 20%回撤需25%涨幅回本；30%需43%

#### 3️⃣ Research Manager — 养家/92科比/涅槃重升评判框架

裁判必须用养家心法评判辩论：
- **"赚钱效应/恐慌效应决定大势"** — 判定当前谁占优
- **"不同阶段不同手法"** — 强势→Bull权重高；弱势→Bear权重高；平衡→中性权重高
- **"试错单感受市场情绪"** — 数据模糊时推荐小仓位测试

**MANDATORY**: 必须声明在92科比周期中的位置。Buy/Overweight要求周期在启动或早期发酵；Sell/Underweight适合高潮晚期或衰退

#### 4️⃣ Aggressive Debater — 赵老哥/Asking/养家框架

**赵老哥**：只做龙头主升浪。三个确认信号：题材第一生产力、分歧转一致、万亿大单封板

**Asking**：**"行情在绝望中诞生，在犹豫中上涨，在疯狂中死亡"** — 用情绪数据定位阶段。悲观=最佳激进时机；混合=可参与；疯狂才需谨慎

#### 5️⃣ Conservative Debater — 北京炒家/涅槃重升/退学炒股框架

**北京炒家（A股最稳游资之一）**：
- **模式一致性比选到牛股更重要**
- **严格分仓，单票≤1/3**
- **专注首板，不打接力** — 股票已大涨则低风险入场点已过

**涅槃重升**：回撤计算威慑 + "稳定复利是唯一的道路"

**MANDATORY**: 指出Aggressive分析师被哪种小明驱动

#### 6️⃣ Neutral Debater — 92科比/养家/闻少框架

**92科比周期定位**：MANDATORY — 判定阶段并据此定仓位：
- 启动期：10-20%测试仓
- 发酵期：20-40%核心仓
- 高潮期：10-15%战术仓
- 衰退期：<5%或退出

**闻少盘口验证**：成交量不说谎
- 价涨量增 = 真趋势
- 价平量增 = 主力出货
- 价跌量缩 = 游资离场
- 价涨量缩 = 反弹非反转

#### 7️⃣ Portfolio Manager — 养家/北京炒家/涅槃重升仓位体系

**养家仓位体系**：
- Buy = 奋力一击（高确信+低风险）
- Sell = 风险已至
- Hold/Underweight/Overweight = 试错+观察（默认状态）

**北京炒家**：单票≤1/3；模式一致性

**涅槃重升**：止损必须限制在15-20%最大回撤

---

## ⭐ 缠论技术分析强制维度注入（2026-06-08 新增）

### 设计理念

与游资大师框架相同的设计——不满足于"缠论报告作为可选输入"，而是把**缠中说禅的买卖点体系、背驰理论、中枢结构、级别递归**直接嵌入到每个辩论角色的prompt中。让Bull不是"说技术形态好"，而是**用三买论证趋势延续、用中枢上沿突破论证压力变支撑**；让Bear不是"说技术形态差"，而是**用三卖论证下跌趋势确认、用背了又背拆解抄底论**。

### 7个文件、各角色的缠论分配

| 角色 | 缠论调用角度 | 核心心法 |
|------|-------------|---------|
| **Bull Researcher** 🐂 | 一买/二买/三买做多信号、中枢突破、底背驰 | "三买=缠论最强做多信号"、"中枢上沿突破=压力变支撑" |
| **Bear Researcher** 🐻 | 一卖/二卖/三卖做空信号、顶背驰、区间套共振 | "三卖=缠论最强做空信号"、"背了又背=大级别下跌未结束" |
| **Research Manager** ⚖️ | 走势类型定评级、买卖点定偏向 | "盘整方向不明→Hold" |
| **Aggressive Debater** 🔥 | 三买最佳进场、区间套共振向上 | "三买+缩量回踩=加仓机会" |
| **Conservative Debater** 🛡️ | 级别分析拆穿假底背驰、中枢下沿破位 | "次级别三买在大级别下跌趋势中是陷阱" |
| **Neutral Debater** ⚪ | 走势类型仲裁、中枢区间定方向 | "缠论自身说方向未定，任何激进押注都是赌博" |
| **Portfolio Manager** 🏆 | 买卖点辅助止盈止损位 | "一卖出现→减仓；三买出现→持有" |

### 注入代码模板

每个角色注入的模式遵循以下模板：

```python
# 1. 读取state
chanlun_report = state.get("chanlun_report", "")

# 2. 在prompt的A-Share Framework中添加缠论维度
### ⭐ 缠论技术分析 (Chanlun Theory) — MANDATORY DIMENSION
You MUST explicitly cite the chanlun report in your argument.

**买卖点 framing:**
- **第三类买点（三买）出现** = 最强信号描述
- **第二类买点（二买）出现** = 趋势确认描述
- **第一类买点（一买）出现+底背驰** = 趋势逆转描述

**走势类型 framing:**
- **上涨趋势（两个以上中枢）** = 趋势延续论据
- **下跌趋势（两个以上中枢）** = 趋势反转论据
- **盘整（一个中枢）** = 方向不明中性论据

**背驰 framing:**
- **无背驰** = 趋势健康
- **盘整背驰后反转** = 突破/跌破信号
- **背了又背** = 大级别趋势碾压小级别信号

**中枢 framing:**
- **中枢上沿突破** = 压力变支撑
- **中枢下沿被跌破** = 支撑变压力

**Must address**: Even if the chanlun report is sparse, state what you can infer.

# 3. 在Resources中加入报告
Chanlun Technical Analysis Report: {chanlun_report}
```

### 缠论维度 vs 游资维度的关键区别

| 维度 | 游资大师框架 | 缠论框架 |
|------|------------|---------|
| 分析对象 | 短线资金博弈、情绪周期、席位行为 | K线结构、趋势级别、买卖点位置 |
| 多空对称性 | 不对称（养家/赵老哥偏多，闻少/退学偏空，北京炒家偏防守） | **完美对称**（一买~三买对一卖~三卖，底背驰对顶背驰） |
| 最佳仲裁工具 | 闻少盘口语言（成交量验证） | 走势类型（上涨/下跌/盘整）+ 级别递归 |
| 裁判用法 | 养家"赚钱效应/恐慌效应"周期评判 | 买卖点类型+走势类型定方向 |
| Neutral用法 | 92科比周期定位仓位 | 中枢震荡=方向不明→减仓 |

### 与游资框架的协同

缠论NEVER替代游资分析——两者互补：
- **游资看"人"**（谁在买/卖、情绪好不好、有没有接盘侠）
- **缠论看"结构"**（趋势完不完整、背驰了没有、有没有买卖点）
- **Bull** = 游资说大众情人确认 + 缠论说三买确认 = 双确认
- **Bear** = 游资说游资在撤退 + 缠论说三卖出现 = 双确认
- **Neutral** = 游资说成交量萎缩 + 缠论说盘整中 = 双中性

---

### 通用改造模式（可复用于任何新维度）

要将任何report升级为"强制辩论维度"，遵循以下模式：

```python
# 步骤1：在7个文件中各加一行 state读取
new_report = state.get("new_report", "")

# 步骤2：在prompt的A-Share Framework/Bear Framework/etc中
# 插入 ⭐ 标签的强制维度，位于现有维度之后

### ⭐ 新维度名称 — MANDATORY DIMENSION
You MUST explicitly cite the new report.
- 看多加仓信号（针对Bull/Aggressive）
- 看空减仓信号（针对Bear/Conservative）
- 平衡仲裁信号（针对Neutral/裁判）

**Must address**: 即使数据稀疏也要说能推断什么

# 步骤3：在Resources末尾加入
New Report: {new_report}
```

### 改造关键原则

1. **每个角色有专属框架角度** — 不是所有角色用同样的话术
2. **MANDATORY标签强制执行** — LLM必须引用，不能跳过
3. **与已有维度协同而非替代** — 缠论+游资双重确认比单一维度更强
4. **数据稀疏时也要表态** — "没有买卖点"本身就是一个信号
5. **裁判必须仲裁** — Research Manager和Portfolio Manager收到所有报告
