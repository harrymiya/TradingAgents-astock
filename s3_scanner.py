#!/usr/bin/env python3
"""
s3_scanner.py — S3超跌反弹每日扫描脚本（支持盘中实时模式）

实战流程:
  每天收盘后(或实时)扫描全市场，找出符合条件的S3信号
  输出: 信号列表 + 核心指标 + 操作建议
  
用法:
  python3 s3_scanner.py                 # 扫描最近一个交易日(用feat表)
  python3 s3_scanner.py --realtime      # 盘中实时模式(腾讯API覆盖chg)
  python3 s3_scanner.py --date 2026-06-08  # 指定日期
  python3 s3_scanner.py --rank 10       # 只显示TOP N
"""
import sqlite3, os, sys, json, re, urllib.request

DB = os.path.expanduser("~/.hermes/astock_data.db")


def scan(date_str=None, top_n=20, realtime=False):
    """扫描S3信号"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # 默认最新日期
    if not date_str:
        cur.execute("SELECT MAX(date) FROM feat")
        date_str = cur.fetchone()[0]
    
    print(f"\n{'='*60}")
    print(f"  S3超跌反弹 — {date_str} 扫描")
    print(f"{'='*60}")
    
    # 1. 全市场统计
    cur.execute("""
        SELECT COUNT(DISTINCT code), COUNT(*) 
        FROM feat WHERE date = ? AND chg IS NOT NULL
    """, (date_str,))
    total_stocks, total_records = cur.fetchone()
    print(f"\n  全市场: {total_records}只")
    
    # 2. S3信号 — 优化版
    # 核心参数: pos<20, chg3-7%, vr1.2-2.5, ma20<-8%, 实体<70%
    # (优化来源: feat表回测, 比原版wr5从60.6%提升到71.1%)
    cur.execute("""
        SELECT f.code, s.name, 
               f.close, f.open, f.high, f.low,
               f.chg, f.vr_5, f.vr_20, f.pos_20d, f.pos_60d,
               f.ma20_pct, f.ma60_pct, 
               f.ret1, f.ret3, f.ret5,
               f.volume,
               f.down_days
        FROM feat f
        JOIN stocks s ON f.code = s.code
        WHERE f.date = ?
          AND f.pos_20d < 20 
          AND f.chg >= 3 AND f.chg < 7        -- 优化: 上限7%不是8%
          AND f.vr_5 >= 1.2 AND f.vr_5 < 2.5   -- 优化: 上限2.5不是3
          AND f.ma20_pct < -8                   -- ★核心新增: 深偏离ma20
          AND f.down_days < 5                   -- ★升级: 连跌<5天(胜率30%->68%)
          -- 排除688打头（科创板）
          AND f.code NOT LIKE '688%'
          -- 排除ST
          AND s.name NOT LIKE '%ST%'
        ORDER BY f.chg DESC
    """, (date_str,))
    
    signals = cur.fetchall()
    
    # 🆕 实时模式：用腾讯行情覆盖chg
    if realtime and signals:
        print(f"\n  📡 实时模式：正在查询腾讯行情...", end=" ")
        sys.stdout.flush()
        codes = [s[0] for s in signals]
        # 批量查询
        rt_map = {}
        for i in range(0, len(codes), 50):
            batch = codes[i:i+50]
            q = ",".join([("sh" if c.startswith('6') else "sz") + c for c in batch])
            try:
                resp = urllib.request.urlopen(f"http://qt.gtimg.cn/q={q}", timeout=5)
                text = resp.read().decode("gbk")
                for line in text.split("\n"):
                    m = re.search(r'"([^"]*)"', line)
                    if not m: continue
                    f = m.group(1).split("~")
                    if len(f) < 33: continue
                    code = f[2]; chg = float(f[32]) if f[32] else 0; price = float(f[3]) if f[3] else 0
                    rt_map[code] = (chg, price)
            except:
                pass
        
        removed = 0
        checked = 0
        new_signals = []
        for s in signals:
            code = s[0]
            if code in rt_map:
                rt_chg, rt_price = rt_map[code]
                checked += 1
                # 实时chg不满足S3的chg条件 → 剔除
                if rt_chg < 3 or rt_chg >= 7:
                    removed += 1
                    continue
                # 替换为实时数据
                s = list(s)
                s[3] = rt_price  # close
                s[6] = rt_chg   # chg
                s = tuple(s)
            new_signals.append(s)
        signals = new_signals
        print(f"检查{checked}只, 剔除{removed}只(实时涨幅不满足)")
    
    if not signals:
        msg = f"❌ 今日无S3信号"
        print(f"\n  {msg}")
        conn.close()
        return msg
    
    # 3. 分类统计
    strong = [s for s in signals if s[6] >= 5]  # chg >= 5%
    moderate = [s for s in signals if 3 <= s[6] < 5]
    
    # 4. 市场状态
    cur.execute("SELECT AVG(chg) FROM feat WHERE date=? AND chg IS NOT NULL", (date_str,))
    market_chg = cur.fetchone()[0] or 0
    
    market_state = "极弱"
    # 涨跌比数据
    cur.execute("SELECT SUM(CASE WHEN chg>0 THEN 1 ELSE 0 END)*1.0/COUNT(*) FROM feat WHERE date=? AND chg IS NOT NULL", (date_str,))
    up_ratio = cur.fetchone()[0] or 0.5
    
    if market_chg > 0.5:
        market_state = "强势"
    elif market_chg > 0:
        market_state = "震荡偏强"
    elif market_chg > -0.5:
        market_state = "震荡偏弱"
    
    # 5. 今日最佳：实体小阳线的信号
    best_signals = []
    for s in signals:
        code, name, close, open_, high, low = s[:6]
        chg, vr5, vr20, pos20, pos60 = s[6:11]
        ma20_pct, ma60_pct = s[11:13]
        ret1, ret3, ret5 = s[13:16]
        
        # 实体占比（越小说明是温和放量，越健康）
        body = abs(close - open_)
        range_ = high - low if high != low else 0.001
        body_ratio = body / range_ * 100
        
        # 综合评分
        score = 0
        if body_ratio < 60: score += 2  # 实体不大，温和放量
        if vr5 < 2.0: score += 1         # 不过分放量
        if pos20 < 15: score += 1        # 位置够低
        if ma20_pct < -8: score += 1     # 远离MA20
        if chg < 6: score += 1           # 没涨停（涨停买不到）
        if ret1 is not None and ret1 > 0: score += 1
        if down_days := s[17]:
            if down_days >= 3: score += 1  # 连跌3天以上企稳
        
        best_signals.append((score, code, name, close, chg, vr5, pos20, 
                            round(body_ratio, 1), ret1, ret3, ret5, down_days))
    
    # 按评分排序
    best_signals.sort(key=lambda x: -x[0])
    
    # --- 输出 ---
    lines = []
    lines.append(f"📡 **S3超跌反弹 — {date_str}**")
    lines.append(f"")
    lines.append(f"市场状态: {market_state} (全市场均{market_chg:+.2f}%)")
    lines.append(f"信号总数: {len(signals)}只 (强势{len(strong)}只 + 普通{len(moderate)}只)")
    lines.append(f"")
    
    # TOP 15 推荐
    lines.append(f"**🔥 精选排行 (TOP {min(top_n, len(best_signals))})**")
    lines.append(f"")
    lines.append(f"```")
    lines.append(f"{'#':>3} {'代码':>6} {'名称':<8} {'价格':>7} {'涨跌':>6} {'量比':>5} {'位置':>5} {'实体':>5} {'次日':>7} {'5日':>7} {'评分':>4}")
    lines.append(f"{'─'*60}")
    
    for i, s in enumerate(best_signals[:top_n]):
        score, code, name, close, chg, vr5, pos20, body, r1, r3, r5, dd = s
        r1_str = f"{r1:+.1f}%" if r1 is not None else "N/A"
        r5_str = f"{r5:+.1f}%" if r5 is not None else "N/A"
        close_str = f"{close:.2f}"
        lines.append(f"{i+1:>3} {code:>6} {name:<8} {close_str:>7} {chg:>+5.1f}% {vr5:>4.1f} {pos20:>4.0f} {body:>4.0f}% {r1_str:>7} {r5_str:>7} {score:>3}")
    
    lines.append(f"```")
    lines.append(f"")
    lines.append(f"**操作建议:**")
    lines.append(f"  1. 今日(尾盘)确认信号 → 明日开盘买入TOP 3-5只")
    lines.append(f"  2. 每只仓位15%，最多同时持有5只")
    lines.append(f"  3. 持有T+5天(约5个交易日)后卖出")
    lines.append(f"  4. 止损-7%(单只) | 不止盈(让利润跑)")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"_S3超跌反弹自动扫描_")
    
    msg = "\n".join(lines)
    print(msg)
    
    conn.close()
    return msg


if __name__ == "__main__":
    date_str = None
    top_n = 20
    realtime = False
    
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--date" and i + 1 < len(args):
            date_str = args[i + 1]
        elif arg == "--rank" and i + 1 < len(args):
            top_n = int(args[i + 1])
        elif arg == "--realtime":
            realtime = True
    
    scan(date_str, top_n, realtime)
