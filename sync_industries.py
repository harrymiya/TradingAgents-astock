#!/usr/bin/env python3
"""
sync_industries.py — 全市场行业分类同步脚本（多连接IP池版）

用5个通达信服务器IP同时拉取，每个IP独立TCP连接，不抢带宽。
4367只约40-50分钟跑完。

用法:
  python3 sync_industries.py                          # 拉取缺失的
  python3 sync_industries.py --all                    # 全量覆盖
  python3 sync_industries.py --codes 000063,600519    # 指定股票
  
cron: 每月1日08:00 全量更新
"""
import sqlite3, os, re, time, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

DB = os.path.expanduser("~/.hermes/astock_data.db")

sys.path.insert(0, '/home/harrydolly/code/TradingAgents-astock')
from mootdx.quotes import Quotes

# 5个通达信服务器IP池 - 每个线程用不同的IP
TDX_SERVERS = [
    ('202.108.253.139', 80),
    ('202.108.253.158', 80),
    ('180.153.18.170', 7709),
    ('115.238.56.198', 7709),
    ('218.75.126.9', 7709),
]
# 再加5个备用
TDX_SERVERS_EXTRA = [
    ('180.153.18.172', 80),
    ('202.108.253.130', 80),
    ('218.75.126.3', 7709),
    ('115.238.56.7', 7709),
    ('61.152.107.162', 7709),
]

_thread_local = threading.local()

def get_client(server_idx):
    """每个线程有自己的连接，连不同的服务器"""
    if server_idx < len(TDX_SERVERS):
        ip, port = TDX_SERVERS[server_idx]
    else:
        ip, port = TDX_SERVERS_EXTRA[server_idx - len(TDX_SERVERS)]
    try:
        return Quotes.factory(market='std', tcp=(ip, port, True)), ip
    except:
        return None, ip

def parse_industry(text):
    if not isinstance(text, str):
        return None
    m = re.search(r'所属研究行业[：:]?\s*([^(\r\n]+)', text)
    if m: return m.group(1).strip()
    m = re.search(r'所属行业[：:]?\s*([^(\r\n]+)', text)
    if m: return m.group(1).strip()
    return None

def fetch_batch(codes_batch, server_idx, worker_id):
    """
    单个工作线程：连一个服务器IP，拉一批股票
    返回 [(code, industry), ...]
    """
    result = []
    
    # 建立连接（用分配的服务器）
    client, ip = get_client(server_idx)
    if client is None:
        # 备用
        ip = f"fallback_{worker_id}"
        client = Quotes.factory(market='std', tcp=('202.108.253.139', 80, True))
    
    for code in codes_batch:
        try:
            f10 = client.F10(code, 'industry')
            ind = parse_industry(f10.get('行业分析', ''))
            if ind:
                result.append((code, ind))
        except:
            # 断连重连
            try:
                client, ip = get_client(server_idx)
                if client is None:
                    client = Quotes.factory(market='std', tcp=('202.108.253.139', 80, True))
            except:
                pass
    
    return result


def main():
    renew_all = '--all' in sys.argv
    specific = None
    if '--codes' in sys.argv:
        idx = sys.argv.index('--codes')
        if idx + 1 < len(sys.argv):
            specific = sys.argv[idx + 1].split(',')
    
    # 确保表存在
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_industries (
            code TEXT PRIMARY KEY,
            industry_l1 TEXT,
            industry_l2 TEXT,
            industry_l3 TEXT,
            concept_tags TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    
    # 获取股票列表
    if specific:
        codes = specific
    elif renew_all:
        codes = [r[0] for r in conn.execute("""
            SELECT DISTINCT code FROM daily_klines
            WHERE code NOT LIKE '688%' AND code NOT LIKE '4%'
            AND code NOT LIKE '83%' AND code NOT LIKE '87%'
            ORDER BY code
        """).fetchall()]
    else:
        codes = [r[0] for r in conn.execute("""
            SELECT DISTINCT f.code FROM feat f
            WHERE f.code NOT LIKE '688%' AND f.code NOT LIKE '4%'
            AND f.code NOT LIKE '83%' AND f.code NOT LIKE '87%'
            AND f.code NOT IN (SELECT code FROM stock_industries WHERE industry_l1 IS NOT NULL)
            ORDER BY f.code
        """).fetchall()]
    conn.close()
    
    total = len(codes)
    if total == 0:
        print("✅ 所有股票行业数据已齐全")
        return
    
    WORKERS = min(5, total)
    batch_size = (total + WORKERS - 1) // WORKERS
    
    print(f"📡 同步行业分类: {total}只")
    print(f"   工作线程: {WORKERS}个 (各连不同服务器)")
    print(f"   每批: {batch_size}只")
    print()
    
    # 平分任务
    batches = []
    for i in range(WORKERS):
        start = i * batch_size
        end = min(start + batch_size, total)
        if start < end:
            batches.append((codes[start:end], i))
    
    t0 = time.time()
    all_results = []
    done_batches = 0
    
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        fut_map = {
            ex.submit(fetch_batch, codes_batch, i, i): (i, len(codes_batch))
            for codes_batch, i in batches
        }
        
        for f in as_completed(fut_map):
            worker_id, count = fut_map[f]
            batch_results = f.result()
            all_results.extend(batch_results)
            done_batches += 1
            
            # 每完成一个线程就写入DB
            conn2 = sqlite3.connect(DB)
            for code, ind in batch_results:
                conn2.execute(
                    "INSERT OR REPLACE INTO stock_industries (code, industry_l1, industry_l2, industry_l3, updated_at) "
                    "VALUES (?, ?, ?, ?, datetime('now'))",
                    (code, ind, ind, ind)
                )
            conn2.commit()
            conn2.close()
            
            el = time.time() - t0
            total_sofar = sum(b[1] for _, _, b in [(None, None, None)])  # placeholder
            # 统计进度
            cnt = conn2 = sqlite3.connect(DB)
            sofar = cnt.execute("SELECT COUNT(*) FROM stock_industries").fetchone()[0]
            cnt.close()
            
            pct = sofar * 100 // total
            rate = sofar / max(el, 1)
            remain = (total - sofar) / max(rate, 0.1) / 60
            print(f"  [线程{worker_id+1}] 成功{len(batch_results)}/{count}只  "
                  f"累计{sofar}/{total} {pct}%  {el:.0f}s  ETA{remain:.0f}min  {rate:.1f}只/s")
    
    el = time.time() - t0
    print(f"\n✅ 完成! {len(all_results)}/{total}只 耗时{el:.0f}s ({el/60:.1f}min)")
    
    # 统计
    conn3 = sqlite3.connect(DB)
    rows = conn3.execute("""
        SELECT industry_l1, COUNT(*) as n 
        FROM stock_industries WHERE industry_l1 IS NOT NULL 
        GROUP BY industry_l1 ORDER BY n DESC LIMIT 20
    """).fetchall()
    print("行业分布 Top 20:")
    for ind, cnt in rows:
        print(f"  {ind}: {cnt}只")
    conn3.close()


if __name__ == "__main__":
    main()
