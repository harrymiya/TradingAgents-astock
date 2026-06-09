#!/usr/bin/env python3
"""
sync_to_10yr.py — 把数据库从3.5年补全到10年(2016~2026)

策略：对每只股票检查最早日期，如果>2016-01-01就重新拉全量替换
分批处理，避免一次性占满内存
"""

import sqlite3
import os
import sys
import time
from datetime import datetime, date

DB = os.path.expanduser("~/.hermes/astock_data.db")
TARGET_START = "2016-01-01"
BATCH_SIZE = 100  # 每批100只
SLEEP_BETWEEN = 2  # 批次间休息2秒

# 排除的股票代码前缀
EXCLUDE_PREFIXES = ('4', '8')  # 新三板/北交所


def need_sync(cur, code):
    """检查是否需要补数据——最早日期>2016或者数据量不足"""
    cur.execute("SELECT MIN(date), COUNT(*) FROM daily_klines WHERE code=?", (code,))
    r = cur.fetchone()
    if not r or not r[0]:
        return True
    min_date = r[0]
    count = r[1]
    # 如果已经覆盖10年且数据量够，跳过
    if min_date <= TARGET_START and count >= 2000:
        return False
    return True


def sync_stock(client, cur, code, start_date, end_date):
    """同步单只股票的数据"""
    try:
        df = client.get_k_data(code=code, start_date=start_date, end_date=end_date)
        if df is None or len(df) == 0:
            return 0
        
        # 删除该股票现有数据（重新拉全量）
        cur.execute("DELETE FROM daily_klines WHERE code=?", (code,))
        
        # 写入新数据
        inserted = 0
        for _, row in df.iterrows():
            date_str = str(row["date"]).replace("-", "")
            if len(date_str) == 8:
                date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            
            cur.execute("""
                INSERT OR REPLACE INTO daily_klines 
                (code, date, open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                code, date_str,
                float(row["open"]), float(row["high"]),
                float(row["low"]), float(row["close"]),
                float(row["volume"]), float(row.get("amount", 0) or 0)
            ))
            inserted += 1
        
        return inserted
    except Exception as e:
        print(f"    [ERR] {code}: {e}", file=sys.stderr)
        return -1


def main():
    print("=" * 60)
    print(f"  全市场数据补全 → 10年 ({TARGET_START} ~ 2026)")
    print("=" * 60)
    
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # 获取所有需补数据的股票
    cur.execute("SELECT code, name FROM stocks ORDER BY code")
    all_stocks = cur.fetchall()
    print(f"\n总股票数: {len(all_stocks)}只")
    
    # 过滤出需要同步的
    to_sync = []
    for code, name in all_stocks:
        if code.startswith(EXCLUDE_PREFIXES):
            continue
        if need_sync(cur, code):
            to_sync.append((code, name))
    
    print(f"需要补数据: {len(to_sync)}只")
    print(f"已是最新: {len(all_stocks) - len(to_sync)}只\n")
    
    if not to_sync:
        print("✅ 所有股票数据已覆盖10年")
        conn.close()
        return
    
    # 分批同步
    from mootdx.quotes import Quotes
    
    total_inserted = 0
    total_errors = 0
    total_skipped = 0
    t0 = time.time()
    
    for batch_start in range(0, len(to_sync), BATCH_SIZE):
        batch = to_sync[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(to_sync) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"\n--- 批次 {batch_num}/{total_batches} ({len(batch)}只) ---")
        
        try:
            client = Quotes.factory(market='std')
        except Exception as e:
            print(f"  [ERR] mootdx连接失败: {e}")
            time.sleep(5)
            continue
        
        for code, name in batch:
            inserted = sync_stock(client, cur, code, TARGET_START, "2026-06-08")
            if inserted > 0:
                total_inserted += inserted
                print(f"  ✅ {code} {name}: {inserted}行")
            elif inserted == 0:
                total_skipped += 1
                print(f"  ⏭️ {code} {name}: 无数据")
            else:
                total_errors += 1
        
        conn.commit()
        print(f"  本批提交完成. 累计: {total_inserted:,}行, 错误{total_errors}只")
        
        if batch_num < total_batches:
            print(f"  休息{SLEEP_BETWEEN}秒...")
            time.sleep(SLEEP_BETWEEN)
    
    t1 = time.time()
    elapsed = t1 - t0
    
    print(f"\n{'='*60}")
    print(f"  同步完成!")
    print(f"  新增数据: {total_inserted:,}行")
    print(f"  成功: {len(to_sync) - total_errors - total_skipped}只")
    print(f"  跳过: {total_skipped}只")
    print(f"  错误: {total_errors}只")
    print(f"  耗时: {elapsed/60:.1f}分钟")
    
    # 数据统计
    cur.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM daily_klines")
    r = cur.fetchone()
    print(f"\n数据库状态: {r[0]:<12} ~ {r[1]:<12} ({r[2]:,}行)")
    
    cur.execute("SELECT code, COUNT(*) as cnt FROM daily_klines GROUP BY code ORDER BY cnt DESC LIMIT 3")
    for row in cur.fetchall():
        print(f"  最多: {row[0]}: {row[1]}天")
    
    conn.close()


if __name__ == "__main__":
    main()
