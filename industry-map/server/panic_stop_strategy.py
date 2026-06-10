"""
尾盘高胜率战法 — 恐慌阴+停顿阳选股器

核心逻辑：
  1. 前期有涨停板（近20日内涨停，代表有人气）
  2. 从高点调整下来，最后出一根大阴线（恐慌阴，当日跌幅>=4%）
  3. 第2天不再继续恐慌，出现停顿（小阳/十字星/小阴线）
  4. 停顿阳的低点不破恐慌阴低点（或破不超过1%）
  5. 排除顶部特征（无跳空缺口/连续涨停不超过5个）
  6. 30分钟级别MACD即将金叉（辅助条件）

买入：恐慌阴后第2天尾盘（14:50后）
止损：恐慌阴或停顿阳的最低点
止盈：+5%减半仓，+10%继续减
"""

import sqlite3
import os
import sys
from datetime import datetime, timedelta
import urllib.request
import json

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')

def get_last_trade_date(conn):
    """获取数据库中最新的交易日"""
    row = conn.execute("SELECT DISTINCT date FROM daily_klines ORDER BY date DESC LIMIT 1").fetchone()
    return row[0] if row else None

def get_stock_list(conn):
    """获取可交易的股票列表（排除ST/科创板/北交所/退市）"""
    rows = conn.execute("""
        SELECT DISTINCT d.code, s.name FROM daily_klines d
        JOIN stocks s ON d.code = s.code
        WHERE s.name NOT LIKE '%ST%' 
          AND s.name NOT LIKE '%退市%'
          AND d.code NOT LIKE '688%'
          AND d.code NOT LIKE '4%'
          AND d.code NOT LIKE '83%'
          AND d.code NOT LIKE '87%'
          AND d.code NOT LIKE '8%'
          AND d.code NOT LIKE '920%'
        ORDER BY d.code
    """).fetchall()
    return [(r[0], r[1]) for r in rows]

def get_klines(conn, code, days=120):
    """获取日K线数据（最新N天，返回正序：最早→最新）"""
    rows = conn.execute("""
        SELECT date, open, high, low, close, volume, amount
        FROM daily_klines WHERE code = ? ORDER BY date DESC LIMIT ?
    """, (code, days)).fetchall()
    rows = list(reversed(rows))  # 正序
    return rows

def check_panic_stop_strategy(klines, lookback=60):
    """
    检查恐慌阴+停顿阳战法
    
    参数:
        klines: 正序日K线列表 [(date, open, high, low, close, volume, amount), ...]
        lookback: 向后看的K线数量
    
    返回:
        dict: {match: bool, detail: str, panic_idx: int, stop_idx: int, ...}
    """
    if not klines or len(klines) < 5:
        return {'match': False, 'detail': '数据不足'}
    
    n = len(klines)
    
    # 最新5条K线
    t0 = klines[-1]  # 今天（停顿阳）
    t1 = klines[-2]  # 昨天（恐慌阴）
    
    # 需要至少20根K线来看前面涨停
    if n < 20:
        return {'match': False, 'detail': '历史数据不足20天'}
    
    # 收集最近60天的K线
    recent = klines[-min(lookback, n):]
    
    # ===== 条件1：前期有涨停板（近20天内） =====
    recent_20 = klines[-22:-2] if n >= 22 else klines[-n+2:-2]
    zt_days = []
    for i, k in enumerate(recent_20):
        if i == 0: continue
        prev_close = recent_20[i-1][4]
        cur_close = k[4]
        if prev_close > 0 and round(prev_close * 1.1, 2) - cur_close < 0.01:
            zt_days.append((k[0], k[4]))
        # 创业板/科创板20%涨停
        elif prev_close > 0 and round(prev_close * 1.2, 2) - cur_close < 0.01:
            zt_days.append((k[0], k[4]))
    
    if len(zt_days) == 0:
        return {'match': False, 'detail': '近20日无涨停'}
    
    # ===== 条件2：排除连续涨停太多的（无量市场不选5-6个涨停的） =====
    # 算近期涨幅
    if len(recent_20) >= 10:
        recent_rise = (recent_20[-1][4] / recent_20[0][4] - 1) * 100
        # 排除涨幅太高的（市场缩量时）
        if recent_rise > 60:
            return {'match': False, 'detail': f'前期涨幅过大({recent_rise:.0f}%)，排除'}
    
    # ===== 条件3：恐慌阴（T-1）当日跌幅 >= 4% =====
    t1_close = t1[4]
    t1_open = t1[1]
    # 算跌幅
    if len(klines) >= 3:
        t2 = klines[-3]
        chg_panic = (t1_close / t2[4] - 1) * 100
    else:
        chg_panic = 0
    
    if chg_panic > -3.5:  # 放宽到-3.5%，实际回测时可调整
        return {'match': False, 'detail': f'恐慌阴跌幅不足({chg_panic:+.1f}%)'}
    
    # 恐慌阴是阴线（收盘 < 开盘）
    if t1_close >= t1_open:
        return {'match': False, 'detail': '恐慌阴不是阴线'}
    
    # ===== 条件4：恐慌阴成交量放大（恐慌性抛售） =====
    if len(klines) >= 8:
        avg_vol_5 = sum(k[5] for k in klines[-8:-1]) / 7
        if t1[5] < avg_vol_5 * 0.8:
            return {'match': False, 'detail': '恐慌阴量能不足'}
    
    # ===== 条件5：停顿阳（T-0）不再继续恐慌 =====
    t0_close = t0[4]
    t0_open = t0[1]
    
    # 停顿阳收盘应该在恐慌阴收盘附近或上方（不继续大跌）
    chg_stop = (t0_close / t1_close - 1) * 100 if t1_close > 0 else 0
    
    # 停顿日跌幅不能超过-2%（就是不继续暴跌）
    if chg_stop < -2:
        return {'match': False, 'detail': f'停顿日继续大跌({chg_stop:+.1f}%)'}
    
    # 停顿阳低点不破恐慌阴低点（或破的不深）
    panic_low = t1[3]  # 恐慌阴最低点
    stop_low = t0[3]   # 停顿阳最低点
    
    low_diff_pct = (stop_low - panic_low) / panic_low * 100 if panic_low > 0 else 0
    
    # 破恐慌阴低点不超过1%
    if low_diff_pct < -1:
        return {'match': False, 'detail': f'停顿阳破恐慌阴过低({low_diff_pct:+.1f}%)'}
    
    # ===== 条件6：排除顶部特征 =====
    # 恐慌阴后不能有跳空缺口向下
    if t0_open < t1_close * 0.97 and t0_open < t1_close:
        # 跳空低开超过3%算跳空
        return {'match': False, 'detail': '恐慌后有跳空缺口'}
    
    # 排除恐慌阴实体太小
    panic_body = abs(t1_close - t1_open)
    panic_range = t1[2] - t1[3]  # high - low
    if panic_range > 0 and panic_body / panic_range < 0.3:
        return {'match': False, 'detail': '恐慌阴实体太小，可能不是真恐慌'}
    
    # ===== 条件7：从高点下来调整了一段时间 =====
    # 最近20天最高点
    if len(klines) >= 25:
        recent_high = max(k[2] for k in klines[-25:-1])
        current_close = t0_close
        pullback = (current_close - recent_high) / recent_high * 100
        # 调整幅度应该在-3%到-25%之间
        if pullback > -2:
            return {'match': False, 'detail': f'调整幅度不够({pullback:+.1f}%)'}
        if pullback < -30:
            return {'match': False, 'detail': f'调整过深({pullback:+.1f}%)'}
    
    # 全部条件通过！
    return {
        'match': True,
        'detail': f'恐慌跌{chg_panic:.1f}%→停顿{chg_stop:+.1f}%, 低点差{low_diff_pct:+.1f}%, 涨停{len(zt_days)}次',
        'panic_chg': round(chg_panic, 2),
        'stop_chg': round(chg_stop, 2),
        'low_diff': round(low_diff_pct, 2),
        'zt_count': len(zt_days),
        'price': t0_close,
        'panic_date': t1[0],
        'stop_date': t0[0],
        'panic_low': panic_low,
        'stop_low': stop_low,
    }


def scan_all(conn, target_date=None):
    """全市场扫描"""
    if target_date is None:
        target_date = get_last_trade_date(conn)
    
    stocks = get_stock_list(conn)
    results = []
    
    print(f"开始全市场扫描 {target_date}，共{len(stocks)}只股票...")
    
    for idx, (code, name) in enumerate(stocks):
        if idx % 500 == 0:
            print(f"  进度: {idx}/{len(stocks)}")
        
        klines = get_klines(conn, code, 80)
        result = check_panic_stop_strategy(klines)
        
        if result['match']:
            results.append({
                'code': code,
                'name': name,
                'price': result['price'],
                'panic_chg': result['panic_chg'],
                'stop_chg': result['stop_chg'],
                'low_diff': result['low_diff'],
                'zt_count': result['zt_count'],
                'detail': result['detail'],
                'panic_date': result['panic_date'],
                'stop_date': result['stop_date'],
                'panic_low': result['panic_low'],
                'stop_low': result['stop_low'],
            })
    
    # 按恐慌跌幅排序（跌得最狠的排前面）
    results.sort(key=lambda r: r['panic_chg'])
    
    return results


def run_scan(output=True):
    """运行扫描"""
    conn = sqlite3.connect(DB_PATH)
    last_date = get_last_trade_date(conn)
    print(f"最新交易日: {last_date}")
    
    results = scan_all(conn, last_date)
    
    conn.close()
    
    if output:
        print(f"\n{'='*70}")
        print(f"尾盘高胜率战法 — 全市场扫描结果 ({last_date})")
        print(f"共选出 {len(results)} 只")
        print(f"{'='*70}")
        print(f"{'代码':>6} {'名称':<8} {'价格':>7} {'恐慌跌幅':>8} {'停顿涨幅':>8} {'低点差':>6} {'涨停次数':>6}  {'详情'}")
        print(f"{'-'*70}")
        for r in results[:20]:
            print(f"{r['code']} {r['name']:<8} {r['price']:>7.2f} {r['panic_chg']:>+7.1f}% {r['stop_chg']:>+7.1f}% {r['low_diff']:>+5.1f}% {r['zt_count']:>5d}次  {r['detail']}")
    
    return results


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--scan':
        run_scan()
    else:
        print("用法: python3 panic_stop_strategy.py --scan")
