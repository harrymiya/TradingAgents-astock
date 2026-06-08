# 东财push2his API — 离线K线数据获取

当股票不在SQLite数据库（如688科创板/新股/数据未同步）时使用。

## 日K线

```python
import requests

url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
params = {
    "secid": "1.{code}",     # 沪: 1.{code}  深: 0.{code}
    "fields1": "f1,f2,f3,f4,f5,f6",
    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    "klt": "101",            # 101=日K   102=周K  103=月K
    "fqt": "1",              # 1=前复权  0=不复权  2=后复权
    "end": "20500101",
    "lmt": "120",            # 最多120条
}

r = requests.get(url, params=params, timeout=15)
data = r.json()
klines = data["data"]["klines"]
# 每行格式: 日期,开盘,收盘,最高,最低,成交量(手),成交额,振幅%,涨跌幅%,涨跌额,换手率%
for k in klines:
    parts = k.split(",")
    date, open_, close_, high, low, vol_hand, amount = parts[0:7]
```

## 实时行情

```python
url = "http://qt.gtimg.cn/q=sh{code}"  # sh=沪市  sz=深市
r = requests.get(url, timeout=10)
# 返回格式: v_sh{code}="1~名称~代码~现价~昨收~开盘~成交量~..."
# 用 regex 解析: re.search(r'~([\d.]+)~([\d.]+)~([\d.]+)~(\d+)', text)
```

## 数据结构转换

东财成交量单位是"手"（1手=100股），转DataFrame时乘以100：

```python
import pandas as pd
records = []
for k in klines:
    p = k.split(',')
    records.append({
        'Date': p[0],
        'Open': float(p[1]),
        'Close': float(p[2]),
        'High': float(p[3]),
        'Low': float(p[4]),
        'Volume': float(p[5]) * 100,  # 手→股
        'Amount': float(p[6]),
    })
df = pd.DataFrame(records)
```

## 注意事项
- 东财push2his可能返回**倒序**数据（最新在前），需检查 `df.iloc[0]["Date"]` 与 `df.iloc[-1]["Date"]`，必要时 `records.reverse()`
- 新浪API也会返回倒序（最新在前）——跟东财不同，新浪需要反转
- 新浪日K线单位与东财不同：`scale=240` 是日线，`datalen` 最多120
