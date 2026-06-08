# TradingAgents-Astock API Pitfalls & Verified Behaviour

## `get_stock_data(symbol, start_date, end_date)`

**Signature**: `get_stock_data(symbol: str, start_date: str, end_date: str) -> str`

**Return type**: CSV string (NOT a pandas DataFrame, NOT JSON)
- Header line: `Date,Open,High,Low,Close,Volume`
- Preceded by `#` comments (source, record count, timestamp)
- Must parse with: `pd.read_csv(StringIO(csv_str), comment='#')`
- The `.index` is NOT set — use `Date` column directly

**Parameters**: requires BOTH `start_date` and `end_date` (not just one date).

**Fallback behaviour**: If mootdx is not installed or fails, auto-falls back to Sina HTTP (returns ~100 rows).

**Verified working** (2026-06-07):
- `get_stock_data("000063", "2026-01-01", "2026-06-05")` → 100 rows via Sina
- `get_stock_data("301183", "2026-01-01", "2026-06-05")` → 100 rows via Sina
- After mootdx bestip: `get_stock_data("000063", ...)` → 99 rows via mootdx

## `get_fundamentals(symbol, trade_date)`

**Signature**: `get_fundamentals(symbol: str, trade_date: str) -> str`

**Return type**: CSV string with fields:
```
Name, Price, PE (TTM), PE (Static), PB, Market Cap, Float Market Cap, Turnover Rate, Change, Limit Up, Limit Down
```

Must be parsed from raw text (simple line-by-line is easier than CSV since it has header comments).

**Verified example**:
```
Name: 中兴通讯
Price: 39.13
PE (TTM): 41.83
PE (Static): 35.71
PB: 2.44
Market Cap (100M CNY): 1576.01
Turnover Rate: 11.51%
Change: 3.68%
```

## `get_news(symbol, start_date, end_date)`

**Signature**: `get_news(symbol: str, start_date: str, end_date: str) -> list[dict]`

⚠️ **May return HTML** (同花顺 sell-side page) instead of parsed news items in non-mootdx environments. Fallback to `web_search` for news data.

## `get_hot_stocks(trade_date)`

⚠️ **Returns raw HTML** in most environments. Not reliable without full dependency chain.

## `get_industry_comparison(symbol, trade_date)`

⚠️ **May return empty or error**. Not reliable outside full mootdx environment.

## `get_fund_flow(symbol, trade_date)`

⚠️ **May return connection errors**. East Money push2 API has intermittent connectivity.

## `get_global_news(curr_date)`

Not tested. 财联社 source may have anti-scraping measures.

## Chanlun Module

### Entry Point

The correct function name is **`analyze_chanlun()`**, NOT `get_chanlun_full_report()`.

```python
from tradingagents.dataflows.chanlun import analyze_chanlun, klines_from_dataframe
```

Returns a `ChanLunResult` dataclass with:
- `to_markdown_report()` → printable string
- `.bi_list`, `.zhongshu_list`, `.beichi_signals`, `.buy_sell_points`
- `.support_levels`, `.resistance_levels`
- `.trend_type`, `.current_level`
- `.fractals` (List[Fractal], NOT dict — access via `.type == 'top'` filter)

### klines_from_dataframe

```python
klines = klines_from_dataframe(df, date_col="Date",
    ohlc=("Open", "High", "Low", "Close", "Volume"))
```

The DataFrame must have the date as a column (not index), even though `get_stock_data` returns the Date as a column.

### Chanlun Tool Functions (LangChain @tool)

Located in `tradingagents/agents/utils/chanlun_tools.py`:
- `get_chanlun_bi(klines_json: str) -> str`
- `get_chanlun_zhongshu(klines_json: str) -> str`
- `get_chanlun_beichi(klines_json: str) -> str`
- `get_chanlun_full_report(klines_json: str) -> str`

All take a JSON string of KLine dicts (NOT CSV), return formatted text.

## mootdx Setup

```bash
pip install mootdx -i https://pypi.tuna.tsinghua.edu.cn/simple
python -m mootdx bestip  # REQUIRED before first use — selects fastest server
```

If mootdx is not installed, all mootdx-dependent functions silently fall back to HTTP (Sina/EastMoney).
