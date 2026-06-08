# Zero-Dependency A-Share HTTP API Reference

When TradingAgents-Astock's pandas/mootdx deps are unavailable, use these direct HTTP endpoints.

## 1. Realtime Quotes (Tencent Finance)

GET https://qt.gtimg.cn/q={code_list}

Multiple codes comma-separated: sz000063,sz301183,sh688017

Response is GBK-encoded pipe-delimited. Key fields by index:

| Index | Field | Type | Example |
|-------|-------|------|---------|
| 1 | name | str | 中兴通讯 |
| 2 | code | str | 000063 |
| 3 | current price | float | 39.13 |
| 4 | prev close | float | 37.74 |
| 5 | today open | float | 37.58 |
| 6 | volume (shares) | int | 4637054 |
| 32 | change pct | float | 3.68 |
| 33 | day high | float | 41.30 |
| 34 | day low | float | 37.05 |
| 37 | turnover (yuan) | float | 1.83e10 |
| 38 | turnover rate | float | 11.51 |
| 39 | PE | float | 41.83 |
| 45 | market cap | float | 1.57e11 |
| 46 | PB | float | 2.44 |

Code prefixes: sz=Shenzhen, sh=Shanghai, bj=Beijing.

## 2. K-Line (Sina Finance)

GET https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={code}&scale={scale}&datalen={count}

Parameters: symbol like sz000063, scale 240=daily 60=60min 30=30min, datalen=bars to return.

Returns JSON array of {day, open, high, low, close, volume}.

## 3. US Stock K-Line (Sina)

GET https://stock.finance.sina.com.cn/usstock/api/json_v2.php/US_MinKService.getDailyK?symbol={ticker}&type=daily&num={days}

Tickers: NVDA, AMD, AVGO, MU, SMCI

Returns raw JSON array with keys d(date), o(open), h(high), l(low), c(close), v(volume).

## 4. Batch Stock Scan

```
python -c "import urllib.request; codes=['sz000063','sz301183','sh688017','sz300308','sz002371']; url='https://qt.gtimg.cn/q='+','.join(codes); raw=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=10).read().decode('gbk')
for line in raw.strip().split('\n'):
    parts=line.split('~')
    if len(parts)>40:
        print(f'{parts[1]:12s} {parts[2]} {parts[3]} {parts[32]}%')"
```

## 5. Sector/Concept Board

East Money push2 (may need specific headers for Python):
- Sector ranking: http://push2.eastmoney.com/api/qt/clist/get?cb=&fid=f3&po=1&pz=20&pn=1&np=1&fs=m:90+t:2&fields=f2,f3,f4,f12,f14
- Concept ranking: same URL with fs=m:90+t:3
