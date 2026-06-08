#!/usr/bin/env python3
"""
实战回测 + 每日扫描脚本

S3超跌反弹实战流程：
  1. 每天14:45用实时行情(或前一日K线)扫描S3信号
  2. 筛选条件: 20日位置<20, 涨3-8%, 量比>1.2
  3. 精选: 收涨小阳(开盘到收盘涨幅不大)
  4. 次日开盘买入 -> 持有T+5天 -> 收盘卖出

回测部分：确认收益
每日扫描：生成信号清单
"""

import sqlite3
import os
from collections import defaultdict
from datetime import datetime, date

DB = os.path.expanduser("~/.hermes/astock_data.db")

# ============================================================
# 回测引擎
# ============================================================

def simulate_realistic():
    """
    真实回测模型:
    - 尾盘(T日收盘)看到S3信号
    - T+1日开盘买入
    - 持有到T+N日收盘卖出
    - 资金约束：20万本金，每只15%，最多5只
    """
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    print("=" * 65)
    print("  S3超跌反弹 — 实战回测")
    print("  流程: T日尾盘确认信号 → T+1开盘买入 → T+N收盘卖出")
    print("=" * 65)
    
    # 获取所有S3信号 + 前后价格
    cur.execute("""
        SELECT f.code, f.date, d.close as sig_close, d.open as sig_open,
               f.chg, f.vr_5, f.pos_20d
        FROM feat f
        JOIN daily_klines d ON f.code = d.code AND f.date = d.date
        WHERE f.pos_20d < 20 AND f.chg >= 3 AND f.chg < 8 
          AND f.vr_5 >= 1.2 AND f.vr_5 < 3
        ORDER BY f.date
    """)
    signals_raw = cur.fetchall()
    
    # 再获取第二天的开盘价和after N天的收盘价
    # 用JOIN到后面日期
    cur.execute("""
        CREATE TEMP VIEW IF NOT EXISTS price_seq AS
        SELECT code, date, open, close,
               LEAD(date, 1) OVER (PARTITION BY code ORDER BY date) as next_date,
               LEAD(open, 1) OVER (PARTITION BY code ORDER BY date) as next_open,
               LEAD(close, 1) OVER (PARTITION BY code ORDER BY date) as next_close,
               LEAD(close, 5) OVER (PARTITION BY code ORDER BY date) as close_5d,
               LEAD(close, 10) OVER (PARTITION BY code ORDER BY date) as close_10d
        FROM daily_klines
    """)
    
    print(f"  总信号: {len(signals_raw):,}")
    
    # 每种持有期测试
    configs = [
        ("T+1", 1, "next_close"),
        ("T+5", 5, "close_5d"),
        ("T+10", 10, "close_10d"),
    ]
    
    for label, hold_days, price_col in configs:
        CAPITAL = 200000
        cash = CAPITAL
        positions = []
        trades = []
        
        # 找持有期价格
        cur.execute(f"""
            SELECT f.code, f.date, f.chg, p.next_open, p.{price_col}
            FROM feat f
            JOIN price_seq p ON f.code = p.code AND f.date = p.date
            WHERE f.pos_20d < 20 AND f.chg >= 3 AND f.chg < 8 
              AND f.vr_5 >= 1.2 AND f.vr_5 < 3
              AND p.next_open IS NOT NULL
              AND p.{price_col} IS NOT NULL
            ORDER BY f.date
        """)
        rows = cur.fetchall()
        
        daily_sigs = defaultdict(list)
        for r in rows:
            daily_sigs[r[1]].append(r)
        
        for date in sorted(daily_sigs.keys()):
            sigs = daily_sigs[date]
            
            # --- 卖出（T日之前买入的，如果有hold_days应该卖出）---
            new_pos = []
            for code, bdate, bprice, buydate_idx in positions:
                days_held = len([d for d in sorted(daily_sigs.keys()) if d > buydate_idx and d <= date])
                if days_held >= hold_days:
                    # 找到sell price
                    for s in sigs:
                        if s[0] == code:
                            sell_price = s[4] if price_col == "close_5d" else s[3]
                            break
                    else:
                        # 没找到，从feat里查
                        cur.execute("SELECT close FROM daily_klines WHERE code=? AND date=?", (code, date))
                        r2 = cur.fetchone()
                        if r2:
                            sell_price = r2[0]
                        else:
                            new_pos.append((code, bdate, bprice, buydate_idx))
                            continue
                    
                    gross_ret = (sell_price - bprice) / bprice * 100
                    net_ret = gross_ret - 0.3  # 交易成本
                    proceeds = bprice * 100 * (1 + net_ret / 100)
                    cash += proceeds
                    
                    trades.append({
                        "code": code, "buy_date": buydate_idx, "sell_date": date,
                        "gross_ret": round(gross_ret, 2), "net_ret": round(net_ret, 2),
                    })
                else:
                    new_pos.append((code, bdate, bprice, buydate_idx))
            positions = new_pos
            
            # --- 买入 ---
            can_buy = 5 - len(positions)
            if can_buy > 0 and date in daily_sigs:
                sigs_today = daily_sigs[date]
                sigs_today.sort(key=lambda x: abs(x[2] - 5))  # chg 接近5%的优先（不追太高也不太低）
                
                for s in sigs_today[:can_buy]:
                    code = s[0]
                    if any(p[0] == code for p in positions):
                        continue
                    
                    next_open = s[3]  # T+1开盘价
                    sig_date = s[1]
                    
                    if next_open is None:
                        continue
                    
                    alloc = cash * 0.15
                    cost = alloc * 1.003
                    if cost > cash:
                        continue
                    
                    shares = int(cost / next_open / 100) * 100
                    if shares < 100:
                        continue
                    
                    actual_cost = shares * next_open * 1.003
                    if actual_cost > cash:
                        continue
                    
                    cash -= actual_cost
                    positions.append((code, sig_date, next_open, date))
        
        # 统计
        final_value = cash
        for code, bdate, bprice, buydate_idx in positions:
            cur.execute("SELECT close FROM daily_klines WHERE code=? AND date=?", (code, sorted(daily_sigs.keys())[-1]))
            r2 = cur.fetchone()
            if r2:
                final_value += bprice * 100 * r2[0] / bprice
        
        total_ret = (final_value / CAPITAL - 1) * 100
        
        if trades:
            wins = [t for t in trades if t["net_ret"] > 0]
            wr = len(wins) / len(trades) * 100
            avg_ret = sum(t["net_ret"] for t in trades) / len(trades)
            print(f"\n  ▶ {label} 开盘买入")
            print(f"    交易: {len(trades)}笔 | 胜率: {wr:.1f}% | 均收益: {avg_ret:+.2f}%")
            print(f"    总收益: {total_ret:>+7.2f}%")
        else:
            print(f"\n  ▶ {label} 开盘买入 — 无交易")
    
    conn.close()
    return


# ============================================================
# 每日扫描（供cronjob调用）
# ============================================================

def scan_today(save_file=None):
    """
    扫描今天的S3信号
    用feat表里的最近一日数据（实际使用时应该接实时行情）
    输出格式：适合推送到飞书
    """
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # 获取最新日期
    cur.execute("SELECT MAX(date) FROM feat")
    latest = cur.fetchone()[0]
    
    print(f"\n📡 S3超跌反弹 - {latest} 扫描")
    print("=" * 55)
    
    # 扫描S3信号
    cur.execute("""
        SELECT f.code, s.name, f.close, f.chg, f.vr_5, f.pos_20d,
               f.ma20_pct, f.ret1, f.ret3, f.ret5
        FROM feat f
        JOIN stocks s ON f.code = s.code
        WHERE f.date = ? 
          AND f.pos_20d < 20 
          AND f.chg >= 3 AND f.chg < 8 
          AND f.vr_5 >= 1.2 AND f.vr_5 < 3
        ORDER BY f.chg DESC
    """, (latest,))
    
    signals = cur.fetchall()
    
    if not signals:
        msg = f"📡 {latest} S3超跌反弹扫描\n\n❌ 今日无信号"
        print(msg)
        conn.close()
        return msg
    
    # 分类
    strong = [s for s in signals if s[3] >= 5]  # 涨5%+的
    normal = [s for s in signals if 3 <= s[3] < 5]  # 涨3-5%的
    
    msg_parts = [f"📡 **S3超跌反弹 — {latest}**"]
    msg_parts.append(f"")
    msg_parts.append(f"总信号: {len(signals)}只")
    msg_parts.append(f"")
    
    # 强势信号 TOP 10
    if strong:
        msg_parts.append(f"**🔥 强势信号 (涨5%+)**")
        for s in strong[:10]:
            name, code, close, chg, vr, pos, ma20, r1, r3, r5 = s[1], s[0], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9]
            r1_str = f"次日{r1:+.1f}%" if r1 is not None else "N/A"
            r5_str = f"5日{r5:+.1f}%" if r5 is not None else "N/A"
            msg_parts.append(f"  {code} {name} 涨{chg:+.1f}% 量{vr:.1f} 位{pos:.0f} {r1_str} {r5_str}")
    
    if normal:
        msg_parts.append(f"")
        msg_parts.append(f"**📗 普通信号 (涨3-5%)**")
        for s in normal[:15]:
            name, code, close, chg, vr, pos, ma20, r1, r3, r5 = s[1], s[0], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9]
            r1_str = f"次日{r1:+.1f}%" if r1 is not None else "N/A"
            r5_str = f"5日{r5:+.1f}%" if r5 is not None else "N/A"
            msg_parts.append(f"  {code} {name} 涨{chg:+.1f}% 量{vr:.1f} 位{pos:.0f} {r1_str} {r5_str}")
    
    if len(signals) > 25:
        msg_parts.append(f"")
        msg_parts.append(f"...还有{len(signals)-25}只未列出")
    
    msg_parts.append(f"")
    msg_parts.append(f"---")
    msg_parts.append(f"操作建议: 明日开盘买入TOP3-5只, 持有5天")
    
    msg = "\n".join(msg_parts)
    print(msg)
    
    # 保存到文件
    if save_file:
        os.makedirs(os.path.dirname(save_file), exist_ok=True)
        with open(save_file, "w") as f:
            f.write(msg)
        print(f"\n已保存到 {save_file}")
    
    conn.close()
    return msg


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        # 每日扫描模式
        scan_today()
    elif len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        # 回测模式
        simulate_realistic()
    else:
        print("用法:")
        print("  python3 strategy_engine.py --backtest   # 回测")
        print("  python3 strategy_engine.py --scan       # 今日扫描")
