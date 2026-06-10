"""
尾盘高胜率战法 — 回测脚本 V2
直接按目标日期取K线，不再依赖策略函数
"""

import sqlite3
import os
import sys
import json

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')


def get_klines_up_to(conn, code, target_date, lookback=80):
    """获取截止到target_date最近lookback天K线"""
    rows = conn.execute("""
        SELECT date, open, high, low, close, volume, amount
        FROM daily_klines WHERE code = ? AND date <= ?
        ORDER BY date DESC LIMIT ?
    """, (code, target_date, lookback)).fetchall()
    return list(reversed(rows))


def check_signal(klines):
    """
    检查恐慌阴+停顿阳战法信号（用原始K线判断，不依赖外部函数）
    
    K线格式: [(date, open, high, low, close, volume, amount), ...]
    最后一根=停顿阳(T-0)，倒数第二根=恐慌阴(T-1)
    """
    if not klines or len(klines) < 5:
        return None
    
    n = len(klines)
    t0 = klines[-1]  # 停顿阳
    t1 = klines[-2]  # 恐慌阴
    
    if n < 22:
        return None
    
    recent_22 = klines[-22:-2] if n >= 24 else klines[-n+2:-2]
    
    # === 条件1：前期有涨停板（近20天内） ===
    has_zt = False
    zt_count = 0
    recent_20_for_zt = recent_22[-20:] if len(recent_22) >= 20 else recent_22
    
    for i, k in enumerate(recent_20_for_zt):
        if i == 0:
            continue
        prev_close = recent_20_for_zt[i-1][4]
        cur_close = k[4]
        if prev_close > 0:
            if round(prev_close * 1.1, 2) - cur_close < 0.01:
                has_zt = True
                zt_count += 1
            elif round(prev_close * 1.2, 2) - cur_close < 0.01:
                has_zt = True
                zt_count += 1
    
    if not has_zt:
        return None
    
    # === 条件2：排除前期涨幅太大的 ===
    if len(recent_20_for_zt) >= 10:
        recent_rise = (recent_20_for_zt[-1][4] / recent_20_for_zt[0][4] - 1) * 100
        if recent_rise > 60:
            return None
    
    # === 条件3：恐慌阴跌幅 >= 3.5% ===
    t2 = klines[-3]
    chg_panic = (t1[4] / t2[4] - 1) * 100 if t2[4] > 0 else 0
    
    if chg_panic > -3.5:
        return None
    
    # 恐慌阴要真阴线
    if t1[4] >= t1[1]:
        return None
    
    # 恐慌阴实体不能太小
    panic_body = abs(t1[4] - t1[1])
    panic_range = t1[2] - t1[3]
    if panic_range > 0 and panic_body / panic_range < 0.3:
        return None
    
    # 恐慌阴放量（恐慌性抛售）
    if n >= 8:
        avg_vol_7 = sum(klines[i][5] for i in range(-8, -1)) / 7
        if t1[5] < avg_vol_7 * 0.8:
            return None
    
    # === 条件4：停顿阳不再恐慌 ===
    chg_stop = (t0[4] / t1[4] - 1) * 100 if t1[4] > 0 else 0
    
    if chg_stop < -2:
        return None
    
    # 停顿阳低点不破恐慌阴低点太多
    panic_low = t1[3]
    stop_low = t0[3]
    low_diff = (stop_low - panic_low) / panic_low * 100 if panic_low > 0 else 0
    
    if low_diff < -1:
        return None
    
    # === 条件5：排除跳空 ===
    if t0[1] < t1[4] * 0.97 and t0[1] < t1[4]:
        return None
    
    # === 条件6：调整幅度检查 ===
    if n >= 25:
        recent_high = max(klines[i][2] for i in range(-25, -1))
        pullback = (t0[4] - recent_high) / recent_high * 100
        if pullback > -2 or pullback < -30:
            return None
    
    return {
        'price': t0[4],
        'panic_chg': round(chg_panic, 2),
        'stop_chg': round(chg_stop, 2),
        'low_diff': round(low_diff, 2),
        'zt_count': zt_count,
        'panic_low': panic_low,
        'stop_low': stop_low,
    }


def backtest(start_date='2023-06-01', end_date='2026-06-10',
             hold_days=5, stop_profit_pct=5, stop_loss_pct=5):
    
    conn = sqlite3.connect(DB_PATH)
    
    all_dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM daily_klines WHERE date >= ? AND date <= ? ORDER BY date",
        (start_date, end_date)).fetchall()]
    
    stocks = conn.execute("""
        SELECT DISTINCT d.code, s.name FROM daily_klines d
        JOIN stocks s ON d.code = s.code
        WHERE s.name NOT LIKE '%ST%' AND s.name NOT LIKE '%退市%'
          AND d.code NOT LIKE '688%' AND d.code NOT LIKE '4%'
          AND d.code NOT LIKE '83%' AND d.code NOT LIKE '87%'
          AND d.code NOT LIKE '8%' AND d.code NOT LIKE '920%'
        ORDER BY d.code
    """).fetchall()
    
    codes = [r[0] for r in stocks]
    name_map = {r[0]: r[1] for r in stocks}
    
    print(f"回测: {start_date} ~ {end_date}, {len(all_dates)}个交易日, {len(codes)}只股票")
    print(f"持仓: {hold_days}天, 止盈{stop_profit_pct}%, 止损{stop_loss_pct}%\n")
    
    # Date → code list
    signal_cache = {}
    
    # 每只股票逐日检查
    for si, code in enumerate(codes):
        if si % 200 == 0:
            print(f"  扫描进度: {si}/{len(codes)}", end='\r')
        
        # 获取该股全部日线
        rows = conn.execute("""
            SELECT date, open, high, low, close, volume, amount
            FROM daily_klines WHERE code = ? ORDER BY date
        """, (code,)).fetchall()
        
        if len(rows) < 25:
            continue
        
        # 对每个交易日检查（从第25天开始）
        for i in range(24, len(rows)):
            kline_window = rows[i-24:i+1]  # 25~80天
            if len(kline_window) > 80:
                kline_window = kline_window[-80:]
            
            result = check_signal(kline_window)
            if result:
                signal_date = rows[i][0]
                if signal_date < start_date:
                    continue
                
                if signal_date not in signal_cache:
                    signal_cache[signal_date] = []
                signal_cache[signal_date].append({
                    'code': code,
                    'name': name_map.get(code, '?'),
                    'price': result['price'],
                    'panic_chg': result['panic_chg'],
                    'stop_chg': result['stop_chg'],
                    'zt_count': result['zt_count'],
                    'panic_low': result['panic_low'],
                    'stop_low': result['stop_low'],
                })
    
    print(f"  扫描完成: {sum(len(v) for v in signal_cache.values())}个信号\n")
    
    # ===== 交易模拟 =====
    # 信号日尾盘买入 → 持有hold_days天
    total_trades = 0
    wins = 0
    losses = 0
    total_return = 0
    max_win = 0
    max_loss = 0
    trade_log = []
    date_set = set(all_dates)
    
    for si, (signal_date, signals) in enumerate(signal_cache.items()):
        if si % 100 == 0:
            print(f"  交易模拟: {si}/{len(signal_cache)}日", end='\r')
        
        # 找signal_date在all_dates中的位置
        if signal_date not in date_set:
            continue
        date_pos = all_dates.index(signal_date)
        
        for signal in signals:
            code = signal['code']
            buy_price = signal['price']
            
            if buy_price <= 0:
                continue
            
            # 找hold_days后的日期
            end_pos = date_pos + hold_days
            if end_pos >= len(all_dates):
                continue
            
            sell_date = all_dates[end_pos]
            sell_row = conn.execute(
                "SELECT close FROM daily_klines WHERE code = ? AND date = ?",
                (code, sell_date)).fetchone()
            
            if not sell_row:
                continue
            
            sell_price = sell_row[0]
            ret = (sell_price / buy_price - 1) * 100
            
            # 持有期内止盈止损检查
            for check_i in range(1, hold_days + 1):
                check_pos = date_pos + check_i
                if check_pos >= len(all_dates):
                    break
                check_date_str = all_dates[check_pos]
                check_row = conn.execute(
                    "SELECT close, high, low FROM daily_klines WHERE code = ? AND date = ?",
                    (code, check_date_str)).fetchone()
                if not check_row:
                    continue
                
                high, low = check_row[1], check_row[2]
                ret_high = (high / buy_price - 1) * 100
                ret_low = (low / buy_price - 1) * 100
                
                if ret_low <= -stop_loss_pct:
                    ret = ret_low  # 止损
                    break
                if ret_high >= stop_profit_pct:
                    # 冲高止盈，算半仓止盈+半仓收盘
                    ret = stop_profit_pct * 0.5 + (check_row[0] / buy_price - 1) * 100 * 0.5
                    break
            
            total_trades += 1
            if ret > 0:
                wins += 1
            else:
                losses += 1
            
            total_return += ret
            max_win = max(max_win, ret)
            max_loss = min(max_loss, ret)
            
            trade_log.append({
                'date': signal_date,
                'code': code,
                'name': signal['name'],
                'buy': round(buy_price, 2),
                'ret': round(ret, 2),
                'panic_chg': signal['panic_chg'],
                'detail': f"恐慌{signal['panic_chg']:+.0f}%→停顿{signal['stop_chg']:+.0f}%, 涨停{signal['zt_count']}次"
            })
    
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"【尾盘高胜率战法】回测结果")
    print(f"{'='*60}")
    print(f"回测区间: {start_date} ~ {end_date}")
    print(f"交易次数: {total_trades}")
    
    if total_trades == 0:
        print("无任何交易信号!")
        return
    
    win_rate = wins / total_trades * 100
    avg_ret = total_return / total_trades
    avg_win = sum(t['ret'] for t in trade_log if t['ret'] > 0) / max(wins, 1)
    avg_loss = sum(t['ret'] for t in trade_log if t['ret'] <= 0) / max(losses, 1)
    
    print(f"盈利次数: {wins} ({win_rate:.1f}%)")
    print(f"亏损次数: {losses}")
    print(f"平均收益: {avg_ret:+.2f}%")
    print(f"平均盈利: {avg_win:+.2f}%")
    print(f"平均亏损: {avg_loss:+.2f}%")
    print(f"盈亏比: {abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "盈亏比: inf")
    print(f"最大盈利: {max_win:+.2f}%")
    print(f"最大亏损: {max_loss:+.2f}%")
    
    # 胜率区间分布
    win_groups = {'>=10%': 0, '5-10%': 0, '0-5%': 0, '-5-0%': 0, '<-5%': 0}
    for t in trade_log:
        r = t['ret']
        if r >= 10: win_groups['>=10%'] += 1
        elif r >= 5: win_groups['5-10%'] += 1
        elif r >= 0: win_groups['0-5%'] += 1
        elif r >= -5: win_groups['-5-0%'] += 1
        else: win_groups['<-5%'] += 1
    
    print(f"\n收益分布:")
    for k, v in win_groups.items():
        print(f"  {k}: {v}次 ({v/total_trades*100:.1f}%)")
    
    # Best/Worst
    trade_log.sort(key=lambda x: x['ret'], reverse=True)
    print(f"\n最佳5次:")
    for t in trade_log[:5]:
        print(f"  {t['date']} {t['code']} {t['name']:<8} 买入{t['buy']:.2f} 收益{t['ret']:+.1f}% {t['detail']}")
    
    print(f"\n最差5次:")
    for t in trade_log[-5:]:
        print(f"  {t['date']} {t['code']} {t['name']:<8} 买入{t['buy']:.2f} 收益{t['ret']:+.1f}% {t['detail']}")
    
    # 保存
    with open('/tmp/panic_backtest_result.json', 'w') as f:
        json.dump({
            'total_trades': total_trades, 'win_rate': round(win_rate, 1),
            'avg_return': round(avg_ret, 2), 'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2), 'max_win': round(max_win, 2),
            'max_loss': round(max_loss, 2),
        }, f)


if __name__ == '__main__':
    backtest(start_date='2023-06-01', end_date='2026-06-10',
             hold_days=5, stop_profit_pct=5, stop_loss_pct=5)
