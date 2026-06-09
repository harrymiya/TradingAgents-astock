#!/usr/bin/env python3
"""
行业数据同步 - 并行版
每个进程用指定IP，每处理一只重新建连，防止hang死
"""
import sqlite3, os, re, sys, time

DB = '/home/harrydolly/.hermes/astock_data.db'
sys.path.insert(0, '/home/harrydolly/code/TradingAgents-astock')
from mootdx.quotes import Quotes

if len(sys.argv) < 4:
    print("用法: sync_parallel.py <code_start> <code_end> <worker_name> [server_ip] [port]")
    sys.exit(1)

code_start = sys.argv[1]
code_end = sys.argv[2]
wname = sys.argv[3]
server_ip = sys.argv[4] if len(sys.argv) > 4 else None
port = int(sys.argv[5]) if len(sys.argv) > 5 else 7709

def get_industry(code):
    """单次F10调用，每次都新连接"""
    try:
        if server_ip:
            client = Quotes.factory(market='std', tcp=(server_ip, port, True))
        else:
            client = Quotes.factory(market='std')
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
        return l1, l2, l3
    except Exception as e:
        return None, None, None

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

svr_str = f'{server_ip}:{port}' if server_ip else 'auto'
print(f'[{wname}] {total}只需拉 ({code_start}~{code_end}) svr={svr_str}', flush=True)
if not codes:
    print(f'[{wname}] 无需处理', flush=True)
    sys.exit(0)

conn = sqlite3.connect(DB)
conn.execute('PRAGMA synchronous=OFF')
conn.execute('PRAGMA cache_size=-64000')

t0 = time.time()
success = 0

for j, code in enumerate(codes):
    l1, l2, l3 = get_industry(code)
    if l1 or l2 or l3:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO stock_industries (code, industry_l1, industry_l2, industry_l3, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                (code, l1, l2, l3)
            )
            success += 1
        except:
            pass
    
    if (j+1) % 50 == 0 or j+1 == total:
        conn.commit()
        elapsed = time.time() - t0
        rate = (j+1) / max(elapsed, 1)
        remain_s = (total-j-1) / max(rate, 1)
        print(f'[{wname}] {j+1}/{total} 成功{success}只  {elapsed:.0f}s  ETA{remain_s/60:.0f}min  {rate:.2f}只/s', flush=True)

conn.close()
print(f'[{wname}] ✅ 完成! {success}/{total}只 耗时{time.time()-t0:.0f}s', flush=True)
