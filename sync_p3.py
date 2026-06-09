#!/usr/bin/env python3
"""Part 3/5: 1760~2640, 连180.153.18.170:7709"""
import sqlite3, os, re, sys
sys.path.insert(0, '/home/harrydolly/code/TradingAgents-astock')
from mootdx.quotes import Quotes
DB = '/home/harrydolly/.hermes/astock_data.db'
conn = sqlite3.connect(DB)
rows = conn.execute("SELECT DISTINCT code FROM daily_klines WHERE code NOT LIKE '688%' AND code NOT LIKE '4%' AND code NOT LIKE '83%' AND code NOT LIKE '87%' ORDER BY code").fetchall()
conn.close()
codes = [r[0] for r in rows]
part = codes[1760:2640]
print(f'part3: {len(part)}只, {part[0]}~{part[-1]}', flush=True)
client = Quotes.factory(market='std', tcp=('180.153.18.170', 7709, True))
print('conn OK', flush=True)
conn = sqlite3.connect(DB)
for j, code in enumerate(part):
    try:
        f10 = client.F10(code, 'industry_analysis')
        hys = f10.get('行业分析', '')
        if isinstance(hys, str):
            m = re.search(r'所属研究行业[：]?\s*([^(\r\n]+)', hys)
            ind = m.group(1).strip() if m else None
            if not ind:
                m = re.search(r'所属行业[：]?\s*([^(\r\n]+)', hys)
                ind = m.group(1).strip() if m else None
            if ind:
                conn.execute("INSERT OR REPLACE INTO stock_industries (code, industry_l1, industry_l2, industry_l3, updated_at) VALUES (?, ?, ?, ?, datetime('now'))", (code, ind, ind, ind))
    except:
        try: client = Quotes.factory(market='std', tcp=('180.153.18.170', 7709, True))
        except: pass
    if (j+1) % 50 == 0 or j+1 == len(part):
        conn.commit()
        print(f'[part3] {j+1}/{len(part)}', flush=True)
conn.close()
print(f'[part3] done!', flush=True)
