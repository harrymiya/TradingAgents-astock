#!/usr/bin/env python3
"""
sync_to_10yr_v2.py — 把数据库从3.5年补全到10年(2016~2026)

核心策略：
1. 不删现有数据（先备份）
2. 对每只股票：如果最早日期>2016-01-01，拉全量补充
3. 使用 INSERT OR REPLACE（有就覆盖，没有就插入）
4. mootdx客户端全程复用，避免连接重建失败
"""

import sqlite3
import os
import sys
import time
from datetime import datetime

DB = os.path.expanduser("~/.hermes/astock_data.db")
TARGET_START = "2016-01-04"
BATCH_SIZE = 50
SLEEP_BETWEEN = 1

# 排除北交所(920)
EXCLUDE_PREFIXES = ('920',)


def get_stock_min_date(cur, code):
    """获取该股票已有数据的最早日期"""
    cur.execute("SELECT MIN(date) FROM daily_klines WHERE code=?", (code,))
    r = cur.fetchone()
    return r[0] if r and r[0] else None


def need_sync(min_date):
    """是否需要补数据"""
    if min_date is None:
        return True
    if min_date <= TARGET_START:
        return False
    return True


def sync_stock(client, cur, code, records_only=False):
    """同步单只股票，返回插入行数"""
    try:
        if records_only:
            # 只检查记录数，不拉数据
            cur.execute("SELECT COUNT(*) FROM daily_klines WHERE code=?", (code,))
            return cur.fetchone()[0]
        
        df = client.get_k_data(code=code, start_date=TARGET_START, end_date="2026-06-08")
        if df is None or len(df) == 0:
            return 0
        
        inserted = 0
        for _, row in df.iterrows():
            date_raw = str(row["date"]).replace("-", "")
            if len(date_raw) == 8:
                date_str = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
            else:
                date_str = date_raw
            
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
        return -1


def main():
    print("=" * 60)
    print(f"  全市场补全 → 10年 ({TARGET_START} ~ 2026-06-08)")
    print("  策略: INSERT OR REPLACE, 不删现有数据")
    print("=" * 60)
    
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # 获取所有股票
    cur.execute("SELECT code, name FROM stocks ORDER BY code")
    all_stocks = cur.fetchall()
    
    # 过滤：需同步的
    to_sync = []
    already_done = 0
    excluded = 0
    
    for code, name in all_stocks:
        if code.startswith(EXCLUDE_PREFIXES):
            excluded += 1
            continue
        min_date = get_stock_min_date(cur, code)
        if need_sync(min_date):
            # 检查记录数是否合理
            cur.execute("SELECT COUNT(*) FROM daily_klines WHERE code=?", (code,))
            cnt = cur.fetchone()[0]
            if cnt >= 2000 and min_date and min_date <= TARGET_START:
                already_done += 1
                continue
            to_sync.append((code, name, min_date or "无数据", cnt))
    
    print(f"\n总股票: {len(all_stocks)}只")
    print(f"已覆盖10年: {already_done}只")
    print(f"需补数据: {len(to_sync)}只")
    print(f"已排除(北交所): {excluded}只")
    
    if not to_sync:
        print("\n✅ 全部已覆盖10年!")
        conn.close()
        return
    
    print(f"\n首批10只样例:")
    for code, name, md, cnt in to_sync[:10]:
        print(f"  {code} {name}: 当前最早{md}({cnt}天) → 需补到{TARGET_START}")
    
    # ===== 开始同步 =====
    from mootdx.quotes import Quotes
    
    # 初始化一次客户端，全程复用
    print("\n连接mootdx...")
    client = Quotes.factory(market='std')
    print("✅ mootdx已连接\n")
    
    total_ok = 0
    total_err = 0
    total_rows = 0
    t0 = time.time()
    
    for i, (code, name, min_date, cur_cnt) in enumerate(to_sync):
        # 进度
        if i > 0 and i % BATCH_SIZE == 0:
            elapsed = time.time() - t0
            rate = i / elapsed * 60 if elapsed > 0 else 0
            percent = i / len(to_sync) * 100
            print(f"\n[{i}/{len(to_sync)}] {percent:.0f}% | "
                  f"OK{total_ok} ERR{total_err} | "
                  f"+{total_rows:,}行 | {rate:.0f}只/分 | "
                  f"{elapsed/60:.1f}分")
            conn.commit()
            print(f"  已提交DB")
            if i < len(to_sync) - 1:
                time.sleep(SLEEP_BETWEEN)
        
        rows = sync_stock(client, cur, code)
        if rows > 0:
            total_ok += 1
            total_rows += rows
            if total_ok <= 5 or total_ok % 500 == 0:
                print(f"  ✅ {code} {name}: {rows}行", flush=True)
        elif rows == 0:
            total_ok += 1  # 没数据也算正常（退市的）
        else:
            total_err += 1
            if total_err <= 10 or total_err % 100 == 0:
                print(f"  ❌ {code} {name}: 失败", flush=True)
    
    # 最后提交
    conn.commit()
    t1 = time.time()
    
    print(f"\n{'='*60}")
    print(f"  同步完成!")
    print(f"  成功: {total_ok}只 | 失败: {total_err}只 | 新增: {total_rows:,}行")
    print(f"  耗时: {(t1-t0)/60:.1f}分 | {(t1-t0)/max(1,total_ok):.1f}秒/只")
    
    # 最终统计
    cur.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM daily_klines")
    r = cur.fetchone()
    print(f"\n📊 数据库最终状态:")
    print(f"  日期: {r[0]} ~ {r[1]}")
    print(f"  总行数: {r[2]:,}")
    
    cur.execute("SELECT COUNT(DISTINCT code) FROM daily_klines")
    stocks = cur.fetchone()[0]
    cur.execute("SELECT AVG(cnt) FROM (SELECT COUNT(*) as cnt FROM daily_klines GROUP BY code)")
    avg_days = cur.fetchone()[0]
    print(f"  股票: {stocks}只 | 平均: {avg_days:.0f}天/只")
    
    conn.close()


if __name__ == "__main__":
    main()
