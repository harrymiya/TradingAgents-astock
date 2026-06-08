#!/usr/bin/env python3
"""
游资短线选股器 — 基于18位顶级游资心法 + 情绪流龙头战法 + 短线训练营

策略:
  1. qiangshi:  游资强势股  (炒股养家/赵老哥 — "要做就做最强")
  2. dixi:      游资低吸    (炒股养家/爱在冰川 — "横盘龙头低吸")
  3. fanbao:    游资反包    (短线训练营/闻少 — "弱转强/反包竞价")

用法:
  cd /home/harrydolly/code/TradingAgents-astock
  source .venv/bin/activate

  python3 youzi_screener.py --strategy qiangshi --all
  python3 youzi_screener.py --strategy dixi --all
  python3 youzi_screener.py --strategy fanbao --all
  python3 youzi_screener.py --stock 000608
"""

import sys, os, argparse
import numpy as np
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

import sqlite3
import pandas as pd

from tradingagents.dataflows.astock_db import (
    DB_PATH, get_stock_list, get_klines
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
# 策略1: 游资强势股 — "要做就做最强"
# ============================================================

def check_qiangshi(df):
    """
    炒股养家/赵老哥模式：强势股识别
    
    核心条件（源自养家心法）：
    1. "要做就做最强，选股选大众情人"
    2. "强势阶段做最强个股的主升浪"
    3. "有赚钱效应的情况下，做热点为主"
    
    日线级别实现：
    - 最近3日有大涨（≥5%或涨停），说明强势
    - 成交量放大（有资金关注）
    - 均线多头排列（趋势向上）
    - 不是已经连板太多（避免接盘）
    """
    if df is None or len(df) < 20:
        return False, []

    close = df['Close'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    vol = df['Volume'].values.astype(float)
    n = len(df)
    reasons = []

    # 1. 最近3日有大涨
    recent_high = max(high[-3:])
    base_price = close[-4] if n >= 4 else close[-3]
    max_chg = (recent_high - base_price) / base_price * 100

    if max_chg < 4:
        return False, ["近3日无强势表现（最大涨幅{:.1f}% < 4%）".format(max_chg)]

    reasons.append("近3日最大涨幅{:.1f}%".format(max_chg))

    # 2. 成交量放大（比之前放量）
    vol_ma20 = pd.Series(vol).rolling(20).mean().values
    vol_ratio = vol[-5:].mean() / vol_ma20[-1] if vol_ma20[-1] > 0 else 1

    if vol_ratio < 1.2:
        pass  # 不强制放量
    else:
        reasons.append("成交量放大{:.1f}倍".format(vol_ratio))

    # 3. 均线多头排列
    ma5 = pd.Series(close).rolling(5).mean().values
    ma10 = pd.Series(close).rolling(10).mean().values
    ma20 = pd.Series(close).rolling(20).mean().values

    # 最近3日均线与短期均线关系
    if ma5[-1] > ma10[-1] > ma20[-1]:
        reasons.append("均线多头排列（MA5>MA10>MA20）")
    elif ma5[-1] > ma10[-1]:
        reasons.append("MA5>MA10")
    elif ma5[-1] > ma20[-1]:
        reasons.append("股价在MA20之上")

    # 4. 当前价在均线上方（趋势未破）
    if close[-1] < ma10[-1] * 0.95:
        return False, ["已跌破MA10（{}, {:.2f} < {:.2f}）".format(
            len(reasons), close[-1], ma10[-1])]

    # 5. 检查是否为近期新高（但非极端高位——赵老哥不接最后一棒）
    high_60 = max(high[-60:]) if n >= 60 else max(high)
    if close[-1] >= high_60 * 0.95:
        reasons.append("接近60日高点（强势）")

    reasons.append("✅ 游资强势股特征")
    return True, reasons


# ============================================================
# 策略2: 游资低吸 — "横盘龙头低吸/超跌反弹"
# ============================================================

def check_dixi(df):
    """
    炒股养家/爱在冰川模式：低吸信号
    
    核心条件：
    1. 养家："弱势阶段做超跌反弹，大部分第二天冲高就走"
    2. 养家："超跌的品种稳住了，强势的个股机会就大些"
    3. 爱在冰川："横盘龙头低吸"
    4. 短线训练营："强势股低吸"、"超跌低吸"
    
    日线级别：
    - 之前有明显上涨（证明是强势股）
    - 最近3-8日回调（从高点回落）
    - 回调缩量（惜售）
    - 不破关键支撑（MA20/MA60）
    - 有企稳迹象（最后几天小阳线/锤子线）
    """
    if df is None or len(df) < 25:
        return False, []

    close = df['Close'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    vol = df['Volume'].values.astype(float)
    n = len(df)
    reasons = []

    # 1. 之前有上涨（证明是强势股/有主力关注）
    # 找最近30天内的最高点
    lookback = min(30, n - 5)
    max_idx = np.argmax(high[-lookback:]) + (n - lookback)
    max_price = high[max_idx]
    peak_days_ago = n - 1 - max_idx

    if peak_days_ago < 2 or peak_days_ago > 12:
        return False, ["高点距今{:.0f}天，不在2-10天理想范围".format(peak_days_ago)]

    # 从低点到高点的涨幅
    pre_low = min(low[max_idx - min(15, max_idx):max_idx + 1])
    pre_chg = (max_price - pre_low) / pre_low * 100
    if pre_chg < 8:
        return False, ["前期涨幅{:.1f}% < 8%（不够强势）".format(pre_chg)]

    reasons.append("前期从{:.2f}涨到{:.2f}（{:.1f}%），强势股特征".format(
        pre_low, max_price, pre_chg))

    # 2. 从高点回调
    pullback = (max_price - close[-1]) / max_price * 100
    if pullback < 2:
        return False, ["回调不足（{:.1f}% < 2%）".format(pullback)]
    if pullback > 20:
        return False, ["回调过深（{:.1f}% > 20%），可能已破位".format(pullback)]

    reasons.append("从{:.2f}回调{:.1f}%".format(max_price, pullback))

    # 3. 回调缩量（惜售/分歧减小）
    vol_ma5 = pd.Series(vol).rolling(5).mean().values
    vol_ma20 = pd.Series(vol).rolling(20).mean().values
    recent_vol = vol[-3:].mean() if n >= 3 else vol[-1]
    vol_shrink = recent_vol / vol_ma20[-1] if vol_ma20[-1] > 0 else 1

    if vol_shrink < 1.2:
        reasons.append("缩量回调（量比{:.2f}）".format(vol_shrink))
    elif vol_shrink < 1.8:
        reasons.append("量能温和（量比{:.2f}）".format(vol_shrink))
    else:
        reasons.append("量能偏大（量比{:.2f}），可能仍有抛压".format(vol_shrink))

    # 4. 检查支撑
    ma20 = pd.Series(close).rolling(20).mean().values
    ma60 = pd.Series(close).rolling(60).mean().values if n >= 60 else ma20

    if close[-1] > ma20[-1]:
        reasons.append("在MA20({:.2f})上方，支撑有效".format(ma20[-1]))
    elif close[-1] > ma60[-1]:
        reasons.append("跌破MA20但仍在MA60({:.2f})上方".format(ma60[-1]))
    else:
        return False, ["跌破MA60({:.2f})，支撑失效".format(ma60[-1])]

    # 5. 企稳迹象——最后2天收阳或十字星
    if close[-1] > close[-2] and close[-2] > close[-3] if n >= 3 else True:
        reasons.append("最后两日连阳企稳")
    elif close[-1] > close[-2]:
        reasons.append("最后一日收阳企稳")

    # 6. 空间势能（素论概念）——当前价在ZG附近
    from chanlun_screener import find_zones
    zones = find_zones(df)
    if zones:
        last_zone = zones[-1]
        dist_from_zg = (close[-1] - last_zone['zg']) / last_zone['zg'] * 100
        if -8 < dist_from_zg < 2:
            reasons.append("当前价在ZG({:.2f})附近，空间势能足".format(last_zone['zg']))

    reasons.append("✅ 游资低吸信号")
    return True, reasons


# ============================================================
# 策略3: 游资反包 — "弱转强/反包竞价"
# ============================================================

def check_fanbao(df):
    """
    短线训练营/闻少模式：反包信号
    
    核心条件：
    1. 短线训练营："弱转强竞价 — 昨天烂板今天竞价走强→连板"
    2. 短线训练营："昨涨停被砸，今天竞价量增价高→低吸反包"
    3. 闻少："分歧转一致"、"弱转强模式"
    
    日线级别：
    - 昨日涨停被砸/冲高回落（上影线）
    - 今日上涨（反包修复）
    - 今日成交量不能太小（有资金参与）
    """
    if df is None or len(df) < 10:
        return False, []

    close = df['Close'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    open_ = df['Open'].values.astype(float)
    vol = df['Volume'].values.astype(float)
    n = len(df)
    reasons = []

    if n < 3:
        return False, ["数据不足"]
    
    # 昨日数据
    y_close = close[-2]
    y_high = high[-2]
    y_low = low[-2]
    y_open = open_[-2]
    
    # 今日数据
    t_close = close[-1]
    t_high = high[-1]
    t_open = open_[-1]
    
    # 前日数据
    b_close = close[-3] if n >= 3 else None

    # 1. 昨日有上影线（冲高回落）
    y_upper_shadow = (y_high - max(y_close, y_open)) / (y_high - y_low) * 100 if y_high > y_low else 0
    
    if y_upper_shadow < 20 and y_high - y_close < 1.5:
        return False, ["昨日无明显上影线"]

    reasons.append("昨日上影线占比{:.0f}%".format(y_upper_shadow))

    # 2. 昨日涨幅较大（至少冲高3%以上）
    y_chg = (y_high - y_open) / y_open * 100 if y_open > 0 else 0
    if y_chg < 3:
        return False, ["昨日冲高幅度{:.1f}% < 3%".format(y_chg)]
    
    reasons.append("昨日最高冲高{:.1f}%".format(y_chg))

    # 3. 今日上涨（反包特征）
    t_chg = (t_close - y_close) / y_close * 100
    if t_chg < 0.5:
        return False, ["今日涨幅{:.2f}% < 0.5%，无反包动作".format(t_chg)]
    
    reasons.append("今日+{:.2f}%，反包修复中".format(t_chg))

    # 4. 今日量能——比昨日缩量或放量（不同模式）
    vol_ma5 = pd.Series(vol).rolling(5).mean().values
    t_vol_ratio = vol[-1] / vol_ma5[-1] if vol_ma5[-1] > 0 else 1
    
    if t_vol_ratio > 1.2:
        reasons.append("今日量能放大{:.1f}倍（有资金认可）".format(t_vol_ratio))
    elif t_vol_ratio > 0.7:
        reasons.append("量能维持（量比{:.1f}）".format(t_vol_ratio))
    
    # 5. 如果今日站上昨日最高→强反包
    if t_close > y_high:
        reasons.append("✅ 今日收盘站上昨日最高，强反包！")
    elif t_high > y_high:
        reasons.append("今日最高突破昨日高点")
    
    # 6. 反包类型识别
    if t_close > y_high:
        reasons.append("类型：强反包（阳包阴）")
    elif t_close > y_close:
        reasons.append("类型：弱反包（修复中）")

    reasons.append("✅ 游资反包信号")
    return True, reasons


# ============================================================
# 策略注册
# ============================================================

ALL_STRATEGIES = {
    'qiangshi': {
        'name': '游资强势股',
        'desc': '养家/赵老哥—要做就做最强',
        'func': check_qiangshi,
    },
    'dixi': {
        'name': '游资低吸',
        'desc': '养家/爱在冰川—横盘龙头低吸+超跌反弹',
        'func': check_dixi,
    },
    'fanbao': {
        'name': '游资反包',
        'desc': '短线训练营/闻少—弱转强+反包竞价',
        'func': check_fanbao,
    },
}


# ============================================================
# 扫描引擎
# ============================================================

def scan_all(strategy_name='qiangshi', max_stocks=None, verbose=True):
    strategy = ALL_STRATEGIES.get(strategy_name)
    if not strategy:
        print(f"❌ 未知策略: {strategy_name}")
        print(f"   可用: {', '.join(ALL_STRATEGIES.keys())}")
        return []

    stocks = get_stock_list()
    if max_stocks:
        stocks = stocks[:max_stocks]

    hits = []
    total = len(stocks)
    start_time = datetime.now()
    scanned = 0

    print(f"📡 游资选股 — {strategy['name']}（{strategy['desc']}）")
    print(f"   候选池: {total}只")
    print(f"   数据来源: SQLite\n")

    for i, (code, name) in enumerate(stocks, 1):
        if not is_valid_ticker(code, name or ""):
            continue
        scanned += 1

        if verbose and i % 500 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"   进度: {i}/{total} | 已扫{scanned}只 | 命中{len(hits)}只 | {elapsed:.0f}s")

        try:
            df, _ = read_klines(code)
            if df is None or len(df) < 25:
                continue
            hit, reasons = strategy['func'](df)
            if hit:
                cur = float(df['Close'].values[-1])
                chg = ((cur / float(df['Close'].values[-2])) - 1) * 100
                hits.append({
                    'code': code, 'name': name,
                    'price': cur, 'chg_today': chg,
                    'reasons': reasons,
                })
                if verbose:
                    print(f"  ✅ {name}({code}) 价{cur:.2f} 当日{chg:+.2f}%")
                    for r in reasons:
                        print(f"     {r}")
        except:
            pass

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'=' * 60}")
    print(f"  扫描完成: {strategy['name']}")
    print(f"  候选: {total} | 有效: {scanned} | 命中: {len(hits)} | 耗时: {elapsed:.1f}s")
    for h in hits:
        print(f"  {h['name']}({h['code']}) 价{h['price']:.2f} 当日{h['chg_today']:+.2f}%")
    return hits


def analyze_stock(code):
    name = get_stock_name(code)
    df, end_date = read_klines(code)
    if df is None:
        print(f"❌ {name}({code}): 数据不足")
        return

    cur = float(df['Close'].values[-1])
    chg = ((cur / float(df['Close'].values[-2])) - 1) * 100

    print(f"\n{'=' * 60}")
    print(f"  游资选股分析: {name}({code})")
    print(f"  最新: {end_date} | 价: {cur:.2f} | 当日: {chg:+.2f}% | 数据: {len(df)}根K线")
    print(f"{'=' * 60}\n")

    for key, strategy in ALL_STRATEGIES.items():
        hit, reasons = strategy['func'](df)
        icon = "✅" if hit else "❌"
        print(f"  {icon} {strategy['name']} ({strategy['desc']})")
        for r in reasons:
            print(f"     {r}")
        print()


def main():
    parser = argparse.ArgumentParser(description="游资短线选股器")
    parser.add_argument("--strategy", default=None,
                        help=f"策略: {', '.join(ALL_STRATEGIES.keys())}")
    parser.add_argument("--all", action="store_true", help="全市场扫描")
    parser.add_argument("--stock", default=None, help="单只分析")
    parser.add_argument("--max", type=int, default=None, help="上限")
    parser.add_argument("--list", action="store_true", help="列出策略")
    args = parser.parse_args()

    if args.list:
        print("游资短线选股策略:")
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
