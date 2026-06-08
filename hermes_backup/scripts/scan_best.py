#!/usr/bin/env python3
"""缠论(三买v2)+游资(强势股) 精筛版"""
import sys, sqlite3, numpy as np, pandas as pd
from collections import defaultdict

DB = '/home/harrydolly/.hermes/astock_data.db'
conn = sqlite3.connect(DB)
end = conn.execute('SELECT MAX(date) FROM daily_klines').fetchone()[0]
rows = conn.execute('''
    SELECT d.code, s.name, d.date, d.open, d.high, d.low, d.close, d.volume, d.amount
    FROM daily_klines d LEFT JOIN stocks s ON d.code = s.code
    WHERE d.date>=? AND d.code NOT LIKE "688%" AND d.code NOT LIKE "4%"
    AND d.code NOT LIKE "83%" AND d.code NOT LIKE "87%" AND d.code NOT LIKE "8%"
    AND (s.name IS NULL OR (s.name NOT LIKE "%ST%" AND s.name NOT LIKE "%*ST%"))
    ORDER BY d.code, d.date
''', (f"{pd.Timestamp(end)-pd.Timedelta(days=90):%Y-%m-%d}",))
rows = rows.fetchall()
conn.close()

by_code = defaultdict(list)
for r in rows: by_code[r[0]].append(r)

hits = []
for code, klines in by_code.items():
    try:
        if len(klines) < 25: continue
        name = klines[-1][1] or code
        df = pd.DataFrame(klines, columns=['c','n','Date','O','H','L','C','V','A'])
        c=df['C'].values; h=df['H'].values; l=df['L'].values; v=df['V'].values; n=len(df)
        if c[-1] < 2: continue
        if np.mean(v[-20:])*100 < 800000: continue

        zones = []
        for i in range(max(0,n-60), n-8):
            seg_h = h[i:i+8]; seg_l = l[i:i+8]
            if len(seg_h) < 5: continue
            sg=float(seg_h.max()); sd=float(seg_l.min())
            if sd>0 and (sg-sd)/sd*100<25: zones.append((sg,sd))
        if zones: zg,zd=zones[-1]
        else:
            vola=pd.Series(h-l).rolling(10).std().values
            if len(vola)<=20: continue
            mi=int(np.argmin(vola[-30:]))+n-30
            if mi+10>n: continue
            zg=float(np.max(h[mi:mi+10])); zd=float(np.min(l[mi:mi+10]))

        seg_h20 = h[-20:] if n>=20 else h
        if len(seg_h20)==0: continue
        ri=int(np.argmax(seg_h20))+(n-20 if n>=20 else 0)
        rh=float(h[ri]); cur=float(c[-1])
        if rh<=zg*1.01: continue
        pb=(rh-cur)/rh*100
        if pb<2 or pb>20: continue
        if cur<=zg: continue

        base=float(c[-4]) if n>=4 else float(c[-3])
        seg3 = h[-3:] if n>=3 else [cur]
        mh = float(np.max(seg3)) if len(seg3)>0 else cur
        mc=max((mh-base)/base, (cur-base)/base)*100
        if mc<4: continue
        va=float(np.mean(v[-20:])) if n>=20 else float(np.mean(v))
        vr=float(v[-1])/va if va>0 else 1
        if vr<0.6: continue
        ma20=float(np.mean(c[-20:])) if n>=20 else 0
        if ma20>0 and cur<ma20*0.95: continue

        bad=False
        for j in range(max(2,n-5), n):
            pc=(c[j-1]-c[j-2])/c[j-2]*100 if c[j-2]!=0 else 0
            cc=(c[j]-c[j-1])/c[j-1]*100 if c[j-1]!=0 else 0
            if pc>9 and cc<-5: bad=True; break
        if bad: continue

        chg=(cur-c[-2])/c[-2]*100 if c[-2]!=0 else 0
        hits.append({'code':code,'name':name,'price':cur,'chg':chg,'pb':pb,'vr':vr,'zg':zg})
    except: continue

hits.sort(key=lambda x: abs(x['pb']-10))
print(f'{"="*60}')
print(f'  三买v2 + 强势股 — 精筛版')
print(f'  日期: {end} | 扫描: {len(by_code)}只 | 命中: {len(hits)}只')
print(f'{"="*60}')
print(f'\n{"代码":>6} {"名称":<10} {"价格":>8} {"涨跌":>7} {"回抽":>6} {"量比":>4} {"中枢":>8}')
print(f'{"-"*55}')
for h in hits[:25]:
    ic='💥' if abs(h['chg'])>=9.5 else '🔥' if abs(h['chg'])>=5 else ''
    print(f'{h["code"]:>6} {h["name"]:<10} {h["price"]:>8.2f} {h["chg"]:>+7.2f}%{ic} {h["pb"]:>6.1f}% {h["vr"]:>4.1f}x {h["zg"]:>8.2f}')

print(f'\n{"="*60}')
print(f'  按回抽幅度分类')
print(f'{"="*60}')
early = [h for h in hits if h['pb'] < 5]
mid = [h for h in hits if 5 <= h['pb'] <= 12]
late = [h for h in hits if h['pb'] > 12]
print(f'  🔵 刚突破(<5%): {len(early)}只 — 等缩量回踩后再入场')
for h in early[:5]:
    print(f'    {h["code"]} {h["name"]} {h["price"]:.2f} 回抽{h["pb"]:.1f}%')
print(f'  🟢 最佳介入(5~12%): {len(mid)}只 ⭐')
for h in mid[:10]:
    print(f'    {h["code"]} {h["name"]} {h["price"]:.2f} 回抽{h["pb"]:.1f}% {h["chg"]:+.2f}%')
print(f'  🟡 深回踩(>12%): {len(late)}只 — 低吸，MA20止损')
for h in late[:5]:
    print(f'    {h["code"]} {h["name"]} {h["price"]:.2f} 回抽{h["pb"]:.1f}%')

print(f'\n{"="*60}')
print(f'  你的持仓')
for code, name, cost in [('301231','荣信文化',34.62),('300550','和仁科技',14.63),
                          ('600503','华丽家族',2.82),('603586','金麒麟',17.63)]:
    m=[h for h in hits if h['code']==code]
    if m:
        h=m[0]; pnl=(h['price']-cost)/cost*100
        print(f'  {code} {name}  {h["price"]:.2f}  浮盈{pnl:+.2f}%  ✅')
    else:
        print(f'  {code} {name}  未命中')
