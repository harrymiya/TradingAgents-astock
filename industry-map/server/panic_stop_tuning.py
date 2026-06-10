"""
尾盘高胜率战法 — 参数调优回测
尝试不同参数组合找到最优
"""

import sqlite3
import os
import sys
import json

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')


def scan_and_backtest(conn, codes, all_dates, params):
    """
    单次回测
    params: {min_panic_chg, max_panic_chg, min_zt_count, min_stop_chg, 
             max_pullback, min_low_diff, hold_days, stop_profit, stop_loss}
    """
    min_panic = params.get('min_panic_chg', -3.5)
    max_panic = params.get('max_panic_chg', -30)
    min_zt = params.get('min_zt_count', 0)
    min_stop_chg = params.get('min_stop_chg', -99)
    max_pullback = params.get('max_pullback', -2)
    min_low_diff = params.get('min_low_diff', -1.5)
    hold_days = params.get('hold_days', 5)
    stop_profit = params.get('stop_profit', 5)
    stop_loss = params.get('stop_loss', 5)
    min_vol_ratio = params.get('min_vol_ratio', 0.8)
    
    date_set = set(all_dates)
    total_trades = 0
    wins = 0
    losses = 0
    total_ret = 0
    
    for ci, code in enumerate(codes):
        if ci % 500 == 0:
            print(f"  [{ci}/{len(codes)}] trades={total_trades}", end='\r')
        
        rows = conn.execute("""
            SELECT date, open, high, low, close, volume, amount
            FROM daily_klines WHERE code = ? ORDER BY date
        """, (code,)).fetchall()
        
        if len(rows) < 25:
            continue
        
        for i in range(24, len(rows)):
            window = rows[i-24:i+1]
            if len(window) > 80:
                window = window[-80:]
            
            signal = check_signal_raw(window, min_panic, max_panic, min_zt, 
                                       min_stop_chg, max_pullback, min_low_diff,
                                       min_vol_ratio)
            if not signal:
                continue
            
            tgt_date = window[-1][0]
            if tgt_date < '2023-06-01' or tgt_date > '2026-06-10':
                continue
            if tgt_date not in date_set:
                continue
            date_pos = all_dates.index(tgt_date)
            
            buy = signal['price']
            if buy <= 0:
                continue
            
            end_pos = date_pos + hold_days
            if end_pos >= len(all_dates):
                continue
            
            sell_row = conn.execute(
                "SELECT close FROM daily_klines WHERE code=? AND date=?",
                (code, all_dates[end_pos])).fetchone()
            if not sell_row:
                continue
            
            ret = (sell_row[0] / buy - 1) * 100
            
            # 止盈止损
            for check_i in range(1, hold_days + 1):
                cp = date_pos + check_i
                if cp >= len(all_dates):
                    break
                cr = conn.execute(
                    "SELECT close, high, low FROM daily_klines WHERE code=? AND date=?",
                    (code, all_dates[cp])).fetchone()
                if not cr:
                    continue
                
                rh = (cr[1] / buy - 1) * 100
                rl = (cr[2] / buy - 1) * 100
                
                if rl <= -stop_loss:
                    ret = rl
                    break
                if rh >= stop_profit:
                    ret = stop_profit * 0.5 + (cr[0] / buy - 1) * 100 * 0.5
                    break
            
            total_trades += 1
            if ret > 0:
                wins += 1
            else:
                losses += 1
            total_ret += ret
    
    wr = wins / total_trades * 100 if total_trades > 0 else 0
    avg_ret = total_ret / total_trades if total_trades > 0 else 0
    return total_trades, wr, avg_ret


def check_signal_raw(window, min_panic, max_panic, min_zt, 
                      min_stop_chg, max_pullback, min_low_diff, min_vol_ratio):
    """信号检查（纯逻辑，参数可调）"""
    if len(window) < 5:
        return None
    
    t0, t1 = window[-1], window[-2]
    
    # 涨停检查
    recent_22 = window[-22:-2] if len(window) >= 24 else window[-len(window)+2:-2]
    if len(recent_22) < 5:
        return None
    
    zt_count = 0
    for i in range(1, len(recent_22)):
        prev = recent_22[i-1][4]
        cur = recent_22[i][4]
        if prev > 0:
            if round(prev * 1.1, 2) - cur < 0.01:
                zt_count += 1
    if zt_count < min_zt:
        return None
    
    # 涨幅过滤
    if len(recent_22) >= 10:
        rise = (recent_22[-1][4] / recent_22[0][4] - 1) * 100
        if rise > 60:
            return None
    
    # 恐慌阴
    chg_panic = (t1[4] / window[-3][4] - 1) * 100 if window[-3][4] > 0 else 0
    if chg_panic > min_panic or chg_panic < max_panic:
        return None
    if t1[4] >= t1[1]:  # 必须真阴线
        return None
    body = abs(t1[4] - t1[1])
    rng = t1[2] - t1[3]
    if rng > 0 and body / rng < 0.3:
        return None
    # 放量
    if len(window) >= 8:
        avg_vol = sum(window[i][5] for i in range(-8, -1)) / 7
        if t1[5] < avg_vol * min_vol_ratio:
            return None
    
    # 停顿
    chg_stop = (t0[4] / t1[4] - 1) * 100 if t1[4] > 0 else 0
    if chg_stop < min_stop_chg:
        return None
    low_diff = (t0[3] - t1[3]) / t1[3] * 100 if t1[3] > 0 else 0
    if low_diff < min_low_diff:
        return None
    
    # 跳空
    if t0[1] < t1[4] * 0.97 and t0[1] < t1[4]:
        return None
    
    # 调整幅度
    recent_high = max(window[i][2] for i in range(-25, -1)) if len(window) >= 25 else window[-2][2]
    pullback = (t0[4] - recent_high) / recent_high * 100
    if pullback > max_pullback or pullback < -30:
        return None
    
    return {'price': t0[4]}


def run_tuning():
    conn = sqlite3.connect(DB_PATH)
    
    all_dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM daily_klines WHERE date>='2023-06-01' AND date<='2026-06-10' ORDER BY date"
    ).fetchall()]
    
    codes = [r[0] for r in conn.execute("""
        SELECT DISTINCT d.code FROM daily_klines d
        JOIN stocks s ON d.code = s.code
        WHERE s.name NOT LIKE '%ST%' AND s.name NOT LIKE '%退市%'
          AND d.code NOT LIKE '688%' AND d.code NOT LIKE '4%'
          AND d.code NOT LIKE '83%' AND d.code NOT LIKE '87%'
          AND d.code NOT LIKE '8%' AND d.code NOT LIKE '920%'
        ORDER BY d.code
    """).fetchall()]
    
    print(f"调优参数扫描: {len(codes)}只股票, {len(all_dates)}个交易日\n")
    
    configs = [
        # (params)
        # 基准
        {'min_panic_chg': -3.5, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -99, 'max_pullback': -2, 'min_low_diff': -1.5, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 0.8},
        # 更严恐慌跌幅
        {'min_panic_chg': -4.0, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -99, 'max_pullback': -2, 'min_low_diff': -1.5, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 0.8},
        # 恐慌更狠
        {'min_panic_chg': -5.0, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -99, 'max_pullback': -2, 'min_low_diff': -1.5, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 0.8},
        # 必须停顿阳（不跌）
        {'min_panic_chg': -4.0, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -0.5, 'max_pullback': -2, 'min_low_diff': -1.5, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 0.8},
        # 必须放量更大
        {'min_panic_chg': -4.0, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -99, 'max_pullback': -2, 'min_low_diff': -1.5, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 1.2},
        # 至少2个涨停
        {'min_panic_chg': -4.0, 'max_panic_chg': -30, 'min_zt_count': 2, 'min_stop_chg': -99, 'max_pullback': -2, 'min_low_diff': -1.5, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 0.8},
        # 低点不破（更严）
        {'min_panic_chg': -4.0, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -99, 'max_pullback': -2, 'min_low_diff': 0, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 0.8},
        # 更低调整
        {'min_panic_chg': -4.0, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -99, 'max_pullback': -5, 'min_low_diff': -1.5, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 0.8},
        # 更短持有
        {'min_panic_chg': -4.0, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -99, 'max_pullback': -2, 'min_low_diff': -1.5, 'hold_days': 3, 'stop_profit': 4, 'stop_loss': 3, 'min_vol_ratio': 0.8},
        # 更长持有
        {'min_panic_chg': -4.0, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -99, 'max_pullback': -2, 'min_low_diff': -1.5, 'hold_days': 10, 'stop_profit': 8, 'stop_loss': 5, 'min_vol_ratio': 0.8},
        # 组合：恐慌>5%+放量1.2+不破低点
        {'min_panic_chg': -5.0, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -99, 'max_pullback': -2, 'min_low_diff': 0, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 1.2},
        # 组合：恐慌>4%+至少1涨停+停顿不跌
        {'min_panic_chg': -4.0, 'max_panic_chg': -30, 'min_zt_count': 1, 'min_stop_chg': -1, 'max_pullback': -2, 'min_low_diff': -1, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 0.8},
        # 组合：恐慌>6%+放量+停顿阳
        {'min_panic_chg': -6.0, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -0.5, 'max_pullback': -2, 'min_low_diff': -1, 'hold_days': 5, 'stop_profit': 5, 'stop_loss': 5, 'min_vol_ratio': 1.0},
        # 宽松+快速
        {'min_panic_chg': -3.5, 'max_panic_chg': -30, 'min_zt_count': 0, 'min_stop_chg': -99, 'max_pullback': -1, 'min_low_diff': -2, 'hold_days': 3, 'stop_profit': 3, 'stop_loss': 3, 'min_vol_ratio': 0.7},
    ]
    
    labels = [
        "基准",
        "恐慌≥4%",
        "恐慌≥5%",
        "停顿不跌",
        "放量1.2x",
        "至少2涨停",
        "不破低点",
        "调整更深",
        "3日快进快出",
        "10日中长线",
        "恐慌5%+放量+不破低",
        "恐慌4%+1涨停+停顿",
        "恐慌6%+放量+阳线",
        "宽松+快进快出",
    ]
    
    results = []
    for i, params in enumerate(configs):
        print(f"\n--- 配置{i+1}: {labels[i]} ---")
        trades, wr, avg = scan_and_backtest(conn, codes, all_dates, params)
        print(f"  交易: {trades}, 胜率: {wr:.1f}%, 平均收益: {avg:+.2f}%")
        results.append((labels[i], trades, wr, avg, params))
    
    print(f"\n\n{'='*70}")
    print(f"调优结果排序（按胜率）")
    print(f"{'='*70}")
    results.sort(key=lambda x: x[2], reverse=True)
    for label, trades, wr, avg, _ in results:
        print(f"  {wr:5.1f}% | {avg:+6.2f}% | {trades:5d}次 | {label}")
    
    conn.close()


if __name__ == '__main__':
    run_tuning()
