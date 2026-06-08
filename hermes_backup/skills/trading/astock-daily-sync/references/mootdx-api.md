# mootdx API参考 — 通达信TCP数据获取

## 概述

mootdx 是通达信行情的 Python 封装，通过 TCP 协议直连通达信行情服务器，比腾讯 HTTP API 快 3 倍以上（~0.18s/stock vs ~0.5s/stock）。支持 OHLCV K线、财务快照、F10 文本等。

## 安装

```bash
pip install mootdx
```

mootdx 锁死 httpx==0.25.2，与 langchain-google-genai 冲突。在 TradingAgents-Astock 项目已解决（`.venv` 中已安装）。

## 初始化

```python
from mootdx.quotes import Quotes
client = Quotes.factory(market='std')
```

## 核心API

### get_k_data(code, start_date, end_date) — ⭐ 推荐

**一次性拉取指定日期范围的日K线**。内部自动处理分页，返回 pandas DataFrame。

```python
df = client.get_k_data(
    code='000001',          # 6位代码（无需带sh/sz前缀）
    start_date='2023-01-01',
    end_date='2026-06-08'
)
```

**返回格式**（pandas DataFrame）：

| 列名 | 含义 | 备注 |
|:----|:----|:----|
| open | 开盘价 | float |
| close | 收盘价 | float |
| high | 最高价 | float |
| low | 最低价 | float |
| vol | 成交量 | 股数（不是手！） |
| amount | 成交额 | float |
| date | 交易日期 | datetime64 或 str |
| code | 股票代码 | str |

**特点**：
- 数据范围可以是任何时间段，不限800天
- 内部用 `bars()` 自动分页合并
- 返回827行（近3.5年）仅需 ~0.18s
- 失败时返回空DataFrame或None

### bars(symbol, frequency, start, offset) — 低层接口

```python
bars_data = client.bars(
    symbol='000001',    # 6位代码
    frequency=9,        # 9=日线，1=1分钟，5=5分钟
    start=0,            # 起始偏移
    offset=800          # 最大返回条数（上限800）
)
```

返回 list of tuples。单次最大800条，超出的需分页。

### quotes(symbols) — 实时行情

```python
quotes = client.quotes(symbols=['000001', '000002'])
```

### stocks() — 全市场股票列表

```python
all_stocks = client.stocks()  # 返回全部代码
```

### get_k_data 与 bars 的对比

| 特性 | get_k_data | bars |
|:----|:----------|:----|
| 参数 | start_date/end_date (日期字符串) | start/offset (整数偏移) |
| 单次上限 | 无限制（自动分页） | 800条 |
| 返回类型 | pandas DataFrame | list[tuple] |
| 列名 | open/close/high/low/vol/amount/date/code | 序号索引 |
| 时间范围 | 任意 | 从latest_date往前数800条 |
| 速度 | 0.18s/827行 | 0.05s/800行 |
| 推荐度 | ⭐⭐⭐（高级） | ⭐（低级） |

## 市场兼容性

```python
client = Quotes.factory(market='std')
```

| 市场 | 代码前缀 | get_k_data | 备注 |
|:----|:--------|:----------:|:----|
| 深市主板 | 000/001/002 | ✅ | 全量支持 |
| 创业板 | 300/301 | ✅ | 全量支持 |
| 沪市主板 | 600/601/603/605 | ✅ | 全量支持 |
| 科创板 | 688 | ✅ | **std市场可用** |
| 北交所 | 4/8/920 | ❌ | `'datetime'` 错误 |

**关键发现**：科创板（688）可以用 `market='std'` 的客户端获取数据，无需单独用 kcb 市场。

## 逐只历史同步模式（sync_history_all.py）

```python
from mootdx.quotes import Quotes
client = Quotes.factory(market='std')

for code, name in stocks:
    # 检查是否已有完整数据
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM daily_klines WHERE code=?", (code,))
    cnt, mn, mx = cur.fetchone()
    conn.close()
    
    if cnt >= 600 and mn and mn <= '2023-01-01':
        continue  # 已有完整历史，跳过
    
    try:
        df = client.get_k_data(code=code, start_date='2023-01-01', end_date='2026-06-08')
        if df is not None and len(df) > 0:
            records = []
            for idx in range(len(df)):
                row = df.iloc[idx]
                records.append((
                    code,
                    str(row['date']),
                    float(row['open']),
                    float(row['high']),
                    float(row['low']),
                    float(row['close']),
                    float(row['vol']),
                    float(row['amount'])
                ))
            # INSERT OR REPLACE
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.executemany(
                "INSERT OR REPLACE INTO daily_klines (code, date, open, high, low, close, volume, amount) VALUES (?,?,?,?,?,?,?,?)",
                records
            )
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"FAIL: {code} {name}: {e}")
    
    time.sleep(0.01)
```

**性能**：
- ~0.18s/stock，~1 stock/sec 稳定
- 全市场5178只正常股（排除ST) ≈ 86分钟
- ~800行/stock，全市场约400万行

## 常见异常

### 1. `'datetime'` 错误
- 原因：mootdx 无法解析该股票的日期字段
- 常见于：北交所（920开头）和部分退市股
- 解决：try/except 捕获，标记为空记录后跳过

### 2. 连接断开
- mootdx TCP 连接在长时间无操作后可能断开
- 解决方案：抛出异常后重新 `Quotes.factory(market='std')`
- `sync_close.py` 已内置自动重连（遍历6个备用服务器）

### 3. SQLite写锁冲突
- 不要同时运行多个写入mootdx的进程
- `INSERT OR REPLACE` 是安全的，但并发的 execute 会锁

## sync_history_all.py 脚本

位置：`/home/harrydolly/code/TradingAgents-astock/sync_history_all.py`

**首次全量同步**（用mootdx拉取2023-01-01至今的所有数据）：

```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
python3 sync_history_all.py                                     # 全市场
python3 sync_history_all.py --code 000001                       # 单只
python3 sync_history_all.py --check                             # 检查覆盖
python3 sync_history_all.py --skip 100 --max 400                # 某批次
```

**脚本策略**：
- 排除 ST/*ST/退市股（名字包含ST或退的）
- 对已有 >600天 且 最早日期 <= 2023-01-01 的股票自动跳过（断点续传）
- 无数据的股票写 '1970-01-01' 空标记，防止反复重试
- 进度日志写到 `~/.hermes/sync_history.log`

**后台运行监控**：

```bash
# 启动
python3 sync_history_all.py &

# 监控
tail -f ~/.hermes/sync_history.log

# 看日志最后N行
tail -5 ~/.hermes/sync_history.log
```

## DB字段索引映射（重要坑）

`cursor.fetchall()` 返回 `daily_klines` 表的元组，**字段顺序由SQL决定**：

```sql
-- 表定义
CREATE TABLE daily_klines (
    code TEXT, date TEXT, open REAL, high REAL, 
    low REAL, close REAL, volume REAL, amount REAL
);

-- 写入时 INSERT 顺序就是字段顺序
INSERT INTO daily_klines (code, date, open, high, low, close, volume, amount)
VALUES (?,?,?,?,?,?,?,?)
```

所以 `fetchall()` 返回的每一行：
```
r[0] = code
r[1] = name (如果join了stocks表)
r[2] = date
r[3] = open
r[4] = high
r[5] = low
r[6] = close    <-- 注意索引！
r[7] = volume   <-- 不是close！
r[8] = amount
```

**常见坑**：直觉上以为 close 在第7位（索引7），但实际上 `close` 在 `r[6]`、`volume` 在 `r[7]`。用错会导致：
- 把成交量当价格 → 收益率异常（几亿%）
- 市场判断完全错误（用成交量而非收盘价计算涨跌幅）
