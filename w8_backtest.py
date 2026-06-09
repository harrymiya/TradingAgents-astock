#!/usr/bin/env python3
"""
W8选股器 历史回测脚本
用feat表历史数据模拟W8的8维度评分，验证TOP20的T+5收益

流程：
  1. 对每个交易日，从feat表取出当日所有股票的特征数据
  2. 用W8的8个Analyst逻辑（基于feat字段）算出当日评分
  3. 取TOP20 -> T+1开盘买入 -> T+5收盘卖出
  4. 统计胜率、盈亏比、最大回撤、夏普比率

用法：
  python3 w8_backtest.py                    # 全量回测
  python3 w8_backtest.py --sample 100        # 抽样回测（快）
  python3 w8_backtest.py --year 2025         # 指定年份
"""

import sqlite3
import os
import sys
import time
import math
from datetime import datetime, date
from collections import defaultdict

DB = os.path.expanduser("~/.hermes/astock_data.db")

# ============================================================
# W8 Score 模拟函数（基于feat预计算字段，不走Python Analyst类）
# 这是为了回测速度优化的版本——全部用SQLite窗口函数能算的字段
# ============================================================

def compute_w8_from_feat(row):
    """
    基于feat表单行数据，模拟W8的8维度评分
    row: (code, date, close, open, high, low, volume,
          chg, amp, vr_5, vr_20, ma5, ma10, ma20, ma60,
          ma20_pct, ma60_pct, pos_20d, pos_60d, down_days, up_days)
    返回: total_score (0-80)
    """
    if row is None:
        return 0
    
    chg = row[7] if row[7] is not None else 0
    amp = row[8] if row[8] is not None else 0
    vr_5 = row[9] if row[9] is not None else 1
    vr_20 = row[10] if row[10] is not None else 1
    ma5 = row[11] if row[11] is not None else 0
    ma10 = row[12] if row[12] is not None else 0
    ma20 = row[13] if row[13] is not None else 0
    ma60 = row[14] if row[14] is not None else 0
    ma20_pct = row[15] if row[15] is not None else 0
    ma60_pct = row[16] if row[16] is not None else 0
    pos_20d = row[17] if row[17] is not None else 50
    pos_60d = row[18] if row[18] is not None else 50
    down_days = row[19] if row[19] is not None else 0
    up_days = row[20] if row[20] is not None else 0
    close = row[2]
    volume = row[6]
    
    total = 0
    
    # === 市场 (0-10) ===
    mk = 0
    # 均线0-4
    if close > ma5: mk += 1
    if ma5 > ma10: mk += 1
    if ma10 > ma20: mk += 1
    if close > ma20: mk += 1
    # 位置0-3
    if pos_20d < 20: mk += 3
    elif pos_20d < 35: mk += 2
    elif pos_20d < 50: mk += 1
    # MACD模拟0-2
    mk += 0  # feat表无MACD字段，中性
    # 量价0-1
    if chg > 0 and vr_5 > 0.8: mk += 1
    total += min(mk, 10)
    
    # === 情绪 (0-10) ===
    em = 0
    # 超卖度0-3
    if pos_20d < 15: em += 3
    elif pos_20d < 25: em += 2
    elif pos_20d < 40: em += 1
    # 恐慌度0-3
    if down_days >= 4: em += 3
    elif down_days >= 3: em += 2
    elif down_days >= 2: em += 1
    # 波动率0-2
    if 3 <= amp <= 8: em += 1
    if amp > 5: em += 1
    # 连续下跌跌幅
    if down_days >= 2 and chg < 0: em += 1
    total += min(em, 10)
    
    # === 事件 (0-10) ===
    ev = 0
    # feats表不含多日涨停统计，用chg近似
    if chg >= 9.5: ev += 4
    elif chg >= 5: ev += 2
    # 量能异动
    if vr_5 > 2: ev += 3
    elif vr_5 > 1.5: ev += 1
    # 方向
    if chg > 3: ev += 1
    total += min(ev, 10)
    
    # === 基本面 (0-10) ===
    fn = 0
    # MA20偏离度（超跌安全边际）
    if ma20_pct < -12: fn += 3
    elif ma20_pct < -8: fn += 2
    elif ma20_pct < -4: fn += 1
    # 位置安全
    if pos_20d < 10: fn += 3
    elif pos_20d < 20: fn += 2
    elif pos_20d < 35: fn += 1
    # 连续下跌深度
    if down_days >= 5 and ma20_pct < -8: fn += 2
    elif down_days >= 3: fn += 1
    total += min(fn, 10)
    
    # === 政策 (0-10) ===
    pl = 2  # 中性——回测无法判断历史政策题材
    # 创业板加分
    # （无法从feat表判断，中性处理）
    total += min(pl, 10)
    
    # === 游资 (0-10) ===
    cf = 0
    # 量能爆发
    if vr_5 > 4: cf += 3
    elif vr_5 > 2.5: cf += 2
    elif vr_5 > 1.5: cf += 1
    # 连涨
    if up_days >= 4: cf += 2
    elif up_days >= 2: cf += 1
    # 缩量回调
    if chg < 0 and vr_5 < 0.8: cf += 2
    # 振幅活性
    if amp > 7: cf += 2
    elif amp > 4.5: cf += 1
    total += min(cf, 10)
    
    # === 解禁 (0-10) ===
    lk = 5  # 中性——回测无法判断历史解禁数据
    # 放量下跌风险
    if chg < -5 and vr_5 > 1.5: lk -= 2
    # 连跌抛压
    if down_days >= 5 and chg < 0: lk -= 1
    # 缩量企稳
    if vr_5 < 0.7 and abs(chg) < 2: lk += 1
    total += max(0, min(lk, 10))
    
    # === 缠论 (0-10) ===
    cl = 0
    # 深偏离 = 底背驰近似
    if ma20_pct < -10 and pos_20d < 15: cl += 3
    elif ma20_pct < -6 and pos_20d < 25: cl += 2
    # 底部区域
    if pos_20d < 10: cl += 2
    # 下跌速度衰减
    if down_days >= 3 and chg > -2: cl += 2
    # 跌后企稳
    if ma20_pct < -8 and vr_5 < 0.8: cl += 1
    total += min(cl, 10)
    
    return total


def backtest(start_date="2023-01-01", end_date="2026-06-05", top_n=20, hold_days=5):
    """
    W8历史回测
    每天取feat表当日数据 → 模拟W8评分 → TOP20 → T+hold_days收益
    
    返回:
      trades: [{date, code, score, ret}]
      stats: {total_trades, win_rate, avg_return, sharpe, max_drawdown}
    """
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # 获取所有交易日
    cur.execute("""
        SELECT DISTINCT date FROM feat 
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date, end_date))
    trade_dates = [r[0] for r in cur.fetchall()]
    
    print(f"回测区间: {start_date} ~ {end_date}")
    print(f"交易日: {len(trade_dates)}天")
    print(f"持有天数: T+{hold_days}")
    print()
    
    trades = []
    t0 = time.time()
    
    for day_idx, trade_date in enumerate(trade_dates):
        if (day_idx + 1) % 100 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (day_idx + 1) * (len(trade_dates) - day_idx - 1)
            print(f"  进度: {day_idx+1}/{len(trade_dates)}天 | {elapsed:.0f}s | ETA {eta:.0f}s")
        
        # 当日所有股票
        cur.execute("""
            SELECT code, date, close, open, high, low, volume, chg, amp, 
                   vr_5, vr_20, ma5, ma10, ma20, ma60,
                   ma20_pct, ma60_pct, pos_20d, pos_60d, down_days, up_days
            FROM feat
            WHERE date = ? AND code NOT LIKE '688%' AND code NOT LIKE '4%'
              AND code NOT LIKE '83%' AND code NOT LIKE '87%'
              AND chg IS NOT NULL
        """, (trade_date,))
        rows = cur.fetchall()
        
        if not rows:
            continue
        
        # 每只股票算W8评分
        scored = []
        for row in rows:
            code = row[0]
            score = compute_w8_from_feat(row)
            scored.append((score, code))
        
        # 取TOP20
        scored.sort(key=lambda x: -x[0])
        top = scored[:top_n]
        
        # 查T+hold_days的收益率
        target_date_idx = day_idx + hold_days
        if target_date_idx < len(trade_dates):
            sell_date = trade_dates[target_date_idx]
            for score, code in top:
                cur.execute("""
                    SELECT ret1, ret2, ret3, ret5, ret10
                    FROM feat WHERE code = ? AND date = ?
                """, (code, trade_date))
                ret_row = cur.fetchone()
                if ret_row:
                    # 根据hold_days选对应收益
                    if hold_days == 1: ret = ret_row[0]
                    elif hold_days == 2: ret = ret_row[1]
                    elif hold_days == 3: ret = ret_row[2]
                    elif hold_days == 5: ret = ret_row[3]
                    elif hold_days == 10: ret = ret_row[4]
                    else: ret = None
                    
                    if ret is not None:
                        trades.append({
                            "date": trade_date,
                            "sell_date": sell_date,
                            "code": code,
                            "score": score,
                            "ret": ret
                        })
    
    conn.close()
    
    # === 统计 ===
    if not trades:
        print("⚠️ 无交易记录")
        return [], {}
    
    returns = [t["ret"] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    
    total = len(trades)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / total * 100 if total > 0 else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    avg_return = sum(returns) / total if total > 0 else 0
    profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float('inf')
    
    # 夏普比率（假设无风险利率0）
    std = (sum((r - avg_return) ** 2 for r in returns) / total) ** 0.5 if total > 1 else 0
    sharpe = avg_return / std * (252 ** 0.5) if std > 0 else 0
    
    # 最大回撤
    cumulative = 0
    peak = 0
    max_dd = 0
    for r in returns:
        cumulative += r
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
    
    # 收益分布
    deciles = {f"{i*10}-{i*10+10}%": len([r for r in returns if i*10 <= r < i*10+10]) for i in range(-10, 11)}
    
    stats = {
        "total_trades": total,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "profit_factor": profit_factor,
        "total_return": sum(returns),
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "std": std,
        "best_trade": max(returns),
        "worst_trade": min(returns),
    }
    
    # === 按月度统计 ===
    monthly = defaultdict(list)
    for t in trades:
        ym = t["date"][:7]
        monthly[ym].append(t["ret"])
    
    monthly_stats = {}
    for ym, rets in sorted(monthly.items()):
        m_wins = [r for r in rets if r > 0]
        m_wr = len(m_wins) / len(rets) * 100
        monthly_stats[ym] = {
            "trades": len(rets),
            "win_rate": m_wr,
            "avg_ret": sum(rets) / len(rets),
        }
    
    return trades, stats, monthly_stats


def print_stats(stats, monthly_stats=None):
    """打印回测统计"""
    print(f"\n{'='*60}")
    print(f"  📊 W8选股器 回测报告")
    print(f"{'='*60}")
    print(f"  总交易次数:     {stats['total_trades']:,}")
    print(f"  胜率:           {stats['win_rate']:.1f}%")
    print(f"  平均单笔收益:   {stats['avg_return']:+.2f}%")
    print(f"  平均盈利:       {stats['avg_win_pct']:+.2f}%")
    print(f"  平均亏损:       {stats['avg_loss_pct']:.2f}%")
    print(f"  盈亏比:         {stats['profit_factor']:.2f}")
    print(f"  累计收益:       {stats['total_return']:+.2f}%")
    print(f"  夏普比率:       {stats['sharpe']:.2f}")
    print(f"  最大回撤:       {stats['max_drawdown']:.2f}%")
    print(f"  最好单笔:       {stats['best_trade']:+.2f}%")
    print(f"  最差单笔:       {stats['worst_trade']:.2f}%")
    
    if monthly_stats:
        print(f"\n  {'='*60}")
        print(f"  月度统计")
        print(f"  {'月份':<8} {'交易':>5} {'胜率':>8} {'均收益':>8}")
        print(f"  {'-'*32}")
        for ym, ms in monthly_stats.items():
            flag = "🟢" if ms["avg_ret"] > 0 else "🔴"
            print(f"  {ym:<8} {ms['trades']:>5} {ms['win_rate']:>7.1f}% {ms['avg_ret']:>+7.2f}% {flag}")


if __name__ == "__main__":
    sample = False
    year_filter = None
    
    for arg in sys.argv[1:]:
        if arg.startswith("--sample"):
            sample = True
        elif arg.startswith("--year"):
            year_filter = arg.split("=")[1] if "=" in arg else "2025"
    
    if year_filter:
        start = f"{year_filter}-01-01"
        end = f"{year_filter}-12-31"
    elif sample:
        start = "2023-01-01"
        end = "2023-06-30"
    else:
        start = "2023-01-01"
        end = "2026-06-05"
    
    t0 = time.time()
    trades, stats, monthly = backtest(start_date=start, end_date=end, top_n=20, hold_days=5)
    print_stats(stats, monthly)
    print(f"\n总耗时: {time.time()-t0:.0f}s")
