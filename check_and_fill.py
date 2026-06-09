#!/usr/bin/env python3
"""
数据完整性校验脚本 — 检查最近3个交易日数据，缺失则补全

用法:  python3 check_and_fill.py [--date 2026-06-09]
"""
import sqlite3, os, sys, urllib.request, time
from datetime import datetime, timedelta

DB = os.path.expanduser("~/.hermes/astock_data.db")

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def get_recent_days(target_date, count=3):
    """获取target_date最近的count个交易日"""
    conn = sqlite3.connect(DB)
    days = conn.execute("""
        SELECT DISTINCT date FROM daily_klines
        WHERE date <= ? ORDER BY date DESC LIMIT ?
    """, (target_date, count + 5)).fetchall()
    conn.close()
    return [d[0] for d in days[:count]]

def check_data(target_date):
    """检查最近3个交易日数据完整性"""
    days = get_recent_days(target_date, 3)
    log(f"最近3个交易日: {days}")
    
    conn = sqlite3.connect(DB)
    results = []
    for d in days:
        k_cnt = conn.execute("SELECT COUNT(*) FROM daily_klines WHERE date=?", (d,)).fetchone()[0]
        f_cnt = conn.execute("SELECT COUNT(*) FROM feat WHERE date=?", (d,)).fetchone()[0]
        results.append((d, k_cnt, f_cnt))
        log(f"  {d}: daily_klines={k_cnt}条  feat={f_cnt}条")
    conn.close()
    
    missing = [(d, k, f) for d, k, f in results if k < 4000 or f < 4000]
    return results, missing

def check_and_fill(target_date=None):
    """主逻辑：检查并补全"""
    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")
    
    print(f"\n{'='*50}")
    print(f"  数据完整性校验 + 补全")
    print(f"  日期: {target_date}")
    print(f"{'='*50}")
    
    days = get_recent_days(target_date, 3)
    log(f"最近3个交易日: {days}")
    
    conn = sqlite3.connect(DB)
    missing_list = []
    
    for d in days:
        k_cnt = conn.execute("SELECT COUNT(*) FROM daily_klines WHERE date=?", (d,)).fetchone()[0]
        f_cnt = conn.execute("SELECT COUNT(*) FROM feat WHERE date=?", (d,)).fetchone()[0]
        status = "✅" if k_cnt >= 4000 and f_cnt >= 4000 else "⚠️"
        print(f"  {status} {d}: daily_klines={k_cnt}条  feat={f_cnt}条")
        if k_cnt < 4000:
            missing_list.append(d)
    
    if not missing_list:
        log("✅ 数据完整，无需补全")
        conn.close()
        return True
    
    log(f"⚠️ 发现缺失: {missing_list}")
    conn.close()
    return False

if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    check_and_fill(date_arg)
