#!/usr/bin/env python3
"""
三阴选股 — 全市场数据库扫描版

从 SQLite 数据库读取日线K线，不拉在线接口。
数据库由 astock-daily-sync skill 维护，每日收盘后自动同步。

用法:
    cd /home/harrydolly/code/TradingAgents-astock
    source .venv/bin/activate
    python3 ~/.hermes/skills/trading/three-crows-screening/scripts/screen_from_db.py

    # 指定日期（不指定则用数据库最新日期）
    python3 screen_from_db.py --date 2026-06-05

    # 只分析前20只（调试用）
    python3 screen_from_db.py --max 20
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from three_crows import three_black_crows_screen, is_valid_ticker, format_results

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

from tradingagents.dataflows.astock_db import (
    DB_PATH,
    get_stock_list,
    get_klines,
    get_db_stats,
    save_scan_result,
)

import sqlite3
import numpy as np


def read_klines_from_db(code, start_date, end_date):
    """从数据库读取K线，转换成three_crows能用的DataFrame
    
    注意：新浪接口不返回 Amount（成交额），数据库中的 Amount 可能为 0。
    当 Amount 全部为 0 时，用 Volume*100*(Open+Close)/2 估算成交额。
    """
    rows = get_klines(code, start_date, end_date)
    if not rows or len(rows) < 10:
        return None

    import pandas as pd
    df = pd.DataFrame(rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Amount'])
    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount']:
        df[col] = df[col].astype(float)
    
    # Amount=0 时用 Volume 估算成交额
    if df['Amount'].sum() == 0:
        df['Amount'] = df['Volume'] * 100 * (df['Open'] + df['Close']) / 2
    
    return df


def get_stock_name_by_code(code):
    """从数据库获取股票名称"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM stocks WHERE code = ?", (code,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else code


def get_latest_trade_date_from_db():
    """获取数据库中最新的交易日"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT MAX(date) FROM daily_klines")
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else datetime.now().strftime("%Y-%m-%d")


def scan_from_db(max_stocks=None, scan_date=None, min_klines=30, verbose=True):
    """全市场从数据库扫描三阴选股
    
    参数:
        max_stocks: 最多扫多少只（调试用）
        scan_date: 以哪天为T，默认数据库最新日期
        min_klines: 最少需要多少根K线（排除数据太少的）
    """
    # 确定扫描日期
    if scan_date is None:
        scan_date = get_latest_trade_date_from_db()
    
    # 计算需要回看的天数（大约40个交易日）
    end_date = scan_date
    start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=90)
    start_date = start_dt.strftime("%Y-%m-%d")
    
    # 获取股票列表
    stocks = get_stock_list()
    if max_stocks:
        stocks = stocks[:max_stocks]
    
    total = len(stocks)
    print(f"📡 三阴选股 — 全市场数据库扫描")
    print(f"   扫描日期: {scan_date}")
    print(f"   数据范围: {start_date} ~ {end_date}")
    print(f"   候选池: {total}只股票")
    print(f"   数据来源: SQLite数据库 (不拉在线接口)")
    print()
    
    hits = []
    scanned = 0
    skipped_st = 0
    skipped_no_data = 0
    skipped_short = 0
    skipped_688 = 0
    start_time = datetime.now()
    
    for i, (code, name) in enumerate(stocks, 1):
        # 排除规则
        if not is_valid_ticker(code, name or ""):
            skipped_st += 1
            continue
        
        scanned += 1
        
        if verbose and (i % 200 == 0 or i == 1):
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"  扫描进度: {i}/{total} | 已扫{scanned}只 | 命中{len(hits)}只 | 耗时{elapsed:.0f}s")
        
        try:
            df = read_klines_from_db(code, start_date, end_date)
            if df is None or len(df) < min_klines:
                skipped_short += 1
                continue
            
            if three_black_crows_screen(df, stock_name=name):
                cur = float(df['Close'].values[-1])
                chg_t = ((cur / float(df['Close'].values[-2])) - 1) * 100 if len(df) > 1 else 0
                
                # 计算涨停日涨跌幅
                zt_chg = 0
                for j in range(1, 6):
                    if len(df) > j:
                        chg = (float(df['Close'].values[-j]) / float(df['Close'].values[-j-1]) - 1) * 100
                        if chg > 9.5 or (chg > 19 and len(df) > j):  # 涨停
                            zt_chg = max(zt_chg, chg)
                
                hits.append({
                    'code': code,
                    'name': name,
                    'price': cur,
                    'chg_today': chg_t,
                    'zt_chg': zt_chg,
                })
                
                print(f"  ✅ {name}({code}) 价{cur:.2f} 当日{chg_t:+.2f}% 涨停日{zt_chg:+.2f}%")
                
        except Exception as e:
            if verbose:
                pass  # 静默失败
        
        if max_stocks and scanned >= max_stocks:
            break
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print(f"\n{'='*60}")
    print(f"  扫描完成!")
    print(f"  候选池: {total}只")
    print(f"  有效扫描: {scanned}只")
    print(f"  命中: {len(hits)}只")
    print(f"  排除(ST/688等): {skipped_st}只")
    print(f"  数据不足: {skipped_short}只")
    print(f"  耗时: {elapsed:.1f}秒")
    print(f"\n  📋 命中列表:")
    for h in hits:
        print(f"    {h['name']}({h['code']}) 价{h['price']:.2f} 当日{h['chg_today']:+.2f}% 涨停日{h['zt_chg']:+.2f}%")
    
    # 保存扫描结果
    try:
        results_to_save = []
        for h in hits:
            results_to_save.append({
                'code': h['code'],
                'name': h['name'],
                'price': h['price'],
                'chg_today': round(h['chg_today'], 2),
                'formula': '三阴选股',
                'zt_date': '',
                'zt_chg': round(h['zt_chg'], 2),
            })
        save_scan_result(scan_date, results_to_save)
        print(f"\n  💾 结果已保存到数据库 (scan_cache, {scan_date})")
    except Exception as e:
        print(f"\n  ⚠️ 保存结果失败: {e}")
    
    print(f"{'='*60}")
    return hits


def main():
    parser = argparse.ArgumentParser(description="三阴选股 — 全市场数据库扫描")
    parser.add_argument("--date", default=None, help="扫描日期（默认数据库最新日期）")
    parser.add_argument("--max", type=int, default=None, help="最多扫多少只（调试用）")
    parser.add_argument("--verbose", action="store_true", default=True)
    args = parser.parse_args()
    
    scan_from_db(
        max_stocks=args.max,
        scan_date=args.date,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
