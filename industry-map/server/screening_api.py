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
    for c in candidates:
        code = c['code']
        if code in rt:
            r = rt[code]
            old_chg = c.get('chg', 0)
            old_close = c.get('close', 0)
            c['chg'] = round(r['chg'], 2)
            c['close'] = round(r['price'], 2)
            c['realtime_chg'] = round(r['chg'], 2)
            c['realtime_price'] = round(r['price'], 2)
            c['_is_realtime'] = True
            
            # 检查实时涨跌幅是否还满足S3条件
            strategy = c.get('strategy', '')
            if 'S3' in strategy:
                if r['chg'] < 3 or r['chg'] >= 7:
                    removed_signal += 1
                    log(f"  ❌ {code} {c.get('name','')} 实时chg={r['chg']:+.2f}% 已不满足S3 → 剔除")
                    continue  # 不加入最终结果
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
    """
    跨策略通用评分
    维度：
    1. **产业链热度** (0-10分)
    2. **行业景气趋势** (0-8分)
    3. **基本面+资金趋势** (0-7分)
    4. **恐慌阴加分** (0-3分)
    """
    conn = sqlite3.connect(DB)
    md_rows = conn.execute("""
        SELECT f.code, f.pos_60d, f.ret1, f.ret3, f.ret5,
               f.volume, f.chg, f.vr_5, f.amp
        FROM feat f
        WHERE f.date = ?
    """, (date_str,)).fetchall()
    md_cols = ['code','pos_60d','ret1','ret3','ret5','volume','chg','vr_5','amp']
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
    
    ind_conn = sqlite3.connect(DB)
    ind_rows = ind_conn.execute(
        "SELECT code, industry_l1, industry_l2, industry_l3 FROM stock_industries"
    ).fetchall()
    stock_industry_map = {}
    for r in ind_rows:
        stock_industry_map[r[0]] = {'l1': r[1] or '', 'l2': r[2] or '', 'l3': r[3] or ''}
    ind_conn.close()
    
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
        if code not in stock_chains:
            stock_chains[code] = []
        stock_chains[code].append(chain_name)
    
    HOT_KEYWORDS = ['AI', '算力', '芯片', '半导体', '机器人', '低空经济', '新能源',
                    '光伏', '电池', '汽车', '光模块', 'PCB', '软件', '算网',
                    '消费电子', '创新药', '军工', '商业航天']
    
    scored = []
    for c in candidates:
        code = c['code']
        row = md_map.get(code)
        if not row:
            continue
        
        scores = {}
        total = 0
        
        ## 维度1：产业链热度 (0-10分)
        chain_score = 0
        chain_tag = ''
        chains = stock_chains.get(code, [])
        ind_info = stock_industry_map.get(code, {})
        ind_l1 = ind_info.get('l1', '')
        ind_l2 = ind_info.get('l2', '')
        
        matched_chains = []
        for ch in all_chains:
            if ch in chains:
                matched_chains.append(ch)
        
        hot_keyword_matches = []
        for kw in HOT_KEYWORDS:
            if kw in ind_l1 or kw in ind_l2 or kw in ind_l2:
                hot_keyword_matches.append(kw)
        
        if matched_chains:
            chain_score += 7
            chain_tag = matched_chains[0]
        if hot_keyword_matches:
            chain_score += 3
            if not chain_tag:
                chain_tag = hot_keyword_matches[0]
        chain_score = min(chain_score, 10)
        scores['产业链热度'] = chain_score
        total += chain_score
        
        ## 维度2：行业景气趋势 (0-8分)
        trend_score = 0
        ret5 = float(row['ret5'])
        pos60 = float(row['pos_60d'])
        
        if ret5 > 3: trend_score += 3
        elif ret5 > 0: trend_score += 2
        elif ret5 > -3: trend_score += 1
        
        if 20 <= pos60 <= 80: trend_score += 3
        elif pos60 < 20: trend_score += 1
        elif pos60 > 80: trend_score += 1
        
        vr5 = float(row['vr_5'])
        if 0.6 <= vr5 <= 1.5: trend_score += 2
        elif vr5 < 0.6: trend_score += 1
        
        trend_score = min(trend_score, 8)
        scores['景气趋势'] = trend_score
        total += trend_score
        
        ## 维度3：资金信号 (0-7分)
        signal_score = 0
        ret1 = float(row['ret1'])
        if ret1 > 0: signal_score += 2
        
        amp = float(row['amp'])
        if amp < 4: signal_score += 2
        elif amp < 6: signal_score += 1
        
        if pos60 < 50: signal_score += 2
        elif pos60 < 80: signal_score += 1
        
        chg = float(row['chg'])
        if chg > 0 and vr5 >= 1.0: signal_score += 1
        
        signal_score = min(signal_score, 7)
        scores['资金信号'] = signal_score
        total += signal_score
        
        ## 维度4：恐慌阴+停顿阳加分 (0-3分)
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
                    if i < 2:
                        continue
                    d1 = klines[i-1]
                    d2 = klines[i]
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
                                            has_zt = True
                                            break
                                panic_bonus = max(panic_bonus, 3 if has_zt else 2)
                    elif chg_d1 <= -2.5 and d1[4] < d1[1]:
                        chg_d2 = (d2[4] / d1[4] - 1) * 100 if d1[4] > 0 else 0
                        if chg_d2 > -2:
                            panic_bonus = max(panic_bonus, 1)
        except:
            pass
        
        c['panic_bonus'] = panic_bonus
        total += panic_bonus
        
        # 🆕 添加实时标记
        is_rt = c.get('_is_realtime', False) or c.get('realtime_chg') is not None
        if is_rt:
            total -= 1  # 实时数据不确定性扣1分
            scores['实时'] = -1
        
        c['scores'] = scores
        c['total_score'] = total
        c['chain_tag'] = chain_tag
        c['matched_chains'] = matched_chains[:2]
        c['ind_info'] = f"{ind_l1}/{ind_l2}" if ind_l2 else ind_l1
        scored.append(c)
    
    scored.sort(key=lambda x: x['total_score'], reverse=True)
    return scored[:10]


# ================================================================
# 组合接口
# ================================================================

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
    log(f"▶ 流水线{'(实时)' if realtime else ''} {date_str}")
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
        "realtime": realtime
    }


if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "pipeline"
    realtime = "--realtime" in sys.argv
    result = json_handler(json.dumps({"action": action, "realtime": realtime}))
    data = json.loads(result[2].decode())
    print(json.dumps(data, ensure_ascii=False, indent=2)[:5000])
