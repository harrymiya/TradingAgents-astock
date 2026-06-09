#!/usr/bin/env python3
"""
scan_pipeline.py — 三阶段选股流水线

纯Python脚本，完全基于SQLite数据库运算，不依赖外部API。
三阴直接从 daily_klines 表通过SQL窗口函数计算。

用法:
  python3 scan_pipeline.py                  # 完整流水线（最新交易日）
  python3 scan_pipeline.py --date 2026-06-08  # 指定日期
  python3 scan_pipeline.py --stage 1        # 只跑第一阶段
  python3 scan_pipeline.py --stage 2        # 跑1+2阶段
  python3 scan_pipeline.py --candidates 000887,002575  # 跳过1-2直接跑第三阶段

输出:
  ~/.hermes/pipeline_output/{date}_stage1.json
  ~/.hermes/pipeline_output/{date}_stage2.json
  ~/.hermes/pipeline_output/{date}_final.json
"""
import sys, os, json, sqlite3, time, re
from datetime import datetime, timedelta
from collections import defaultdict

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

DB = os.path.expanduser("~/.hermes/astock_data.db")
OUTPUT_DIR = os.path.expanduser("~/.hermes/pipeline_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# 工具函数
# ============================================================

def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    print(f"  [{t}] {msg}")

def get_latest_date():
    conn = sqlite3.connect(DB)
    d = conn.execute("SELECT MAX(date) FROM feat").fetchone()[0]
    conn.close()
    return d

def prev_n_trading_days(target_date, n):
    """获取 target_date 之前的第n个交易日（含target_date本身）"""
    conn = sqlite3.connect(DB)
    days = conn.execute("""
        SELECT DISTINCT date FROM daily_klines 
        WHERE date <= ? ORDER BY date DESC LIMIT ?
    """, (target_date, n + 5)).fetchall()
    conn.close()
    days = [d[0] for d in days]
    if len(days) >= n:
        return days[n - 1]
    return None

def get_trading_days(target_date, count):
    """返回从target_date往前count个交易日（含target_date，倒序）"""
    conn = sqlite3.connect(DB)
    days = conn.execute("""
        SELECT DISTINCT date FROM daily_klines 
        WHERE date <= ? ORDER BY date DESC LIMIT ?
    """, (target_date, count + 5)).fetchall()
    conn.close()
    return [d[0] for d in days]


def load_market_data(target_date):
    """从feat表加载全市场数据，返回list[dict]"""
    conn = sqlite3.connect(DB)
    rows = conn.execute("""
        SELECT f.code, s.name,
               f.close, f.chg, f.amp, f.vr_5, f.vr_20,
               f.pos_20d, f.pos_60d, f.ma20_pct, f.ma60_pct,
               f.ret1, f.ret3, f.ret5, f.down_days, f.up_days,
               f.volume, f.ma5, f.ma10, f.ma20
        FROM feat f
        JOIN stocks s ON f.code = s.code
        WHERE f.date = ?
          AND f.code NOT LIKE '688%'
          AND s.name NOT LIKE '%ST%'
          AND s.name NOT LIKE '%*ST%'
          AND f.code NOT LIKE '4%'
          AND f.code NOT LIKE '83%'
          AND f.code NOT LIKE '87%'
          AND f.chg IS NOT NULL
    """, (target_date,)).fetchall()
    conn.close()
    
    cols = ['code','name','close','chg','amp','vr_5','vr_20',
            'pos_20d','pos_60d','ma20_pct','ma60_pct',
            'ret1','ret3','ret5','down_days','up_days',
            'volume','ma5','ma10','ma20']
    
    result = []
    for row in rows:
        d = {}
        for i, col in enumerate(cols):
            val = row[i]
            if col in ('close','chg','amp','vr_5','vr_20','pos_20d','pos_60d',
                       'ma20_pct','ma60_pct','ret1','ret3','ret5',
                       'down_days','up_days','volume','ma5','ma10','ma20'):
                try:
                    val = float(val)
                except:
                    val = 0.0
            d[col] = val
        result.append(d)
    return result


# ============================================================
# 第一阶段：策略筛选
# ============================================================

def stage1_three_crows(target_date, conn=None):
    """
    三阴选股 — 纯SQLite，从 daily_klines 表计算
    
    通达信三阴公式：
    T-3涨停 (REF(C,3)/REF(C,4)>=1.095)
    AND AMOUNT < REF(AMOUNT,1) AND REF(AMOUNT,1) < REF(AMOUNT,2)
    AND C > REF(O,3)
    AND O > REF(L,3)
    AND C < REF(C,1)
    """
    need_close = conn or sqlite3.connect(DB)
    should_close = conn is None
    
    # 获取最近7个交易日
    days = get_trading_days(target_date, 7)
    if len(days) < 6:
        log(f"  交易日不足: {len(days)}/6，跳过三阴")
        if should_close: need_close.close()
        return []
    
    # T=今日, T1=昨日, T2=前天, T3=3天前, T4=4天前
    t0 = days[0]    # 今日
    t1 = days[1]    # 昨天
    t2 = days[2]    # 前天
    t3 = days[3]    # 3天前
    t4 = days[4]    # 4天前
    t5 = days[5]    # 5天前
    
    log(f"  三阴日期: T(今日)={t0}, T-1={t1}, T-2={t2}, T-3(涨停日)={t3}, T-4={t4}")
    
    # 直接用SQL窗口函数算
    sql = f"""
        WITH k AS (
            SELECT code,
                   MAX(CASE WHEN date = '{t0}' THEN close END) AS c0,
                   MAX(CASE WHEN date = '{t0}' THEN open END) AS o0,
                   MAX(CASE WHEN date = '{t0}' THEN low END) AS l0,
                   MAX(CASE WHEN date = '{t0}' THEN volume END) AS v0,
                   MAX(CASE WHEN date = '{t1}' THEN close END) AS c1,
                   MAX(CASE WHEN date = '{t1}' THEN open END) AS o1,
                   MAX(CASE WHEN date = '{t1}' THEN volume END) AS v1,
                   MAX(CASE WHEN date = '{t2}' THEN close END) AS c2,
                   MAX(CASE WHEN date = '{t2}' THEN volume END) AS v2,
                   MAX(CASE WHEN date = '{t3}' THEN close END) AS c3,
                   MAX(CASE WHEN date = '{t3}' THEN open END) AS o3,
                   MAX(CASE WHEN date = '{t3}' THEN low END) AS l3,
                   MAX(CASE WHEN date = '{t3}' THEN volume END) AS v3,
                   MAX(CASE WHEN date = '{t4}' THEN close END) AS c4,
                   MAX(CASE WHEN date = '{t5}' THEN close END) AS c5
            FROM daily_klines
            WHERE date IN ('{t0}','{t1}','{t2}','{t3}','{t4}','{t5}')
            GROUP BY code
            HAVING c0 IS NOT NULL AND c1 IS NOT NULL AND c3 IS NOT NULL AND c4 IS NOT NULL
        )
        SELECT k.code, s.name, k.c0, (k.c0 - k.c1) / k.c1 * 100 AS chg,
               k.v0, k.v1, k.v2, k.c3, k.o3, k.l3, k.c4, k.c5
        FROM k
        JOIN stocks s ON k.code = s.code
        WHERE 1=1
          AND k.code NOT LIKE '688%'
          AND s.name NOT LIKE '%ST%' AND s.name NOT LIKE '%*ST%'
          AND k.code NOT LIKE '4%' AND k.code NOT LIKE '83%' AND k.code NOT LIKE '87%'
          -- T-3涨停 (REF(C,3)/REF(C,4) >= 1.095)
          AND ROUND(k.c4 * 1.1, 2) - k.c3 < 0.01
          -- AMOUNT 递减: v0 < v1 < v2 且 v3 > v2（涨停日放量）
          AND k.v0 < k.v1 AND k.v1 < k.v2
          -- C > REF(O,3)
          AND k.c0 > k.o3
          -- O > REF(L,3)
          AND k.o0 > k.l3
          -- 收跌: C < REF(C,1)
          AND k.c0 < k.c1
    """
    
    rows = need_close.execute(sql).fetchall()
    
    candidates = []
    for r in rows:
        code, name, price, chg, v0, v1, v2, c3, o3, l3, c4, c5 = r
        candidates.append({
            'code': code,
            'name': name,
            'price': float(price or 0),
            'chg': round(float(chg or 0), 2),
            'strategy': '三阴',
            'detail': f"涨停日{c3:.2f}→量{v0:.0f}<{v1:.0f}<{v2:.0f}→收跌"
        })
    
    if should_close: need_close.close()
    return candidates


def stage1_s3(market_data):
    """S3超跌反弹 — feat表条件过滤"""
    candidates = []
    for row in market_data:
        if (row['pos_20d'] < 20 and
            3 <= row['chg'] < 7 and
            1.2 <= row['vr_5'] < 2.5 and
            row['ma20_pct'] < -8):
            candidates.append({
                'code': row['code'],
                'name': row['name'],
                'price': row['close'],
                'chg': row['chg'],
                'strategy': 'S3',
                'detail': f"超跌(20日位{row['pos_20d']:.0f}%, vr{row['vr_5']:.1f}x, MA20{row['ma20_pct']:.1f}%)"
            })
    return candidates


def stage1_sanmai(market_data, target_date):
    """三买v2 — 中枢突破+回抽不破ZG"""
    import numpy as np
    
    conn = sqlite3.connect(DB)
    candidates = []
    
    stocks_with_name = {r['code']: r for r in market_data}
    codes = list(stocks_with_name.keys())
    
    for ci, code in enumerate(codes):
        row = stocks_with_name[code]
        
        klines = conn.execute("""
            SELECT date, open, high, low, close, volume
            FROM daily_klines WHERE code = ? ORDER BY date DESC LIMIT 90
        """, (code,)).fetchall()
        klines = list(reversed(klines))
        
        if len(klines) < 25:
            continue
        
        arr = np.array([(k[1], k[2], k[3], k[4]) for k in klines], dtype=float)
        highs, lows, closes = arr[:,1], arr[:,2], arr[:,3]
        n = len(klines)
        cur = float(closes[-1])
        
        try:
            # 找中枢
            zones = []
            for i in range(max(0, n-60), n-8):
                seg_h = highs[i:i+8]; seg_l = lows[i:i+8]
                sg = float(seg_h.max()); sd = float(seg_l.min())
                if sd > 0 and (sg-sd)/sd*100 < 15:
                    zones.append((sg, sd))
            
            if zones:
                zg, zd = zones[-1]
            else:
                # 找波动率最小区间
                ps = []
                for idx in range(max(0,n-30), min(n-10,n-1)):
                    sl = highs[max(0,idx):min(n-1,idx+10)] - lows[max(0,idx):min(n-1,idx+10)]
                    if len(sl) >= 5:
                        ps.append((np.std(sl), idx))
                if not ps: continue
                mi = min(ps, key=lambda x: x[0])[1]
                if mi + 10 > n: continue
                zg = float(np.max(highs[mi:mi+10]))
                zd = float(np.min(lows[mi:mi+10]))
                if zd > 0 and (zg-zd)/zd*100 >= 12: continue
            
            # 检验突破
            seg20_h = highs[-20:] if n >= 20 else highs
            ri = int(np.argmax(seg20_h)) + (n - 20 if n >= 20 else 0)
            rh = float(highs[ri])
            if rh <= zg * 1.03: continue
            
            pb = (rh - cur) / rh * 100
            if pb < 5 or pb > 15: continue
            if cur <= zg: continue
            
            vr5 = float(row['vr_5'])
            if vr5 < 0.6: continue
            
            ma20 = float(row['ma20'])
            close_feat = float(row['close'])
            if ma20 > 0 and close_feat < ma20: continue
            
            # 排除涨停后大跌
            bad = False
            for j in range(max(2, n-5), n):
                pc = (closes[j-1]-closes[j-2])/closes[j-2]*100 if closes[j-2] != 0 else 0
                cc = (closes[j]-closes[j-1])/closes[j-1]*100 if closes[j-1] != 0 else 0
                if pc > 9 and cc < -5: bad = True; break
            if bad: continue
            
            candidates.append({
                'code': code, 'name': row['name'],
                'price': cur, 'chg': float(row['chg']),
                'strategy': '三买v2',
                'detail': f"中枢{zg:.0f}→突破{rh:.0f}→回抽{pb:.0f}%"
            })
        except:
            continue
        
        if (ci + 1) % 500 == 0:
            log(f"  三买进度: {ci+1}/{len(codes)} → {len(candidates)}只")
    
    conn.close()
    return candidates


def stage1_merge(candidates_list):
    """合并三个策略的并集，去重"""
    result = {}
    for group in candidates_list:
        for c in group:
            code = c['code']
            if code in result:
                result[code]['strategy'] += f"+{c['strategy']}"
                result[code]['detail'] += f" | {c['detail']}"
            else:
                result[code] = dict(c)
    return list(result.values())


# ============================================================
# 第二阶段：6维度评分 → 前10
# ============================================================

def stage2_score(candidates, market_data):
    """
    第二阶段评分 — 策略质量 + 板块热度
    
    两轮过滤：
    1. 策略质量分（S3/三买各自的数据区分特征）
    2. 板块热度分（属于热门产业链/行业则加分）
    
    板块数据来源（优先级）：
    - 产业链地图DB chain_stocks（AI算力/半导体等13大产业链）
    - stock_industries（通达信F10行业分类，后台持续拉取中）
    
    数据依据（2026年回测）：
    - S3真实区分特征：低振幅 > 小量比 > ma20偏离不极端
    - 三买v2区分特征：回抽5-12%最优 > 站稳MA20 > 量比温和
    """
    scored = []
    md_map = {r['code']: r for r in market_data}
    
    # 加载产业链映射：code → 产业链名列表
    conn = sqlite3.connect(DB)
    chain_map = {}
    try:
        rows = conn.execute("""
            SELECT DISTINCT cs.code, i.name
            FROM chain_stocks cs
            JOIN chain_links cl ON cs.link_id=cl.id
            JOIN chain_industry_tags cit ON cl.chain_id=cit.chain_id
            JOIN industries i ON cit.industry_id=i.id
        """).fetchall()
        for code, ind_name in rows:
            if code not in chain_map:
                chain_map[code] = []
            chain_map[code].append(ind_name)
    except:
        pass
    
    # 加载通达信行业分类
    industry_map = {}
    try:
        rows = conn.execute("SELECT code, industry_name FROM stock_industries WHERE industry_name IS NOT NULL").fetchall()
        for code, ind_name in rows:
            industry_map[code] = ind_name
    except:
        pass
    conn.close()
    
    # 热门板块（产业链名 + 通达信行业关键词映射）
    CHAIN_HOT_INDUSTRIES = ['AI算力', 'AI应用', '半导体', 'CPO(共封装光学)', 
                            '机器人', '低空经济', '新能源', '商业航天']
    # 通达信行业名 → 是否热门
    INDUSTRY_HOT_KEYWORDS = ['通信', '半导体', '芯片', '软件', 'IT', '电子', '计算机',
                             '光伏', '电池', '电力', '汽车', '机器人', '航空航天',
                             'AI', '算力', '光模块', 'PCB', '消费电子']
    
    for c in candidates:
        code = c['code']
        row = md_map.get(code)
        if not row: continue
        
        strategy = c.get('strategy', '')
        detail = c.get('detail', '')
        
        scores = {}
        total = 0
        
        # ================================================================
        # S3评分（基于数据：低振幅+小量比+ma20偏离不极端）
        # ================================================================
        if 'S3' in strategy:
            s3_score = 0
            # 数据：振幅2-4%胜率24.4% >> 4-6%胜率15.9% >> 6-8%胜率12.3% >> >8%胜率11.3%
            amp = float(row['amp'])
            if amp < 3: s3_score += 3
            elif amp < 5: s3_score += 4    # 最优区间
            elif amp < 7: s3_score += 2
            else: s3_score += 1
            
            # 数据：ma20偏离-8~-10%胜率18.4% > -15~-10%胜率12.7% > -25~-15%胜率9.1%
            mp20 = float(row['ma20_pct'])
            if mp20 >= -10: s3_score += 4
            elif mp20 >= -15: s3_score += 2
            else: s3_score += 1
            
            # 数据：量比1.2-1.5胜率16.8% > 1.5-2.0胜率11.0% > 2.0-2.5胜率9.4%
            vr5 = float(row['vr_5'])
            if vr5 < 1.5: s3_score += 3
            elif vr5 < 2.0: s3_score += 1
            
            s3_score = min(s3_score, 10)
            scores['S3反转质量'] = s3_score
            total += s3_score
        
        # ================================================================
        # 三买v2评分（回抽幅度+均线支撑+量价配合）
        # ================================================================
        if '三买' in strategy:
            sm_score = 0
            # 回抽5-12%是黄金区间
            m = re.search(r'回抽([\d.]+)%', detail)
            if m:
                pb = float(m.group(1))
                if 5 <= pb <= 12: sm_score += 4
                elif 3 <= pb < 5: sm_score += 2
                else: sm_score += 1
            
            # 站在MA20上方是强支撑
            ma20 = float(row['ma20'])
            close = float(row['close'])
            if ma20 > 0:
                ma20_dist = (close - ma20) / ma20 * 100
                if 0 < ma20_dist <= 5: sm_score += 3  # 刚站上，最佳
                elif ma20_dist > 5: sm_score += 1      # 离均线远了
                elif -3 <= ma20_dist <= 0: sm_score += 1 # 略破但可能假破
            
            # 5日线趋势向上
            ma5 = float(row['ma5'])
            if close > ma5: sm_score += 2
            
            # 量比适中（不放巨量，维持温和）
            vr5 = float(row['vr_5'])
            if 0.6 <= vr5 <= 1.5: sm_score += 1
            
            sm_score = min(sm_score, 10)
            scores['三买中枢质量'] = sm_score
            total += sm_score
        
        # ================================================================
        # 通用加分项
        # ================================================================
        bonus = 0
        # 60日位置不过高（有上涨空间）
        pos60 = float(row['pos_60d'])
        if pos60 < 50: bonus += 2
        # 次日预期收益为正
        if float(row['ret1']) > 0: bonus += 2
        # 三日预期收益为正
        if float(row['ret3']) > 0: bonus += 1
        scores['通用加分'] = min(bonus, 5)
        total += min(bonus, 5)
        
        # ================================================================
        # 板块热度加分（产业链DB + 通达信行业分类）
        # ================================================================
        industries = chain_map.get(code, [])
        hot_matched = [ind for ind in industries if ind in CHAIN_HOT_INDUSTRIES]
        
        # 检查通达信行业分类
        tdx_industry = industry_map.get(code, '')
        tdx_hot = False
        if tdx_industry:
            for kw in INDUSTRY_HOT_KEYWORDS:
                if kw in tdx_industry:
                    tdx_hot = True
                    break
        
        sector_score = 0
        sector_tag = ''
        if hot_matched:
            sector_score = 5
            sector_tag = ','.join(hot_matched)
        elif tdx_hot:
            sector_score = 3
            sector_tag = tdx_industry
        
        if sector_score > 0:
            scores['板块热度'] = sector_score
            total += sector_score
        
        c['sector'] = sector_tag
        
        # 双策略命中额外加分
        strategy_set = set(s.strip() for s in re.split(r'[+]', strategy) if s.strip())
        if len(strategy_set) >= 2:
            scores['多策略共振'] = 3
            total += 3
        
        c['scores'] = scores
        c['total_score'] = total
        scored.append(c)
    
    scored.sort(key=lambda x: x['total_score'], reverse=True)
    return scored[:10]


# ============================================================
# 第三阶段：框架评估 → 前3
# ============================================================

def stage3_agent_evaluation(candidates, target_date):
    log(f"第三阶段：DeepSeek框架深度评估 — {len(candidates)}只")
    
    results = []
    for c in candidates:
        code = c['code']
        name = c['name']
        log(f"  ▶ {code} {name}")
        
        import subprocess
        result = subprocess.run(
            ['python3', 'cli/analyze.py', '--ticker', code, '--output', 'summary'],
            capture_output=True, text=True, timeout=120,
            cwd=PROJECT_DIR,
            env={**os.environ, 'DEEPSEEK_API_KEY': os.environ.get('DEEPSEEK_API_KEY', '')}
        )
        
        output = result.stdout if result.returncode == 0 else result.stderr
        summary = output[:2000] if output else "框架返回为空"
        
        framework_score = _score_agent_report(summary, c)
        c['framework_report'] = summary[:800]
        c['framework_score'] = framework_score
        results.append(c)
    
    for r in results:
        r['final_score'] = round(r['total_score'] * 0.6 + r.get('framework_score', 0) * 4, 1)
    
    results.sort(key=lambda x: x['final_score'], reverse=True)
    return results[:3]


def _score_agent_report(report, candidate):
    if not report or len(report) < 50: return 3
    score = 5
    if 'bull' in report.lower() and 'bear' in report.lower(): score += 2
    if any(kw in report for kw in ['买入','买','持有','卖出','建议']): score += 2
    if any(kw in report for kw in ['均线','MACD','RSI','支撑','阻力','中枢','背驰']): score += 1
    if '风险' in report or '止损' in report: score += 1
    if '目标' in report and '元' in report: score += 1
    return min(10, score)


# ============================================================
# 主流程
# ============================================================

def run_pipeline(target_date=None, max_stage=3):
    if not target_date:
        target_date = get_latest_date()
    
    print(f"\n{'='*55}")
    print(f"  三阶段选股流水线")
    print(f"  日期: {target_date}")
    print(f"  策略: S3超跌反弹 + 三买v2中枢突破")
    print(f"{'='*55}")
    t0 = time.time()
    
    # 加载市场数据
    log(f"加载市场数据...")
    market_data = load_market_data(target_date)
    log(f"全市场: {len(market_data)}只 (排除ST/688)")
    
    if max_stage >= 1:
        print(f"\n{'─'*55}")
        print(f"  第一阶段：S3超跌反弹 + 三买v2")
        print(f"{'─'*55}")
        t1 = time.time()
        
        log("S3超跌反弹...")
        s3 = stage1_s3(market_data)
        log(f"S3超跌反弹: {len(s3)}只")
        for c in s3[:10]:
            print(f"    {c['code']} {c['name']:<8}  {c['price']:.2f}  {c['chg']:+.2f}%")
        if len(s3) > 10:
            print(f"    ...还有{len(s3)-10}只")
        
        log("三买v2 (中枢突破)...")
        sanmai = stage1_sanmai(market_data, target_date)
        log(f"三买v2: {len(sanmai)}只")
        for c in sanmai[:10]:
            print(f"    {c['code']} {c['name']:<8}  {c['price']:.2f}  {c['chg']:+.2f}%")
        if len(sanmai) > 10:
            print(f"    ...还有{len(sanmai)-10}只")
        
        merged = stage1_merge([s3, sanmai])
        elapsed = time.time() - t1
        log(f"✅ 并集: {len(merged)}只 (去重后) | 耗时: {elapsed:.0f}s")
        
        strategy_counts = defaultdict(int)
        for c in merged:
            strategy_counts[c['strategy']] += 1
        for s, n in sorted(strategy_counts.items(), key=lambda x: -x[1]):
            print(f"    {s}: {n}只")
        
        if not merged:
            print("\n❌ 第一阶段无候选股，流程终止")
            return
        
        with open(os.path.join(OUTPUT_DIR, f"{target_date}_stage1.json"), 'w') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2, default=str)
        
        if max_stage >= 2:
            print(f"\n{'─'*55}")
            print(f"  第二阶段：6维度评分 → 前10")
            print(f"{'─'*55}")
            
            top10 = stage2_score(merged, market_data)
            
            # 收集所有评分维度名
            all_keys = set()
            for c in top10:
                all_keys.update(c.get('scores', {}).keys())
            score_keys = sorted(all_keys)
            header = f"{'代码':>8} {'名称':<10} {'总分':>5}  "
            for k in score_keys:
                header += f"{k:<12}"
            header += " 策略"
            print(header)
            print(f"{'─'*max(70, len(header))}")
            for c in top10:
                s = c['scores']
                line = f"{c['code']:>8} {c['name']:<10} {c['total_score']:>5}  "
                for k in score_keys:
                    line += f"{s.get(k, 0):>4}       "
                sector_tag = c.get('sector', '')
                if sector_tag:
                    line += f"  🔥{sector_tag}"
                else:
                    line += f"  {c['strategy']}"
                print(line)
            
            with open(os.path.join(OUTPUT_DIR, f"{target_date}_stage2.json"), 'w') as f:
                json.dump(top10, f, ensure_ascii=False, indent=2, default=str)
            
            if max_stage >= 3:
                print(f"\n{'─'*55}")
                print(f"  第三阶段：DeepSeek框架深度评估")
                print(f"{'─'*55}")
                
                top3 = stage3_agent_evaluation(top10, target_date)
                
                print(f"\n{'代码':>8} {'名称':<10} {'综合分':>6}  {'6维':>4} {'框架':>4}  策略")
                print(f"{'─'*55}")
                for c in top3:
                    print(f"{c['code']:>8} {c['name']:<10} {c['final_score']:>6.1f}  "
                          f"{c['total_score']:>4} {c.get('framework_score',0):>4}  "
                          f"{c['strategy']}")
                
                with open(os.path.join(OUTPUT_DIR, f"{target_date}_final.json"), 'w') as f:
                    json.dump(top3, f, ensure_ascii=False, indent=2, default=str)
    
    log(f"✅ 流水线完成 | 总耗时: {time.time()-t0:.0f}s")


# ============================================================
# 入口
# ============================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="三阶段选股流水线")
    parser.add_argument('--date', type=str, default=None)
    parser.add_argument('--stage', type=int, default=3)
    parser.add_argument('--candidates', type=str, default=None,
                       help='跳过1-2阶段，直接对候选做第三阶段')
    args = parser.parse_args()
    
    if args.candidates:
        codes = args.candidates.split(',')
        target = args.date or get_latest_date()
        md = load_market_data(target)
        md_map = {r['code']: r for r in md}
        cands = []
        for code in codes:
            row = md_map.get(code)
            if row:
                cands.append({
                    'code': code, 'name': row['name'],
                    'price': row['close'], 'chg': row['chg'],
                    'strategy': '手动', 'detail': '',
                    'scores': {}, 'total_score': 50
                })
        if cands:
            top3 = stage3_agent_evaluation(cands, target)
            for c in top3:
                print(f"  {c['code']} {c['name']} 综合{c.get('final_score',50)}")
    else:
        run_pipeline(args.date, max_stage=args.stage)
