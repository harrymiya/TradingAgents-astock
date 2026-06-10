#!/usr/bin/env python3
"""
screening_api.py — 选股API，每个策略走完整3级管道
  Stage 1: SQL条件筛选（现有逻辑）
  Stage 2: 6维度评分 → Top10（与 scan_pipeline.py 一致）
  Stage 3: TradingAgents LLM深度分析（异步，前端轮询结果）
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
        
        if action == "s3":
            data = run_s3_stage2(date)
        elif action == "sanmai":
            data = run_sanmai_stage2(date)
        elif action == "sanyin":
            data = run_sanyin_stage2(date)
        elif action == "pipeline":
            data = run_pipeline_stage2(date)
        else:
            data = {"error": f"Unknown action: {action}"}
        
        resp = json.dumps(data, ensure_ascii=False, default=str)
        return (200, {"Content-Type": "application/json; charset=utf-8"}, resp.encode())
    except Exception as e:
        log(f"ERROR: {e}")
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
# Stage 1: 策略筛选（保持原有逻辑不变）
# ================================================================

def stage1_s3(date_str):
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
        results.append(d)
    conn.close()
    log(f"S3 Stage1: {len(results)}只")
    return results

def stage1_sanmai(date_str):
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
        pos20 = float(pos20 or 0)
        pos60 = float(pos60 or 0)
        ma20_pct = float(ma20_pct or 0)
        ma60_pct = float(ma60_pct or 0)
        ret1 = float(ret1 or 0)
        ret3 = float(ret3 or 0)
        ret5 = float(ret5 or 0)
        volume = float(volume or 0)
        
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
                'detail': detail
            })
        except:
            continue
        
        if (len(results) + 1) % 500 == 0:
            log(f"  三买进度: {len(results)}只")
    
    conn.close()
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
# Stage 2: 6维度评分 → Top10（与 scan_pipeline.py 一致）
# ================================================================

def stage2_score(candidates, date_str):
    """6维度评分 → Top10"""
    # 加载feat全市场数据（用于评分需要的字段）
    conn = sqlite3.connect(DB)
    md_rows = conn.execute("""
        SELECT f.code, f.close, f.chg, f.amp, f.vr_5, f.vr_20,
               f.pos_20d, f.pos_60d, f.ma20_pct, f.ma60_pct,
               f.ret1, f.ret3, f.ret5, f.volume, f.ma5, f.ma10, f.ma20
        FROM feat f
        WHERE f.date = ?
    """, (date_str,)).fetchall()
    md_cols = ['code','close','chg','amp','vr_5','vr_20',
               'pos_20d','pos_60d','ma20_pct','ma60_pct',
               'ret1','ret3','ret5','volume','ma5','ma10','ma20']
    md_map = {}
    for r in md_rows:
        d = dict(zip(md_cols, r))
        for k in md_cols[1:]:
            try: d[k] = float(d[k])
            except: d[k] = 0
        md_map[d['code']] = d
    conn.close()

    # 热门产业链
    CHAIN_HOT_INDUSTRIES = ['AI算力', 'AI应用', '半导体', 'CPO(共封装光学)', 
                            '机器人', '低空经济', '新能源', '商业航天']
    INDUSTRY_HOT_KEYWORDS = ['通信', '半导体', '芯片', '软件', 'IT', '电子', '计算机',
                             '光伏', '电池', '电力', '汽车', '机器人', '航空航天',
                             'AI', '算力', '光模块', 'PCB', '消费电子']

    scored = []
    for c in candidates:
        code = c['code']
        row = md_map.get(code)
        if not row:
            continue

        strategy = c.get('strategy', '')
        detail = c.get('detail', '')
        scores = {}
        total = 0

        # S3评分
        if 'S3' in strategy:
            s3_score = 0
            amp = float(row['amp'])
            if amp < 3: s3_score += 3
            elif amp < 5: s3_score += 4
            elif amp < 7: s3_score += 2
            else: s3_score += 1
            mp20 = float(row['ma20_pct'])
            if mp20 >= -10: s3_score += 4
            elif mp20 >= -15: s3_score += 2
            else: s3_score += 1
            vr5 = float(row['vr_5'])
            if vr5 < 1.5: s3_score += 3
            elif vr5 < 2.0: s3_score += 1
            s3_score = min(s3_score, 10)
            scores['S3反转质量'] = s3_score
            total += s3_score

        # 三买v2评分
        if '三买' in strategy:
            sm_score = 0
            m = re.search(r'回抽([\d.]+)%', detail)
            if m:
                pb = float(m.group(1))
                if 5 <= pb <= 12: sm_score += 4
                elif 3 <= pb < 5: sm_score += 2
                else: sm_score += 1
            ma20 = float(row['ma20'])
            close = float(row['close'])
            if ma20 > 0:
                ma20_dist = (close - ma20) / ma20 * 100
                if 0 < ma20_dist <= 5: sm_score += 3
                elif ma20_dist > 5: sm_score += 1
                elif -3 <= ma20_dist <= 0: sm_score += 1
            ma5 = float(row['ma5'])
            if close > ma5: sm_score += 2
            vr5 = float(row['vr_5'])
            if 0.6 <= vr5 <= 1.5: sm_score += 1
            sm_score = min(sm_score, 10)
            scores['三买中枢质量'] = sm_score
            total += sm_score

        # 三阴评分（缩量+止损距离）
        if '三阴' in strategy:
            sy_score = 5
            vr5 = float(row['vr_5'])
            if vr5 < 0.6: sy_score += 3
            elif vr5 < 0.8: sy_score += 1
            mp20 = float(row['ma20_pct'])
            if mp20 > -5: sy_score += 2
            scores['三阴止盈质量'] = sy_score
            total += sy_score

        # 通用加分
        bonus = 0
        pos60 = float(row['pos_60d'])
        if pos60 < 50: bonus += 2
        if float(row['ret1']) > 0: bonus += 2
        if float(row['ret3']) > 0: bonus += 1
        scores['通用加分'] = min(bonus, 5)
        total += min(bonus, 5)

        # 板块热度（简化版—直接从candidate的产业链信息）
        sector_score = 0
        sector_tag = ''
        # 检查是否在热门产业链中
        if 'sector' in c and c['sector']:
            for hot in CHAIN_HOT_INDUSTRIES:
                if hot in c['sector']:
                    sector_score = 5
                    sector_tag = hot
                    break
        if sector_score > 0:
            scores['板块热度'] = sector_score
            total += sector_score

        # 多策略共振
        strategy_set = set(s.strip() for s in re.split(r'[+]', strategy) if s.strip())
        if len(strategy_set) >= 2:
            scores['多策略共振'] = 3
            total += 3

        c['scores'] = scores
        c['total_score'] = total
        c['sector'] = sector_tag
        scored.append(c)

    scored.sort(key=lambda x: x['total_score'], reverse=True)
    return scored[:10]


# ================================================================
# 组合接口：Stage 1 + Stage 2
# ================================================================

def run_s3_stage2(date_str=None):
    if not date_str:
        date_str = get_latest_date()
    log(f"▶ S3策略 {date_str}")
    cand = stage1_s3(date_str)
    # 检查是否有产业链归属信息（从industry_data）
    _enrich_with_industry(cand)
    top10 = stage2_score(cand, date_str)
    log(f"S3 Top10: {[c['code'] for c in top10]}")
    return {"date": date_str, "count": len(cand), "top10_count": len(top10), "results": top10}

def run_sanmai_stage2(date_str=None):
    if not date_str:
        date_str = get_latest_date()
    log(f"▶ 三买策略 {date_str}")
    cand = stage1_sanmai(date_str)
    _enrich_with_industry(cand)
    top10 = stage2_score(cand, date_str)
    log(f"三买 Top10: {[c['code'] for c in top10]}")
    return {"date": date_str, "count": len(cand), "top10_count": len(top10), "results": top10}

def run_sanyin_stage2(date_str=None):
    if not date_str:
        date_str = get_latest_date()
    log(f"▶ 三阴策略 {date_str}")
    cand = stage1_sanyin(date_str)
    _enrich_with_industry(cand)
    top10 = stage2_score(cand, date_str)
    log(f"三阴 Top10: {[c['code'] for c in top10]}")
    return {"date": date_str, "count": len(cand), "top10_count": len(top10), "results": top10}

def run_pipeline_stage2(date_str=None):
    if not date_str:
        date_str = get_latest_date()
    log(f"▶ 流水线策略 {date_str}")
    s3 = stage1_s3(date_str)
    sanmai = stage1_sanmai(date_str)
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
        "top10_count": len(top10), "results": top10
    }


# ================================================================
# 辅助：给候选股补充产业链归属
# ================================================================

def _enrich_with_industry(candidates):
    """从产业链DB补充 sector 字段（所属热门产业链）"""
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


if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "pipeline"
    result = json_handler(json.dumps({"action": action}))
    data = json.loads(result[2].decode())
    print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
