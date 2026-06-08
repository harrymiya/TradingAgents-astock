---
name: chanlun-market-data
description: A股实时行情、基本面、新闻、资金流等市场数据获取 —— 基于 TradingAgents-Astock 项目的数据层封装
version: 1
tags: [chanlun-framework]
related_skills: [chanlun-framework]
---

# chanlun-market-data

## 用途
获取 A 股实时/历史数据用于分析。当你需要K线、财务数据、新闻、资金流、龙虎榜、板块行情等时，加载此 skill。

## 数据源架构（TradingAgents-Astock 项目）

项目路径：`/home/harrydolly/code/TradingAgents-astock/`

所有数据源免费直连，零 API Key 依赖。

| 来源 | 协议 | 提供内容 |
|------|------|---------|
| **mootdx** | TCP 7709 | OHLCV K线、财务快照、F10 文本 |
| **腾讯财经** | HTTP (qt.gtimg.cn) | PE/PB/市值/换手率（实时） |
| **东方财富** | HTTP | 龙虎榜、限售解禁、板块行情、资金流 |
| **新浪财经** | HTTP | K线历史、财报三表 |
| **同花顺 10jqka** | HTTP | EPS 一致预期、热股题材 |
| **财联社 cls.cn** | HTTP | 全球财经快讯 |
| **百度股市通** | HTTP | 概念板块分类 |

## 可用API函数列表

所有函数在 `tradingagents/dataflows/a_stock.py` 中。

### 1. K线行情
```
get_stock_data(symbol: str, curr_date: str) -> pd.DataFrame
```
返回：OHLCV + 成交量，Date作为索引
参数：symbol = "688017"（6位代码）, curr_date = "2026-06-07"

### 2. 技术指标
```
get_indicators(symbol: str, curr_date: str) -> dict
```
返回：各种技术指标

### 3. 基本面
```
get_fundamentals(symbol: str, curr_date: str) -> dict
```
返回：财务指标、估值指标

```
get_balance_sheet(symbol: str, curr_date: str) -> dict
get_cashflow(symbol: str, curr_date: str) -> dict
get_income_statement(symbol: str, curr_date: str) -> dict
```

### 4. 新闻
```
get_news(symbol: str, curr_date: str, page_size: int = 20) -> list[dict]
get_global_news(curr_date: str) -> list[dict]
```
get_news：个股相关新闻（东财+新浪）
get_global_news：全球财经快讯（财联社）

### 5. 信号层（A股特色）
```
get_profit_forecast(symbol: str, curr_date: str) -> dict
```
EPS一致预期（同花顺）

```
get_hot_stocks(curr_date: str) -> list[dict]
```
热股题材

```
get_northbound_flow(curr_date: str) -> dict
```
北向资金流向（沪股通+深股通）

```
get_concept_blocks(curr_date: str) -> list[dict]
```
概念板块分类

```
get_fund_flow(symbol: str, curr_date: str) -> dict
```
资金流向（主力/超大单/大单/中单/小单）

```
get_dragon_tiger_board(trade_date: str) -> list[dict]
```
龙虎榜

```
get_lockup_expiry(curr_date: str, days_ahead: int = 30) -> list[dict]
```
限售解禁监控

```
get_industry_comparison(symbol: str, curr_date: str) -> dict
```
行业对比

### 6. 工具函数
```
resolve_ticker(user_input: str) -> str
```
中文股票名→6位代码

```
_normalize_ticker(symbol: str) -> str
```
清理代码格式（SH688017→688017）

## 数据使用流程

```python
# 安装依赖
pip install mootdx pandas requests python-dateutil

# 获取数据
from tradingagents.dataflows.a_stock import (
    get_stock_data, get_indicators, get_fundamentals,
    get_news, get_global_news, get_hot_stocks,
    get_northbound_flow, get_concept_blocks, get_fund_flow,
    get_dragon_tiger_board, get_lockup_expiry,
    get_industry_comparison, resolve_ticker
)

# 示例：获取K线
df = get_stock_data("688017", "2026-06-07")
print(df.tail())

# 示例：获取新闻
news = get_news("688017", "2026-06-07")
for n in news[:3]:
    print(f"{n['time']} | {n['title']}")
```

## 美股数据获取（AI链映射参考）

通过新浪财经API获取美股AI龙头日K线：

```
GET https://stock.finance.sina.com.cn/usstock/api/json_v2.php/US_MinKService.getDailyK?symbol={NVDA|AMD|AVGO|MU|SMCI}&type=daily&num=10
```

返回JSON数组，字段：d(日期) o(开盘) h(最高) l(最低) c(收盘) v(成交量)。

用于判断美股→A股的映射联动（详见chanlun-industry-trend skill的"美股→A股映射关系"章节）。

## 注意
- 所有函数的 `symbol` 参数接受 6 位代码或中文名
- `curr_date` 格式为 "YYYY-MM-DD"
- 部分 API 依赖 mootdx 的 TCP 连接（端口 7709），首次调用可能稍慢
- 东财、新浪等 HTTP 接口无需额外配置
- 如果 mootdx/pandas 依赖无法安装，使用 `references/direct-http-api.md` 中的零依赖方案

## 在 TradingAgents 框架内使用
- 所有 dataflow 函数已作为 LangChain Tool 封装在 `tradingagents/agents/utils/` 下
- Analyst Agent 通过 tool calling 自动调用这些函数
- 缠论 Analyst 需要传入 KLine JSON（由 `get_stock_data` 提供）

## 缠论数据获取流程
```python
# 1. 获取 K 线（返回 DataFrame）
df = get_stock_data("688017", "2026-06-05")

# 2. 转为 JSON 传给缠论工具
import json
klines_json = json.dumps([
    {"date": str(row["date"])[:10], "open": row["open"], 
     "high": row["high"], "low": row["low"], 
     "close": row["close"], "volume": row["volume"]}
    for _, row in df.iterrows()
])

# 3. 调用缠论分析
result = get_chanlun_full_report(klines_json)
```

## 美股→A股映射关系（实战关键）
AI链的A股与美股高度联动：美股AI股（NVDA/AMD/AVGO）大跌→A股AI链次日大概率低开。但不同类型标的受影响程度不同：
- **强映射**：光模块（中际旭创↔NVDA）、GPU芯片（海光↔AMD）、存储（澜起↔MU）、封测（长电↔TSM）
- **弱映射**：通信设备（中兴通讯，受AI芯片直接影响小）、应用层（机器人/智驾，更多受国内政策驱动）
- 验证：6/5 美股AI大跌时，A股光模块/存储/封测跌5-8%，但中兴通讯逆势+3.68%

## 参考来源
- 项目：`code/TradingAgents-astock/`
- 核心文件：`tradingagents/dataflows/a_stock.py`（~2000行数据获取逻辑）
- 路由层：`tradingagents/dataflows/interface.py`
