#!/usr/bin/env python3
"""
行业数据同步 - 单线程单服务器版本
带详细调试输出
"""
import sqlite3, os, re, sys, time
sys.path.insert(0, '/home/harrydolly/code/TradingAgents-astock')
from mootdx.quotes import Quotes

host = sys.argv[1]
port = int(sys.argv[2])
code_start = sys.argv[3]
code_end = sys.argv[4]
wname = sys.argv[5]
DB = '/home/harrydolly/.hermes/astock_data.db'

print(f'[{wname}] step1: 查询数据库需要同步的股票...', flush=True)
conn = sqlite3.connect(DB)
rows = conn.execute(
    "SELECT DISTINCT f.code FROM feat f "
    "WHERE f.code >= ? AND f.code <= ? "
    "AND f.code NOT LIKE '688%' "
    "AND f.code NOT LIKE '4%' "
    "AND f.code NOT LIKE '83%' AND f.code NOT LIKE '87%' "
    "AND f.code NOT IN (SELECT code FROM stock_industries) "
    "ORDER BY f.code",
    (code_start, code_end)
).fetchall()
conn.close()

codes = [r[0] for r in rows]
print(f'[{wname}] 需拉{len(codes)}只 ({code_start}~{code_end})', flush=True)
if not codes:
    print(f'[{wname}] 无需处理', flush=True)
    sys.exit(0)

print(f'[{wname}] step2: 建立mootdx连接 {host}:{port}...', flush=True)
try:
    client = Quotes.factory(market='std', tcp=(host, port, True))
    print(f'[{wname}] 连接成功', flush=True)
except Exception as e:
    print(f'[{wname}] 连接失败: {e}', flush=True)
    sys.exit(1)

print(f'[{wname}] step3: 连接数据库...', flush=True)
conn = sqlite3.connect(DB)
conn.execute('PRAGMA synchronous=OFF')
conn.execute('PRAGMA cache_size=-64000')
print(f'[{wname}] DB连接成功', flush=True)

t0 = time.time()
success = 0

for j, code in enumerate(codes):
    try:
        f10 = client.F10(code, 'industry_analysis')
        hys = f10.get('行业分析', '') if isinstance(f10, dict) else str(f10)
        l1 = l2 = l3 = None
        if isinstance(hys, str):
            for line in hys.split('\n'):
                m = re.search(r'所属研究行业[：:]\s*([^\r\n(]+)', line)
                if m:
                    parts = re.split(r'[/\uFF0F]', m.group(1).strip())
                    parts = [p.strip().lstrip(':') for p in parts if p.strip()]
                    if len(parts) >= 1: l1 = parts[0]
                    if len(parts) >= 2: l2 = parts[1]
                    if len(parts) >= 3: l3 = parts[2]
                    break
                m2 = re.search(r'所属行业[：:]\s*([^\r\n(]+)', line)
                if m2:
                    parts = re.split(r'[/\uFF0F]', m2.group(1).strip())
                    parts = [p.strip().lstrip(':') for p in parts if p.strip()]
                    if len(parts) >= 1: l1 = parts[0]
                    break
        if l1 or l2 or l3:
            conn.execute(
                "INSERT OR REPLACE INTO stock_industries (code, industry_l1, industry_l2, industry_l3, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                (code, l1, l2, l3)
            )
            success += 1
    except Exception as e:
        pass

    if (j+1) % 100 == 0 or j+1 == len(codes):
        conn.commit()
        elapsed = time.time() - t0
        rate = (j+1) / max(elapsed, 1)
        remain_s = (len(codes)-j-1) / max(rate, 1)
        print(f'[{wname}] {j+1}/{len(codes)} 成功{success}只  {elapsed:.0f}s  ETA{remain_s/60:.0f}min  {rate:.1f}只/s', flush=True)

conn.close()
print(f'[{wname}] ✅ 完成! {success}/{len(codes)}只 耗时{time.time()-t0:.0f}s', flush=True)
