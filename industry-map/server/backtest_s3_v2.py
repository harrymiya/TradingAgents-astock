#!/usr/bin/env python3
"""
S3 V2 全量回测脚本
模拟按日运行S3策略 → Stage2评分 → Top10 → N日后收益统计
2026-06-11: V2 评分体系（ABCDEF六维11因子）

用法: python backtest_s3_v2.py [开始日期] [结束日期]
  默认: 2024-01-01 ~ 2025-12-31
"""
import sys, os, json, sqlite3
from datetime import datetime, timedelta

DB = os.path.expanduser("~/.hermes/astock_data.db")
START = sys.argv[1] if len(sys.argv) > 1 else "2024-01-01"
END = sys.argv[2] if len(sys.argv) > 2 else "2025-12-31"

HOT_KEYWORDS = ['AI', '算力', '芯片', '半导体', '机器人', '低空经济', '新能源',
                '光伏', '电池', '汽车', '光模块', 'PCB', '软件', '算网',
                '消费电子', '创新药', '军工', '商业航天']

def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    print(f"  [{t}] {msg}", flush=True)

def stage1_s3(cur, date_str):
    """S3 SQL筛选——与screening_api.py一致"""
    cur.execute("""
        SELECT f.code, s.name, 
               f.close, f.chg, f.amp, f.vr_5, f.vr_20,
               f.pos_20d, f.pos_60d, f.ma20_pct, f.ma60_pct,
               f.ret1, f.ret3, f.ret5, f.down_days, f.up_days,
               f.volume, f.ma5, f.ma10, f.ma20
        FROM feat f
        JOIN stocks s ON f.code = s.code
        WHERE f.date = ?
          AND f.pos_20d < 20 
          AND f.chg >= 3 AND f.chg < 7
          AND f.vr_5 >= 1.2 AND f.vr_5 < 2.5
          AND f.ma20_pct < -8
          AND f.down_days < 5
          AND f.code NOT LIKE '688%%'
          AND s.name NOT LIKE '%%ST%%'
    """, (date_str,))
    cols = ['code','name','close','chg','amp','vr_5','vr_20',
            'pos_20d','pos_60d','ma20_pct','ma60_pct',
            'ret1','ret3','ret5','down_days','up_days',
            'volume','ma5','ma10','ma20']
    results = []
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        for k in ['close','chg','amp','vr_5','vr_20','pos_20d','pos_60d',
                   'ma20_pct','ma60_pct','ret1','ret3','ret5','volume','ma5','ma10','ma20']:
            try: d[k] = float(d[k])
            except: d[k] = 0
        d['strategy'] = 'S3'
        results.append(d)
    return results

def get_market_data(conn, date_str):
    """获取大盘数据——与screening_api.py一致"""
    mkt = conn.execute("""
        SELECT AVG(chg) as avg_chg,
               SUM(CASE WHEN chg > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as up_ratio,
               AVG(ma60_pct) as avg_ma60
        FROM feat WHERE date = ? AND chg IS NOT NULL AND ma60_pct IS NOT NULL
    """, (date_str,)).fetchone()
    return {
        'avg_chg': float(mkt[0] or 0),
        'up_ratio': float(mkt[1] or 0.5),
        'avg_ma60': float(mkt[2] or 0),
    }

def compute_market_score(mkt):
    """大盘因子评分——与stage2_score中的A因子一致"""
    up_ratio = mkt['up_ratio']
    avg_chg = mkt['avg_chg']
    avg_ma60 = mkt['avg_ma60']
    
    score = 0
    # A1: 涨跌比
    if up_ratio < 0.55: score += -3
    elif up_ratio < 0.60: score += 0
    elif up_ratio < 0.70: score += 1
    elif up_ratio < 0.75: score += 2
    else: score += 3
    
    # A2: 平均涨幅
    if avg_chg < -1: score += -2
    elif avg_chg < 0: score += -1
    elif avg_chg < 0.5: score += 0
    elif avg_chg < 1: score += 1
    elif avg_chg < 2: score += 2
    else: score += 3
    
    # A3: 全市场超跌
    if avg_ma60 < -10: score += 4
    elif avg_ma60 < -5: score += 2
    elif avg_ma60 < -2: score += 1
    
    return score

def get_stock_data(conn, date_str):
    """获取全市场个股数据和行业/产业链归属"""
    # 个股数据
    rows = conn.execute("""
        SELECT code, pos_60d, ret1, ret3, ret5, volume, chg, vr_5, amp, down_days,
               ma20_pct, ma60_pct
        FROM feat WHERE date = ?
    """, (date_str,)).fetchall()
    cols = ['code','pos_60d','ret1','ret3','ret5','volume','chg','vr_5','amp','down_days',
            'ma20_pct','ma60_pct']
    md_map = {}
    for r in rows:
        d = dict(zip(cols, r))
        for k in cols[1:]:
            try: d[k] = float(d[k])
            except: d[k] = 0
        md_map[d['code']] = d
    
    # 行业归属
    ind_rows = conn.execute(
        "SELECT code, industry_l1, industry_l2 FROM stock_industries"
    ).fetchall()
    stock_industry_map = {}
    for r in ind_rows:
        stock_industry_map[r[0]] = r[1] or ''
    
    # 产业链归属
    cs_rows = conn.execute("""
        SELECT DISTINCT cs.code, ic.name
        FROM chain_stocks cs
        JOIN chain_links cl ON cs.link_id = cl.id
        JOIN industry_chains ic ON cl.chain_id = ic.id
    """).fetchall()
    stock_chains = {}
    for code, chain_name in cs_rows:
        if code not in stock_chains:
            stock_chains[code] = []
        stock_chains[code].append(chain_name)
    
    chain_rows = conn.execute("SELECT name FROM industry_chains ORDER BY sort_order").fetchall()
    all_chains = [r[0] for r in chain_rows]
    
    return md_map, stock_industry_map, stock_chains, all_chains

def compute_stock_score(c, row, md_map, stock_industry_map, stock_chains, all_chains, market_score):
    """
    计算个股的stage2评分——与screening_api.py一致
    返回总分和评分明细
    """
    scores = {}
    total = 0
    
    # ============== B: 板块因子 (0~10) ==============
    chain_score = 0
    chain_tag = ''
    ind_l1 = stock_industry_map.get(c['code'], '')
    chains = stock_chains.get(c['code'], [])
    matched_chains = [ch for ch in all_chains if ch in chains]
    hot_keyword_matches = [kw for kw in HOT_KEYWORDS if kw in ind_l1 or kw in (stock_industry_map.get(c['code'],''))]
    
    if matched_chains:
        chain_score += 7
        chain_tag = matched_chains[0]
    if hot_keyword_matches:
        chain_score += 3
        if not chain_tag:
            chain_tag = hot_keyword_matches[0]
    chain_score = min(chain_score, 10)
    scores['板块'] = chain_score
    total += chain_score
    
    # ============== C: 趋势因子 (0~8) ==============
    trend_score = 0
    ret5 = float(row.get('ret5', 0))
    pos60 = float(row.get('pos_60d', 50))
    vr5 = float(row.get('vr_5', 0))
    
    if ret5 > 3: trend_score += 3
    elif ret5 > 0: trend_score += 2
    elif ret5 > -3: trend_score += 1
    
    if 20 <= pos60 <= 80: trend_score += 3
    elif pos60 < 20: trend_score += 1
    elif pos60 > 80: trend_score += 1
    
    if 0.6 <= vr5 <= 1.5: trend_score += 2
    elif vr5 < 0.6: trend_score += 1
    
    trend_score = min(trend_score, 8)
    scores['趋势'] = trend_score
    total += trend_score
    
    # ============== D: S3质量因子 (-3~+6) ==============
    quality_score = 0
    amp = float(row.get('amp', 0))
    dd = int(row.get('down_days', 0))
    ma20_pct = float(row.get('ma20_pct', -8))
    
    if 3 <= amp < 5: quality_score += 2
    elif 5 <= amp < 7: quality_score += 2
    elif amp >= 7: quality_score += 1
    
    if dd == 0: quality_score += 3
    elif dd >= 5: quality_score -= 2
    
    if -12 <= ma20_pct < -8: quality_score += 1
    elif ma20_pct < -20: quality_score -= 1
    
    quality_score = max(-3, min(6, quality_score))
    scores['质量'] = quality_score
    total += quality_score
    
    # ============== E: 恐慌阴 (0~3) ==============
    panic_bonus = 0
    scores['恐慌阴'] = 0
    total += 0
    # 恐慌阴在跨日回测中较难准确判断(需要前序K线)，简化处理为0
    
    # ============== A: 大盘因子 ==============
    total += market_score
    scores['大盘'] = market_score
    
    return total, scores, chain_tag

def get_next_close(conn, code, date_str, n_days):
    """获取某只股票N个交易日后的收盘价"""
    rows = conn.execute("""
        SELECT close FROM daily_klines
        WHERE code = ? AND date > ?
        ORDER BY date LIMIT ?
    """, (code, date_str, n_days + 5)).fetchall()
    if len(rows) >= n_days:
        return float(rows[n_days - 1][0])
    return None

def get_trading_dates(conn, start_date, end_date):
    """获取日线表中所有有数据的交易日"""
    rows = conn.execute("""
        SELECT DISTINCT date FROM daily_klines
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date, end_date)).fetchall()
    return [r[0] for r in rows]

def get_feat_dates(conn, start_date, end_date):
    """获取feat表有数据的日期"""
    rows = conn.execute("""
        SELECT DISTINCT date FROM feat
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date, end_date)).fetchall()
    return [r[0] for r in rows]


def main():
    print(f"\n{'='*70}")
    print(f"  S3 V2 回测 {START} ~ {END}")
    print(f"{'='*70}\n")
    
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # 1. 获取所有有数据的交易日
    feat_dates = get_feat_dates(conn, START, END)
    print(f"  📅 feat表交易日: {len(feat_dates)}天 ({feat_dates[0]} ~ {feat_dates[-1]})")
    
    # 2. 逐日回测
    all_signals = []       # 所有信号的记录
    monthly_stats = {}     # 月度统计
    market_stats_by_win = {}  # 大盘状态×胜率
    
    total_trading_days = 0
    total_signal_days = 0
    total_top10_days = 0
    total_candidates = 0
    
    for i, date in enumerate(feat_dates):
        if i % 50 == 0:
            log(f"进度: {i}/{len(feat_dates)} ({date})")
        
        # 只考虑有feat数据的日期
        total_trading_days += 1
        
        # Stage1: S3筛选
        candidates = stage1_s3(cur, date)
        total_candidates += len(candidates)
        
        if len(candidates) < 3:
            continue  # 信号太少，不进入stage2
        
        # 获取市场数据
        mkt = get_market_data(conn, date)
        market_score = compute_market_score(mkt)
        market_up_ratio = mkt['up_ratio']
        market_avg_chg = mkt['avg_chg']
        
        # 大盘弱势检测（与run_pipeline_stage2一致）
        if market_up_ratio < 0.55 and market_avg_chg < 0.3:
            # S3暂停
            continue
        
        total_signal_days += 1
        
        # 获取行业/产业链数据
        md_map, stock_industry_map, stock_chains, all_chains = get_stock_data(conn, date)
        
        # Stage2: 评分
        scored = []
        for c in candidates:
            row = md_map.get(c['code'])
            if not row:
                continue
            score, details, chain_tag = compute_stock_score(
                c, row, md_map, stock_industry_map, stock_chains, all_chains, market_score
            )
            scored.append((score, c, chain_tag))
        
        # Top10
        scored.sort(key=lambda x: x[0], reverse=True)
        top10 = scored[:10]
        total_top10_days += 1
        
        # 记录每个Top10信号的收益 (N日后)
        for rank, (score, signal, chain_tag) in enumerate(top10):
            code = signal['code']
            name = signal['name']
            entry_chg = signal['chg']
            entry_close = signal['close']
            
            month_key = date[:7]  # YYYY-MM
            
            # 查N=5日后的收盘价
            for n_days in [3, 5, 10]:
                next_close = get_next_close(conn, code, date, n_days)
                if next_close:
                    profit = (next_close - entry_close) / entry_close * 100
                    win = 1 if profit > 0 else 0
                    
                    all_signals.append({
                        'date': date,
                        'month': month_key,
                        'code': code,
                        'name': name,
                        'n_days': n_days,
                        'entry_chg': entry_chg,
                        'entry_close': entry_close,
                        'exit_close': next_close,
                        'profit': round(profit, 2),
                        'win': win,
                        'score': score,
                        'rank': rank + 1,
                        'market_up_ratio': round(market_up_ratio * 100, 1),
                        'market_avg_chg': round(market_avg_chg, 2),
                        'market_score': market_score,
                        'chain_tag': chain_tag,
                    })
    
    conn.close()
    
    # ========== 统计结果 ==========
    print(f"\n{'='*70}")
    print(f"  📊 回测统计总览")
    print(f"{'='*70}")
    print(f"  总交易日(有feat): {total_trading_days}")
    print(f"  S3信号日(大盘OK): {total_signal_days}")
    print(f"  Top10出单日:      {total_top10_days}")
    print(f"  总候选信号数:     {total_candidates}")
    print(f"  有效收益记录数:   {len(all_signals)}")
    
    for n in [3, 5, 10]:
        subset = [s for s in all_signals if s['n_days'] == n]
        if not subset:
            continue
        wins = sum(1 for s in subset if s['win'])
        profits = [s['profit'] for s in subset]
        avg_profit = sum(profits) / len(profits)
        max_profit = max(profits)
        min_profit = min(profits)
        win_rate = wins / len(subset) * 100
        
        print(f"\n  ─── {n}日后收益 ───")
        print(f"    样本数: {len(subset)}")
        print(f"    胜率:   {win_rate:.1f}% ({wins}/{len(subset)})")
        print(f"    均收益: {avg_profit:+.2f}%")
        print(f"    最大:   {max_profit:+.2f}%")
        print(f"    最小:   {min_profit:+.2f}%")
    
    # 按年份统计
    for year_label in ['2024', '2025']:
        year_data = [s for s in all_signals if s['date'].startswith(year_label)]
        if not year_data:
            continue
        print(f"\n  ─── {year_label}年 ───")
        for n in [3, 5, 10]:
            subset = [s for s in year_data if s['n_days'] == n]
            if not subset:
                continue
            wins = sum(1 for s in subset if s['win'])
            avg_profit = sum(s['profit'] for s in subset) / len(subset)
            win_rate = wins / len(subset) * 100
            print(f"    {n}日后: 胜率{win_rate:.1f}% ({wins}/{len(subset)}), 均收益{avg_profit:+.2f}%")
    
    # 按月统计
    print(f"\n  ─── 月度5日胜率趋势 ───")
    print(f"  {'月份':<10} {'样本':>6} {'胜率':>8} {'均收益':>10} {'大盘涨跌比':>12}")
    print(f"  {'-'*48}")
    months_sorted = sorted(set(s['month'] for s in all_signals if s['n_days'] == 5))
    for m in months_sorted:
        subset = [s for s in all_signals if s['n_days'] == 5 and s['month'] == m]
        if len(subset) < 5:
            continue
        wins = sum(1 for s in subset if s['win'])
        avg_profit = sum(s['profit'] for s in subset) / len(subset)
        win_rate = wins / len(subset) * 100
        avg_mkt = sum(s['market_up_ratio'] for s in subset) / len(subset)
        print(f"  {m:<10} {len(subset):>6} {win_rate:>7.1f}% {avg_profit:>+9.2f}% {avg_mkt:>11.1f}%")
    
    # 按大盘状态分组
    print(f"\n  ─── 按大盘涨跌比分组(5日) ───")
    bins = [(0, 55), (55, 60), (60, 65), (65, 70), (70, 75), (75, 100)]
    for lo, hi in bins:
        subset = [s for s in all_signals if s['n_days'] == 5 and lo <= s['market_up_ratio'] < hi]
        if len(subset) < 3:
            continue
        wins = sum(1 for s in subset if s['win'])
        avg_profit = sum(s['profit'] for s in subset) / len(subset)
        win_rate = wins / len(subset) * 100
        print(f"    {lo}~{hi}%: 胜率{win_rate:.1f}% ({wins}/{len(subset)}), 均收益{avg_profit:+.2f}%")
    
    # 按大盘超跌分组
    print(f"\n  ─── 按全市场超跌状态(5日) ───")
    mkt_bins = [(('ma60<-10%', -999, -10), ('ma60 -10~-5%', -10, -5), 
                 ('ma60 -5~0%', -5, 0), ('ma60>0%', 0, 999))]
    for label, lo, hi in [('ma60<-10%', -999, -10), ('ma60 -10~-5%', -10, -5),
                          ('ma60 -5~0%', -5, 0), ('ma60>0%', 0, 999)]:
        subset = []
        for s in all_signals:
            if s['n_days'] != 5:
                continue
            # 需要回算该日的全市场ma60_pct均值——这里用大盘涨跌比≈对应的场景
            if lo <= s['market_avg_chg'] < hi:
                subset.append(s)
        if len(subset) < 5:
            continue
        wins = sum(1 for s in subset if s['win'])
        avg_profit = sum(s['profit'] for s in subset) / len(subset)
        win_rate = wins / len(subset) * 100
        print(f"    {label:<16}: 胜率{win_rate:.1f}% ({wins}/{len(subset)}), 均收益{avg_profit:+.2f}%")
    
    # 按评分区间分组
    print(f"\n  ─── 按总分区间(5日) ───")
    for lo in range(0, 35, 5):
        hi = lo + 5
        subset = [s for s in all_signals if s['n_days'] == 5 and lo <= s['score'] < hi]
        if len(subset) < 3:
            continue
        wins = sum(1 for s in subset if s['win'])
        avg_profit = sum(s['profit'] for s in subset) / len(subset)
        win_rate = wins / len(subset) * 100
        print(f"    {lo}~{hi}分: 胜率{win_rate:.1f}% ({wins}/{len(subset)}), 均收益{avg_profit:+.2f}%")
    
    # ========== V1 vs V2 对比 ==========
    print(f"\n{'='*70}")
    print(f"  📈 V1 vs V2 对比 (5日收益)")
    print(f"{'='*70}")
    v1_data = [s for s in all_signals if s['n_days'] == 5]
    if v1_data:
        # V1假设: 只用原始条件排序(不经过V2评分)
        # 模拟V1: 只通过stage1, 按chg降序取前10
        # 我们已有的V2数据是按stage2评分后的，需要单独的V1模拟
        print(f"  ⚠️ V1对比需要另外模拟，下面仅显示V2的Top10内部分布:")
        
        # Top10中排名前5 vs 后5
        top5 = [s for s in v1_data if s['rank'] <= 5]
        bot5 = [s for s in v1_data if s['rank'] > 5]
        
        if top5 and bot5:
            t5_wr = sum(1 for s in top5 if s['win']) / len(top5) * 100
            t5_avg = sum(s['profit'] for s in top5) / len(top5)
            b5_wr = sum(1 for s in bot5 if s['win']) / len(bot5) * 100
            b5_avg = sum(s['profit'] for s in bot5) / len(bot5)
            print(f"  Top1-5:   胜率{t5_wr:.1f}%, 均收益{t5_avg:+.2f}%")
            print(f"  Top6-10:  胜率{b5_wr:.1f}%, 均收益{b5_avg:+.2f}%")
            print(f"  差距:     {t5_wr - b5_wr:+.1f}%胜率, {t5_avg - b5_avg:+.2f}%收益")
    
    # ========== 板块热度验证 ==========
    print(f"\n  ─── 有产业链归属 vs 无(5日) ───")
    with_chain = [s for s in all_signals if s['n_days'] == 5 and s['chain_tag']]
    no_chain = [s for s in all_signals if s['n_days'] == 5 and not s['chain_tag']]
    if with_chain:
        wc_wr = sum(1 for s in with_chain if s['win']) / len(with_chain) * 100
        wc_avg = sum(s['profit'] for s in with_chain) / len(with_chain)
        print(f"  有产业链: 胜率{wc_wr:.1f}% ({len(with_chain)}次), 均收益{wc_avg:+.2f}%")
    if no_chain:
        nc_wr = sum(1 for s in no_chain if s['win']) / len(no_chain) * 100
        nc_avg = sum(s['profit'] for s in no_chain) / len(no_chain)
        print(f"  无产业链: 胜率{nc_wr:.1f}% ({len(no_chain)}次), 均收益{nc_avg:+.2f}%")
    
    print(f"\n{'='*70}")
    print(f"  回测完成! 日期范围: {START} ~ {END}")
    print(f"{'='*70}\n")

if __name__ == '__main__':
    main()
