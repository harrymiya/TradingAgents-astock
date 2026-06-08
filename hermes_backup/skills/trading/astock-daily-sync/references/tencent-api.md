# 腾讯HTTP API参考

## 1. 日K线（前复权）

**Endpoint:** `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get`

**参数:**
```
param={prefix}{code},day,,,800,qfq
  prefix: sh(沪)/sz(深)
  code: 6位股票代码
  day: 日线
  800: 最多返回800条
  qfq: 前复权
```

**请求示例:**
```python
import urllib.request, json
url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz301231,day,,,800,qfq"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read().decode('utf-8'))
days = data["data"]["sz301231"]["qfqday"]  # list of [date, open, close, high, low, volume]
```

**返回格式:**
```json
{
  "code": 0,
  "data": {
    "sz301231": {
      "qfqday": [
        ["2023-02-16", "11.832", "11.752", "12.062", "11.652", "1279123.000"],
        ...
      ]
    }
  }
}
```

**列顺序:** `[date, open, close, high, low, volume]`
- ⚠️注意：close在第2列，high在第3列，与常见格式相反

**特点:**
- 无频率限制，可全市场批量拉取
- 前复权价格
- 不含成交额（Amount），需用 `volume*100*(open+close)/2` 估算

## 2. 分时数据（盘中实时）⚠️ 已失效

**腾讯分钟K线接口已失效**（2026-06-08 确认）：
- `web.ifzq.gtimg.cn/appstock/app/kline/mkline` → 302重定向到 `web3.ifzq.gtimg.cn` 域名无法解析
- `web.ifzq.gtimg.cn/appstock/app/minute/query` → 返回 `Can't load controller: AppController`

**替代方案：使用 `qt.gtimg.cn` 实时行情接口**（见下面第2节），可以获取：
- 当前价、昨收、今开、最高、最低
- 成交量（手）、成交额
- 换手率%、振幅%、PE(TTM)
- 涨跌额、涨跌幅%

盘中分析不依赖分时明细（分钟级粒度），实时行情数据已足够做盘中位置判断。

## 3. 实时行情（盘中首选）⭐

**Endpoint:** `http://qt.gtimg.cn/q={prefix}{code}`

**参数:**
```
prefix: sh(沪)/sz(深)  — 注意上海用sh，深圳用sz
code: 6位股票代码
```

**请求示例:**
```python
import requests
url = f"http://qt.gtimg.cn/q=sz301231"
r = requests.get(url, timeout=10)
# 返回: v_sz301231="51~荣信文化~301231~35.06~33.81~32.66~122024~...~..."
parts = r.text.split("~")
```

**字段索引（0-based，从分割后数组）:**
| 索引 | 含义 | 示例 |
|:---:|:----|:----|
| 1 | 股票名 | 荣信文化 |
| 3 | **当前价** | 35.06 |
| 4 | 昨收 | 33.81 |
| 5 | 今开 | 32.66 |
| 6 | **成交量(手)** | 122024 |
| 31 | 涨跌额 | 1.25 |
| 32 | **涨跌幅%** | 3.70 |
| 33 | **最高** | 35.98 |
| 34 | **最低** | 32.66 |
| 37 | 成交额 | 422345678 |
| 38 | **换手率%** | 18.71 |
| 39 | PE(TTM) | -97.6 |
| 43 | **振幅%** | 9.82 |

**特点：**
- 极快，单次HTTP请求 <200ms
- 无频率限制
- 盘中实时更新
- 可用 `r.text.split("~")` 解析

## 4. 盘中分析数据获取

使用 `live_data.py` 统一接入：

```python
from tradingagents.dataflows.live_data import get_data_for_analysis, format_analysis_text

# DB历史日线 + 腾讯当天实时行情（盘中推荐）
data = get_data_for_analysis("301231", "荣信文化")
# data['daily_klines'] — 合并后日线列表 [{date, open, high, low, close, volume, amount}]
# data['today_info'] — 盘中实时行情
#     {price, open, high, low, volume, pre_close, change, change_pct,
#      amount, turnover(%), pe, amplitude(%)}
# data['today_kline'] — 今天日K线（如果日线API有）
# data['minute_data'] — 分时（可能为None）

print(format_analysis_text(data))
# 输出格式化的分析文本
```

## ⚠️ 解析陷阱（2026-06-08 发现）

腾讯日线API的JSON结构复杂的嵌套方式容易让人犯错。正确的解析路径：

### 标准结构
```json
{
  "code": 0,           // 成功
  "msg": "",
  "data": {
    "sz301231": {       // 键是完整代码（带前缀），不是裸代码！
      "qfqday": [       // 可能是qfqday或day
        ["2026-06-08", "32.66", "34.92", "35.98", "32.66", "123805"]
        //  [date,      open,   close,  high,   low,    volume]
      ],
      "qt": {...},       // 附加信息，忽略
      "mx_price": ...,
      "prec": ...,
      "version": ...
    }
  }
}
```

### 正确的解析Python代码
```python
import requests
code = "301231"
prefix = "sz" if code.startswith(("0", "3")) else "sh"
full_code = f"{prefix}{code}"  # "sz301231"

url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full_code},day,,,800,qfq"
r = requests.get(url, timeout=10)
data = r.json()

# 路径: data → data["data"] → data["data"][full_code] → ["qfqday"]
inner = data.get("data") or data
stock_data = inner.get(full_code) if isinstance(inner, dict) else inner

# 查找日线数组（qfqday或day）
days = None
for k in ("qfqday", "day", "klines"):
    if k in stock_data:
        days = stock_data[k]
        break

# 解析
klines = []
for item in days:
    klines.append({
        "date": str(item[0]),
        "open": float(item[1]),   # 注意第1列是open
        "close": float(item[2]),  # 第2列是close
        "high": float(item[3]),   # 第3列是high
        "low": float(item[4]),    # 第4列是low
        "volume": float(item[5]), # 第5列是volume
        "amount": float(item[6]) if len(item) > 6 and item[6] else 0,
    })
```

### 常见坑
1. ❌ 用 `code` 作为key（即 `"301231"`）取——应该用 `full_code`（即 `"sz301231"`）
2. ❌ 检查 `"qt" not in stock_data`——`stock_data` 字典总是包含 `qt` 键
3. ❌ sleep不够——全量4371只时每50只后sleep(0.5s)
4. ⚠️ `requests.get` 偶发超时——加 `timeout=5` 并用 `try/except` 兜底

### live_data.py 中的修复版 fetch_tencent_kline
见 `/home/harrydolly/code/TradingAgents-astock/tradingagents/dataflows/live_data.py` 第21行。

| 特性 | 腾讯API | 新浪API |
|------|:------:|:-------:|
| 频率限制 | 无 | HTTP 456限流 |
| 股票列表 | 无独立接口，从DB读 | `StockService` 已失效 |
| 日线天数 | 800天 | 800条 |
| 复权 | 前复权 | 未复权 |
| 分时数据 | ✅ 支持 | 不支持 |
| 成交额 | ❌ 需估算 | ❌ 需估算 |
| 稳定性 | ✅ 稳定 | ❌ 返回`Service not valid` |
