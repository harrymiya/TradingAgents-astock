# A股实时行情API参考

## 腾讯HTTP API (稳定，无认证)

```python
import requests

def get_realtime(code):
    """获取A股实时行情"""
    prefix = 'sh' if code.startswith('6') else 'sz'
    r = requests.get(f'http://qt.gtimg.cn/q={prefix}{code}', timeout=5)
    parts = r.text.split('~')
    # 字段索引（腾讯格式固定）
    return {
        'name':   parts[1],          # 股票名
        'code':   parts[2],          # 6位代码
        'price':  float(parts[3]),   # 现价
        'y_close': float(parts[4]),  # 昨收
        'open':   float(parts[5]),   # 今开
        'volume': int(parts[6]),     # 成交量(手)
        'buy':    float(parts[9]),   # 买一
        'sell':   float(parts[19]),  # 卖一
        'chg_amt': float(parts[31]), # 涨跌额
        'chg_pct': float(parts[32]), # 涨跌幅%
        'high':   float(parts[33]),  # 最高
        'low':    float(parts[34]),  # 最低
        'turnover': float(parts[38]),# 换手率%
        'pe':     float(parts[39]) if parts[39] else 0,   # PE(动)
        'mcap':   float(parts[45]) if parts[45] else 0,   # 总市值(亿)
        'mcap_circ': float(parts[44]) if parts[44] else 0, # 流通市值(亿)
    }
```

**批量查询**(一次最多5个): `http://qt.gtimg.cn/q=sh600519|sz300750|sz000001`

## 东财push2his日K线 (有时断连)

```python
url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
params = {
    'secid': f'0.{code}',       # 0=深市/1=沪市
    'fields1': 'f1,f2,f3,f4,f5,f6',
    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
    'klt': '101',              # 101=日线
    'fqt': '1',                # 1=前复权
    'end': '20500101',
    'lmt': '120',
}
```

**问题**: 频繁请求时 `Connection aborted` / `Remote end closed connection`。此时切换新浪备用。

## 新浪日K线 (备用，倒序返回)

```python
url = f'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=240&ma=no&datalen=120'
r = requests.get(url, timeout=10)
data = r.json()  # ⚠️ 返回的是倒序（最新在前）
records = [{'Date': d['day'], 'Open': float(d['open']), ...} for d in data]
records.reverse()  # 一定要翻转成时间正序
```

**特点**: 稳定，但数据滞后约1-2个交易日（不如东财及时）。

## 代码前缀规则

| 交易所 | 前缀 |
|--------|------|
| 沪市主板/688科创板 | `sh` |
| 深市主板/创业板 | `sz` |
| 北交所 | `bj` |

## 实时行情中的低开高走判断

```python
o, y, p = rt['open'], rt['y_close'], rt['price']
if o < y * 0.98 and p > y:
    low_up = '⬆低开高走翻红'  # 强信号
elif o < y * 0.98 and p > o:
    low_up = '⬆低开修复中'   # 弱信号
```
