#!/usr/bin/env python3
"""
screening_api.py — 黄金坑选股 V3 API
  仅支持 action=golden_pit（星球双圈方法论）
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
        
        if action == "golden_pit":
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

# ================================================================
# 实时行情获取
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


# ================================================================
# ⭐ 黄金坑选股 V3 — 星球方法论（唯一策略）
# ================================================================

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
    action = sys.argv[1] if len(sys.argv) > 1 else "golden_pit"
    realtime = "--realtime" in sys.argv
    result = json_handler(json.dumps({"action": "golden_pit", "realtime": realtime}))
    data = json.loads(result[2].decode())
    print(f"VERSION:{data.get('golden_pit_version','?')}|COUNT:{data.get('count','?')}|MARKET:{data.get('market_tag','?')}")
    for r in data.get('results',[])[:5]:
        print(f"  {r['name']}({r['code']}) {r['total_score']}分 ⭐{r.get('chain','')}")
