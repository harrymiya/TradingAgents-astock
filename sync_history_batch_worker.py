#!/usr/bin/env python3
"""Batch worker for sync_history_all - processes a single batch"""
import sqlite3, os, sys, time, json
from datetime import datetime

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')
START_DATE = '2023-01-01'
END_DATE = '2026-06-08'

def insert_batch(records):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO daily_klines (code, date, open, high, low, close, volume, amount) VALUES (?,?,?,?,?,?,?,?)",
        records
    )
    conn.commit()
    conn.close()

def get_stock_db_count(code):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM daily_klines WHERE code=?", (code,))
    cnt = cur.fetchone()[0]
    conn.close()
    return cnt

from mootdx.quotes import Quotes
client = Quotes.factory(market='std')

codes_batch = json.loads(sys.argv[1])
batch_id = int(sys.argv[2])

print(f"[Batch {batch_id}] Starting {len(codes_batch)} stocks...")
total_new = 0
fail = 0
skipped = 0

t0 = time.time()
for i, (code, name) in enumerate(codes_batch):
    cnt = get_stock_db_count(code)
    if cnt >= 600:
        skipped += 1
        if (i+1) % 100 == 0:
            print(f"[Batch {batch_id}] [{i+1}/{len(codes_batch)}] {code} {name}: skipping ({cnt} lines exist)")
        continue
    
    try:
        df = client.get_k_data(code=code, start_date=START_DATE, end_date=END_DATE)
        if df is not None and len(df) > 0:
            records = []
            for idx in range(len(df)):
                row = df.iloc[idx]
                d = str(row['date'])
                if '-' not in d:
                    continue
                records.append((
                    code, d,
                    float(row['open']), float(row['high']),
                    float(row['low']), float(row['close']),
                    float(row['vol']), float(row['amount'])
                ))
            if records:
                insert_batch(records)
                total_new += len(records)
                if (i+1) % 50 == 0:
                    elapsed = time.time() - t0
                    rate = (i+1) / elapsed if elapsed > 0 else 0
                    print(f"[Batch {batch_id}] [{i+1}/{len(codes_batch)}] {code} {name}: +{len(records)} ({total_new} total, {rate:.1f}/s)")
        else:
            # 没数据——可能是退市股，写入空记录防止反复重试
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR IGNORE INTO daily_klines (code, date, open, high, low, close, volume, amount) VALUES (?, '1970-01-01', 0, 0, 0, 0, 0, 0)", (code,))
            conn.commit()
            conn.close()
    except Exception as e:
        fail += 1
    
    time.sleep(0.01)

elapsed = time.time() - t0
print(f"[Batch {batch_id}] DONE: +{total_new} new, {fail} fail, {skipped} skip, {elapsed:.0f}s")
