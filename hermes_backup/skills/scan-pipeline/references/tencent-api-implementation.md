# scan_pipeline.py 关键实现参考

## 三阴选股（腾讯API版）

文件：`/home/harrydolly/code/TradingAgents-astock/scan_pipeline.py`

### 腾讯API获取日线

```python
_TENCENT_CACHE = {}

def get_tencent_kline(code, days=30):
    if code in _TENCENT_CACHE:
        return _TENCENT_CACHE[code]
    mkt = 'sz' if code.startswith('3') or code.startswith('0') else 'sh'
    try:
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={mkt}{code},day,,,{days},qfq"
        resp = urllib.request.urlopen(url, timeout=8)
        data = json.loads(resp.read().decode('utf-8'))
        raw = data['data'][f'{mkt}{code}']['qfqday']
        by_date = {}
        for d in raw:
            by_date[d[0]] = {'O': float(d[1]), 'C': float(d[2]),
                             'H': float(d[3]), 'L': float(d[4])}
        _TENCENT_CACHE[code] = by_date
        return by_date
    except:
        return None
```

### 三阴核心判断

```python
def stage1_three_crows(df, target_date):
    candidates = []
    for _, row in df.iterrows():
        code = row['code']
        klines = get_tencent_kline(code)
        if not klines:
            continue
        required = ['2026-06-03','2026-06-04','2026-06-05','2026-06-08','2026-06-09']
        if any(d not in klines for d in required):
            continue
        t3 = klines['2026-06-04']
        t = klines['2026-06-09']
        t1 = klines['2026-06-08']
        t4 = klines['2026-06-03']

        if not (round(t4['C']*1.1, 2) - t3['C'] < 0.01):
            continue
        if not (t['C'] > t3['O']):
            continue
        if not (t['O'] > t3['L']):
            continue
        if not (t['C'] < t1['C']):
            continue
        candidates.append({
            'code': code, 'name': row['name'],
            'price': t['C'], 'chg': (t['C']-t1['C'])/t1['C']*100,
            'strategy': '三阴',
            'detail': '涨停启动→缩量回调3天→今日企稳收跌'
        })
    return candidates
```

### S3超跌反弹

```python
def stage1_s3(df, target_date):
    subset = df[
        (df['pos_20d'] < 20) &
        (df['chg'] >= 3) & (df['chg'] < 7) &
        (df['vr_5'] >= 1.2) & (df['vr_5'] < 2.5) &
        (df['ma20_pct'] < -8)
    ]
    # ... 构建并返回
```

### 三买v2（收紧版）

关键参数（2026-06-09生效）：
- 中枢振幅：<15%（原25%）
- 突破阈值：>ZG*1.03（原1.01）
- 回抽幅度：5-15%（原2-20%）
- 量比底线：vr_5 > 0.6（新增）
- MA20过滤：close > ma20（新增）

### 6维度评分

```python
def stage2_score(candidates, df, target_date):
    # 每维0-10分，总分60
    scores = {}
    # 趋势位置
    scores['趋势位置'] = min(10, ts)  # MA排列+位置+偏离
    scores['量能健康'] = min(10, vs)  # vr5+vr20+成交量
    scores['波动筹码'] = min(10, vs2) # 振幅+位置广度
    scores['策略置信'] = min(10, sc)  # 多策略共振+权重
    scores['短期动量'] = min(10, ms)  # ret1+ret3+chg
    scores['安全边际'] = min(10, ss)  # MA偏离+回抽区间
    return scored[:10]  # Top 10
```
