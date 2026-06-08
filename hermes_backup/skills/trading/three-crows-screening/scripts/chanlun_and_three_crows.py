#!/usr/bin/env python3
"""
缠论 + 三阴 联合全市场筛选
从DB读取日线，同时跑：
  缠论4策略：底分型+底背驰、关键K线突破、三买v2、线段逆驰(nichi)
  三阴选股：涨停启动→3天缩量回调→今日企稳

用法:
  cd /home/harrydolly/code/TradingAgents-astock
  source .venv/bin/activate
  python3 ~/.hermes/skills/trading/three-crows-screening/scripts/chanlun_and_three_crows.py
  python3 ~/.hermes/skills/trading/three-crows-screening/scripts/chanlun_and_three_crows.py --date 2026-06-08
"""
import sys, os, sqlite3, numpy as np
from datetime import datetime, timedelta

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")
import pandas as pd


# ============================================================
# 工具
# ============================================================

def read_klines(code, lookback_days=90):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT MAX(date) FROM daily_klines")
    maxd = c.fetchone()[0]
    if not maxd:
        conn.close()
        return None, None
    end = maxd
    start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    c.execute("""SELECT date,open,high,low,close,volume,amount FROM daily_klines
                 WHERE code=? AND date>=? AND date<=? ORDER BY date""", (code, start, end))
    rows = c.fetchall()
    conn.close()
    if not rows or len(rows) < 20:
        return None, None
    df = pd.DataFrame(rows, columns=['Date','Open','High','Low','Close','Volume','Amount'])
    for col in ['Open','High','Low','Close','Volume','Amount']: df[col] = df[col].astype(float)
    if df['Amount'].sum() == 0:
        df['Amount'] = df['Volume'] * 100 * (df['Open'] + df['Close']) / 2
    return df, end

def calc_macd(df, fast=12, slow=26, signal=9):
    c = df['Close'].values.astype(float)
    ema_f = pd.Series(c).ewm(span=fast).mean().values
    ema_s = pd.Series(c).ewm(span=slow).mean().values
    dif = ema_f - ema_s
    dea = pd.Series(dif).ewm(span=signal).mean().values
    return dif, dea, 2*(dif-dea)

def get_stocks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT code, name FROM stocks ORDER BY code")
    stocks = cur.fetchall()
    conn.close()
    # 排除 ST / 688 / 4 / 83 / 87
    filtered = []
    for code, name in stocks:
        if name and ('ST' in name or '*ST' in name): continue
        if code.startswith('4') or code.startswith('83') or code.startswith('87') or code.startswith('688'): continue
        filtered.append((code, name))
    return filtered

def is_valid_ticker(code, name=""):
    if not code.isdigit() or len(code) != 6: return False
    if code[0] == '4' or code.startswith('83') or code.startswith('87') or code.startswith('688'): return False
    if name and ('ST' in name or '*ST' in name): return False
    return True


# ============================================================
# 缠论 4 策略
# ============================================================

def check_fenxing(high, low, i):
    if i < 1 or i >= len(high)-1: return None
    h1,h2,h3=high[i-1],high[i],high[i+1]; l1,l2,l3=low[i-1],low[i],low[i+1]
    if h2>h1 and h2>h3 and l2>l1 and l2>l3: return 'top'
    if l2<l1 and l2<l3 and h2<h1 and h2<h3: return 'bottom'
    return None

# 策略1：底分型+底背驰
def check_di_beichi(df):
    if df is None or len(df) < 30: return False, []
    c = df['Close'].values.astype(float); h=df['High'].values.astype(float); l=df['Low'].values.astype(float)
    dif,dea,macd = calc_macd(df)
    reasons = []; n = len(df)
    fx_idx = -1
    for i in range(n-3, n):
        r = check_fenxing(h,l,i)
        if r == 'bottom': fx_idx=i; reasons.append(f"底分型i={i}"); break
    if fx_idx < 0: return False, ["无底分型"]
    seg_s = max(0, fx_idx-20); prev_s = max(0, seg_s-30)
    recent_area = abs(sum(macd[seg_s:fx_idx+1][macd[seg_s:fx_idx+1]<0]))
    prev_area = abs(sum(macd[prev_s:seg_s][macd[prev_s:seg_s]<0])) if len(macd[prev_s:seg_s])>5 else 0
    reasons.append(f"绿柱面积: 后{recent_area:.1f} / 前{prev_area:.1f}")
    if prev_area > 0 and recent_area > 0 and recent_area / prev_area < 0.9:
        reasons.append(f"面积缩小{recent_area/prev_area:.2f} ✓")
        return True, reasons
    return False, reasons

# 策略2：关键K线突破（第79课强底分型）
def check_guanjian_kline(df):
    if df is None or len(df) < 20: return False, []
    h=df['High'].values.astype(float); l=df['Low'].values.astype(float); c=df['Close'].values.astype(float)
    reasons=[]; n=len(df)
    for i in range(n-3, n):
        r = check_fenxing(h,l,i)
        if r == 'bottom' and c[i+1] > h[i-1]:
            reasons.append(f"强底分型C3({c[i+1]:.2f})>H1({h[i-1]:.2f})")
            vol=df['Volume'].values.astype(float)
            vma5=pd.Series(vol).rolling(5).mean().values[-1]
            if vol[i+1] > vma5*1.5: reasons.append(f"放量{vol[i+1]/vma5:.1f}倍")
            return True, reasons
    return False, ["无关键底分型"]

# 策略3：三买v2
def check_san_mai(df):
    if df is None or len(df) < 30: return False, []
    h=df['High'].values.astype(float); l=df['Low'].values.astype(float); c=df['Close'].values.astype(float)
    v=df['Volume'].values.astype(float)
    reasons=[]; n=len(df)
    zones=[]
    for i in range(max(0,n-60), n-8):
        seg_h=max(h[i:i+8]); seg_l=min(l[i:i+8]); pct=(seg_h-seg_l)/seg_l*100
        if pct < 25: zones.append((i,i+8,seg_h,seg_l))
    if not zones:
        vola=pd.Series(h-l).rolling(10).std().values
        if len(vola) > 20:
            i=np.argmin(vola[-30:]) + n-30
            zg,zd=max(h[i:i+10]), min(l[i:i+10])
            reasons.append(f"近似中枢[{zd:.2f},{zg:.2f}]")
        else: return False, ["无中枢"]
    else:
        valid=[z for z in zones if z[1] < n-3]
        if not valid: valid=zones
        zg,zd=valid[-1][2],valid[-1][3]
        reasons.append(f"中枢[{zd:.2f},{zg:.2f}]")
    recent_h_idx=np.argmax(h[-20:]) + n-20 if n>=20 else np.argmax(h)
    recent_h=h[recent_h_idx]
    if recent_h <= zg*1.01: reasons.append(f"未突破{zg:.2f}"); return False, reasons
    reasons.append(f"突破H={recent_h:.2f}>ZG={zg:.2f}")
    cur=c[-1]
    pullback=(recent_h-cur)/recent_h*100
    if pullback < 2: reasons.append("刚突破未回抽"); return False, reasons
    if pullback > 20: reasons.append(f"回抽过深{pullback:.1f}%"); return False, reasons
    if cur > zg: reasons.append(f"✅ 三买活跃! C={cur:.2f}>ZG={zg:.2f}"); return True, reasons
    elif min(l[recent_h_idx:]) > zg*0.99: reasons.append("✅ 三买成立"); return True, reasons
    return False, reasons

# 策略4：线段逆驰(nichi)
def check_nichi(df):
    """基于素论的线段逆驰：最后一笔回撤不破前中枢+量缩价稳"""
    if df is None or len(df) < 30: return False, []
    c=df['Close'].values.astype(float); h=df['High'].values.astype(float)
    l=df['Low'].values.astype(float); v=df['Volume'].values.astype(float)
    reasons=[]; n=len(df)
    dif,dea,macd=calc_macd(df)
    # 近20天最低点
    low20=min(l[-20:])
    low20_idx=np.argmin(l[-20:]) + n-20
    # 从最低点到现在的反弹幅度
    rebound=(c[-1]-low20)/low20*100
    if rebound < 3 or rebound > 30: return False, [f"反弹{rebound:.1f}%不在3%-30%范围"]
    reasons.append(f"反弹{rebound:.1f}%")
    # 量缩确认
    v20_avg=np.mean(v[-20:])
    v5_avg=np.mean(v[-5:])
    if v5_avg > v20_avg*0.8: reasons.append(f"量缩{v5_avg/v20_avg:.2f}倍均量")
    # MACD在零轴附近金叉
    if len(dif) > 2 and dif[-1] > dif[-2] and abs(dif[-1]) < 0.5:
        reasons.append(f"MACD dif={dif[-1]:.3f} 金叉向上")
        return True, reasons
    return False, reasons


# ============================================================
# 三阴选股（严格对照通达信公式）
# ============================================================

def check_three_crows(df, name=""):
    """原文three_crows.py的三阴条件，直接移植核心算法"""
    if df is None or len(df) < 10: return False
    c=df['Close'].values.astype(float); o=df['Open'].values.astype(float)
    h=df['High'].values.astype(float); l=df['Low'].values.astype(float)
    if 'Amount' in df.columns: amo=df['Amount'].values.astype(float)
    else: amo=df['Volume'].values.astype(float)*100*(o+c)/2
    t=len(df)-1
    if t < 5: return False
    c0=o0=a0=l0=h0=0  # silence linter
    c0,c1,c2,c3,c4=c[t],c[t-1],c[t-2],c[t-3],c[t-4]
    o0,o1,o2,o3,o4=o[t],o[t-1],o[t-2],o[t-3],o[t-4]
    h0,h1,h2,h3,h4=h[t],h[t-1],h[t-2],h[t-3],h[t-4]
    l0,l1,l2,l3,l4=l[t],l[t-1],l[t-2],l[t-3],l[t-4]
    a0,a1,a2,a3=amo[t],amo[t-1],amo[t-2],amo[t-3]

    # 排除ST
    if name and ('ST' in name or '*ST' in name): return False

    # 跳空加跌停排除
    jump = sum(1 for i in range(4) if t-i > 0 and h[t-i] < l[t-i-1])
    down = sum(1 for i in range(3) if t-i > 0 and c[t-i-1] > 0 and c[t-i]/c[t-i-1] <= 0.9)
    if jump > 0 and down >= 1: return False

    # T-3涨停 REF((REF(C,1)*1.1-C)<0.01, 3)
    limit_p = round(c4 * 1.1, 2)
    if not (limit_p - c3) < 0.01: return False

    # 量缩递减: T-2 > T-3, T-1 < T-2, T < T-1
    if not (a2 > a3): return False
    if not (a1 < a2): return False
    if not (a0 < a1): return False

    # C > REF(O,3)
    if not (c0 > o3): return False

    # OPEN > REF(LOW,3)
    if not (o0 > l3): return False

    # 今日收阴
    if c1 == 0: return False
    if not ((c0 - c1) / c1 < 0): return False

    return True


# ============================================================
# 主扫描
# ============================================================

CHANLUN_STRATEGIES = [
    ("底分型+底背驰", check_di_beichi),
    ("关键K线突破", check_guanjian_kline),
    ("三买v2", check_san_mai),
    ("线段逆驰(nichi)", check_nichi),
]

def scan(verbose=True, max_stocks=None):
    stocks = get_stocks()
    if max_stocks: stocks = stocks[:max_stocks]
    total = len(stocks)
    print(f"{'='*60}")
    print(f"  缠论 + 三阴 联合全市场筛选")
    print(f"  DB: {os.path.expanduser('~/.hermes/astock_data.db')}")
    print(f"  候选池: {total}只")
    print(f"  日期: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*60}\n")

    t0 = datetime.now()
    results = []
    scanned = 0

    for i, (code, name) in enumerate(stocks, 1):
        if not is_valid_ticker(code, name): continue
        scanned += 1
        if verbose and i % 500 == 0:
            elapsed = (datetime.now() - t0).total_seconds()
            print(f"  进度: {i}/{total} 命中{len(results)} {elapsed:.0f}s")

        df, ed = read_klines(code)
        if df is None or len(df) < 30: continue

        cur = float(df['Close'].values[-1])
        pre = float(df['Close'].values[-2])
        chg = ((cur/pre)-1)*100 if pre else 0

        hit_strategies = []
        reasons = []

        # 缠论4策略
        for sname, sfunc in CHANLUN_STRATEGIES:
            hit, rs = sfunc(df)
            if hit:
                hit_strategies.append(sname)
                reasons.extend(rs)

        # 三阴
        if check_three_crows(df, name):
            hit_strategies.append("三阴选股")
            reasons.append("涨停→3缩量→企稳")

        if hit_strategies:
            results.append({
                "code": code, "name": name, "price": cur, "chg": chg,
                "strategies": "/".join(hit_strategies),
                "reasons": reasons,
            })

    elapsed = (datetime.now() - t0).total_seconds()

    # 排序：按命中策略数量降序
    results.sort(key=lambda x: -len(x['strategies'].split('/')))

    print(f"\n{'='*60}")
    print(f"  扫描完成!")
    print(f"  候选池: {total}只 | 扫描: {scanned}只")
    print(f"  命中: {len(results)}只")
    print(f"  耗时: {elapsed:.0f}s")
    print(f"{'='*60}\n")

    if not results:
        print("  ❌ 无股票命中")
        return results

    # 统计策略命中分布
    from collections import Counter
    strategy_counts = Counter()
    for r in results:
        for s in r['strategies'].split('/'):
            strategy_counts[s] += 1
    print("  📊 策略命中分布:")
    total_hits = sum(strategy_counts.values())
    for s, cnt in sorted(strategy_counts.items(), key=lambda x: -x[1]):
        print(f"    {s}: {cnt}次")
    print()

    # 打印结果
    print(f"  {'代码':>6} {'名称':<10} {'策略':<24} {'价格':>7} {'涨跌':>7}")
    print(f"  {'-'*60}")
    for r in results:
        print(f"  {r['code']:>6} {r['name']:<10} {r['strategies']:<24} {r['price']:>7.2f} {r['chg']:>+6.2f}%")

    print()
    # 多策略命中标记
    multi = [r for r in results if len(r['strategies'].split('/')) >= 2]
    if multi:
        print(f"  🎯 多策略共振 ({len(multi)}只):")
        for r in multi:
            print(f"    {r['code']} {r['name']} [{r['strategies']}] {r['price']:.2f} {r['chg']:+.2f}%")

    return results


if __name__ == "__main__":
    max_n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    scan(verbose=True, max_stocks=max_n)
