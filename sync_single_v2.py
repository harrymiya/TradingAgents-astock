#!/usr/bin/env python3
"""
行业数据同步 - 单线程单服务器版（带F10超时保护）
每次F10如果超过15秒，自动重连后重试
"""
import sqlite3, os, re, sys, time, signal

host = sys.argv[1]
port = int(sys.argv[2])
code_start = sys.argv[3]
code_end = sys.argv[4]
wname = sys.argv[5]
DB = '/home/harrydolly/.hermes/astock_data.db'

sys.path.insert(0, '/home/harrydolly/code/TradingAgents-astock')
from mootdx.quotes import Quotes

# F10超时处理：使用signal.alarm（仅主线程有效，但对纯Python调用有效）
TIMEOUT = 15  # 每次F10最多等15秒

def get_f10_with_timeout(client, code):
    """带超时的F10调用"""
    result = [None, None]  # [data, error]
    finished = [False]
    
    def handler(signum, frame):
        raise TimeoutError(f"F10({code}) timeout after {TIMEOUT}s")
    
    old_handler = signal.signal(signal.SIGALRM, handler)
    signal.alarm(TIMEOUT)
    try:
        f10 = client.F10(code, 'industry_analysis')
        hys = f10.get('行业分析', '') if isinstance(f10, dict) else str(f10)
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        return hys
    except TimeoutError as e:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        raise e
    except Exception as e:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        raise e

# 获取需要处理的股票
print(f'[{wname}] 查询股票...', flush=True)
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

# 建立mootdx连接（默认自动选最快服务器）
print(f'[{wname}] 连接服务器...', flush=True)
try:
    client = Quotes.factory(market='std')
    print(f'[{wname}] 连接成功', flush=True)
except Exception as e:
    print(f'[{wname}] 连接失败: {e}', flush=True)
    sys.exit(1)

conn = sqlite3.connect(DB)
conn.execute('PRAGMA synchronous=OFF')
conn.execute('PRAGMA cache_size=-64000')

t0 = time.time()
success = 0
reconnects = 0

for j, code in enumerate(codes):
    retries = 3
    ok = False
    while retries > 0 and not ok:
        try:
            hys = get_f10_with_timeout(client, code)
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
            ok = True
        except (TimeoutError, Exception) as e:
            retries -= 1
            if retries <= 0:
                break
            # 重连
            try:
                client = Quotes.factory(market='std', tcp=(host, port, True))
                reconnects += 1
            except:
                time.sleep(2)
    
    if (j+1) % 100 == 0 or j+1 == len(codes):
        conn.commit()
        elapsed = time.time() - t0
        rate = (j+1) / max(elapsed, 1)
        remain_s = (len(codes)-j-1) / max(rate, 1)
        per_stock = elapsed / (j+1)
        print(f'[{wname}] {j+1}/{len(codes)} 成功{success}只  {elapsed:.0f}s  ETA{remain_s/60:.0f}min  {rate:.2f}只/s  {per_stock:.1f}s/只  rcx{reconnects}', flush=True)

# 最终commit
conn.commit()
conn.close()
elapsed = time.time()-t0
print(f'[{wname}] ✅ 完成! 成功{success}/{len(codes)}只 耗时{elapsed:.0f}s 重连{reconnects}次', flush=True)
