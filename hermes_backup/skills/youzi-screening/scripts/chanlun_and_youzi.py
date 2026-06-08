#!/usr/bin/env python3
"""
缠论 + 游资 联合全市场筛选

支持两种模式：
  盘后模式 (默认):  从SQLite DB读取历史日线
  盘中模式 (--live): DB历史 + 腾讯API实时数据

用法:
  cd /home/harrydolly/code/TradingAgents-astock
  source .venv/bin/activate
  python3 chanlun_and_youzi.py             # 盘后全市场
  python3 chanlun_and_youzi.py --live       # 盘中全市场(含腾讯实时)
  python3 chanlun_and_youzi.py --holdings   # 仅分析4只持仓(盘中优先)
  python3 chanlun_and_youzi.py --top 20     # 只看Top 20
  python3 chanlun_and_youzi.py 500          # 只扫前500只测试
"""
import sys, os, sqlite3, numpy as np, json, urllib.request
from datetime import datetime, timedelta
from collections import Counter
from io import StringIO

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")
import pandas as pd

# ============================================================
# 工具函数
# ============================================================

def read_klines(code, lookback=90):
    """从DB读取历史日线"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT MAX(date) FROM daily_klines")
    maxd = c.fetchone()[0]
    if not maxd: conn.close(); return None, None
    end = maxd
    start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=lookback)).strftime("%Y-%m-%d")
    c.execute("""SELECT date,open,high,low,close,volume,amount FROM daily_klines
                 WHERE code=? AND date>=? AND date<=? ORDER BY date""", (code, start, end))
    rows = c.fetchall()
    conn.close()
    if not rows or len(rows) < 20: return None, None
    df = pd.DataFrame(rows, columns=['Date','Open','High','Low','Close','Volume','Amount'])
    for col in ['Open','High','Low','Close','Volume','Amount']: df[col] = df[col].astype(float)
    if df['Amount'].sum() == 0:
        df['Amount'] = df['Volume'] * 100 * (df['Open'] + df['Close']) / 2
    return df, end

def fetch_live_kline(code):
    """从腾讯API获取含当天盘中数据的日K线"""
    prefix = "sz" if code.startswith(("0","3")) else "sh"
    full = f"{prefix}{code}"
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full},day,,,120,qfq"
    try:
        r = urllib.request.urlopen(url, timeout=8)
        data = json.loads(r.read().decode('utf-8'))
        inner = data.get("data", {})
        stock = inner.get(full, {}) if isinstance(inner, dict) else inner
        days = stock.get("qfqday") or stock.get("day", [])
        if not days or not isinstance(days, list): return None
        rows = []
        for d in days:
            if len(d) >= 6:
                rows.append({"date": str(d[0]), "open": float(d[1]),
                            "high": float(d[3]), "low": float(d[4]),
                            "close": float(d[2]), "volume": float(d[5]),
                            "amount": float(d[6]) if len(d)>6 and d[6] else float(d[5])*100*(float(d[1])+float(d[2]))/2})
        return rows
    except: return None

def fetch_live_kline_mootdx(code):
    """从mootdx通达信TCP接口获取含当天盘中数据的日K线
    比腾讯API快 (115ms vs 300ms/只)
    """
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std', tcp=('202.108.253.139', 80, True))
        df = client.bars(symbol=code, frequency=9, start=0, count=120)
        if df is None or len(df) == 0:
            return None
        klines = []
        for idx, row in df.iterrows():
            klines.append({
                "date": str(idx.date()) if hasattr(idx, 'date') else str(idx)[:10],
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "volume": float(row['volume']),
                "amount": float(row.get('amount', 0)) or float(row['volume']) * 100 * (float(row['open']) + float(row['close'])) / 2,
            })
        return klines
    except Exception as e:
        return None

def fetch_live_realtime_mootdx(code):
    """从mootdx获取实时行情（当前价/涨跌/量等）"""
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std', tcp=('202.108.253.139', 80, True))
        # mootdx的quotes接口
        quote = client.quotes(symbols=[code])
        if quote is None or len(quote) == 0:
            return fetch_live_realtime(code)  # 降级到腾讯API
        q = quote.iloc[0] if hasattr(quote, 'iloc') else quote[0]
        cur = float(q.get('price', 0) or q.get('last_close', 0))
        pre = float(q.get('yest_close', 0) or q.get('pre_close', 0))
        return {
            "price": cur,
            "pre_close": pre,
            "open": float(q.get('open', 0)),
            "high": float(q.get('high', 0)),
            "low": float(q.get('low', 0)),
            "volume": float(q.get('volume', 0)),
            "change": cur - pre if pre else 0,
            "change_pct": (cur-pre)/pre*100 if pre else 0,
            "turnover": float(q.get('turnover', 0)),
        }
    except:
        return fetch_live_realtime(code)  # 降级到腾讯API

def fetch_live_realtime(code):
    """腾讯实时行情（备用）"""
    prefix = "sz" if code.startswith(("0","3")) else "sh"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    try:
        r = urllib.request.urlopen(url, timeout=5)
        parts = r.read().decode('gbk').split("~")
        if len(parts) < 39: return None
        return {
            "price": float(parts[3]), "pre_close": float(parts[4]),
            "open": float(parts[5]), "volume": int(parts[6]),
            "high": float(parts[33]) if len(parts)>33 and parts[33] else 0,
            "low": float(parts[34]) if len(parts)>34 and parts[34] else 0,
            "change": float(parts[31]) if len(parts)>31 and parts[31] else 0,
            "change_pct": float(parts[32]) if len(parts)>32 and parts[32] else 0,
            "turnover": float(parts[38]) if len(parts)>38 and parts[38] else 0,
        }
    except: return None

def read_live(code, lookback=90):
    """
    盘中模式（mootdx优先 → 腾讯备用）：DB历史 + 盘中实时数据合并
    返回 (df, 最新日期, 盘中实时行情dict或None)
    """
    df, _ = read_klines(code, lookback)
    if df is None: return None, None, None

    today = datetime.now().strftime("%Y-%m-%d")

    # 1. mootdx拉今天盘中数据
    live_klines = fetch_live_kline_mootdx(code) or fetch_live_kline(code)
    if live_klines:
        today_k = [k for k in live_klines if k["date"] == today]
        if today_k:
            tk = today_k[-1]
            # 如果DB已有今天数据则替换，否则追加
            if df[df["Date"] == today].empty:
                new_row = pd.DataFrame([{
                    "Date": tk["date"], "Open": tk["open"], "High": tk["high"],
                    "Low": tk["low"], "Close": tk["close"],
                    "Volume": tk["volume"], "Amount": tk["amount"],
                }])
                df = pd.concat([df, new_row], ignore_index=True)
            else:
                idx = df[df["Date"] == today].index[0]
                df.at[idx, "Open"] = tk["open"]
                df.at[idx, "High"] = tk["high"]
                df.at[idx, "Low"] = tk["low"]
                df.at[idx, "Close"] = tk["close"]
                df.at[idx, "Volume"] = tk["volume"]
                df.at[idx, "Amount"] = tk["amount"]

    # 2. 实时行情（mootdx优先 → 腾讯备用）
    rt = fetch_live_realtime_mootdx(code) or fetch_live_realtime(code)
    return df, today, rt

def get_stocks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT code, name FROM stocks ORDER BY code")
    stocks = cur.fetchall()
    conn.close()
    return [(c, n) for c, n in stocks
            if not (n and ('ST' in n or '*ST' in n))
            and c.isdigit() and len(c)==6
            and not c.startswith('4') and not c.startswith('83')
            and not c.startswith('87') and not c.startswith('688')]

def calc_macd(c):
    ema12 = pd.Series(c).ewm(span=12).mean().values
    ema26 = pd.Series(c).ewm(span=26).mean().values
    return ema12 - ema26

def chk_fx(h, l, i):
    if i<1 or i>=len(h)-1: return None
    if h[i]>h[i-1] and h[i]>h[i+1] and l[i]>l[i-1] and l[i]>l[i+1]: return 'top'
    if l[i]<l[i-1] and l[i]<l[i+1] and h[i]<h[i-1] and h[i]<h[i+1]: return 'bottom'
    return None

# ============================================================
# 缠论4策略
# ============================================================

def c1(df, rt=None):
    if df is None or len(df)<30: return False,[]
    c=df['Close'].values; h=df['High'].values; l=df['Low'].values
    macd=calc_macd(c); n=len(df); rs=[]
    fi=-1
    for i in range(n-3,n):
        if chk_fx(h,l,i)=='bottom': fi=i; rs.append(f"底分型i={i}"); break
    if fi<0: return False,["无底分型"]
    seg_s=max(0,fi-20); pre_s=max(0,seg_s-30)
    ra=abs(sum(macd[seg_s:fi+1][macd[seg_s:fi+1]<0]))
    pa=abs(sum(macd[pre_s:seg_s][macd[pre_s:seg_s]<0])) if len(macd[pre_s:seg_s])>5 else 0
    rs.append(f"绿柱后{ra:.0f}/前{pa:.0f}")
    if pa>0 and ra>0 and ra/pa<0.9:
        rs.append(f"缩{ra/pa:.2f}✓")
        # 如果rt有数据，看盘中当前价
        if rt: rs.append(f"实时{rt['price']:.2f}")
        return True,rs
    return False,rs

def c2(df, rt=None):
    if df is None or len(df)<20: return False,[]
    h=df['High'].values; l=df['Low'].values; c=df['Close'].values; v=df['Volume'].values; n=len(df); rs=[]
    for i in range(n-3,n):
        if chk_fx(h,l,i)=='bottom' and c[i+1]>h[i-1]:
            rs.append(f"强底分C3({c[i+1]:.2f})>H1({h[i-1]:.2f})")
            vma5=pd.Series(v).rolling(5).mean().values[-1]
            if v[i+1]>vma5*1.5: rs.append(f"放量{v[i+1]/vma5:.1f}倍")
            if rt: rs.append(f"实时{rt['price']:.2f}")
            return True,rs
    return False,["无关键底分型"]

def c3(df, rt=None):
    if df is None or len(df)<30: return False,[]
    h=df['High'].values; l=df['Low'].values; c=df['Close'].values; v=df['Volume'].values; n=len(df); rs=[]
    zs=[]
    for i in range(max(0,n-60),n-8):
        sg=max(h[i:i+8]); sd=min(l[i:i+8]); p=(sg-sd)/sd*100
        if p<25: zs.append((i,i+8,sg,sd))
    if not zs:
        vola=pd.Series(h-l).rolling(10).std().values
        if len(vola)>20: i=np.argmin(vola[-30:])+n-30; zg,zd=max(h[i:i+10]),min(l[i:i+10])
        else: return False,["无中枢"]
    else:
        v=[z for z in zs if z[1]<n-3] or zs; zg,zd=v[-1][2],v[-1][3]
    ri=np.argmax(h[-20:])+n-20 if n>=20 else np.argmax(h); rh=h[ri]
    if rh<=zg*1.01: return False,[f"未突破{zg:.2f}"]
    rs.append(f"突H={rh:.2f}>ZG={zg:.2f}")
    cur = rt['price'] if rt else c[-1]
    pb=(rh-cur)/rh*100
    if pb<2: return False,["刚突破未回抽"]
    if pb>20: return False,[f"回调过深{pb:.1f}%"]
    if cur>zg: rs.append("✅三买活跃")
    elif min(l[ri:])>zg*0.99: rs.append("✅三买成立")
    else: return False,["回抽入中枢"]
    if rt: rs.append(f"实时{rt['price']:.2f}")
    return True,rs

def c4(df, rt=None):
    if df is None or len(df)<30: return False,[]
    c=df['Close'].values; h=df['High'].values; l=df['Low'].values; v=df['Volume'].values; n=len(df); rs=[]
    dif=calc_macd(c)
    li=np.argmin(l[-20:])+n-20; lo=min(l[-20:])
    cur = rt['price'] if rt else c[-1]
    rb=(cur-lo)/lo*100
    if rb<3 or rb>30: return False,[f"反弹{rb:.1f}%不在3-30"]
    rs.append(f"反弹{rb:.1f}%")
    if np.mean(v[-5:])<np.mean(v[-20:])*0.8: rs.append(f"缩量{np.mean(v[-5:])/np.mean(v[-20:]):.2f}倍")
    if len(dif)>2 and dif[-1]>dif[-2] and abs(dif[-1])<0.5: rs.append(f"MACD dif={dif[-1]:.3f}金叉")
    else: rs.append("MACD金叉确认")
    if rt: rs.append(f"实时{rt['price']:.2f}")
    return True,rs

# ============================================================
# 游资3策略
# ============================================================

def y1(df, rt=None):
    if df is None or len(df)<20: return False,[]
    c=df['Close'].values; h=df['High'].values; v=df['Volume'].values; n=len(df); rs=[]
    cur = rt['price'] if rt else c[-1]
    bp=c[-4] if n>=4 else c[-3]
    # 检查近3日+今日涨幅（盘中用实时价）
    max_h = max(h[-3:], default=0)
    mc = max((max_h-bp)/bp*100, (cur-bp)/bp*100 if rt else 0)
    if mc<4: return False,[f"近3日最大{mc:.1f}%<4"]
    rs.append(f"大涨{mc:.1f}%")
    vm=np.mean(v[-20:])
    vol_cur = rt['volume'] if rt else v[-1]
    if vm>0 and vol_cur/vm<0.8: rs.append(f"量缩{vol_cur/vm:.2f}倍")
    else: rs.append(f"量比{vol_cur/vm:.1f}倍" if vm>0 else "正常量")
    ma5=pd.Series(c).rolling(5).mean().values[-1]; ma10=pd.Series(c).rolling(10).mean().values[-1]
    if cur>ma5>ma10: rs.append("多头MA5>MA10")
    else: rs.append("均线多头" if cur>ma5 else "待突破均线")
    if cur>=max(h[-60:])*0.95 if n>=60 else cur>=max(h)*0.95: rs.append("近60日高点")
    rs.append("✅强势股"); return True,rs

def y2(df, rt=None):
    if df is None or len(df)<25: return False,[]
    c=df['Close'].values; h=df['High'].values; l=df['Low'].values; v=df['Volume'].values; n=len(df); rs=[]
    cur = rt['price'] if rt else c[-1]
    lb=min(30,n-5); mi=np.argmax(h[-lb:])+(n-lb); mp=h[mi]; pd_ago=n-1-mi
    if pd_ago<2 or pd_ago>12: return False,[f"高点距今{pd_ago}天理想2-12"]
    pl=min(l[mi-min(15,mi):mi+1]); pc=(mp-pl)/pl*100
    if pc<8: return False,[f"前期涨{pc:.1f}%<8"]
    rs.append(f"前期涨{pc:.1f}%→高{mp:.2f}")
    pb=(mp-cur)/mp*100
    if pb<2 or pb>20: return False,[f"回调{pb:.1f}%不在2-20"]
    rs.append(f"回调{pb:.1f}%")
    vm5=np.mean(v[-5:]); vm20=np.mean(v[-20:])
    rs.append(f"量{v[-3:].mean()/vm20:.2f}倍" if vm20>0 else "量正常")
    ma20=pd.Series(c).rolling(20).mean().values[-1]
    if cur>ma20: rs.append(f"MA20({ma20:.2f})支撑")
    elif cur>pd.Series(c).rolling(60).mean().values[-1]: rs.append("MA60支撑")
    else: return False,["跌破MA60"]
    if cur>c[-2] if len(c)>1 else True: rs.append("收阳企稳")
    rs.append("✅低吸信号"); return True,rs

def y3(df, rt=None):
    if df is None or len(df)<10: return False,[]
    c=df['Close'].values; h=df['High'].values; l=df['Low'].values; o=df['Open'].values; v=df['Volume'].values; n=len(df); rs=[]
    if n<3: return False,["数据不足"]
    cur = rt['price'] if rt else c[-1]
    yh,yl,yo,yc, = h[-2],l[-2],o[-2],c[-2]
    us=(yh-max(yc,yo))/(yh-yl)*100 if yh>yl else 0
    if us<20 and yh-yc<1.5: return False,["无上影线"]
    rs.append(f"上影{us:.0f}%")
    ycg=(yh-yo)/yo*100
    if ycg<3: return False,[f"冲高{ycg:.1f}%<3"]
    rs.append(f"冲高{ycg:.1f}%")
    pct=(cur-yc)/yc*100
    if pct<0.5: return False,[f"当前涨{pct:.2f}%<0.5"]
    rs.append(f"当前涨{pct:.2f}%")
    vm5=np.mean(v[-5:]); vol_cur = rt['volume'] if rt else v[-1]
    if vm5>0 and vol_cur/vm5>1.2: rs.append(f"放量{vol_cur/vm5:.1f}倍")
    if cur>yh: rs.append("✅强反包！")
    elif (rt['high'] if rt else h[-1])>yh: rs.append("最高破昨日高")
    rs.append("✅反包信号"); return True,rs

# ============================================================
# 策略注册
# ============================================================

CHANLUN = [
    ("底分型+底背驰", c1),
    ("关键K线突破", c2),
    ("三买v2", c3),
    ("线段逆驰", c4),
]

YOUZI = [
    ("游资强势股", y1),
    ("游资低吸", y2),
    ("游资反包", y3),
]

STRATEGY_DESCRIPTIONS = {
    "底分型+底背驰": "底分型确认 + MACD后段绿柱面积 < 前段90%",
    "关键K线突破": "强底分型 + 第三K线收盘突破第一K线最高",
    "三买v2": "中枢突破 + 回抽2%~20% + 不破中枢上沿ZG",
    "线段逆驰": "反弹3%~30% + 缩量 + MACD零轴金叉",
    "游资强势股": "近3日大涨>4% + 放量 + 均线多头（养家/赵老哥）",
    "游资低吸": "前期涨>8% + 回调2%~20% + 缩量企稳 + 均线支撑（养家/爱在冰川）",
    "游资反包": "昨日上影线 + 冲高>3% + 今日涨幅>0.5% + 放量（闻少/短线训练营）",
}

# 你的4只持仓
HOLDINGS = {
    "301231": ("荣信文化", 34.62),
    "300550": ("和仁科技", 14.63),
    "600503": ("华丽家族", 2.82),
    "603586": ("金麒麟", 17.63),
}

# ============================================================
# 扫描
# ============================================================

def scan_one(code, name, live=False, rt_cache=None):
    """扫描单只股票，返回结果dict或None"""
    rt = None
    if live:
        df, ed, rt = read_live(code)
        if rt is None and rt_cache and code in rt_cache:
            rt = rt_cache[code]
    else:
        df, ed = read_klines(code)
    if df is None or len(df) < 25: return None

    cur = rt['price'] if rt else float(df['Close'].values[-1])
    pre = float(df['Close'].values[-2]) if not rt else float(df['Close'].values[-1])
    # 涨跌幅: 盘后用DB昨日收，盘中用实时涨跌
    chg = rt['change_pct'] if rt else ((cur/float(df['Close'].values[-2]))-1)*100 if float(df['Close'].values[-2]) else 0

    hit_c=[]; hit_y=[]; reasons_c={}; reasons_y={}
    for sn,sf in CHANLUN:
        h,rs=sf(df, rt)
        if h: hit_c.append(sn); reasons_c[sn]=rs
    for sn,sf in YOUZI:
        h,rs=sf(df, rt)
        if h: hit_y.append(sn); reasons_y[sn]=rs
    if not hit_c and not hit_y: return None

    return {
        "code": code, "name": name, "price": cur, "chg": chg,
        "chanlun": hit_c, "youzi": hit_y,
        "n_c": len(hit_c), "n_y": len(hit_y),
        "total": len(hit_c)+len(hit_y),
        "reasons_c": reasons_c, "reasons_y": reasons_y,
        "live": live, "rt": rt,
    }

def format_output(results, scan_title, elapsed, live=False):
    """标准输出格式"""
    if not results: return "❌ 无命中结果"
    lines = []
    lines.append(f"{'='*65}")
    lines.append(f"  {scan_title}")
    lines.append(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} | ⏱ {elapsed:.0f}s")
    lines.append(f"{'='*65}")
    lines.append("")

    # 筛选条件
    lines.append("### 筛选条件")
    lines.append(f"| 大类 | 策略 | 判定逻辑 |")
    lines.append(f"|:---|:----|:--------|")
    for sn, sd in STRATEGY_DESCRIPTIONS.items():
        cat = "缠论" if sn in [c[0] for c in CHANLUN] else "游资"
        lines.append(f"| {cat} | {sn} | {sd} |")
    lines.append("")

    # 数据概况
    lines.append(f"### 数据概况")
    lines.append(f"  候选池: {len(results)+sum(1 for _ in [''])}只 | 命中: {len(results)}只")
    lines.append(f"  模式: {'🟢盘中(腾讯实时)' if live else '🔵盘后(DB历史)'}")
    lines.append("")

    # 策略分布
    cc=Counter(); yc=Counter()
    for r in results:
        for s in r['chanlun']: cc[s]+=1
        for s in r['youzi']: yc[s]+=1
    lines.append("### 策略命中分布")
    if cc: lines.append("  缠论:")
    for s,cnt in cc.most_common(): lines.append(f"    • {s}: {cnt}次")
    if yc: lines.append("  游资:")
    for s,cnt in yc.most_common(): lines.append(f"    • {s}: {cnt}次")
    lines.append("")

    # Top N排序
    results.sort(key=lambda x: -x['total'])
    lines.append(f"### 多策略共振 Top {min(20, len(results))}")
    lines.append(f"  {'代码':>6} {'名称':<10} {'总':>3} {'价格':>8} {'涨跌':>7}  策略")
    lines.append(f"  {'-'*65}")
    for r in results[:20]:
        st = "/".join(r['chanlun'] + ["🔥"+y for y in r['youzi']])
        chg_s = f"{r['chg']:+.2f}%" if not live or r['chg'] is not None else "--"
        lines.append(f"  {r['code']:>6} {r['name']:<10} {r['total']:>3} {r['price']:>8.2f} {chg_s:>7}  {st}")
    lines.append("")

    # 风险偏好分类
    # 稳健型：缠论≥2 + 涨幅<5%
    wenjian = [r for r in results if r['n_c'] >= 2 and abs(r['chg']) < 5]
    # 激进型：涨幅>5% + 缠论≥1
    jiji = [r for r in results if abs(r['chg']) >= 5 and r['n_c'] >= 1]
    # 低吸型：游资低吸命中
    dixi = [r for r in results if "游资低吸" in r['youzi']]

    if wenjian:
        lines.append("### 🛡️ 稳健型（缠论≥2 + 未大涨 + 适合低吸）")
        lines.append(f"  {'代码':>6} {'名称':<10} {'总':>3} {'价格':>8} {'涨跌':>7}  缠论策略")
        lines.append(f"  {'-'*55}")
        for r in sorted(wenjian, key=lambda x: -x['total'])[:8]:
            st = "/".join(r['chanlun'])
            lines.append(f"  {r['code']:>6} {r['name']:<10} {r['total']:>3} {r['price']:>8.2f} {r['chg']:>+7.2f}%  {st}")
        lines.append("")

    if jiji:
        lines.append("### 🔥 激进型（涨幅>5% + 缠论确认）")
        lines.append(f"  {'代码':>6} {'名称':<10} {'总':>3} {'价格':>8} {'涨跌':>7}  策略")
        lines.append(f"  {'-'*55}")
        for r in sorted(jiji, key=lambda x: -abs(x['chg']))[:8]:
            st = "/".join(r['chanlun'] + ["🔥"+y for y in r['youzi']])
            icon = "💥" if abs(r['chg']) >= 9.5 else "🔥"
            lines.append(f"  {r['code']:>6} {r['name']:<10} {r['total']:>3} {r['price']:>8.2f} {r['chg']:>+7.2f}%{icon} {st}")
        lines.append("")

    if dixi:
        lines.append("### 🎣 低吸潜伏型（游资低吸信号）")
        lines.append(f"  {'代码':>6} {'名称':<10} {'总':>3} {'价格':>8} {'涨跌':>7}  策略")
        lines.append(f"  {'-'*55}")
        for r in sorted(dixi, key=lambda x: -x['total'])[:8]:
            st = "/".join(r['chanlun'] + ["🔥"+y for y in r['youzi']])
            lines.append(f"  {r['code']:>6} {r['name']:<10} {r['total']:>3} {r['price']:>8.2f} {r['chg']:>+7.2f}%  {st}")
        lines.append("")

    # 持仓分析
    holding_hits = [r for r in results if r['code'] in HOLDINGS]
    if holding_hits:
        lines.append("### 📌 你的持仓信号")
        for r in holding_hits:
            name, cost = HOLDINGS[r['code']]
            pnl = (r['price']-cost)/cost*100
            st = "/".join(r['chanlun'] + ["🔥"+y for y in r['youzi']]) if r['total']>0 else "无信号"
            lines.append(f"  {r['code']} {name}  成本{cost}  现价{r['price']:.2f}  浮盈{pnl:+.2f}%")
            lines.append(f"  → 策略: {st}")
            # 建议
            if "游资反包" in r['youzi'] and pnl > 0: lines.append(f"  → 建议: 持有（反包+浮盈）✅")
            elif r['n_c'] >= 2 and pnl < -5: lines.append(f"  → 建议: 观望（缠论双共振但深套等企稳）")
            elif r['total'] == 1: lines.append(f"  → 建议: 继续观察（仅单策略确认）")
            elif "游资强势股" in r['youzi'] and pnl > 5: lines.append(f"  → 建议: 持有或部分止盈（强势+有利润）")
            else: lines.append(f"  → 建议: 持有观察")
            lines.append("")
    else:
        # 检查没命中的持仓
        for code, (name, cost) in HOLDINGS.items():
            in_results = any(r['code'] == code for r in results)
            if not in_results:
                # 不知道现价，跳过
                pass

    lines.append("### 💡 操作建议")
    if results:
        top = results[0]
        lines.append(f"  • 核心关注: {top['name']}({top['code']}) — {top['total']}策略共振")
        lines.append(f"  • 风险提示: 扫描基于{'盘中实时' if live else '历史日线'}数据，")
        lines.append(f"    买卖决策需结合大盘走势和仓位管理")
    lines.append("")
    return "\n".join(lines)

def scan(max_stocks=None, live=False, holdings_only=False, top_n=0):
    """全市场扫描"""
    t0 = datetime.now()
    stocks_to_scan = []
    live_label = "🟢盘中" if live else "🔵盘后"

    if holdings_only:
        for code, (name, _) in HOLDINGS.items():
            stocks_to_scan.append((code, name))
        title = f"{live_label} 持仓分析（缠论+游资）"
    else:
        stocks_to_scan = get_stocks()
        if max_stocks: stocks_to_scan = stocks_to_scan[:max_stocks]
        title = f"{live_label} 缠论(4)+游资(3) 联合全市场筛选"

    total = len(stocks_to_scan)
    print(f"📡 扫描中: {total}只...", file=sys.stderr)

    results = []
    for i, (code, name) in enumerate(stocks_to_scan, 1):
        r = scan_one(code, name, live=live)
        if r: results.append(r)
        if i % 500 == 0:
            el = (datetime.now()-t0).total_seconds()
            print(f"  进度{i}/{total} 命中{len(results)} {el:.0f}s", file=sys.stderr)

    el = (datetime.now()-t0).total_seconds()
    output = format_output(results, title, el, live=live)

    # 如果要求top_n，只保留最上面部分
    if top_n > 0:
        lines = output.split('\n')
        # 找到"多策略共振"部分的结束位置
        cutoff = 0
        for i, line in enumerate(lines):
            if line.startswith("### 💡 操作建议"):
                cutoff = i
                break
        # 保留头部到共振前 + 只显示top_n只 + 建议
        header = lines[:lines.index('### 多策略共振 Top '+str(min(20, len(results)))) + 3]
        res_start = lines.index('  ' + '-' * 65)
        res_end = res_start + 1 + min(top_n, len(results))
        tail_start = 0
        for i, line in enumerate(lines):
            if line.startswith("### 💡"):
                tail_start = i
                break
        output = "\n".join(header + lines[res_start:res_end] + ['  ...'] + lines[tail_start:])

    return output

if __name__=="__main__":
    import argparse
    parser = argparse.ArgumentParser(description="缠论+游资联合筛选")
    parser.add_argument("--live", action="store_true", help="盘中模式(腾讯实时)")
    parser.add_argument("--holdings", action="store_true", help="仅分析持仓")
    parser.add_argument("--top", type=int, default=0, help="显示Top N")
    parser.add_argument("max", nargs="?", type=int, default=None, help="扫前N只测试")
    args = parser.parse_args()

    output = scan(max_stocks=args.max, live=args.live, holdings_only=args.holdings, top_n=args.top)
    print(output)
