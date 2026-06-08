#!/usr/bin/env python3
"""
全市场近3年历史日线数据——逐只同步，无subprocess，实时输出。
排除ST/退市股。用mootdx get_k_data逐只拉取，INSERT OR REPLACE写入DB。
支持断点续传（已有完整历史的自动跳过）。

用法:
  python3 -u sync_history_all.py          # 全市场
  python3 -u sync_history_all.py --code 000001  # 单只
  python3 -u sync_history_all.py --check        # 检查
"""

import sqlite3
import os
import sys
import time
import json
import argparse
from datetime import datetime
from mootdx.quotes import Quotes

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')
LOG_PATH = os.path.expanduser('~/.hermes/sync_history.log')
START_DATE = '2023-01-01'
END_DATE = '2026-06-08'
GOOD_DAYS_THRESHOLD = 600  # 认为已有的天数标准

def log(msg):
    """同时输出到stdout和日志文件（后台模式有缓冲问题）"""
    print(msg, flush=True)
    with open(LOG_PATH, 'a') as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

def get_stocks():
    """获取非ST非退市的A股"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT code, name FROM stocks ORDER BY code")
    all_stocks = cur.fetchall()
    conn.close()
    
    good = []
    for c, n in all_stocks:
        name = n or ''
        if '退' in name: continue
        if name.startswith('*ST') or name.startswith('ST') or name == 'ST' or ' ST' in name:
            continue
        good.append((c, name if name else c))
    return good

def get_existing(code):
    """查DB中某股票已有多少天"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM daily_klines WHERE code=?", (code,))
    cnt, mn, mx = cur.fetchone()
    conn.close()
    return cnt or 0, mn, mx

def insert(code, records):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO daily_klines (code, date, open, high, low, close, volume, amount) VALUES (?,?,?,?,?,?,?,?)",
        records
    )
    conn.commit()
    conn.close()

def check():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT MIN(date), MAX(date), COUNT(*), COUNT(DISTINCT code) FROM daily_klines WHERE date > '2000-01-01'")
    m = cur.fetchone()
    log(f"📊 DB: {m[0]} ~ {m[1]}, {m[2]:,}行, {m[3]}只")
    
    # 分布
    cur.execute("""
        SELECT CASE WHEN cnt<100 THEN '<100天' WHEN cnt<300 THEN '100-300天' WHEN cnt<500 THEN '500-700天' ELSE '700+天' END,
               COUNT(*)
        FROM (SELECT COUNT(*) cnt FROM daily_klines WHERE date>'2000-01-01' GROUP BY code)
        GROUP BY 1 ORDER BY MIN(cnt)
    """)
    dist = cur.fetchall()
    for r, n in dist:
        log(f"  {r}: {n}只")
    
    cur.execute("SELECT code, name FROM stocks WHERE code NOT IN (SELECT DISTINCT code FROM daily_klines WHERE date>'2000-01-01') LIMIT 10")
    missing = cur.fetchall()
    if missing:
        log(f"\n  无历史数据的10只: {[c for c,_ in missing]}")
    conn.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code', type=str, help='单只股票')
    parser.add_argument('--check', action='store_true', help='检查')
    parser.add_argument('--skip', type=int, default=0, help='跳过前N只')
    parser.add_argument('--max', type=int, default=99999, help='最多处理N只')
    args = parser.parse_args()
    
    if args.check:
        check()
        return
    
    if args.code:
        # 单只
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name FROM stocks WHERE code=?", (args.code,))
        row = cur.fetchone()
        conn.close()
        name = row[0] if row else args.code
        stocks = [(args.code, name)]
    else:
        stocks = get_stocks()
    
    stocks = stocks[args.skip:args.skip+args.max]
    total = len(stocks)
    
    log(f"🔄 开始同步 {total} 只股票 ({START_DATE} ~ {END_DATE})")
    log(f"{'='*60}")
    
    # 预创建mootdx客户端
    log("  初始化mootdx...")
    client = Quotes.factory(market='std')
    log("  OK")
    
    t_start = time.time()
    total_new = 0
    total_skip = 0
    total_fail = 0
    last_report = time.time()
    total_estimate = 0  # 总估算量
    
    for i, (code, name) in enumerate(stocks):
        # 检查是否已有完整数据
        cnt, mn, mx = get_existing(code)
        if cnt >= GOOD_DAYS_THRESHOLD and mn and mn <= START_DATE:
            total_skip += 1
            if (i+1) % 100 == 0:
                elapsed = time.time() - t_start
                rate = (i+1) / elapsed * 3600 if elapsed > 0 else 0
                progress = (i+1) / total * 100
                log(f"  [{i+1}/{total} {progress:.0f}%] 跳过{total_skip}只, 新增{total_new:,}条, {rate:.0f}只/h, {elapsed/60:.1f}min")
            continue
        
        try:
            df = client.get_k_data(code=code, start_date=START_DATE, end_date=END_DATE)
            if df is not None and len(df) > 0:
                records = []
                for idx in range(len(df)):
                    row = df.iloc[idx]
                    d = str(row['date'])
                    if '-' not in d: continue
                    records.append((
                        code, d,
                        float(row['open']), float(row['high']),
                        float(row['low']), float(row['close']),
                        float(row['vol']), float(row['amount'])
                    ))
                if records:
                    insert(code, records)
                    total_new += len(records)
            else:
                # 无数据——空标记
                conn = sqlite3.connect(DB_PATH)
                conn.execute("INSERT OR IGNORE INTO daily_klines (code, date, open, high, low, close, volume, amount) VALUES (?, '1970-01-01', 0,0,0,0,0,0)", (code,))
                conn.commit()
                conn.close()
        except Exception as e:
            total_fail += 1
            if total_fail <= 5 or (total_fail % 10 == 0):
                log(f"  [{i+1}/{total}] ❌ {code} {name}: {e}")
        
        # 进度报告
        now = time.time()
        if now - last_report >= 15 or (i+1) % 200 == 0:
            elapsed = now - t_start
            done = i + 1
            rate = done / elapsed if elapsed > 0 else 0
            remaining = total - done
            eta = remaining / rate / 60 if rate > 0 else 0
            progress = done / total * 100
            log(f"  [{done}/{total} {progress:.0f}%] ✅{total_new:,}条 | ⏭{total_skip}跳 | ❌{total_fail}错 | {rate:.0f}只/s | ETA {eta:.0f}min")
            last_report = now
        
        # 每50只短暂休息
        if (i+1) % 100 == 0:
            time.sleep(0.5)
    
    elapsed = time.time() - t_start
    log(f"\n{'='*60}")
    log(f"🏁 完成！")
    log(f"  总处理: {total}只")
    log(f"  新增: {total_new:,}条")
    log(f"  跳过: {total_skip}只")
    log(f"  失败: {total_fail}只")
    log(f"  耗时: {elapsed:.0f}秒 ({elapsed/60:.1f}分钟)")
    
    check()

if __name__ == '__main__':
    main()
