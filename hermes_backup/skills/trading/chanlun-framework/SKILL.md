---
name: chanlun-framework
description: TradingAgents-Astock 缠论多智能体框架 —— 8层分析师流水线 + DeepSeek LLM 驱动 + A股实时数据 + 缠论算法引擎 + 游资大师/缠论强制辩论维度
version: 2.1.0
tags:
  - 缠论
  - TradingAgents
  - 多智能体
  - A股
  - LangGraph
  - DeepSeek
related_skills:
  - chanlun-theory
  - chanlun-value-research
  - chanlun-market-data
  - chanlun-industry-chain
  - chanlun-industry-trend
  - chanlun-psychology
  - chanlun-decision
  - chanlun-stock-screening
  - youzi-screening
  - portfolio-monitor
  - three-crows-screening
---

# chanlun-framework

## 用途

当你需要**运行完整的缠论分析师流水线**来分析某一支A股时，加载此 skill。

该 skill 描述了 TradingAgents-Astock 框架的完整架构、配置方式、API 注册方式和使用方法。

**注意**：此 skill 依赖 `/home/harrydolly/code/TradingAgents-astock/` 项目，项目必须已安装并配置好 DeepSeek API key。

## 架构总览

```
用户输入（股票代码+日期）
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  数据预处理 ← ensure_data() 检查DB完整性 + 自动补全        │
│  或 live_data.get_data_for_analysis() 腾讯API实时数据     │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────┐
│  8 位 Analyst（串行执行，逐层叠加分析）                │
│                                                       │
│  分析师                   分析维度                    │
│  ─────────────────────────────────────────────────    │
│  1️⃣ Market Analyst       传统技术分析（均线/MACD/RSI） │
│  2️⃣ Social Analyst       社交媒体情绪                  │
│  3️⃣ News Analyst         新闻资讯                     │
│  4️⃣ Fundamentals Analyst 财务三表（资产负债表/利润/现金流）│
│  5️⃣ Policy Analyst       政策面分析                   │
│  6️⃣ Hot Money Analyst    游资/北向资金/主力资金        │
│  7️⃣ Lockup Analyst       限售解禁监控                 │
│  8️⃣ Chanlun Analyst ★    缠论技术分析（笔/中枢/背驰/买卖点）│
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │  Quality Gate    │  ← 5 级质量评分（A/B/C/D/F）
              │  (5 级评分)      │
              └────────┬─────────┘
                       │
              ┌────────┴──────────────────────────────┐
              │  ⚔️ Bull Bear Debate（游资大师框架强化）  │
              │    Bull(养家/赵老哥/92科比) ↔            │
              │    Bear(闻少/退学/涅槃重升)              │
              │    裁判：养家周期+92科比定位+涅槃回撤     │
              │  🧩 缠论强制维度：买卖点+走势类型+背驰     │
              └────────┬──────────────────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  💰 Trader        │  → trader_investment_plan
              └────────┬─────────┘
                       │
                       ▼
              ┌─────────────────────────────────────────────┐
              │  ⚠️ Risk Debate（游资+缠论双向强化）          │
              │    Aggressive(赵老哥/Asking) ↔              │
              │    Conservative(北京炒家/涅槃) ↔             │
              │    Neutral(92科比/闻少)                     │
              │    裁判 Portfolio Manager(养家仓位/分仓原则)  │
              └────────┬──────────────────────────────────┘
                       │
                       ▼
                ┌────────────┐
                │  投资决策    │
                │  + 仓位建议  │
                └────────────┘
```

## 项目路径

```
/home/harrydolly/code/TradingAgents-astock/
├── tradingagents/
│   ├── graph/
│   │   ├── trading_graph.py     # 图编译入口（34个节点）
│   │   ├── setup.py              # 节点注册 + 流水线编排
│   │   └── conditional_logic.py  # 路由条件判断
│   ├── agents/
│   │   ├── agent_states.py      # AgentState 状态定义
│   │   ├── propagation.py       # 状态初始化
│   │   ├── analysts/            # 8 位分析师
│   │   │   ├── market_analyst.py
│   │   │   ├── social_analyst.py
│   │   │   ├── news_analyst.py
│   │   │   ├── fundamentals_analyst.py
│   │   │   ├── policy_analyst.py
│   │   │   ├── hot_money_analyst.py
│   │   │   ├── lockup_analyst.py
│   │   │   └── chanlun_analyst.py   # ★ 缠论分析师
│   │   ├── researchers/         # ★ Bull/Bear 辩论（游资+缠论强化）
│   │   │   ├── bull_researcher.py   # 养家/赵老哥/92科比 + 缠论三买
│   │   │   └── bear_researcher.py   # 闻少/退学/涅槃 + 缠论三卖
│   │   ├── risk_mgmt/           # ★ 风险辩论三方（游资+缠论强化）
│   │   │   ├── aggressive_debator.py   # 赵老哥/Asking + 缠论区间套
│   │   │   ├── conservative_debator.py # 北京炒家/涅槃 + 缠论级别分析
│   │   │   └── neutral_debator.py     # 92科比/闻少 + 缠论走势类型
│   │   ├── managers/            # ★ 两个裁判（游资+缠论强化）
│   │   │   ├── research_manager.py    # 养家周期+92科比定位+缠论
│   │   │   └── portfolio_manager.py   # 养家仓位+分仓原则+缠论
│   │   ├── trader/
│   │   │   └── trader.py        # 交易员（最终交易建议）
│   │   ├── quality_gate.py     # 数据质量门控（5级评分）
│   │   └── utils/
│   │       ├── llm.py           # LLM 工厂（支持 DeepSeek）
│   │       ├── agent_utils.py
│   │       └── chanlun_tools.py  # ★ 缠论工具（4 个 LangChain Tool）
│   ├── dataflows/
│   │   ├── interface.py         # 数据接口路由
│   │   ├── a_stock.py           # A股数据函数（DB->mootdx->Sina三级fallback）
│   │   ├── data_integrity.py    # ★ 新增：DB数据完整性检查+自动补全
│   │   ├── multi_dimension_scan.py  # ★ 新增：8维度全市场筛选
│   │   ├── live_data.py         # ★ 新增：盘中实时数据（腾讯API直连）
│   │   ├── astock_db.py         # SQLite数据库模块
│   │   ├── chanlun/             # ★ 缠论算法引擎
│   │   │   ├── __init__.py      # 主入口：analyze_chanlun()
│   │   │   ├── chanlun_core.py  # 数据模型（分型/笔/中枢/买卖点）
│   │   │   ├── chanlun_bi.py    # 笔划分算法
│   │   │   ├── chanlun_zhongshu.py  # 中枢识别
│   │   │   └── chanlun_beichi.py    # 背驰判断
│   │   └── ...
│   └── __init__.py
└── pyproject.toml
```

## 交互方式

本项目提供 3 种使用方式，**推荐只用 Python API 方式**：

| 方式 | 状态 | 说明 |
|------|------|------|
| **Python API** ✅ | **推荐使用** | `TradingAgentsGraph().propagate(...)` — 可在 Hermes 代码或 Python 脚本中直接调用 |
| typer CLI (`tradingagents`) | ❌ 未更新 | CLI 入口只支持原始 4 个 Analyst，未加缠论/政策/游资/解禁 |
| Streamlit Web UI (`tradingagents-web`) | ❌ 未更新 | Web 界面同理 |

## 环境配置

### 1. Python 环境
```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
```

已安装核心依赖：`langgraph`, `langchain-core`, `langchain-openai`, `mootdx`, `pandas`, `numpy`, `yfinance`。

### 2. DeepSeek API Key —— ⚠️ 关键坑
项目读的是 `os.environ["DEEPSEEK_API_KEY"]`，所以 key 必须提前在 shell 环境中 export。

**Hermes 工具中的注意事项**：
- Terminal 工具会在输出中包含关键词时自动脱敏替换为 `***`。
- 不要通过 `export DEEPSEEK_API_KEY=***` 的命令行传参方式设 key
- **实际配置位置**：在 `/etc/profile` 中 export，terminal中需先 `bash -c 'source /etc/profile; python3 script.py'` 才能读到
- 也可以在同个 Python 进程中用 `os.environ['DEEPSEEK_API_KEY'] = '...'` 硬编码设 key（仅限 single-file 脚本）
- 不要写入 `.env` 文件或 `~/.bashrc`（脱敏器会在文件写入时替换 key 内容）

### 3. LLM 配置
`llm.py` 原生支持 DeepSeek，provider 已改为 `deepseek`。

## 盘中实时 vs 盘后同步数据

### 盘中分析（推荐）
```python
from tradingagents.dataflows.live_data import get_data_for_analysis

data = get_data_for_analysis("301231")
# 返回: {klines, intraday, current_price, today_info, source}
# klines = DB历史日线 + 腾讯当天日线（前复权800天）
# intraday = 当天分时明细（分钟级）
# current_price = 实时价
```

盘中分时数据**不入库**，只临时获取。

### 盘后分析（全市场扫描时）
先调数据完整性检查，再用DB数据：
```python
from tradingagents.dataflows.data_integrity import ensure_data
ensure_data()
```

## 缠论数据流

### 算法层（纯 Python，不调 LLM）
```python
from tradingagents.dataflows.chanlun import analyze_chanlun, klines_from_dataframe
from tradingagents.dataflows.a_stock import get_stock_data
from io import StringIO
import pandas as pd

csv_str = get_stock_data("688017", "2026-01-01", "2026-06-07")
df = pd.read_csv(StringIO(csv_str), comment='#')
klines = klines_from_dataframe(df, date_col="Date",
    ohlc=("Open", "High", "Low", "Close", "Volume"))
result = analyze_chanlun(klines, ticker="688017", trade_date="2026-06-07")
print(result.to_markdown_report())
```

### LangChain Tool 层（给 LLM Analytic 调用）
```python
from tradingagents.agents.utils.chanlun_tools import get_chanlun_full_report
import json
klines_json = json.dumps([{"date":k.date,"open":k.open,...} for k in klines])
print(get_chanlun_full_report.invoke({"klines_json": klines_json}))
```

## 关联参考文件

通过 `skill_view('chanlun-framework', file_path='references/xxx.md')` 访问：

| 文件 | 内容 |
|------|------|
| `references/api-pitfalls.md` | 所有API函数已验证的返回类型、签名、行为细节、备选方案 |
| `references/debate-system-prompt-engineering.md` | Multi-Agent辩论系统Prompt工程（含游资大师+缠论强制维度注入方法论） |
| `references/multi-dimension-scan.md` | 全市场多维度扫描——8 Analyst维度量化映射指南 |
| `references/one-stock-chanlun-workflow.md` | 单只股票缠论分析完整工作流 |
| `references/tradingagents-chanlun-integration.md` | 缠论分析师集成架构记录 |
| `references/live-data-and-integrity.md` | ★ 新增：盘中实时数据获取 & 数据完整性检查 & 腾讯API参考 |
| `references/youzi-knowledge-base-reference.md` | 游资心法18位大师核心框架集成参考 |

## 游资大师强化辩论（7文件注入模式）

2026-06-08 完成：7个辩论角色的prompt中强制要求使用游资大师心法框架进行推理。

### 注入的游资大师

| 角色 | 注入大师 | 核心框架 |
|:----|:--------|:--------|
| Bull Researcher 🐂 | 养家、赵老哥、92科比 | "大众情人"共识选股、分歧转一致、周期阶段定位 |
| Bear Researcher 🐻 | 闻少、退学炒股、涅槃重升 | 退潮期识别、"小明"陷阱识别、控制回撤 |
| Research Manager ⚖️ | 养家、92科比、涅槃重升 | 赚钱效应vs恐慌效应评判、周期定位决定评级 |
| Portfolio Manager 🏆 | 养家、北京炒家、涅槃重升 | 仓位分级体系、单票≤1/3、回撤优先原则 |
| Aggressive Debater 🔥 | 赵老哥、Asking、养家 | 龙头接力信号、绝望中诞生、强势阶段主升浪 |
| Conservative Debater 🛡️ | 北京炒家、涅槃重升、退学炒股 | 分仓原则、回撤计算威慑、"小明"恐惧识别 |
| Neutral Debater ⚪ | 92科比、闻少、养家 | 周期定位决定仓位、盘口语言验证、游资温度计 |

### 游资注入模式（可复用于其他维度）

每个文件3步修改：
1. 读取state：`hot_money_report = state.get("hot_money_report", "")`
2. 在Resources中加入报告引用
3. 在A-Share Framework中插入带 ⭐ **MANDATORY** 标签的强制维度，包含具体心法引用和中文关键概念

**已验证效果**：单次分析中，养家引用59次、赵老哥48次、92科比50次、闻少75次、小明101次、涅槃42次、北京炒家33次、退学25次。

## 缠论强制辩论维度（第二次注入，2026-06-08）

在游资大师框架基础上，将缠论从"Resources中可选引用"升级为**每个角色的强制辩论维度**。

### 注入的缠论框架

| 角色 | 缠论调用角度 | 经典句型 |
|:----|:-----------|:--------|
| Bull 🐂 | 三买=最强做多信号、中枢上沿突破 | "缠论告诉我们多头的技术结构是完整的" |
| Bear 🐻 | 三卖=最强做空信号、背了又背 | "这不是底背驰，是次级别反弹" |
| Research Manager ⚖️ | 买卖点类型决定偏向、走势类型定评级 | "当前盘整方向不明，hold" |
| Aggressive Debater 🔥 | 三买缩量回踩=加仓机会、区间套共振 | "保守派在等什么？缠论三买 confirms" |
| Conservative Debater 🛡️ | 级别分析拆穿假底背驰、中枢下沿破位 | "次级别三买在大级别下跌趋势中是陷阱" |
| Neutral Debater ⚪ | 走势类型仲裁多空、中枢震荡=减仓 | "缠论自身说方向未定，任何激进押注都是赌博" |
| Portfolio Manager 🏆 | 买卖点辅助止盈止损位 | "一卖出现→减仓，三买出现→持有" |

### 默认启用修复

2026-06-08 同时修复了 `tradingagents/graph/trading_graph.py` 第63行的 `selected_analysts` 配置：

```python
# ❌ 旧版（漏了chanlun）
selected_analysts=["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup"]
# ✅ 已修复
selected_analysts=["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup", "chanlun"]
```

任何重置/重新clone后必须检查此项。如果框架跑了但输出中没有`chanlun_report`，第一排查这里。

## 数据完整性检查（全市场扫描前必须执行）

任何全市场批量操作前，调用 `data_integrity.ensure_data()` 确保DB数据最新：

```python
from tradingagents.dataflows.data_integrity import ensure_data
report = ensure_data("2026-06-05")  # 检查→自动补全缺失数据
```

脚本位置：`tradingagents/dataflows/data_integrity.py`

检查内容：
- 每只股票的最新交易日是否为目标日
- 记录数是否足够（>30条）
- 自动从新浪HTTP补缺失数据

当前状态：4371只股票、~19万条日线、最新至2026-06-05。

## 全市场多维度扫描（筛选→框架深度分析流水线）

### 架构

```
每日收盘 → ensure_data()检查补全 → 
多维度扫描(20秒全市场4360只) → 按总分排序Top 50 → 
手动选1-2只送入TradingAgents框架做完整分析
```

### 8 Analyst维度 → 量化筛选条件映射

脚本位置：`tradingagents/dataflows/multi_dimension_scan.py`

| 维度 | 量化逻辑 | 分数范围 | 数据源 |
|:----|:---------|:-------:|:-----|
| **市场** | 均线排列(10/20/60)、量比(5/20日)、5日涨跌幅 | 0-10 | DB K线 |
| **情绪** | RSI(14)区间、MACD多空(DIF/DEA/柱) | 0-10 | DB K线 |
| **事件** | 近10日涨停次数、放量大阳线 | 0-10 | DB K线 |
| **基本面** | PE/PB/营收增速 | 0-10 | ⏳ 待接入腾讯/东财 |
| **政策/题材** | 同花顺热点题材归属 | 0-10 | ⏳ 待接入 `get_hot_stocks()` |
| **游资** | 成交量爆发指数(峰值/均值比)、连板天数、量价配合 | 0-10 | DB K线 |
| **解禁/减持** | 限售解禁压力评估 | 0-10 | ⏳ 待接入 `get_lockup_expiry()` |
| **缠论** | 底分型+MACD底背驰（简化版）、顶部分型判断 | 0-10 | DB K线 |

总分80分（当前基本面/政策/解禁暂返回中性5分，有效50分）。

### 使用方式

```python
from tradingagents.dataflows.multi_dimension_scan import scan_market, show_candidates

# 全市场扫描，返回Top 50
results, date = scan_market(target_date="2026-06-05", top_n=50)

# 查看推荐的深度分析候选
show_candidates(top_n=10, scan_date=date)
```

## 已知坑/注意事项（快速排查）

### Key 配置（最常见失败原因）
- **DEEPSEEK_API_KEY 必须用 `export`**，项目读 `os.environ`
- **终端脱敏**：`DEE...` 在 terminal 工具中被替换为 `***`，不要通过命令传参设 key
- **最佳实践**：把 key 写死在单文件 Python 脚本顶部，用 `python3 /tmp/script.py` 执行

### 数据获取
- **`get_stock_data(symbol, start_date, end_date)`** → 返回 **CSV 字符串**，需 `pd.read_csv(StringIO(csv), comment='#')`
- **`get_fundamentals()`** → 返回 CSV 文本（`Name: XX` 格式行），按行解析
- **`get_news()`** 等 → 可能返回 HTML，不可靠时用 `web_search` 补充
- **mootdx** → 首次使用必须 `python -m mootdx bestip`

### 缠论算法
- 入口是 **`analyze_chanlun()`** 不是 `get_chanlun_full_report()`
- **`result.fractals`** 是 `List[Fractal]` 不是 dict
- `klines_from_dataframe()` 要求 Date 是列名（非 index）

### selected_analysts漏了chanlun（⚠️已修复，但仍需注意）
```python
# ❌ 旧版（漏了chanlun）:
selected_analysts=["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup"]
# ✅ 已修复:
selected_analysts=["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup", "chanlun"]
```
任何重置/重新clone后必须检查此项。

### 新浪API已切换为腾讯API
- 新浪股票列表API（`StockService.getStockNames`）返回 `Service not valid`
- 新浪K线API（`CN_MarketData.getKLineData`）高并发时返回HTTP 456
- 同步脚本已切换为腾讯API，详见 `astock-daily-sync` skill

### 盘中分时不入库
- `live_data.py` 的盘中数据只临时获取，不写入DB
- 收盘后cronjob在16:00执行 `sync_fast.py` 写入当日日线

## 关联 Skills
| Skill | 何时加载 |
|-------|---------|
| chanlun-theory | 需要理解缠论结果含义时 |
| chanlun-value-research | 做基本面筛选时 |
| chanlun-market-data | 需要手动获取数据时 |
| chanlun-industry-chain | 选择赛道时 |
| chanlun-industry-trend | 判断景气周期时 |
| chanlun-psychology | 复盘/心法时 |
| chanlun-decision | 最终决策时 |

## 已知问题/恢复指南

### chanlun未被加入selected_analysts（常见陷阱）
如果框架跑了但输出中没有`chanlun_report`，检查 `tradingagents/graph/trading_graph.py` 第63行：
```python
selected_analysts=["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup"]  # ❌ 漏了chanlun
```
修复：
```python
selected_analysts=["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup", "chanlun"]  # ✅
```

### 辩论环节没有引用缠论数据
即使`chanlun_report`已经生成，Bull/Bear/风险辩论/裁判可能不引用它。需检查以下4类文件的prompt中是否：
1. 读取了 `state.get("chanlun_report", "")`
2. 在Resources中加入了 `Chanlun Technical Analysis Report: {chanlun_report}`
3. 在A-Share Framework中加入了缠论强制维度（详见 `references/debate-system-prompt-engineering.md` 的缠论章节）

### 修改模式（通用——适用于添加任何新维度）
当需要在框架中添加**新强制辩论维度**时，需要改**7个文件**：
1. `agents/researchers/bull_researcher.py` — 多头引用
2. `agents/researchers/bear_researcher.py` — 空头引用
3. `agents/managers/research_manager.py` — 裁判评判
4. `agents/managers/portfolio_manager.py` — 最终决策
5. `agents/risk_mgmt/aggressive_debator.py` — 激进风险
6. `agents/risk_mgmt/conservative_debator.py` — 保守风险
7. `agents/risk_mgmt/neutral_debator.py` — 中性风险

每个文件的改动模式：
a. 读取state：`new_report = state.get("new_report", "")`
b. 在Resources中加入该报告
c. 在A-Share Framework中插入带 `⭐ MANDATORY` 标签的强制维度说明
