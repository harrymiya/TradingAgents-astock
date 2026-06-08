# 单只股票缠论分析工作流

## 完整流程（从K线获取到报告输出）

```python
from io import StringIO
import pandas as pd
from tradingagents.dataflows.a_stock import get_stock_data
from tradingagents.dataflows.chanlun import analyze_chanlun, klines_from_dataframe

# === Step 1: 获取K线数据 ===
csv_str = get_stock_data("301183", "2026-01-01", "2026-06-05")
# 注意：返回CSV字符串，含#注释头，不是DataFrame!
# 格式样例：
#   # Stock data for 301183 (A-stock) from ...
#   # Total records: 100
#   Date,Open,High,Low,Close,Volume
#   2026-01-05,154.01,159.74,152.31,159.52,6867535

# === Step 2: CSV → DataFrame ===
df = pd.read_csv(StringIO(csv_str), comment='#')
# 列名: Date, Open, High, Low, Close, Volume

# === Step 3: DataFrame → KLine对象列表 ===
klines = klines_from_dataframe(df, date_col="Date",
    ohlc=("Open", "High", "Low", "Close", "Volume"))

# === Step 4: 缠论分析 ===
result = analyze_chanlun(klines, ticker="301183", trade_date="2026-06-05")

# === Step 5: 输出报告 ===
print(result.to_markdown_report())

# === 或直接访问结构化数据 ===
fractals = result.fractals           # List[Fractal] — 所有分型
bi_list = result.bi_list             # List[Bi] — 所有笔
zhongshu = result.zhongshu_list      # List[ZhongShu] — 所有中枢
beichi = result.beichi_signals       # List[BeiChiSignal] — 背驰
maidians = result.buy_sell_points    # List[BuySellPoint] — 买卖点
supports = result.support_levels      # List[float] — 支撑位
resist = result.resistance_levels     # List[float] — 阻力位
trend = result.trend_type            # str — 走势类型
```

## 补充数据

### 基本面（返回 CSV 文本）
```python
from io import StringIO

fund_csv = get_fundamentals("301183", "2026-06-05")
# 解析：直接用文本读取
for line in fund_csv.strip().split('\n'):
    if line.startswith('#'):
        continue
    if ':' in line:
        k, v = line.split(':', 1)
        print(f"{k.strip()}: {v.strip()}")
# 关键字段: Name, Price, PE (TTM), PE (Static), PB,
#           Market Cap, Float Market Cap, Turnover Rate, Change
```

### 关键统计计算
```python
prices = df['Close'].values.astype(float)
print(f"近5日: {' → '.join(f'{p:.2f}' for p in prices[-5:])}")
print(f"近20日区间: {min(prices[-20:]):.2f} ~ {max(prices[-20:]):.2f}")
print(f"近20日涨幅: {(prices[-1]/prices[-20]-1)*100:.2f}%")
print(f"近60日涨幅: {(prices[-1]/prices[-60]-1)*100:.2f}%")
```

## 已不可用的数据接口（在当前环境）
以下接口在无 mootdx/东财直连环境下可能返回 HTML 或报错：
- `get_news()` — 个股新闻（需 end_date 参数，但可能返回同花顺完整HTML页面）
- `get_hot_stocks()` — 热股题材
- `get_industry_comparison()` — 行业对比
- `get_fund_flow()` — 资金流向
- `get_northbound_flow()` — 北向资金
- `get_dragon_tiger_board()` — 龙虎榜

替代方案：用 `web_search` 搜索获取相关信息。

## 数据来源说明
- **K线数据**：新浪HTTP（mootdx fallback），100条记录限制
- **基本面**：腾讯财经（直接HTTP），实时PE/PB/市值/换手率
- **日期范围**：需要同时指定 `start_date` 和 `end_date`
- **股票代码**：6位数字代码（如 301183, 688017, 000063）
