#!/usr/bin/env python3
"""
screening_api.py — 选股API，供前端调用
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
    """返回 (status_code, headers, body_bytes)"""
    try:
        result = json.loads(body)
        action = result.get("action", "")
        date = result.get("date", "")
        
        if action == "s3":
            data = run_s3(date)
        elif action == "sanmai":
            data = run_sanmai(date)
        elif action == "sanyin":
            data = run_sanyin(date)
        elif action == "pipeline":
            data = run_pipeline_scan(date)
        else:
            data = {"error": f"Unknown action: {action}"}
        
        resp = json.dumps(data, ensure_ascii=False, default=str)
        return (200, {"Content-Type": "application/json; charset=utf-8"}, resp.encode())
    except Exception as e:
        resp = json.dumps({"error": str(e)}, ensure_ascii=False)
        return (500, {"Content-Type": "application/json; charset=utf-8"}, resp.encode())

# === 选股逻辑（简化版，直接复用scan_pipeline.py的核心逻辑）===

def get_latest_date():
    conn = sqlite3.connect(DB)
    d = conn.execute("SELECT MAX(date) FROM feat").fetchone()[0]
    conn.close()
    return d

def run_s3(date_str=None):
    if not date_str:
        date_str = get_latest_date()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT f.code, s.name, 
               f.close, f.chg, f.vr_5, f.pos_20d, f.ma20_pct, f.ma60_pct,
               f.ret1, f.ret3, f.ret5
        FROM feat f
        JOIN stocks s ON f.code = s.code
        WHERE f.date = ?
          AND f.pos_20d < 20 
          AND f.chg >= 3 AND f.chg < 7
          AND f.vr_5 >= 1.2 AND f.vr_5 < 2.5
          AND f.ma20_pct < -8
          AND f.code NOT LIKE '688%'
          AND s.name NOT LIKE '%ST%'
        ORDER BY f.chg DESC
        LIMIT 50
    """, (date_str,))
    rows = cur.fetchall()
    conn.close()
    
    results = []
    col_names = ['code','name','close','chg','vr_5','pos_20d','ma20_pct','ma60_pct','ret1','ret3','ret5']
    for r in rows:
        d = dict(zip(col_names, r))
        for k in ['close','chg','vr_5','pos_20d','ma20_pct','ma60_pct','ret1','ret3','ret5']:
            try: d[k] = float(d[k])
            except: d[k] = 0
        d['strategy'] = 'S3'
        d['detail'] = f"超跌(20日位{d['pos_20d']:.0f}%, vr{d['vr_5']:.1f}x, MA20{d['ma20_pct']:.1f}%)"
        results.append(d)
    return {"date": date_str, "count": len(results), "results": results}

def run_sanmai(date_str=None):
    if not date_str:
        date_str = get_latest_date()
    conn = sqlite3.connect(DB)
    
    # 从feat表加载全市场数据
    cur = conn.cursor()
    cur.execute("""
        SELECT f.code, s.name, f.close, f.chg, f.vr_5, f.ma5, f.ma10, f.ma20,
               f.pos_20d, f.pos_60d, f.ma20_pct
        FROM feat f
        JOIN stocks s ON f.code = s.code
        WHERE f.date = ?
          AND f.code NOT LIKE '688%'
          AND s.name NOT LIKE '%ST%'
          AND f.close IS NOT NULL
    """, (date_str,))
    market = cur.fetchall()
    
    import numpy as np
    results = []
    
    for idx, (code, name, close, chg, vr5, ma5, ma10, ma20, pos20, pos60, ma20_pct) in enumerate(market):
        chg = float(chg or 0)
        close = float(close or 0)
        vr5 = float(vr5 or 0)
        ma20 = float(ma20 or 0)
        ma5 = float(ma5 or 0)
        
        if close <= 0 or ma20 <= 0:
            continue
        
        # 从daily_klines获取K线数据
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
            
            # 检验突破
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
            
            # 排除大跌
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
                'strategy': '三买v2',
                'detail': detail
            })
        except:
            continue
        
        if (idx + 1) % 500 == 0:
            log(f"  三买进度: {idx+1}/{len(market)} → {len(results)}只")
    
    conn.close()
    results.sort(key=lambda x: abs(x['chg']), reverse=True)
    results = results[:50]
    return {"date": date_str, "count": len(results), "results": results}

def run_sanyin(date_str=None):
    if not date_str:
        date_str = get_latest_date()
    conn = sqlite3.connect(DB)
    
    days = _get_trading_days(date_str, 7)
    if len(days) < 6:
        conn.close()
        return {"date": date_str, "count": 0, "results": [], "error": "交易日不足"}
    
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
        LIMIT 50
    """
    
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
    
    return {"date": date_str, "count": len(results), "results": results}

def run_pipeline_scan(date_str=None):
    """流水线 = S3 + 三买 并集"""
    s3 = run_s3(date_str)
    sanmai = run_sanmai(date_str)
    
    merged = {}
    for r in s3.get("results", []):
        merged[r['code']] = r
    for r in sanmai.get("results", []):
        if r['code'] in merged:
            merged[r['code']]['strategy'] += f"+{r['strategy']}"
            merged[r['code']]['detail'] += f" | {r['detail']}"
        else:
            merged[r['code']] = r
    
    results = list(merged.values())
    # 按chg降序
    results.sort(key=lambda x: abs(x.get('chg', 0)), reverse=True)
    
    return {
        "date": date_str or get_latest_date(),
        "count": len(results),
        "s3_count": s3.get("count", 0),
        "sanmai_count": sanmai.get("count", 0),
        "results": results[:50]
    }

def _get_trading_days(target_date, count):
    conn = sqlite3.connect(DB)
    days = conn.execute("""
        SELECT DISTINCT date FROM daily_klines 
        WHERE date <= ? ORDER BY date DESC LIMIT ?
    """, (target_date, count + 5)).fetchall()
    conn.close()
    return [d[0] for d in days]

if __name__ == "__main__":
    # 测试
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "pipeline"
    result = json_handler(json.dumps({"action": action}))
    data = json.loads(result[2].decode())
    print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
