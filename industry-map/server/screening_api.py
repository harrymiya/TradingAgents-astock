#!/usr/bin/env python3
"""
screening_api.py — 选股API，每个策略走完整3级管道
  Stage 1: SQL条件筛选（支持实时模式：feat表条件 + 腾讯行情覆盖chg）
  Stage 2: 6维度评分 → Top10（与 scan_pipeline.py 一致）
  Stage 3: TradingAgents LLM深度分析（异步，前端轮询结果）

2026-06-11 升级: 新增realtime模式，盘中选股用腾讯实时API覆盖chg
"""
import sys, os, json, sqlite3, re
from datetime import datetime

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

DB = os.path.expanduser("~/.hermes/astock_data.db")

def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    print(f"  [{t}] {msg}", flush=True)

def json_handler(body):
    try:
        result = json.loads(body)
        action = result.get("action", "")
        date = result.get("date", "")
        realtime = result.get("realtime", False)  # 🆕 实时模式标志
        
        if action == "s3":
            data = run_s3_stage2(date, realtime)
        elif action == "sanmai":
            data = run_sanmai_stage2(date, realtime)
        elif action == "sanyin":
            data = run_sanyin_stage2(date)
        elif action == "pipeline":
            data = run_pipeline_stage2(date, realtime)
        elif action == "golden_pit":
            data = run_golden_pit(date, realtime)
        else:
            data = {"error": f"Unknown action: {action}"}
        
        resp = json.dumps(data, ensure_ascii=False, default=str)
        return (200, {"Content-Type": "application/json; charset=utf-8"}, resp.encode())
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        log(traceback.format_exc())
        resp = json.dumps({"error": str(e)}, ensure_ascii=False)
        return (500, {"Content-Type": "application/json; charset=utf-8"}, resp.encode())


# === 工具函数 ===

def get_latest_date():
    conn = sqlite3.connect(DB)
    d = conn.execute("SELECT MAX(date) FROM feat").fetchone()[0]
    conn.close()
    return d

def _get_trading_days(target_date, count):
    conn = sqlite3.connect(DB)
    days = conn.execute("""
        SELECT DISTINCT date FROM daily_klines 
        WHERE date <= ? ORDER BY date DESC LIMIT ?
    """, (target_date, count + 5)).fetchall()
    conn.close()
    return [d[0] for d in days]


# ================================================================
# 🆕 腾讯实时行情获取（盘中覆盖feat数据）
# ================================================================

def fetch_realtime_prices(codes):
    """
    从腾讯API批量获取实时股价和涨跌幅
    返回: {code: {'price': float, 'chg': float, 'high': float, 'low': float, 'volume': float}, ...}
    """
    if not codes:
        return {}
    
    import urllib.request
    import urllib.parse
    
    # 腾讯API需要sz/sh前缀
    batches = []
    batch = []
    for code in codes:
        prefix = "sh" if code.startswith('6') else "sz"
        batch.append(f"{prefix}{code}")
        if len(batch) >= 50:  # 腾讯API限制
            batches.append(batch)
            batch = []
    if batch:
        batches.append(batch)
    
    result = {}
    for batch in batches:
        try:
            qs = ",".join(batch)
            url = f"http://qt.gtimg.cn/q={qs}"
            resp = urllib.request.urlopen(url, timeout=5).read().decode("gbk")
            
            # 腾讯API返回格式: v_sz000001="字段1~字段2~...";
            for line in resp.strip().split("\n"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                m = re.search(r'"([^"]*)"', line)
                if not m:
                    continue
                fields = m.group(1).split("~")
                if len(fields) < 32:
                    continue
                # fields[2] = 代码, fields[3] = 当前价, fields[32] = 涨跌额, fields[33] = 涨跌幅
                # fields[5] = 今开, fields[34] = 最高, fields[35] = 最低
                # fields[6] = 成交量(手) 
                code = fields[2]
                price = float(fields[3]) if fields[3] else 0
                chg_pct = float(fields[32]) if fields[32] else 0  # 涨跌幅%
                high = float(fields[33]) if fields[33] else 0
                low = float(fields[34]) if fields[34] else 0
                volume = float(fields[6]) if fields[6] else 0  # 手
                
                if price > 0:
                    result[code] = {
                        'price': price,
                        'chg': chg_pct,  # 涨跌幅%
                        'high': high,
                        'low': low,
                        'volume': volume,
                    }
        except Exception as e:
            log(f"腾讯行情请求失败(batch {len(batch)}只): {e}")
    
    return result


def apply_realtime(candidates):
    """
    用腾讯实时数据覆盖候选股的chg和close
    如果实时chg不再满足S3条件立即剔除
    """
    if not candidates:
        return candidates
    
    codes = [c['code'] for c in candidates]
    rt = fetch_realtime_prices(codes)
    log(f"腾讯实时已返回 {len(rt)}/{len(codes)} 只数据")
    
    filtered = []
    removed_signal = 0
    market_zero_count = 0  # 超过半数为0说明盘后休市
    total_checked = 0
    for c in candidates:
        code = c['code']
        if code in rt:
            r = rt[code]
            total_checked += 1
            # 检测是否盘后休市（大量股票实时chg=0但有价）
            if r['chg'] == 0 and r['price'] > 0:
                market_zero_count += 1
            old_chg = c.get('chg', 0)
            old_close = c.get('close', 0)
            c['chg'] = round(r['chg'], 2)
            c['close'] = round(r['price'], 2)
            c['realtime_chg'] = round(r['chg'], 2)
            c['realtime_price'] = round(r['price'], 2)
            c['_is_realtime'] = True
    
    # 🆕 盘后保护：超过60%的股票实时chg=0 → 说明休市，直接用feat表数据
    if total_checked > 0 and market_zero_count / total_checked > 0.6:
        log(f"盘后休市状态({market_zero_count}/{total_checked}只chg=0)，跳过实时覆盖")
        return candidates  # 返回原数据
    
    for c in candidates:
        code = c['code']
        if code in rt:
            r = rt[code]
            old_chg = c.get('chg', 0)
            strategy = c.get('strategy', '')
            if 'S3' in strategy:
                if r['chg'] < 3 or r['chg'] >= 7:
                    removed_signal += 1
                    log(f"  ❌ {code} {c.get('name','')} 实时chg={r['chg']:+.2f}% 已不满足S3 → 剔除")
                    continue
                # 量比也查一下：用实时volume反推近似vr5
                if 'vr_5' in c and c['vr_5'] is not None and c['vr_5'] > 0:
                    # 取feat表的量比底线作为参考
                    pass  # vr5用feat表数据，因为量比计算需要近5日均量
            
            filtered.append(c)
            if abs(r['chg'] - old_chg) > 1:
                log(f"  🔄 {code} {c.get('name','')} chg: {old_chg:+.2f}% → {r['chg']:+.2f}%")
        else:
            # 腾讯没返回数据的，带着原数据通过（可能是停牌或节假日）
            filtered.append(c)
    
    log(f"实时覆盖完成: {len(filtered)}只通过, {removed_signal}只因实时chg不满足条件被剔除")
    return filtered


# ================================================================
# Stage 1: 策略筛选（支持实时模式）
# ================================================================

def stage1_s3(date_str, realtime=False):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
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
          AND f.down_days < 5  /* 🆕 连跌<5天，胜率30%→68% */
          AND f.code NOT LIKE '688%'
          AND s.name NOT LIKE '%ST%'
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
        d['detail'] = f"超跌(20日位{d['pos_20d']:.0f}%, vr{d['vr_5']:.1f}x, MA20{d['ma20_pct']:.1f}%)"
        if realtime:
            d['detail'] += " (实时)"
        results.append(d)
    conn.close()
    
    # 🆕 实时模式：用腾讯行情覆盖chg并重新过滤
    if realtime and results:
        log(f"S3 Stage1 (feat): {len(results)}只 → 应用实时数据覆盖...")
        results = apply_realtime(results)
    
    log(f"S3 Stage1{' (实时)' if realtime else ''}: {len(results)}只")
    return results


def stage1_sanmai(date_str, realtime=False):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT f.code, s.name, f.close, f.chg, f.amp, f.vr_5, f.vr_20,
               f.ma5, f.ma10, f.ma20, f.pos_20d, f.pos_60d, f.ma20_pct, f.ma60_pct,
               f.ret1, f.ret3, f.ret5, f.volume
        FROM feat f
        JOIN stocks s ON f.code = s.code
        WHERE f.date = ?
          AND f.code NOT LIKE '688%'
          AND s.name NOT LIKE '%ST%'
          AND f.close IS NOT NULL
          AND f.close > 0
    """, (date_str,))
    market = cur.fetchall()
    
    import numpy as np
    results = []
    
    for code, name, close, chg, amp, vr5, vr20, ma5, ma10, ma20, pos20, pos60, ma20_pct, ma60_pct, ret1, ret3, ret5, volume in market:
        close = float(close or 0)
        chg = float(chg or 0)
        amp = float(amp or 0)
        vr5 = float(vr5 or 0)
        vr20 = float(vr20 or 0)
        ma5 = float(ma5 or 0)
        ma10 = float(ma10 or 0)
        ma20 = float(ma20 or 0)
        if close <= 0 or ma20 <= 0:
            continue

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
        cur_close = float(closes[-1])

        try:
            zones = []
            for i in range(max(0, n-60), n-8):
                seg_h = highs[i:i+8]; seg_l = lows[i:i+8]
                sg = float(seg_h.max()); sd = float(seg_l.min())
                if sd > 0 and (sg-sd)/sd*100 < 15:
                    zones.append((sg, sd))
            if zones:
                zg, zd = zones[-1]
            else:
                ps = []
                for i in range(max(0,n-30), min(n-10,n-1)):
                    sl = highs[max(0,i):min(n-1,i+10)] - lows[max(0,i):min(n-1,i+10)]
                    if len(sl) >= 5:
                        ps.append((float(np.std(sl)), i))
                if not ps: continue
                mi = min(ps, key=lambda x: x[0])[1]
                if mi + 10 > n: continue
                zg = float(np.max(highs[mi:mi+10]))
                zd = float(np.min(lows[mi:mi+10]))
                if zd > 0 and (zg-zd)/zd*100 >= 12: continue
            
            seg20_h = highs[-20:] if n >= 20 else highs
            ri = int(np.argmax(seg20_h)) + (n - 20 if n >= 20 else 0)
            rh = float(highs[ri])
            if rh <= zg * 1.03: continue
            
            pb = (rh - cur_close) / rh * 100
            if pb < 5 or pb > 15: continue
            if cur_close <= zg: continue
            if vr5 < 0.6: continue
            
            ma20_dist = (cur_close - ma20) / ma20 * 100
            if ma20_dist < 0: continue

            bad = False
            for j in range(max(2, n-5), n):
                pc = (closes[j-1]-closes[j-2])/closes[j-2]*100 if closes[j-2] != 0 else 0
                cc = (closes[j]-closes[j-1])/closes[j-1]*100 if closes[j-1] != 0 else 0
                if pc > 9 and cc < -5: bad = True; break
            if bad: continue
            
            detail = f"中枢{zg:.0f}→突破{rh:.0f}→回抽{pb:.0f}%"
            results.append({
                'code': code, 'name': name,
                'close': cur_close, 'chg': round(chg, 2),
                'vr_5': round(vr5, 1), 'ma20_pct': round(ma20_dist, 1),
                'pos_20d': round(pos20, 1), 'pos_60d': round(pos60, 1),
                'amp': round(amp, 2), 'ma5': round(ma5, 2), 'ma10': round(ma10, 2),
                'ma20': round(ma20, 2), 'ret1': round(ret1, 2), 'ret3': round(ret3, 2),
                'ret5': round(ret5, 2), 'volume': volume,
                'strategy': '三买v2',
                'detail': detail,
                '_is_realtime': realtime,
            })
        except:
            continue
        
        if (len(results) + 1) % 500 == 0:
            log(f"  三买进度: {len(results)}只")
    
    conn.close()
    
    # 🆕 实时模式：三买也用实时数据覆盖（但三买不依赖chg，主要看中枢结构）
    # 三买主要看中枢突破+回抽，实时chg变化不会直接剔除，但可以让前端看到实时价
    if realtime and results:
        log(f"三买 Stage1 (feat): {len(results)}只 → 补充实时行情...")
        rt = fetch_realtime_prices([r['code'] for r in results])
        for c in results:
            if c['code'] in rt:
                r = rt[c['code']]
                c['realtime_chg'] = round(r['chg'], 2)
                c['realtime_price'] = round(r['price'], 2)
    
    log(f"三买 Stage1: {len(results)}只")
    return results


def stage1_sanyin(date_str):
    days = _get_trading_days(date_str, 7)
    if len(days) < 6:
        return []

    t0, t1, t2, t3, t4, t5 = days[0], days[1], days[2], days[3], days[4], days[5]

    sql = f"""
        WITH k AS (
            SELECT code,
                   MAX(CASE WHEN date = '{t0}' THEN close END) AS c0,
                   MAX(CASE WHEN date = '{t0}' THEN open END) AS o0,
                   MAX(CASE WHEN date = '{t0}' THEN low END) AS l0,
                   MAX(CASE WHEN date = '{t0}' THEN volume END) AS v0,
                   MAX(CASE WHEN date = '{t1}' THEN close END) AS c1,
                   MAX(CASE WHEN date = '{t1}' THEN volume END) AS v1,
                   MAX(CASE WHEN date = '{t2}' THEN volume END) AS v2,
                   MAX(CASE WHEN date = '{t3}' THEN close END) AS c3,
                   MAX(CASE WHEN date = '{t3}' THEN open END) AS o3,
                   MAX(CASE WHEN date = '{t3}' THEN low END) AS l3,
                   MAX(CASE WHEN date = '{t4}' THEN close END) AS c4
            FROM daily_klines
            WHERE date IN ('{t0}','{t1}','{t2}','{t3}','{t4}')
            GROUP BY code
            HAVING c0 IS NOT NULL AND c1 IS NOT NULL AND c3 IS NOT NULL AND c4 IS NOT NULL
        )
        SELECT k.code, s.name, k.c0, (k.c0 - k.c1) / k.c1 * 100 AS chg,
               k.v0, k.v1, k.v2, k.c3, k.o3, k.l3, k.c4
        FROM k
        JOIN stocks s ON k.code = s.code
        WHERE k.code NOT LIKE '688%'
          AND s.name NOT LIKE '%ST%'
          AND ROUND(k.c4 * 1.1, 2) - k.c3 < 0.01
          AND k.v0 < k.v1 AND k.v1 < k.v2
          AND k.c0 > k.o3
          AND k.o0 > k.l3
          AND k.c0 < k.c1
    """
    conn = sqlite3.connect(DB)
    rows = conn.execute(sql).fetchall()
    conn.close()

    results = []
    for r in rows:
        code, name, price, chg, v0, v1, v2, c3, o3, l3, c4 = r
        results.append({
            'code': code, 'name': name,
            'close': round(float(price or 0), 2),
            'chg': round(float(chg or 0), 2),
            'strategy': '三阴',
            'detail': f"涨停日{float(c3):.2f}→缩量→今日{float(o3 or 0):.2f}开盘站稳→收跌"
        })
    log(f"三阴 Stage1: {len(results)}只")
    return results


# ================================================================
# Stage 2: 6维度评分 → Top10
# ================================================================

def stage2_score(candidates, date_str):
    """跨策略通用评分 + 大盘调节因子 (2026-06-11 V2升级)
    
    11个相关性因子组合评分体系：
    ┌───────┬──────────────────────────────────────┬───────┬──────────────┐
    │ 权重   │ 因子                                │ 范围  │ 来源(回测)    │
    ├───────┼──────────────────────────────────────┼───────┼──────────────┤
    │ A-大盘 │ 大盘涨跌比/涨幅/超跌                │ -3~+8 │ 4445条全量    │
    │ B-板块 │ 产业链归属/热门关键词               │ 0~10  │ 板块分化      │
    │ C-趋势 │ 5日收益/60日位置/量比               │ 0~8   │ stage2原版    │
    │ D-质量 │ 振幅/连跌天数                       │ -3~+6 │ S3自身特征    │
    │ E-恐慌 │ 恐慌阴+停顿阳                       │ 0~3   │ 尾盘战法      │
    │ F-实时 │ 实时数据不确定性                    │ -1~0  │ 盘中模式      │
    └───────┴──────────────────────────────────────┴───────┴──────────────┘
    """
    conn = sqlite3.connect(DB)
    
    # === 大盘状态数据 ===
    market_row = conn.execute("""
        SELECT AVG(chg) as avg_chg,
               SUM(CASE WHEN chg > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as up_ratio,
               AVG(ma60_pct) as avg_ma60
        FROM feat WHERE date = ? AND chg IS NOT NULL AND ma60_pct IS NOT NULL
    """, (date_str,)).fetchone()
    market_avg_chg = float(market_row[0] or 0)
    market_up_ratio = float(market_row[1] or 0.5)
    market_avg_ma60 = float(market_row[2] or 0)
    
    # === A: 大盘因子 (权重-3~+8) ===
    # A1: 大盘涨跌比 (核心因子)
    #  <55% → -3, 55-60% → 0, 60-70% → +1, 70-75% → +2, >=75% → +3
    if market_up_ratio < 0.55: market_score = -3
    elif market_up_ratio < 0.60: market_score = 0
    elif market_up_ratio < 0.70: market_score = 1
    elif market_up_ratio < 0.75: market_score = 2
    else: market_score = 3
    
    # A2: 大盘平均涨幅
    #  <-1% → -2, -1~0% → -1, 0~0.5% → 0, 0.5~1% → +1, 1~2% → +2, >=2% → +3
    if market_avg_chg < -1: market_score += -2
    elif market_avg_chg < 0: market_score += -1
    elif market_avg_chg < 0.5: market_score += 0
    elif market_avg_chg < 1: market_score += 1
    elif market_avg_chg < 2: market_score += 2
    else: market_score += 3
    
    # A3: 全市场超跌加分 (S3反弹概率最高66.4%)
    # 均ma60<-10% → +4, <-5% → +2, <-2% → +1
    if market_avg_ma60 < -10: market_score += 4
    elif market_avg_ma60 < -5: market_score += 2
    elif market_avg_ma60 < -2: market_score += 1
    
    market_tag = "弱势"
    if market_up_ratio >= 0.70: market_tag = "强势"
    elif market_up_ratio >= 0.60: market_tag = "偏强"
    elif market_up_ratio >= 0.55: market_tag = "中性"
    
    # === 全市场个股数据 ===
    md_rows = conn.execute("""
        SELECT f.code, f.pos_60d, f.ret1, f.ret3, f.ret5,
               f.volume, f.chg, f.vr_5, f.amp, f.down_days,
               f.ma20_pct, f.ma60_pct
        FROM feat f
        WHERE f.date = ?
    """, (date_str,)).fetchall()
    md_cols = ['code','pos_60d','ret1','ret3','ret5','volume','chg','vr_5','amp','down_days',
               'ma20_pct','ma60_pct']
    md_map = {}
    for r in md_rows:
        d = dict(zip(md_cols, r))
        for k in md_cols[1:]: 
            try: d[k] = float(d[k])
            except: d[k] = 0
        md_map[d['code']] = d
    
    chain_rows = conn.execute("SELECT name FROM industry_chains ORDER BY sort_order").fetchall()
    all_chains = [r[0] for r in chain_rows]
    conn.close()
    
    # 行业归属
    ind_conn = sqlite3.connect(DB)
    ind_rows = ind_conn.execute(
        "SELECT code, industry_l1, industry_l2, industry_l3 FROM stock_industries"
    ).fetchall()
    stock_industry_map = {}
    for r in ind_rows:
        stock_industry_map[r[0]] = {'l1': r[1] or '', 'l2': r[2] or '', 'l3': r[3] or ''}
    ind_conn.close()
    
    # 产业链归属
    chain_stocks_conn = sqlite3.connect(DB)
    cs_rows = chain_stocks_conn.execute("""
        SELECT DISTINCT cs.code, ic.name
        FROM chain_stocks cs
        JOIN chain_links cl ON cs.link_id = cl.id
        JOIN industry_chains ic ON cl.chain_id = ic.id
    """).fetchall()
    chain_stocks_conn.close()
    stock_chains = {}
    for code, chain_name in cs_rows:
        if code not in stock_chains: stock_chains[code] = []
        stock_chains[code].append(chain_name)
    
    HOT_KEYWORDS = ['AI', '算力', '芯片', '半导体', '机器人', '低空经济', '新能源',
                    '光伏', '电池', '汽车', '光模块', 'PCB', '软件', '算网',
                    '消费电子', '创新药', '军工', '商业航天']
    
    scored = []
    for c in candidates:
        code = c['code']
        row = md_map.get(code)
        if not row: continue
        
        scores = {}
        total = 0
        
        # ============== B: 板块因子 (0~10) ==============
        chain_score = 0; chain_tag = ''
        ind_info = stock_industry_map.get(code, {})
        ind_l1 = ind_info.get('l1', ''); ind_l2 = ind_info.get('l2', '')
        chains = stock_chains.get(code, [])
        
        matched_chains = [ch for ch in all_chains if ch in chains]
        hot_keyword_matches = [kw for kw in HOT_KEYWORDS if kw in ind_l1 or kw in ind_l2]
        
        if matched_chains: chain_score += 7; chain_tag = matched_chains[0]
        if hot_keyword_matches: 
            chain_score += 3
            if not chain_tag: chain_tag = hot_keyword_matches[0]
        chain_score = min(chain_score, 10)
        scores['板块热度'] = chain_score
        total += chain_score
        
        # ============== C: 趋势因子 (0~8) ==============
        trend_score = 0
        ret5 = float(row['ret5']); pos60 = float(row['pos_60d']); vr5 = float(row['vr_5'])
        
        if ret5 > 3: trend_score += 3
        elif ret5 > 0: trend_score += 2
        elif ret5 > -3: trend_score += 1
        
        if 20 <= pos60 <= 80: trend_score += 3
        elif pos60 < 20: trend_score += 1
        elif pos60 > 80: trend_score += 1
        
        if 0.6 <= vr5 <= 1.5: trend_score += 2
        elif vr5 < 0.6: trend_score += 1
        
        trend_score = min(trend_score, 8)
        scores['趋势强度'] = trend_score
        total += trend_score
        
        # ============== D: S3质量因子 (-3~+6) ==============
        quality_score = 0
        amp = float(row['amp']); dd = int(row.get('down_days', 0))
        ma20_pct = float(row.get('ma20_pct', -8))
        
        # D1: 振幅 — 5-7%胜率72% > 3-5%胜率65%
        if 3 <= amp < 5: quality_score += 2
        elif 5 <= amp < 7: quality_score += 2
        elif amp >= 7: quality_score += 1
        
        # D2: 连跌天数 — 0天胜率68% > 1-2天61% > 3-4天65% > >=5天30%
        if dd == 0: quality_score += 3
        elif dd >= 5: quality_score -= 2
        
        # D3: MA20偏离度 — -10~-8%胜率比更深的好
        if -12 <= ma20_pct < -8: quality_score += 1
        elif ma20_pct < -20: quality_score -= 1
        
        quality_score = max(-3, min(6, quality_score))
        scores['S3质量'] = quality_score
        total += quality_score
        
        # ============== E: 恐慌阴因子 (0~3) ==============
        panic_bonus = 0
        try:
            panic_conn = sqlite3.connect(DB)
            klines = panic_conn.execute("""
                SELECT date, open, high, low, close, volume
                FROM daily_klines WHERE code = ? ORDER BY date DESC LIMIT 6
            """, (code,)).fetchall()
            panic_conn.close()
            klines = list(reversed(klines))
            if len(klines) >= 3:
                for i in range(1, len(klines)):
                    if i < 2: continue
                    d1 = klines[i-1]; d2 = klines[i]
                    chg_d1 = (d1[4] / klines[i-2][4] - 1) * 100
                    if chg_d1 <= -3.5 and d1[4] < d1[1]:
                        chg_d2 = (d2[4] / d1[4] - 1) * 100 if d1[4] > 0 else 0
                        if chg_d2 > -2.5:
                            low_diff = (d2[3] - d1[3]) / d1[3] * 100 if d1[3] > 0 else 0
                            if low_diff >= -1.5:
                                has_zt = False
                                for j in range(max(0, i-22), i):
                                    if j+1 < len(klines) and klines[j][4] > 0:
                                        if round(klines[j][4] * 1.1, 2) - klines[j+1][4] < 0.01:
                                            has_zt = True; break
                                panic_bonus = max(panic_bonus, 3 if has_zt else 2)
                    elif chg_d1 <= -2.5 and d1[4] < d1[1]:
                        chg_d2 = (d2[4] / d1[4] - 1) * 100 if d1[4] > 0 else 0
                        if chg_d2 > -2: panic_bonus = max(panic_bonus, 1)
        except: pass
        
        c['panic_bonus'] = panic_bonus
        total += panic_bonus
        if panic_bonus > 0:
            scores['恐慌阴'] = panic_bonus
        
        # ============== F: 实时因子 (-1~0) ==============
        is_rt = c.get('_is_realtime', False) or c.get('realtime_chg') is not None
        if is_rt:
            total -= 1
            scores['实时'] = -1
        
        # ============== A: 大盘因子 (累加到总分) ==============
        total += market_score
        if market_score != 0:
            scores['大盘'] = market_score
        
        c['market_tag'] = market_tag
        c['market_up_ratio'] = round(market_up_ratio * 100, 1)
        c['market_avg_chg'] = round(market_avg_chg, 2)
        c['scores'] = scores
        c['total_score'] = total
        c['chain_tag'] = chain_tag
        c['matched_chains'] = matched_chains[:2]
        c['ind_info'] = f"{ind_l1}/{ind_l2}" if ind_l2 else ind_l1
        scored.append(c)
    
    scored.sort(key=lambda x: x['total_score'], reverse=True)
    return scored[:10]
def _enrich_with_industry(candidates):
    if not candidates:
        return
    codes = [c['code'] for c in candidates]
    try:
        conn = sqlite3.connect(DB)
        rows = conn.execute(f"""
            SELECT DISTINCT cs.code, i.name
            FROM chain_stocks cs
            JOIN chain_links cl ON cs.link_id=cl.id
            JOIN chain_industry_tags cit ON cl.chain_id=cit.chain_id
            JOIN industries i ON cit.industry_id=i.id
            WHERE cs.code IN ({','.join('?' for _ in codes)})
        """, codes).fetchall()
        conn.close()
        ind_map = {}
        for code, ind_name in rows:
            if code not in ind_map:
                ind_map[code] = []
            ind_map[code].append(ind_name)
        for c in candidates:
            if c['code'] in ind_map:
                c['sector'] = ','.join(ind_map[c['code']])
    except Exception as e:
        log(f"_enrich_with_industry error: {e}")


def run_s3_stage2(date_str=None, realtime=False):
    if not date_str:
        date_str = get_latest_date()
    log(f"▶ S3策略 {date_str}{' (实时)' if realtime else ''}")
    cand = stage1_s3(date_str, realtime)
    _enrich_with_industry(cand)
    top10 = stage2_score(cand, date_str)
    log(f"S3 Top10: {[c['code'] for c in top10]}")
    return {"date": date_str, "count": len(cand), "top10_count": len(top10), 
            "results": top10, "realtime": realtime}


def run_sanmai_stage2(date_str=None, realtime=False):
    if not date_str:
        date_str = get_latest_date()
    log(f"▶ 三买策略 {date_str}{' (实时)' if realtime else ''}")
    cand = stage1_sanmai(date_str, realtime)
    _enrich_with_industry(cand)
    top10 = stage2_score(cand, date_str)
    log(f"三买 Top10: {[c['code'] for c in top10]}")
    return {"date": date_str, "count": len(cand), "top10_count": len(top10), 
            "results": top10, "realtime": realtime}


def run_sanyin_stage2(date_str=None):
    if not date_str:
        date_str = get_latest_date()
    log(f"▶ 三阴策略 {date_str}")
    cand = stage1_sanyin(date_str)
    _enrich_with_industry(cand)
    top10 = stage2_score(cand, date_str)
    log(f"三阴 Top10: {[c['code'] for c in top10]}")
    return {"date": date_str, "count": len(cand), "top10_count": len(top10), "results": top10}


def run_pipeline_stage2(date_str=None, realtime=False):
    if not date_str:
        date_str = get_latest_date()
    
    # 🆕 大盘状态检测：涨跌比<55%时，S3胜率仅35% → 暂停推荐
    conn = sqlite3.connect(DB)
    mkt = conn.execute("""
        SELECT SUM(CASE WHEN chg>0 THEN 1 ELSE 0 END)*1.0/COUNT(*),
               AVG(chg)
        FROM feat WHERE date=? AND chg IS NOT NULL
    """, (date_str,)).fetchone()
    conn.close()
    up_ratio = float(mkt[0] or 0.5)
    avg_chg = float(mkt[1] or 0)
    market_weak = up_ratio < 0.55 and avg_chg < 0.3
    
    log(f"▶ 流水线{'(实时)' if realtime else ''} {date_str} (大盘涨跌比{up_ratio*100:.1f}%)")
    
    # 🆕 大盘状态标记（不再暂停S3，但报告里提示）
    # 涨跌比<55% → "逆势操作⚠️"，>=70% → "强势📈"，否则"中性📊"
    if market_weak:
        market_tag_result = "弱势/逆势操作⚠️"
        market_warning_text = f"大盘偏弱(涨跌比{up_ratio*100:.0f}%)，以下信号属逆势操作"
        log(f"  ⚠️ 大盘偏弱(涨跌比{up_ratio*100:.1f}%<55%)，S3继续运行但标记为逆势操作")
    elif up_ratio >= 0.70:
        market_tag_result = "强势📈"
        market_warning_text = ""
    else:
        market_tag_result = "中性📊"
        market_warning_text = ""
    
    # 🆕 如果是实时模式，用腾讯全市场实时数据覆盖涨跌比
    if realtime:
        log(f"  盘中模式: 获取全市场实时涨跌比...")
        try:
            import urllib.request
            # 从feat表取所有有数据的股票code
            conn2 = sqlite3.connect(DB)
            rt_codes = [r[0] for r in conn2.execute(
                "SELECT DISTINCT code FROM feat WHERE date=(SELECT MAX(date) FROM feat)"
            ).fetchall()]
            conn2.close()
            rt_codes = [c for c in rt_codes if not c.startswith('688')]
            
            up_rt = 0; down_rt = 0; zero_rt = 0
            for j in range(0, len(rt_codes), 80):
                batch = rt_codes[j:j+80]
                qs = ",".join(["sh"+c if c.startswith('6') else "sz"+c for c in batch])
                try:
                    resp = urllib.request.urlopen(f"http://qt.gtimg.cn/q={qs}", timeout=4).read().decode("gbk")
                    for line in resp.strip().split("\n"):
                        line = line.strip()
                        if "=" not in line: continue
                        m = re.search(r'"([^"]*)"', line)
                        if not m: continue
                        fields = m.group(1).split("~")
                        if len(fields) < 33: continue
                        try:
                            chg = float(fields[32])
                            if chg > 0: up_rt += 1
                            elif chg < 0: down_rt += 1
                            else: zero_rt += 1
                        except: pass
                except:
                    pass
            
            rt_total = up_rt + down_rt + zero_rt
            if rt_total > 100:  # 有效数据
                up_ratio = up_rt / rt_total
                log(f"  实时全市场涨跌比: {up_rt}/{rt_total}={up_ratio*100:.1f}%")
                # 重新判定大盘状态
                if up_ratio < 0.55:
                    market_tag_result = "弱势/逆势操作⚠️"
                    market_warning_text = f"大盘偏弱(涨跌比{up_ratio*100:.0f}%)，以下信号属逆势操作"
                elif up_ratio >= 0.70:
                    market_tag_result = "强势📈"
                    market_warning_text = ""
                else:
                    market_tag_result = "中性📊"
                    market_warning_text = ""
        except Exception as e:
            log(f"  实时涨跌比获取失败: {e}, 使用feat表数据")
    
    log(f"▶ 流水线{'(实时)' if realtime else ''} {date_str} (大盘涨跌比{up_ratio*100:.1f}%, {market_tag_result})")
    s3 = stage1_s3(date_str, realtime)
    sanmai = stage1_sanmai(date_str, realtime)
    merged = {}
    for r in s3:
        merged[r['code']] = r
    for r in sanmai:
        if r['code'] in merged:
            merged[r['code']]['strategy'] += f"+{r['strategy']}"
            merged[r['code']]['detail'] += f" | {r['detail']}"
        else:
            merged[r['code']] = r
    cand = list(merged.values())
    _enrich_with_industry(cand)
    top10 = stage2_score(cand, date_str)
    log(f"流水线 Top10: {[c['code'] for c in top10]}")
    return {
        "date": date_str, "count": len(cand),
        "s3_count": len(s3), "sanmai_count": len(sanmai),
        "top10_count": len(top10), "results": top10,
        "realtime": realtime,
        "market_tag": market_tag_result,
        "market_warning": market_warning_text
    }


# ================================================================
# 🆕 黄金坑选股 — 优质产业链+超跌+缩量+不追小市值
# ================================================================

# ⭐ 星球方法论 — 产业链质量分 + 景气权重
# 权重 = 质量分 × 景气系数，TMT赛道1.2x
QUALITY_CHAINS = {
    'AI算力': 5, 'CPO共封装光学(全景)': 5, 'CPO全产业链': 5,
    '半导体(qcc)': 5, '半导体设备(qcc)': 5,
    '低空经济(qcc)': 4, '人工智能(qcc)': 4, '医药生物(qcc)': 4,
    '云计算(qcc)': 4, '医疗器械(qcc)': 4, 'IDC(qcc)': 4,
    '汽车电子(qcc)': 4, '数据要素(qcc)': 3, '消费电子(qcc)': 3,
    # 🆕 zsxq研究成果
    'MLCC': 5, 'PCB钻针': 5, '端侧AI': 5, '液冷散热': 4,
    '金刚石散热': 4, '存储芯片': 5, '宇树': 4,
}

# TMT赛道列表（AI主线，景气系数1.2x）
TMT_CHAINS = ['AI算力', 'CPO共封装光学(全景)', 'CPO全产业链', 'MLCC', 'PCB钻针',
              '端侧AI', '液冷散热', '存储芯片', '半导体(qcc)', '半导体设备(qcc)',
              '人工智能(qcc)', '云计算(qcc)', 'IDC(qcc)', '5G(qcc)']

HOT_KW = ['AI','算力','芯片','半导体','机器人','低空经济','新能源',
          '光伏','电池','汽车','光模块','PCB','软件','算网',
          '消费电子','创新药','军工','商业航天']

def run_golden_pit(date_str=None, realtime=False):
    """
    ⭐ 黄金坑选股 V3 — 星球方法论升级版
    
    核心逻辑（谢SS+macro双圈融合）：
    1. 优质产业链候选（15+链条 ⭐1-5分）
    2. 60日线不破 → 真黄金坑（ma60_pct > -10%, 弱势-15%）
    3. 缩量见底 → 量比<0.7
    4. 20日低位 → pos_20d < 10
    5. ma20深度偏离 → ma20_pct < -8%
    6. 大盘弹性联动 → 弱势放宽ma60到-15%
    7. 评分体系：产业链权重×景气系数 + 技术面深度 + 缩量强度 + 实时确认
    """
    if not date_str:
        date_str = get_latest_date()
    
    log(f"▶ 黄金坑V3 {date_str}{' (实时)' if realtime else ''}")
    
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # === 1. 大盘环境判断 ===
    market_up_ratio = 0.5
    market_tag = "中性📊"
    ma60_threshold = -10  # 默认ma60>-10%
    
    if realtime:
        import urllib.request
        log(f"  获取全市场实时涨跌比...")
        rt_codes = [r[0] for r in cur.execute(
            "SELECT DISTINCT code FROM feat WHERE date=(SELECT MAX(date) FROM feat) AND code NOT LIKE '688%%'"
        ).fetchall()]
        up_rt = 0; down_rt = 0
        for j in range(0, len(rt_codes), 80):
            batch = rt_codes[j:j+80]
            qs = ",".join(["sh"+c if c.startswith('6') else "sz"+c for c in batch])
            try:
                resp = urllib.request.urlopen(f"http://qt.gtimg.cn/q={qs}", timeout=4).read().decode("gbk")
                for line in resp.strip().split("\n"):
                    line = line.strip()
                    if "=" not in line: continue
                    m = re.search(r'"([^"]*)"', line)
                    if not m: continue
                    fields = m.group(1).split("~")
                    if len(fields) < 33: continue
                    try:
                        c = float(fields[32])
                        if c > 0: up_rt += 1
                        elif c < 0: down_rt += 1
                    except: pass
            except: pass
        total = up_rt + down_rt
        if total > 100:
            market_up_ratio = up_rt / total
            log(f"  实时涨跌比: {up_rt}/{total}={market_up_ratio*100:.1f}%")
            if market_up_ratio >= 0.70:
                market_tag = "强势📈"
                ma60_threshold = -8  # 强势可收窄
            elif market_up_ratio >= 0.55:
                market_tag = "中性📊"
                ma60_threshold = -10
            else:
                market_tag = "弱势⚠️"
                ma60_threshold = -15  # 弱势放宽ma60
                log(f"  大盘弱势 → ma60阈值放宽到-15%")
    
    # === 2. 收集所有产业链黄金坑候选 ===
    all_codes_data = {}
    for cname, quality in QUALITY_CHAINS.items():
        cid = cur.execute("SELECT id FROM industry_chains WHERE name=?", (cname,)).fetchone()
        if not cid: continue
        
        # TMT赛道景气系数1.2x
        tmt_boost = 1.2 if cname in TMT_CHAINS else 1.0
        
        rows = cur.execute(f"""
            SELECT f.code, s.name, f.close, f.chg, f.vr_5, f.pos_20d, f.ma20_pct,
                   f.ret5, f.ret10, f.down_days, f.ma60_pct, f.amp, f.up_days,
                   f.ma5, f.ma10, f.ma20, f.volume, f.ma60, f.pos_60d, f.vr_20
            FROM feat f JOIN stocks s ON f.code = s.code
            JOIN chain_stocks cs ON f.code = cs.code
            JOIN chain_links cl ON cs.link_id = cl.id
            WHERE cl.chain_id = ? AND f.date = ?
              /* ⭐ 20日低位 */   AND f.pos_20d < 10
              /* ⭐ ma20深度偏离 */ AND f.ma20_pct < -8
              /* ⭐ 缩量见底（星球:量比<0.7）*/ AND f.vr_5 < 0.7 AND f.vr_5 > 0.3
              /* ⭐ 60日线不破（大盘弹性联动） */ AND f.ma60_pct > ?
              /* 排除 */          AND f.code NOT LIKE '688%%' AND s.name NOT LIKE '%%ST%%'
        """, (cid[0], date_str, ma60_threshold)).fetchall()
        
        for r in rows:
            code = r[0]
            d = {
                'code': code, 'name': r[1],
                'close': float(r[2] or 0), 'chg': float(r[3] or 0),
                'vr5': float(r[4] or 1), 'pos20': float(r[5] or 50),
                'ma20': float(r[6] or 0), 'ret5': float(r[7] or 0),
                'ret10': float(r[8] or 0), 'dd': int(r[9] or 0),
                'ma60': float(r[10] or 0), 'amp': float(r[11] or 0),
                'ud': int(r[12] or 0),
                'ma5': float(r[13] or 0), 'ma10': float(r[14] or 0),
                'ma20v': float(r[15] or 0), 'vol': float(r[16] or 0),
                'ma60_line': float(r[17] or 0), 'pos60': float(r[18] or 50),
                'vr20': float(r[19] or 1),
                'chain': cname, 'quality': quality,
                'tmt_boost': tmt_boost,
            }
            # 同一只股票可能出现多个产业链，取最高质量+最强景气
            if code in all_codes_data:
                old = all_codes_data[code]
                old_q = old['quality'] * old['tmt_boost']
                new_q = quality * tmt_boost
                if new_q > old_q:
                    all_codes_data[code] = d
            else:
                all_codes_data[code] = d
    
    conn.close()
    
    if not all_codes_data:
        return {"date": date_str, "count": 0, "results": [],
                "market_up_ratio": round(market_up_ratio*100, 1),
                "market_tag": market_tag,
                "ma60_threshold": ma60_threshold,
                "golden_pit_version": "v3"}
    
    # === 3. 实时行情覆盖（盘中） ===
    codes = list(all_codes_data.keys())
    rt_map = {}
    if realtime:
        import urllib.request
        log(f"  获取实时市值+行情...")
        for i in range(0, len(codes), 60):
            batch = codes[i:i+60]
            qs = ",".join(["sh"+c if c.startswith('6') else "sz"+c for c in batch])
            try:
                resp = urllib.request.urlopen(f"http://qt.gtimg.cn/q={qs}", timeout=6).read().decode("gbk")
                for line in resp.strip().split("\n"):
                    line = line.strip()
                    if "=" not in line: continue
                    m = re.search(r'"([^"]*)"', line)
                    if not m: continue
                    fields = m.group(1).split("~")
                    if len(fields) < 48: continue
                    code = fields[2]
                    try:
                        price = float(fields[3])
                        chg = float(fields[32])
                        mcap = float(fields[45])
                        high = float(fields[33]) if len(fields) > 33 else 0
                        low = float(fields[34]) if len(fields) > 34 else 0
                        vol = float(fields[6]) if len(fields) > 6 else 0
                        if price > 0:
                            rt_map[code] = {
                                'price': price, 'chg': chg, 'mcap': mcap,
                                'high': high, 'low': low, 'volume': vol,
                                'amp': ((high - low) / low * 100) if low > 0 else 0,
                            }
                    except: pass
            except Exception as e:
                log(f"  batch错误: {e}")
        log(f"  实时行情: {len(rt_map)}/{len(codes)}只")
    
    # === 4. ⭐ 星球评分体系（V3版）===
    def _score_v3(d, rt):
        """
        7维评分（满分25分 → 百分制）：
        
        A. 产业链质量（0-10）
           基础分 = quality × tmt_boost × 1.5
        
        B. 60日线安全垫（0-4）
           ma60_pct > -5% → 4分（离60日线近，安全）
           ma60_pct > -10% → 2分（轻度偏离）
           ma60_pct > -15% → 1分（弱势放宽后入选）
        
        C. 缩量强度（0-4）
           vr5 < 0.4 → 4分（极致缩量）
           vr5 < 0.55 → 3分
           vr5 < 0.7 → 2分
        
        D. 位置深度（0-3）
           pos20 < 3 → 3分（接近20日最低）
           pos20 < 6 → 2分
           pos20 < 10 → 1分
        
        E. 连跌清洗（0-3）
           dd >= 5 → 3分（连续下跌出清）
           dd >= 3 → 2分
           dd >= 2 → 1分
        
        F. 实时确认（0-3）
           盘中涨 → 2分
           平盘 → 1分
           跌但>-3% → 0分
           大跌<-3% → -1分
        
        G. 大盘环境（0-3）
           逆势选股（弱势大盘选出）→ 3分
           中性 → 1分
           强势 → 0分
        """
        r = rt if rt.get(d['code']) else {}
        
        # A. 产业链质量（0-10）
        chain_score = d['quality'] * d['tmt_boost'] * 1.5
        chain_score = min(10, chain_score)
        
        # B. 60日线安全垫（0-4）
        m60 = r.get('chg') if 'chg' in r else d['ma60']  # 盘中用实时chg近似
        m60_val = d['ma60']
        if m60_val > -5:
            ma60_score = 4
        elif m60_val > -10:
            ma60_score = 2
        elif m60_val > -15:
            ma60_score = 1
        else:
            ma60_score = 0
        
        # C. 缩量强度（0-4）
        vr = r.get('vr5') if 'vr5' in r else d['vr5']
        if vr < 0.4:
            vr_score = 4
        elif vr < 0.55:
            vr_score = 3
        elif vr < 0.7:
            vr_score = 2
        else:
            vr_score = 1
        
        # D. 位置深度（0-3）
        pos = d['pos20']
        if pos < 3:
            pos_score = 3
        elif pos < 6:
            pos_score = 2
        else:
            pos_score = 1
        
        # E. 连跌清洗（0-3）
        dd = d['dd']
        if dd >= 5:
            dd_score = 3
        elif dd >= 3:
            dd_score = 2
        elif dd >= 2:
            dd_score = 1
        else:
            dd_score = 0
        
        # F. 实时确认（0-3）
        tc = r.get('chg', d['chg'])
        if tc > 2:
            real_score = 2
        elif tc > 0:
            real_score = 1
        elif tc > -3:
            real_score = 0
        else:
            real_score = -1
        
        # G. 大盘环境溢价（0-3）
        if market_up_ratio < 0.55:
            market_score = 3  # 逆势选出加分
        elif market_up_ratio < 0.70:
            market_score = 1
        else:
            market_score = 0
        
        # 总分（25分制）
        total = chain_score + ma60_score + vr_score + pos_score + dd_score + real_score + market_score
        
        # 扣分项
        if r.get('mcap', 0) < 30:
            total -= 3  # 小市值扣分
        if d['vr5'] < 0.35:
            total += 1  # 极致缩量额外奖励
        
        return round(total, 1), {
            'chain': round(chain_score, 1),
            'ma60': ma60_score,
            'vr': vr_score,
            'pos': pos_score,
            'dd': dd_score,
            'real': real_score,
            'market': market_score,
        }
    
    # === 5. 评分+过滤 ===
    all_items = []
    for d in all_codes_data.values():
        rt = rt_map.get(d['code'])
        
        # 实时市值过滤（<30亿排除）
        if rt and 0 < rt['mcap'] < 30:
            continue
        
        score_val, score_detail = _score_v3(d, rt_map)
        
        # 盘中行情覆盖
        close_val = round(rt['price'], 2) if rt else d['close']
        chg_val = round(rt['chg'], 2) if rt else d['chg']
        mcap_val = round(rt['mcap'], 0) if rt else 0
        
        item = {
            'code': d['code'], 'name': d['name'],
            'close': close_val, 'chg': chg_val,
            'mcap': mcap_val,
            'chain': d['chain'], 'total_score': score_val,
            'pos20': round(d['pos20'], 0), 'ma20': round(d['ma20'], 1),
            'ma60': round(d['ma60'], 1),  # ma60_pct
            'vr5': round(d['vr5'], 2), 'dd': d['dd'], 'ud': d['ud'],
            'ret5': round(d['ret5'], 1), 'ret10': round(d['ret10'], 1),
            'amp': round(d['amp'], 1),
            'score_detail': score_detail,
        }
        all_items.append(item)
    
    all_items.sort(key=lambda x: x['total_score'], reverse=True)
    top = all_items[:15]
    
    # 信号分级
    signals = []
    for item in top:
        s = item['total_score']
        if s >= 15:
            grade = '⭐ 黄金坑1级'
        elif s >= 10:
            grade = '✨ 黄金坑2级'
        else:
            grade = '🔹 黄金坑3级'
        signals.append(grade)
    
    log(f"黄金坑V3: {len(all_items)}只符合 → Top{len(top)}")
    log(f"  大盘: {market_tag} | ma60阈值: {ma60_threshold}%")
    for i, item in enumerate(top[:5]):
        log(f"  #{i+1} {item['name']}({item['code']}) {item['total_score']}分 ⭐{item['chain']}")
    
    return {
        "date": date_str, "count": len(all_items), "results": top,
        "market_up_ratio": round(market_up_ratio*100, 1),
        "market_tag": market_tag,
        "ma60_threshold": ma60_threshold,
        "golden_pit_version": "v3",
        "signals": signals,
        "market_warning": f"大盘偏弱(涨跌比{market_up_ratio*100:.0f}%)→ma60放宽到-{abs(ma60_threshold)}%" 
                         if market_up_ratio < 0.55 else "",
        "realtime": realtime,
    }


if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "pipeline"
    realtime = "--realtime" in sys.argv
    result = json_handler(json.dumps({"action": action, "realtime": realtime}))
    data = json.loads(result[2].decode())
    if action == "golden_pit":
        print(f"VERSION:{data.get('golden_pit_version','?')}|COUNT:{data.get('count','?')}|MARKET:{data.get('market_tag','?')}")
        for r in data.get('results',[])[:5]:
            print(f"  {r['name']}({r['code']}) {r['total_score']}分 ⭐{r.get('chain','')}")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
