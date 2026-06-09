#!/usr/bin/env python3
"""
行业数据同步 - 单连接版
每个进程建一次mootdx连接，循环使用
"""
import sqlite3, os, re, sys, time, traceback

DB = '/home/harrydolly/.hermes/astock_data.db'
sys.path.insert(0, '/home/harrydolly/code/TradingAgents-astock')
from mootdx.quotes import Quotes

if len(sys.argv) < 4:
    print("用法: sync_simple.py <code_start> <code_end> <worker_name> [server_ip] [port]")
    sys.exit(1)

code_start = sys.argv[1]
code_end = sys.argv[2]
wname = sys.argv[3]
svr_ip = sys.argv[4] if len(sys.argv) > 4 else None
svr_port = int(sys.argv[5]) if len(sys.argv) > 5 else 7709

# 建连接（只建一次）
try:
    if svr_ip:
        args = (svr_ip, svr_port, True)
        client = Quotes.factory(market='std', tcp=args)
        svr_str = f'{svr_ip}:{svr_port}'
    else:
        client = Quotes.factory(market='std')
        svr_str = 'auto'
except Exception as e:
    print(f'[{wname}] 连接失败: {e}', flush=True)
    sys.exit(1)

print(f'[{wname}] 连接OK svr={svr_str}', flush=True)

# 查询需要处理的股票
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
codes = [r[0] for r in rows]
total = len(codes)
conn.close()

print(f'[{wname}] {total}只需拉 ({code_start}~{code_end})', flush=True)
if not codes:
    print(f'[{wname}] 无需处理', flush=True)
    sys.exit(0)

conn = sqlite3.connect(DB)
conn.execute('PRAGMA synchronous=OFF')
conn.execute('PRAGMA cache_size=-64000')

t0 = time.time()
success = 0
fail = 0

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
        else:
            fail += 1
    except Exception as e:
        fail += 1
        # 如果连续3只失败，重建连接
        if fail % 3 == 0:
            try:
                if svr_ip:
                    client = Quotes.factory(market='std', tcp=(svr_ip, svr_port, True))
                else:
                    client = Quotes.factory(market='std')
            except:
                pass
    
    if (j+1) % 50 == 0 or j+1 == total:
        conn.commit()
        elapsed = time.time() - t0
        rate = (j+1) / max(elapsed, 1)
        remain_s = (total-j-1) / max(rate, 1)
        print(f'[{wname}] {j+1}/{total} 成功{success} 失败{fail}  {elapsed:.0f}s  ETA{remain_s/60:.0f}min  {rate:.2f}只/s', flush=True)

conn.close()
print(f'[{wname}] ✅ 完成! 成功{success}/{total}只 失败{fail} 总耗时{time.time()-t0:.0f}s', flush=True)
