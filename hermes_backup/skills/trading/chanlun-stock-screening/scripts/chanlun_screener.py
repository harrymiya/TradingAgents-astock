#!/usr/bin/env python3
"""
缠论选股器 — 从缠论108课中提取的量化选股策略

策略列表:
  1. 底分型+底背驰选股 (第一类买点基础版)
  2. 关键K线突破选股 (第79课：分型辅助操作)
  3. 简化三买选股 (中枢突破+回抽不破ZG, v2基于缠师原文)

所有策略从 SQLite 数据库读取K线，不拉在线接口。
数据库由 astock-daily-sync skill 维护。

用法:
    cd /home/harrydolly/code/TradingAgents-astock
    source .venv/bin/activate

    # 全市场扫描三买
    python3 ~/.hermes/skills/trading/chanlun-stock-screening/scripts/chanlun_screener.py --strategy san_mai --all

    # 单只股票分析所有策略
    python3 ~/.hermes/skills/trading/chanlun-stock-screening/scripts/chanlun_screener.py --stock 002575

    # 列出现有策略
    python3 ~/.hermes/skills/trading/chanlun-stock-screening/scripts/chanlun_screener.py --list
"""

import sys
import os
import argparse
import numpy as np
from datetime import datetime, timedelta

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

import sqlite3
import pandas as pd

from tradingagents.dataflows.astock_db import (
    DB_PATH,
    get_stock_list,
    get_klines,
    get_db_stats,
    save_scan_result,
)


# ============================================================
# 工具函数
# ============================================================

def read_klines(code, lookback_days=90):
    """从数据库读取K线，估算成交额"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT MAX(date) FROM daily_klines")
    latest = c.fetchone()
    if not latest or not latest[0]:
        conn.close()
        return None, None
    end_date = latest[0]
    start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=lookback_days)
    start_date = start_dt.strftime("%Y-%m-%d")
    
    c.execute("""SELECT date, open, high, low, close, volume, amount 
                 FROM daily_klines WHERE code = ? AND date >= ? AND date <= ?
                 ORDER BY date""", (code, start_date, end_date))
    rows = c.fetchall()
    conn.close()
    
    if not rows or len(rows) < 20:
        return None, None
    
    df = pd.DataFrame(rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Amount'])
    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount']:
        df[col] = df[col].astype(float)
    
    if df['Amount'].sum() == 0:
        df['Amount'] = df['Volume'] * 100 * (df['Open'] + df['Close']) / 2
    
    return df, end_date


def get_stock_name(code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM stocks WHERE code = ?", (code,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else code


def calc_macd(df, fast=12, slow=26, signal=9):
    """计算MACD指标"""
    close = df['Close'].values.astype(float)
    ema_fast = pd.Series(close).ewm(span=fast).mean().values
    ema_slow = pd.Series(close).ewm(span=slow).mean().values
    dif = ema_fast - ema_slow
    dea = pd.Series(dif).ewm(span=signal).mean().values
    macd = 2 * (dif - dea)
    return dif, dea, macd


def is_valid_ticker(code, name=""):
    code = code.strip()
    if not code or not code.isdigit() or len(code) != 6:
        return False
    if code[0] == '4':
        return False
    if code.startswith('83') or code.startswith('87'):
        return False
    if code.startswith('688'):
        return False
    if name and ('ST' in name or '*ST' in name):
        return False
    return True


# ============================================================
# 策略1: 底分型 + MACD底背驰
# ============================================================

def check_fenxing(high, low, i):
    """检查第i根K线是否为分型"""
    if i < 1 or i >= len(high) - 1:
        return None
    h1, h2, h3 = high[i-1], high[i], high[i+1]
    l1, l2, l3 = low[i-1], low[i], low[i+1]
    if h2 > h1 and h2 > h3 and l2 > l1 and l2 > l3:
        return 'top'
    if l2 < l1 and l2 < l3 and h2 < h1 and h2 < h3:
        return 'bottom'
    return None


def check_beichi(df, lookback=30):
    """检查最后几根K线是否有底背驰"""
    if df is None or len(df) < lookback:
        return False, []
    close = df['Close'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    dif, dea, macd = calc_macd(df)
    reasons = []
    n = len(df)
    
    fenxing_found = False
    fenxing_idx = -1
    for i in range(n - 3, n):
        result = check_fenxing(high, low, i)
        if result == 'bottom':
            fenxing_found = True
            fenxing_idx = i
            reasons.append(f"底分型在第{fenxing_idx}根K线")
            break
    if not fenxing_found:
        return False, ["无底分型"]
    
    seg_start = max(0, fenxing_idx - 20)
    recent_negative = macd[seg_start:fenxing_idx+1]
    recent_area = abs(sum(recent_negative[recent_negative < 0]))
    
    prev_start = max(0, seg_start - 30)
    prev_seg = macd[prev_start:seg_start]
    prev_area = abs(sum(prev_seg[prev_seg < 0])) if len(prev_seg) > 5 else 0
    
    if prev_area > 0 and recent_area > 0:
        area_ratio = recent_area / prev_area
        reasons.append(f"MACD绿柱面积: 后段{recent_area:.0f} / 前段{prev_area:.0f} = {area_ratio:.2f}")
        if area_ratio < 0.9:
            dif_recent = dif[seg_start:fenxing_idx+1]
            dif_prev = dif[prev_start:seg_start]
            if not (dif_recent.min() < dif_prev.min() - 0.1):
                reasons.append(f"DIF未创新低 ✓")
                return True, reasons
            else:
                reasons.append(f"DIF创新低，但面积缩小，属弱势背驰")
                return True, reasons
    return False, reasons


def check_guanjian_kline(df):
    """第79课：关键K线分型突破选股"""
    if df is None or len(df) < 20:
        return False, []
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    close = df['Close'].values.astype(float)
    reasons = []
    n = len(df)
    
    for i in range(n - 3, n):
        result = check_fenxing(high, low, i)
        if result == 'bottom':
            if close[i+1] > high[i-1]:
                reasons.append(f"强底分型: C3({close[i+1]:.2f}) > H1({high[i-1]:.2f})")
                ma5 = pd.Series(close).rolling(5).mean().values
                if close[i+1] > ma5[i+1]:
                    reasons.append(f"站上MA5({ma5[i+1]:.2f})")
                vol = df['Volume'].values.astype(float)
                vol_ma5 = pd.Series(vol).rolling(5).mean().values
                if vol[i+1] > vol_ma5[i+1] * 1.5:
                    reasons.append(f"成交量放大{vol[i+1]/vol_ma5[i+1]:.1f}倍")
                return True, reasons
    return False, ["无关键底分型"]


# ============================================================
# 策略2: 第三类买点（基于缠师原文）
# ============================================================

def find_zones(df, min_zone_days=8, max_zone_pct=25):
    """从K线中寻找价格中枢（密集区）"""
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    n = len(df)
    zones = []
    i = max(0, n - 60)
    while i < n - min_zone_days:
        segment_high = max(high[i:i+min_zone_days])
        segment_low = min(low[i:i+min_zone_days])
        segment_range = (segment_high - segment_low) / segment_low * 100
        if segment_range < max_zone_pct:
            zones.append({
                'start': i, 'end': i + min_zone_days,
                'zg': segment_high, 'zd': segment_low,
                'range_pct': segment_range,
            })
            i += min_zone_days
        else:
            i += 1
    return zones


def check_san_mai_v2(df):
    """第三类买点识别（基于缠师原文）
    
    缠师原文要点：
    1. 第三类买点，一定要在第一个中枢后效果最好
    2. 日线的第三类买点 = 看一个30分钟的回抽
    3. 第三类买点的结束位置不一定是整个回拉的最低位置
    """
    if df is None or len(df) < 30:
        return False, []
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    close = df['Close'].values.astype(float)
    vol = df['Volume'].values.astype(float)
    dif, dea, macd = calc_macd(df)
    reasons = []
    n = len(df)
    
    # 1. 找中枢
    zones = find_zones(df, min_zone_days=8, max_zone_pct=25)
    if not zones:
        reasons.append("未发现价格中枢（密集区）")
        vola = pd.Series(high - low).rolling(10).std().values
        min_vola_idx = np.argmin(vola[-30:]) if len(vola) > 30 else 0
        min_vola_idx = n - 30 + min_vola_idx
        zg = max(high[min_vola_idx:min_vola_idx+10])
        zd = min(low[min_vola_idx:min_vola_idx+10])
        reasons.append(f"用最低波动区作为近似中枢 [{zd:.2f}, {zg:.2f}]")
    else:
        valid_zones = [z for z in zones if z['end'] < n - 3]
        if not valid_zones:
            valid_zones = zones
        zone = valid_zones[-1]
        zg, zd = zone['zg'], zone['zd']
        reasons.append(f"中枢区间 [{zd:.2f}, {zg:.2f}] 幅度{zone['range_pct']:.1f}%")
    
    zone_high, zone_low = zg, zd
    zone_range = (zone_high - zone_low) / zone_low * 100
    if zone_range > 30:
        reasons.append(f"中枢幅度{zone_range:.1f}%偏大，可能不是有效中枢")
    
    # 2. 确认突破
    recent_high = max(high[n-20:]) if n >= 20 else max(high)
    recent_high_idx = np.argmax(high[-20:]) + max(0, n-20) if n >= 20 else np.argmax(high)
    
    if recent_high <= zone_high * 1.01:
        reasons.append(f"未突破中枢（最高{recent_high:.2f} <= ZG{zone_high:.2f}）")
        return False, reasons
    
    breakout_vol = vol[recent_high_idx]
    vol_ma20 = pd.Series(vol).rolling(20).mean().values[-1]
    vol_ratio = breakout_vol / vol_ma20 if vol_ma20 > 0 else 1
    
    earlier_zones = [z for z in zones if z['end'] < zone_low and z['range_pct'] < zone_range * 1.2]
    if len(earlier_zones) == 0:
        reasons.append("✅ 第一个中枢！三买效果最佳")
    else:
        reasons.append(f"⚠️ 第{len(earlier_zones)+1}个中枢之后（前面还有{len(earlier_zones)}个）")
    reasons.append(f"突破: H={recent_high:.2f} > ZG={zone_high:.2f} 量比{vol_ratio:.1f}倍")
    
    # 3. 判断回抽
    idx_since_breakout = recent_high_idx
    high_after = max(high[idx_since_breakout:])
    low_after = min(low[idx_since_breakout:])
    cur_close = close[-1]
    pullback = (high_after - cur_close) / high_after * 100 if high_after > 0 else 0
    
    if pullback < 2:
        reasons.append(f"刚突破，未回抽（回撤{pullback:.1f}%）")
        return False, reasons
    if pullback > 20:
        reasons.append(f"回抽过深{pullback:.1f}%，可能已破位")
        return False, reasons
    reasons.append(f"正在回抽: 从{high_after:.2f}回撤{pullback:.1f}%")
    
    # 4. 三买确认：回抽不破中枢上沿
    if cur_close > zone_high:
        reasons.append(f"✅ 三买活跃！当前价{cur_close:.2f} > ZG{zone_high:.2f}")
        reasons.append("   回抽未破中枢，等待次级别背驰确认买点")
        return True, reasons
    elif low_after > zone_high * 0.99:
        reasons.append(f"✅ 三买成立！回抽最低{low_after:.2f} ≈ ZG{zone_high:.2f}")
        return True, reasons
    else:
        reasons.append(f"回抽已进入中枢（最低{low_after:.2f} < ZG{zone_high:.2f}），等待确认")
    return False, reasons


# ============================================================
# 扫描引擎
# ============================================================

ALL_STRATEGIES = {
    'di_fenxing_beichi': {
        'name': '底分型+底背驰',
        'desc': '第一类买点基础版',
        'func': check_beichi,
    },
    'guanjian_kline': {
        'name': '关键K线突破',
        'desc': '第79课强底分型突破',
        'func': check_guanjian_kline,
    },
    'san_mai': {
        'name': '第三类买点(v2)',
        'desc': '中枢突破+回抽不破ZG（基于缠师原文）',
        'func': check_san_mai_v2,
    },
}


def scan_all(strategy_name='di_fenxing_beichi', max_stocks=None, verbose=True):
    strategy = ALL_STRATEGIES.get(strategy_name)
    if not strategy:
        print(f"❌ 未知策略: {strategy_name}")
        print(f"   可用策略: {', '.join(ALL_STRATEGIES.keys())}")
        return []
    stocks = get_stock_list()
    if max_stocks:
        stocks = stocks[:max_stocks]
    hits = []
    total = len(stocks)
    print(f"📡 缠论选股 — {strategy['name']}（{strategy['desc']}）")
    print(f"   候选池: {total}只股票")
    print(f"   数据来源: SQLite数据库\n")
    start_time = datetime.now()
    scanned = 0
    for i, (code, name) in enumerate(stocks, 1):
        if not is_valid_ticker(code, name or ""):
            continue
        scanned += 1
        if verbose and (i % 300 == 0):
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"   进度: {i}/{total} | 已扫{scanned}只 | 命中{len(hits)}只 | {elapsed:.0f}s")
        try:
            df, _ = read_klines(code)
            if df is None or len(df) < 30:
                continue
            hit, reasons = strategy['func'](df)
            if hit:
                cur = float(df['Close'].values[-1])
                chg = ((cur / float(df['Close'].values[-2])) - 1) * 100
                hits.append({'code': code, 'name': name, 'price': cur, 'chg_today': chg, 'reasons': reasons})
                if verbose:
                    print(f"  ✅ {name}({code}) 价{cur:.2f} 当日{chg:+.2f}%")
                    for r in reasons:
                        print(f"     {r}")
        except Exception:
            pass
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'='*60}")
    print(f"  扫描完成: {strategy['name']}")
    print(f"  候选池: {total}")
    print(f"  有效扫描: {scanned}")
    print(f"  命中: {len(hits)}")
    print(f"  耗时: {elapsed:.1f}s")
    for h in hits:
        print(f"  {h['name']}({h['code']}) 价{h['price']:.2f}")
    return hits


def analyze_stock(code):
    name = get_stock_name(code)
    df, end_date = read_klines(code)
    if df is None:
        print(f"❌ {name}({code}): 数据不足")
        return
    cur = float(df['Close'].values[-1])
    chg = ((cur / float(df['Close'].values[-2])) - 1) * 100
    print(f"\n{'='*60}")
    print(f"  缠论选股分析: {name}({code})")
    print(f"  最新日期: {end_date} | 价格: {cur:.2f} | 当日: {chg:+.2f}%")
    print(f"  数据: {len(df)}根K线")
    print(f"{'='*60}\n")
    for key, strategy in ALL_STRATEGIES.items():
        hit, reasons = strategy['func'](df)
        icon = "✅" if hit else "❌"
        print(f"  {icon} {strategy['name']} ({strategy['desc']})")
        for r in reasons:
            print(f"     {r}")
        print()


def main():
    parser = argparse.ArgumentParser(description="缠论选股器")
    parser.add_argument("--strategy", default=None, help=f"策略: {', '.join(ALL_STRATEGIES.keys())}")
    parser.add_argument("--all", action="store_true", help="全市场扫描")
    parser.add_argument("--stock", default=None, help="单只股票分析")
    parser.add_argument("--max", type=int, default=None, help="最多扫多少只")
    parser.add_argument("--list", action="store_true", help="列出所有策略")
    args = parser.parse_args()
    if args.list:
        print("可用策略:")
        for key, s in ALL_STRATEGIES.items():
            print(f"  {key}: {s['name']} — {s['desc']}")
        return
    if args.stock:
        analyze_stock(args.stock)
        return
    if args.strategy:
        scan_all(args.strategy, max_stocks=args.max)
        return
    parser.print_help()


if __name__ == "__main__":
    main()
