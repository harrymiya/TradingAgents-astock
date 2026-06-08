#!/usr/bin/env python3
"""
全能选股工具箱 — 行情判断 + 自动策略 + 持仓分析 + Astock工具链

用法:
  cd /home/harrydolly/code/TradingAgents-astock
  source .venv/bin/activate
  python3 scan_toolbox.py              # 自动行情+选股+持仓
  python3 scan_toolbox.py --holdings   # 只看持仓分析
  python3 scan_toolbox.py --force qiangshi  # 强制策略
  python3 scan_toolbox.py --stock 000887    # 深度分析单只
  python3 scan_toolbox.py --tools          # 列出Astock可用工具
"""
import sys, os, sqlite3, numpy as np, pandas as pd, json
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Optional

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

DB = os.path.expanduser("~/.hermes/astock_data.db")
A_STOCK = os.path.join(PROJECT_DIR, "tradingagents", "dataflows", "a_stock.py")
TOOLKIT_DIR = os.path.expanduser("~/.hermes/research_toolkit")

# 读取工具库（每日深度研究结果）
def load_toolkit():
    """加载最近的深度研究结果"""
    latest = os.path.join(TOOLKIT_DIR, "_latest.json")
    if os.path.exists(latest):
        with open(latest, 'r') as f:
            meta = json.load(f)
        fpath = os.path.join(TOOLKIT_DIR, f"{meta['latest_date']}.json")
        if os.path.exists(fpath):
            with open(fpath, 'r') as f:
                return json.load(f)
    return None

# 工具库缓存
_TOOLKIT_CACHE = None
def get_toolkit():
    global _TOOLKIT_CACHE
    if _TOOLKIT_CACHE is None:
        _TOOLKIT_CACHE = load_toolkit()
    return _TOOLKIT_CACHE

# 你的持仓
HOLDINGS = {
    "301231": {"name": "荣信文化", "cost": 34.62},
    "300550": {"name": "和仁科技", "cost": 14.63},
    "600503": {"name": "华丽家族", "cost": 2.82},
    "603586": {"name": "金麒麟", "cost": 17.63},
}

# ====================================================================
# Part 1: 市场行情判断
# ====================================================================

def market_regime():
    """判断市场状态，返回行情类型和推荐策略"""
    conn = sqlite3.connect(DB)
    end = conn.execute('SELECT MAX(date) FROM daily_klines').fetchone()[0]
    rows = conn.execute('''
        SELECT d.close,
               (SELECT d2.close FROM daily_klines d2 WHERE d2.code=d.code AND d2.date=?),
               (SELECT d3.close FROM daily_klines d3 WHERE d3.code=d.code AND d3.date=?)
        FROM daily_klines d WHERE d.date=?
        AND d.code NOT LIKE "688%" AND d.code NOT LIKE "4%"
        AND d.code NOT LIKE "83%" AND d.code NOT LIKE "87%"
    ''', (f'{pd.Timestamp(end)-pd.Timedelta(days=5):%Y-%m-%d}',
          f'{pd.Timestamp(end)-pd.Timedelta(days=20):%Y-%m-%d}', end))
    data = rows.fetchall()
    conn.close()
    c=np.array([r[0] for r in data]); c5=np.array([r[1] if r[1] else r[0] for r in data])
    c20=np.array([r[2] if r[2] else r[0] for r in data])
    chg5=(c-c5)/c5*100; chg20=(c-c20)/c20*100
    up5=np.sum(chg5>0)/len(chg5)*100; up20=np.sum(chg20>0)/len(chg20)*100
    med5=float(np.median(chg5)); med20=float(np.median(chg20))
    std5=float(np.std(chg5)); zt=int(np.sum(chg5>9.5)); dt=int(np.sum(chg5<-9.5))
    score=up5*0.4+up20*0.3+(med5+10)*2+(med20+10)*0.5
    score=max(0,min(100,score))
    if score>=65: r="强势行情"; a="追最强龙头"; s="qiangshi"
    elif score>=45: r="震荡行情"; a="低吸高抛，题材轮动"; s="sanmai_dixi"
    elif score>=25: r="弱势行情"; a="超跌反弹为主，严控仓位"; s="dixi_beichi"
    else: r="极弱行情"; a="建议空仓或极小仓位试错"; s="dixi_beichi_danger"
    return {"date":end,"regime":r,"score":round(score,1),"up5":round(up5,1),"up20":round(up20,1),
            "med5":f"{med5:+.2f}%","med20":f"{med20:+.2f}%","zt_dt":f"{zt}:{dt}",
            "vol":f"{std5:.1f}%","advice":a,"strat":s}

# ====================================================================
# Part 2: 数据层 — 从DB + Astock工具链
# ====================================================================

def get_klines_df(code, days=90):
    """从DB读取日线"""
    conn = sqlite3.connect(DB)
    end = conn.execute('SELECT MAX(date) FROM daily_klines').fetchone()[0]
    start = f'{pd.Timestamp(end)-pd.Timedelta(days=days):%Y-%m-%d}'
    rows = conn.execute('''SELECT date,open,high,low,close,volume,amount FROM daily_klines
        WHERE code=? AND date>=? AND date<=? ORDER BY date''', (code, start, end)).fetchall()
    conn.close()
    if len(rows) < 20: return None, None
    df = pd.DataFrame(rows, columns=['Date','O','H','L','C','V','A'])
    for col in ['O','H','L','C','V','A']: df[col] = df[col].astype(float)
    return df, end

def get_tencent_quote(codes):
    """从Astock框架取腾讯批量实时行情"""
    try:
        sys.path.insert(0, PROJECT_DIR)
        from tradingagents.dataflows.a_stock import _tencent_quote
        return _tencent_quote(codes)
    except: return {}

def get_fundamentals(code):
    """从Astock框架取基本面数据"""
    try:
        from tradingagents.dataflows.a_stock import get_fundamentals
        raw = get_fundamentals(code)
        if raw:
            lines = raw.strip().split('\n')
            result = {}
            for l in lines:
                if ':' in l and not l.startswith('#'):
                    k, v = l.split(':', 1)
                    result[k.strip()] = v.strip()
            return result
    except: return {}

def get_concept_blocks(code):
    """从Astock框架取题材板块"""
    try:
        from tradingagents.dataflows.a_stock import get_concept_blocks
        return get_concept_blocks(code)
    except: return ""

def get_news(code, limit=5):
    """从Astock框架取新闻"""
    try:
        from tradingagents.dataflows.a_stock import get_news
        return get_news(code, max_results=limit)
    except: return ""

def get_dragon_tiger(code):
    """从Astock框架取龙虎榜"""
    try:
        from tradingagents.dataflows.a_stock import get_dragon_tiger_board
        return get_dragon_tiger_board(code)
    except: return ""

def get_fund_flow(code):
    """从Astock框架取资金流"""
    try:
        from tradingagents.dataflows.a_stock import get_fund_flow
        return get_fund_flow(code)
    except: return ""

def get_lockup(code):
    """从Astock框架取解禁"""
    try:
        from tradingagents.dataflows.a_stock import get_lockup_expiry
        return get_lockup_expiry(code)
    except: return ""

def get_industry_comparison(code):
    """从Astock框架取行业对比"""
    try:
        from tradingagents.dataflows.a_stock import get_industry_comparison
        return get_industry_comparison(code)
    except: return ""

ASTOCK_TOOLS = {
    "_tencent_quote": "腾讯批量实时行情(PE/PB/市值/涨跌幅)",
    "get_fundamentals": "基本面(营收/利润/ROE/负债率)",
    "get_concept_blocks": "题材板块归属(申万行业/概念/地区)",
    "get_news": "个股新闻(东财+新浪)",
    "get_dragon_tiger_board": "龙虎榜数据",
    "get_fund_flow": "资金流(主力/散户/分钟级)",
    "get_lockup_expiry": "限售解禁",
    "get_industry_comparison": "行业对比(PE/PB/ROE)",
}

# ====================================================================
# Part 3: 选股引擎（同之前）
# ====================================================================

def _load_all():
    conn = sqlite3.connect(DB)
    end = conn.execute('SELECT MAX(date) FROM daily_klines').fetchone()[0]
    rows = conn.execute('''
        SELECT d.code, s.name, d.date, d.open, d.high, d.low, d.close, d.volume, d.amount
        FROM daily_klines d LEFT JOIN stocks s ON d.code=s.code
        WHERE d.date>=? AND d.code NOT LIKE "688%" AND d.code NOT LIKE "4%"
        AND d.code NOT LIKE "83%" AND d.code NOT LIKE "87%" AND d.code NOT LIKE "8%"
        AND (s.name IS NULL OR (s.name NOT LIKE "%ST%" AND s.name NOT LIKE "%*ST%"))
        ORDER BY d.code, d.date
    ''', (f'{pd.Timestamp(end)-pd.Timedelta(days=90):%Y-%m-%d}',))
    rows = rows.fetchall()
    conn.close()
    by_code = defaultdict(list)
    for r in rows: by_code[r[0]].append(r)
    return by_code, end

STRATEGIES = {}

def register(fn):
    STRATEGIES[fn.__name__] = fn; return fn

@register
def qiangshi(bc):
    return _scan(bc, sm=True, qs=True, mp=3, mv=100, mx=15, fz=True)
@register
def sanmai_dixi(bc):
    return _scan(bc, sm=True, dx=True, mp=2, mv=80, mx=20, fz=True)
@register
def dixi_beichi(bc):
    return _scan(bc, dx=True, bc_=True, mp=2, mv=50, mx=25, fz=False)
@register
def dixi_beichi_danger(bc):
    return _scan(bc, dx=True, bc_=True, mp=3, mv=100, mx=15, fz=True)

STRAT_NAMES = {
    "qiangshi":"强势股+三买v2","sanmai_dixi":"三买v2+低吸",
    "dixi_beichi":"底背驰+低吸（超跌反弹）","dixi_beichi_danger":"严苛底背驰（极小仓位）",
}

def calc_macd(c):
    e12=pd.Series(c).ewm(span=12).mean().values; e26=pd.Series(c).ewm(span=26).mean().values
    return e12-e26

def _scan(by_code, sm=False, qs=False, dx=False, bc_=False, mp=2, mv=50, mx=25, fz=False):
    hits = []
    for code, klines in by_code.items():
        try:
            if len(klines)<25: continue
            df=pd.DataFrame(klines, columns=['c','n','Date','O','H','L','C','V','A'])
            h=df['H'].values; l=df['L'].values; c=df['C'].values; v=df['V'].values; n=len(df)
            name=klines[-1][1] or code; cur=float(c[-1])
            if cur<mp: continue
            if float(np.mean(v[-20:]))*100<mv*10000: continue
            flags=[]; reasons=[]
            if sm: # 三买
                zones=[]
                for i in range(max(0,n-60),n-8):
                    seg=h[i:i+8]; seg_l=l[i:i+8]
                    if len(seg)<5: continue
                    sg=float(seg.max()); sd=float(seg_l.min())
                    if sd>0 and (sg-sd)/sd*100<25: zones.append((sg,sd))
                if zones: zg,zd=zones[-1]
                else:
                    vola=pd.Series(h-l).rolling(10).std().values
                    if len(vola)<=20: continue
                    mi=int(np.argmin(vola[-30:]))+n-30
                    if mi+10>n: continue
                    zg=float(np.max(h[mi:mi+10])); zd=float(np.min(l[mi:mi+10]))
                seg20=h[-20:] if n>=20 else h
                if len(seg20)==0: continue
                ri=int(np.argmax(seg20))+(n-20 if n>=20 else 0)
                rh=float(h[ri])
                if rh<=zg*1.01: continue
                pb=(rh-cur)/rh*100
                if pb<2 or pb>mx: continue
                if cur<=zg: continue
                flags.append("三买v2"); reasons.append(f"三买{zg:.0f}→回抽{pb:.0f}%")
            if qs: # 强势
                base=float(c[-4]) if n>=4 else float(c[-3])
                seg3=h[-3:] if n>=3 else [cur]
                mh=float(np.max(seg3)) if len(seg3)>0 else cur
                mc=max((mh-base)/base,(cur-base)/base)*100
                if mc<4: continue
                va=float(np.mean(v[-20:])) if n>=20 else float(np.mean(v))
                vr=float(v[-1])/va if va>0 else 1
                if vr<0.6: continue
                ma20=float(np.mean(c[-20:])) if n>=20 else 0
                if ma20>0 and cur<ma20*0.95: continue
                flags.append("强势股"); reasons.append(f"涨{mc:.0f}%")
            if bc_: # 底背驰
                if n<30: continue
                macd=calc_macd(c)
                fx_i=-1
                for i in range(n-3,n):
                    if i<1 or i>=n-1: continue
                    if l[i]<l[i-1] and l[i]<l[i+1] and h[i]<h[i-1] and h[i]<h[i+1]: fx_i=i; break
                if fx_i<0: continue
                ss=max(0,fx_i-20); ps=max(0,ss-30)
                ra=abs(sum(macd[ss:fx_i+1][macd[ss:fx_i+1]<0]))
                pa=abs(sum(macd[ps:ss][macd[ps:ss]<0])) if len(macd[ps:ss])>5 else 0
                if not (pa>0 and ra>0 and ra/pa<0.9): continue
                flags.append("底背驰"); reasons.append(f"背驰{ra/pa:.2f}")
            if dx: # 低吸
                if n<25: continue
                lb=min(30,n-5); mi=int(np.argmax(h[-lb:]))+(n-lb)
                mp_=float(h[mi]); pd_ago=n-1-mi
                if pd_ago<2 or pd_ago>12: continue
                pl=float(min(l[mi-min(15,mi):mi+1])); pc=(mp_-pl)/pl*100
                if pc<8: continue
                pb2=(mp_-cur)/mp_*100
                if pb2<2 or pb2>20: continue
                ma20=float(np.mean(c[-20:])) if n>=20 else 0
                if ma20>0 and cur<ma20*0.93: continue
                flags.append("低吸"); reasons.append(f"回调{pb2:.0f}%")
            if not flags: continue
            if fz:
                bad=False
                for j in range(max(2,n-5),n):
                    pc=(c[j-1]-c[j-2])/c[j-2]*100 if c[j-2]!=0 else 0
                    cc=(c[j]-c[j-1])/c[j-1]*100 if c[j-1]!=0 else 0
                    if pc>9 and cc<-5: bad=True; break
                if bad: continue
            chg=(cur-c[-2])/c[-2]*100 if c[-2]!=0 else 0
            hits.append({'code':code,'name':name,'price':cur,'chg':chg,
                         'flags':flags,'reason':';'.join(reasons),'score':len(flags)*10+min(10,int(abs(chg)))})
        except: continue
    return hits

# ====================================================================
# Part 4: 持仓深度分析
# ====================================================================

def analyze_holding(code, name, cost, df, end):
    """单只持仓深度分析"""
    if df is None: return None
    c=df['C'].values; h=df['H'].values; l=df['L'].values; v=df['V'].values; n=len(df)
    cur=float(c[-1]); chg=(cur-c[-2])/c[-2]*100 if c[-2]!=0 else 0
    pnl=(cur-cost)/cost*100
    ma5=float(np.mean(c[-5:])) if n>=5 else cur
    ma10=float(np.mean(c[-10:])) if n>=10 else cur
    ma20=float(np.mean(c[-20:])) if n>=20 else cur
    ma60=float(np.mean(c[-60:])) if n>=60 else cur
    vol_ma20=float(np.mean(v[-20:])) if n>=20 else 1
    vol_ratio=float(v[-1])/vol_ma20 if vol_ma20>0 else 1
    high20=float(np.max(h[-20:])) if n>=20 else cur
    low20=float(np.min(l[-20:])) if n>=20 else cur

    result = {
        "price": cur, "chg": chg, "pnl": pnl,
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
        "vol_ratio": vol_ratio, "high20": high20, "low20": low20,
        "from_high": (high20-cur)/high20*100,
        "from_low": (cur-low20)/low20*100,
    }

    # 借助Astock框架查更多数据
    try:
        q = get_tencent_quote([code])
        if code in q:
            result['pe'] = q[code].get('pe_ttm', 0)
            result['mcap'] = q[code].get('mcap_yi', 0)
            result['turnover'] = q[code].get('turnover_pct', 0)
    except: pass

    try:
        funda = get_fundamentals(code)
        if funda:
            result['revenue'] = funda.get('营业收入(万)', '')
            result['profit'] = funda.get('净利润(万)', '')
    except: pass

    try:
        blocks = get_concept_blocks(code)
        if blocks:
            result['blocks'] = blocks[:200]  # 截断
    except: pass

    # 判断建议
    if pnl > 5:
        result['action'] = "持有或部分止盈"
        result['reason'] = f"浮盈{pnl:.1f}%，在MA{5 if cur>ma5 else 10:.0f}之上"
    elif pnl > 0:
        result['action'] = "持有，设MA5为止损"
        result['reason'] = f"浮盈{pnl:.1f}%，趋势健康"
    elif pnl > -5:
        result['action'] = "持有观察"
        result['reason'] = f"小幅浮亏{pnl:.1f}%，等反弹减仓"
    elif pnl > -15:
        result['action'] = "谨慎持有，反弹减仓"
        result['reason'] = f"深套{pnl:.1f}%，等反弹到MA10附近减仓"
    else:
        result['action'] = "止损或持有等反弹"
        result['reason'] = f"重度亏损{pnl:.1f}%，建议止损"

    if cur < ma20 * 0.95:
        result['action'] += "（⚠️已破MA20）"
    if vol_ratio < 0.5:
        result['action'] += "（成交量萎缩）"

    return result

# ====================================================================
# Part 5: 输出
# ====================================================================

def run(strategy_name=None, top_n=20):
    by_code, end = load_all_data()
    total = len(by_code)

    regime_info = market_regime()
    strat = strategy_name or regime_info['strat']

    print(f'{"="*60}')
    print(f'  全能选股 — {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'{"="*60}')

    # 行情
    print(f'\n📊 市场: {regime_info["regime"]} (评分{regime_info["score"]})')
    print(f'   上涨{regime_info["up5"]}% | 中位数{regime_info["med5"]} | 涨停:跌停 {regime_info["zt_dt"]}')
    print(f'📌 {regime_info["advice"]}')
    print(f'🎯 策略: {STRAT_NAMES.get(strat, strat)}')
    print()

    # 选股
    func = STRATEGIES.get(strat)
    if func:
        hits = func(by_code)
        hits.sort(key=lambda x: -x['score'])
        print(f'{"="*60}')
        print(f'  {STRAT_NAMES.get(strat, strat)} | 命中{len(hits)}只')
        print(f'{"="*60}')
        print(f'\n{"代码":>6} {"名称":<10} {"价格":>8} {"涨跌":>7}  策略')
        print(f'{"-"*50}')
        for h in hits[:top_n]:
            ic='💥' if abs(h['chg'])>=9.5 else '🔥' if abs(h['chg'])>=5 else ''
            fl='/'.join(h['flags'])
            print(f'{h["code"]:>6} {h["name"]:<10} {h["price"]:>8.2f} {h["chg"]:>+7.2f}%{ic}  {fl}')
        print()
        if hits:
            print(f'🎯 重点推荐 (Top 5):')
            for h in hits[:5]:
                print(f'  {h["code"]} {h["name"]} {h["price"]:.2f} {h["chg"]:+.2f}%')
                print(f'    → {h["reason"]}')
        print()

    # 持仓
    print(f'{"="*60}')
    print(f'  你的持仓')
    print(f'{"="*60}')
    for code, info in HOLDINGS.items():
        df, ed = get_klines_df(code)
        r = analyze_holding(code, info['name'], info['cost'], df, ed)
        if r:
            sig = "⚠️" if r['pnl'] < -5 else "✅" if r['pnl'] > 0 else "➖"
            print(f'\n  {code} {info["name"]}  {sig}')
            print(f'    成本{info["cost"]:.2f} → 现价{r["price"]:.2f}  浮盈{r["pnl"]:+.2f}%  当日{r["chg"]:+.2f}%')
            print(f'    MA5={r["ma5"]:.2f} MA10={r["ma10"]:.2f} MA20={r["ma20"]:.2f}')
            print(f'    量比{r["vol_ratio"]:.1f}x | 距20日高{r["from_high"]:.1f}% | 距20日低{r["from_low"]:.1f}%')
            pe_str = f' PE={r.get("pe","?").__round__(1) if isinstance(r.get("pe"),(int,float)) else r.get("pe","?")}'
            print(f'    {pe_str} | 换手{r.get("turnover","?")}%')
            print(f'    📌 {r["action"]} — {r["reason"]}')
        else:
            print(f'\n  {code} {info["name"]} — 数据不足')

    # 工具库情报
    tk = get_toolkit()
    if tk:
        print(f'\n{"="*60}')
        print(f'  📡 每日深度研究情报 ({tk["date"]})')
        print(f'{"="*60}')
        ms = tk.get('market_summary', {})
        print(f'  市场: 强势股{ms.get("market_health",{}).get("strong_pct","?")}% | 涨停{ms.get("market_health",{}).get("zt_count","?")}只')
        lines = ms.get('main_lines_from_name', [])
        if lines:
            print(f'  行业热点: {", ".join(lines[:5])}')
        candidates = tk.get('candidates', [])[:5]
        if candidates:
            print(f'  精选池:')
            for c in candidates:
                print(f'    {c["code"]} {c["name"]} {c["price"]:.2f} 近5日{c["chg5"]:+.1f}% PE={c.get("pe","?")}')
        chains = tk.get('industry_chains', {})
        if chains:
            print(f'  产业链: {", ".join(chains.keys())}')
            for line, detail in chains.items():
                bl = detail.get('壁垒', [])
                zj = detail.get('涨价逻辑', [])
                fl = detail.get('放量逻辑', [])
                if bl: print(f'    {line}壁垒: {"; ".join(bl[:2])}')
                if zj: print(f'    {line}涨价: {"; ".join(zj[:2])}')
                if fl: print(f'    {line}放量: {"; ".join(fl[:2])}')

    # 工具链提示
    print(f'\n{"="*60}')
    print(f'  Astock工具链可用')
    print(f'{"="*60}')
    for name, desc in ASTOCK_TOOLS.items():
        print(f'  • {name}: {desc}')

def load_all_data():
    return _load_all()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--holdings', action='store_true', help='仅看持仓')
    parser.add_argument('--regime', action='store_true', help='仅看行情')
    parser.add_argument('--force', type=str, default=None, help='强制策略')
    parser.add_argument('--top', type=int, default=20, help='显示N只')
    parser.add_argument('--stock', type=str, default=None, help='单只深度分析')
    parser.add_argument('--tools', action='store_true', help='列出工具')
    args = parser.parse_args()

    if args.tools:
        for n,d in ASTOCK_TOOLS.items(): print(f'{n}: {d}')
        sys.exit(0)

    if args.regime:
        r = market_regime()
        print(f'📊 {r["regime"]} ({r["score"]}) 上涨{r["up5"]}% 中位数{r["med5"]} 波动{r["vol"]}')
        print(f'📌 {r["advice"]}')
        print(f'🎯 策略: {STRAT_NAMES.get(r["strat"],r["strat"])}')
        sys.exit(0)

    if args.stock:
        code = args.stock
        df, end = get_klines_df(code)
        from tradingagents.dataflows.astock_db import get_stock_list
        name = [n for c,n in get_stock_list() if c==code]
        name = name[0] if name else code
        r = analyze_holding(code, name, 0, df, end)
        if r:
            print(f'{name}({code}) 深度分析')
            for k,v in r.items(): print(f'  {k}: {v}')
        sys.exit(0)

    if args.holdings:
        by_code, end = load_all_data()
        print(f'\n{"="*60}')
        print(f'  你的持仓 — {end}')
        print(f'{"="*60}')
        for code, info in HOLDINGS.items():
            df, ed = get_klines_df(code)
            r = analyze_holding(code, info['name'], info['cost'], df, ed)
            if r:
                sig = "⚠️" if r['pnl'] < -5 else "✅" if r['pnl'] > 0 else "➖"
                print(f'\n  {code} {info["name"]}  {sig}')
                print(f'    成本{info["cost"]:.2f} → {r["price"]:.2f}  浮盈{r["pnl"]:+.2f}%')
                print(f'    MA5={r["ma5"]:.2f} MA20={r["ma20"]:.2f} 量比{r["vol_ratio"]:.1f}x')
                pe_str = f' PE={r.get("pe","?").__round__(1)}' if isinstance(r.get("pe"),(int,float)) else ''
                print(f'    {pe_str} | 距高{r["from_high"]:.1f}% | 距低{r["from_low"]:.1f}%')
                print(f'    📌 {r["action"]}')
            else: print(f'\n  {code} {info["name"]} — 数据不足')
        sys.exit(0)

    run(strategy_name=args.force, top_n=args.top)
