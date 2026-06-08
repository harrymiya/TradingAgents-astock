#!/usr/bin/env python3
"""
三阴选股 — 单只股票分析（数据库版）

从 SQLite 数据库读取日线K线，不拉在线接口。

用法:
    cd /home/harrydolly/code/TradingAgents-astock
    source .venv/bin/activate

    python3 single_stock.py 000333          # 按代码
    python3 single_stock.py 002575          # 群兴玩具
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from three_crows import three_black_crows_screen

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

from tradingagents.dataflows.astock_db import (
    DB_PATH,
    get_klines,
    get_stock_list,
)

import sqlite3
import pandas as pd


def read_klines_from_db(code, start_date, end_date):
    """从数据库读取K线，估算成交额"""
    rows = get_klines(code, start_date, end_date)
    if not rows or len(rows) < 10:
        return None
    
    df = pd.DataFrame(rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Amount'])
    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount']:
        df[col] = df[col].astype(float)
    
    # Amount=0 时用 Volume 估算成交额
    if df['Amount'].sum() == 0:
        df['Amount'] = df['Volume'] * 100 * (df['Open'] + df['Close']) / 2
    
    return df


def get_stock_name_from_db(code):
    """从数据库获取股票名称"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM stocks WHERE code = ?", (code,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else code


def get_latest_trade_date():
    """数据库中最新的交易日"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT MAX(date) FROM daily_klines")
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else datetime.now().strftime("%Y-%m-%d")


def diagnose_conditions(df):
    """诊断三阴选股各条件"""
    close = df['Close'].values.astype(float)
    open_ = df['Open'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    amo = df['Amount'].values.astype(float)
    
    c0, o0, h0, l0, a0 = close[-1], open_[-1], high[-1], low[-1], amo[-1]
    c1, o1, h1, l1, a1 = close[-2], open_[-2], high[-2], low[-2], amo[-2]
    c2, o2, h2, l2, a2 = close[-3], open_[-3], high[-3], low[-3], amo[-3]
    c3, o3, h3, l3, a3 = close[-4], open_[-4], high[-4], low[-4], amo[-4]
    c4 = close[-5]
    
    limit_price = round(c4 * 1.1, 2)
    
    lines = []
    lines.append(f"  {'✅' if (limit_price-c3)<0.01 else '❌'} T-3涨停: 涨停价={limit_price:.3f} T-3收盘={c3:.3f} 差={limit_price-c3:.4f}")
    lines.append(f"  {'✅' if a2>a3 else '❌'} T-2放量: {a2:.0f} > {a3:.0f} ({a2>a3})")
    lines.append(f"  {'✅' if a1<a2 else '❌'} T-1缩量: {a1:.0f} < {a2:.0f} ({a1<a2})")
    lines.append(f"  {'✅' if a0<a1 else '❌'} T续缩量: {a0:.0f} < {a1:.0f} ({a0<a1})")
    lines.append(f"  {'✅' if (c0-c1)/c1<0 else '❌'} 今日收阴: {(c0-c1)/c1*100:+.2f}%")
    lines.append(f"  {'✅' if c0>o3 else '❌'} T收>T-3开: {c0:.2f} > {o3:.2f} ({c0>o3})")
    lines.append(f"  {'✅' if o0>l3 else '❌'} T开>T-3低: {o0:.2f} > {l3:.2f} ({o0>l3})")
    
    jump_days, down_days = 0, 0
    for i in range(4):
        idx = -(i+1)
        if i > 0 and high[idx] < low[idx-1]:
            jump_days += 1
    for i in range(3):
        idx = -(i+1)
        if i > 0 and close[idx-1] > 0 and close[idx] / close[idx-1] <= 0.9:
            down_days += 1
    
    no_jump = not (jump_days > 0 and down_days >= 1)
    lines.append(f"  {'✅' if no_jump else '❌'} 无跳空跌停 (跳空{jump_days}天 跌停{down_days}天)")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="三阴选股 - 单只数据库分析")
    parser.add_argument("ticker", help="股票代码（6位数字）")
    parser.add_argument("--days", type=int, default=90, help="回看天数（默认90天）")
    args = parser.parse_args()
    
    ticker = args.ticker.strip()
    if not ticker.isdigit() or len(ticker) != 6:
        print(f"❌ 请输入6位股票代码")
        return
    
    # 获取股票名称
    name = get_stock_name_from_db(ticker)
    if not name:
        print(f"⚠️ 数据库中找不到 {ticker}，可能未同步")
        name = ticker
    
    # 日期范围
    latest = get_latest_trade_date()
    start_dt = datetime.strptime(latest, "%Y-%m-%d") - timedelta(days=args.days)
    start_date = start_dt.strftime("%Y-%m-%d")
    
    print(f"\n{'='*50}")
    print(f"  📡 三阴选股分析 (数据库): {name}({ticker})")
    print(f"  数据: {start_date} ~ {latest}")
    print(f"{'='*50}")
    
    df = read_klines_from_db(ticker, start_date, latest)
    if df is None or len(df) < 10:
        print(f"  ❌ 数据不足 ({len(df) if df is not None else 0}行)，可能数据库未同步")
        return
    
    cur = float(df['Close'].values[-1])
    chg_t = ((cur / float(df['Close'].values[-2])) - 1) * 100 if len(df) > 1 else 0
    chg_5 = ((cur / float(df['Close'].values[-6])) - 1) * 100 if len(df) > 6 else 0
    
    result = three_black_crows_screen(df, stock_name=name)
    
    print(f"\n  当前价: {cur:.2f}  当日: {chg_t:+.2f}%  近5日: {chg_5:+.2f}%")
    
    if result:
        print(f"\n  ✅ 命中三阴选股条件！\n")
    else:
        print(f"\n  ❌ 未命中\n")
        print(f"  📋 条件诊断:")
        print(diagnose_conditions(df))
    
    print(f"\n  📊 最近5日K线:")
    print(f"  {'TAG':4s} {'日期':10s} {'开盘':>8s} {'最高':>8s} {'最低':>8s} {'收盘':>8s} {'成交额':>10s}")
    for j in range(5, 0, -1):
        d = df.iloc[-j]
        print(f"  T-{j} {d['Date']:10s} {float(d['Open']):>8.2f} {float(d['High']):>8.2f} {float(d['Low']):>8.2f} {float(d['Close']):>8.2f} {float(d['Amount']):>10.0f}")
    
    print()


if __name__ == "__main__":
    main()
