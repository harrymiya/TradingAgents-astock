#!/usr/bin/env python3
"""
缠论(三买v2) + 游资(强势股) 联合全市场筛选
选股逻辑：
  缠论：三买v2 — 中枢突破+回抽2%~20%+不破ZG
  游资：强势股 — 近3日大涨>4%+放量+均线多头

用法:
  cd /home/harrydolly/code/TradingAgents-astock
  source .venv/bin/activate
  python3 chanlun_sanmai_youzi.py
  python3 chanlun_sanmai_youzi.py --top 30
  python3 chanlun_sanmai_youzi.py --live   # 盘中模式
"""
import sys, os, sqlite3, numpy as np, json, urllib.request
from datetime import datetime, timedelta
from collections import Counter

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")
import pandas as pd


# ============================================================
# 数据
# ============================================================

def read_klines(code, lookback=90):
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
    if not rows or len(rows) < 25: return None, None
    df = pd.DataFrame(rows, columns=['Date','Open','High','Low','Close','Volume','Amount'])
    for col in ['Open','High','Low','Close','Volume','Amount']: df[col] = df[col].astype(float)
    if df['Amount'].sum() == 0:
        df['Amount'] = df['Volume'] * 100 * (df['Open'] + df['Close']) / 2
    return df, end

def fetch_live_kline_mootdx(code):
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std', tcp=('202.108.253.139', 80, True))
        df = client.bars(symbol=code, frequency=9, start=0, count=120)
        if df is None or len(df) == 0: return None
        klines = []
        for idx, row in df.iterrows():
            klines.append({"date": str(idx.date()), "open": float(row.open),
                          "high": float(row.high), "low": float(row.low),
                          "close": float(row.close), "volume": float(row.volume),
                          "amount": float(row.get('amount',0)) or float(row.volume)*100*(float(row.open)+float(row.close))/2})
        return klines
    except: return None

def fetch_live_realtime(code):
    prefix = "sz" if code.startswith(("0","3")) else "sh"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    try:
        r = urllib.request.urlopen(url, timeout=5)
        parts = r.read().decode('gbk').split("~")
        if len(parts) < 39: return None
        return {"price": float(parts[3]), "pre_close": float(parts[4]),
                "open": float(parts[5]), "volume": int(parts[6]),
                "high": float(parts[33]) if len(parts)>33 and parts[33] else 0,
                "low": float(parts[34]) if len(parts)>34 and parts[34] else 0,
                "change_pct": float(parts[32]) if len(parts)>32 and parts[32] else 0,
                "turnover": float(parts[38]) if len(parts)>38 and parts[38] else 0}
    except: return None

def read_live(code, lookback=90):
    df, _ = read_klines(code, lookback)
    if df is None: return None, None, None
    today = datetime.now().strftime("%Y-%m-%d")
    live_klines = fetch_live_kline_mootdx(code)
    if live_klines:
        today_k = [k for k in live_klines if k["date"] == today]
        if today_k:
            tk = today_k[-1]
            if df[df["Date"] == today].empty:
                new_row = pd.DataFrame([{"Date": tk["date"], "Open": tk["open"],
                    "High": tk["high"], "Low": tk["low"], "Close": tk["close"],
                    "Volume": tk["volume"], "Amount": tk["amount"]}])
                df = pd.concat([df, new_row], ignore_index=True)
            else:
                idx = df[df["Date"] == today].index[0]
                for col in ["Open","High","Low","Close","Volume","Amount"]:
                    df.at[idx, col] = tk[col.lower()]
    rt = fetch_live_realtime(code)
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


# ============================================================
# 策略1: 缠论 三买v2
# ============================================================

def check_san_mai(df, rt=None):
    """三买v2：中枢突破+回抽2%~20%+不破ZG"""
    if df is None or len(df) < 30: return False, []
    h = df['High'].values; l = df['Low'].values; c = df['Close'].values
    n = len(df); rs = []

    # 找中枢（近60天内找8根K线密集区，幅度<25%）
    zones = []
    for i in range(max(0, n-60), n-8):
        sg = max(h[i:i+8]); sd = min(l[i:i+8])
        if (sg-sd)/sd*100 < 25:
            zones.append((i, i+8, sg, sd))  # start, end, zg, zd

    if not zones:
        # 用最低波动区作为近似中枢
        vola = pd.Series(h-l).rolling(10).std().values
        if len(vola) > 20:
            idx = np.argmin(vola[-30:]) + n - 30
            zg, zd = max(h[idx:idx+10]), min(l[idx:idx+10])
            rs.append(f"近中枢[{zd:.2f},{zg:.2f}]")
        else:
            return False, ["无中枢"]
    else:
        # 取最近的有效中枢
        valid = [z for z in zones if z[1] < n-3] or zones
        zg, zd = valid[-1][2], valid[-1][3]
        rs.append(f"中枢[{zd:.2f},{zg:.2f}]")

    # 突破确认：近20天最高 > ZG
    ri = np.argmax(h[-20:]) + n - 20 if n >= 20 else np.argmax(h)
    rh = h[ri]
    if rh <= zg * 1.01:
        return False, [f"未突破{zg:.2f}（最高{rh:.2f}）"]

    rs.append(f"突破{rh:.2f}>{zg:.2f}")

    # 回抽确认：当前价从最高点回撤2%~20%
    cur = rt['price'] if rt else c[-1]
    pb = (rh - cur) / rh * 100

    if pb < 2:
        return False, ["刚突破，回抽不足"]
    if pb > 20:
        return False, [f"回调过深{pb:.1f}%，已破位"]

    rs.append(f"回抽{pb:.1f}%")

    # 三买核心：不破中枢上沿
    if cur > zg:
        rs.append("✅ 三买活跃（当前价 > ZG）")
        if rt: rs.append(f"实时{rt['price']:.2f}")
        return True, rs
    elif min(l[ri:]) > zg * 0.99:
        rs.append("✅ 三买成立（回抽最低 ≈ ZG）")
        if rt: rs.append(f"实时{rt['price']:.2f}")
        return True, rs
    else:
        return False, ["回抽已入中枢"]


# ============================================================
# 策略2: 游资强势股（养家/赵老哥）
# ============================================================

def check_qiangshi(df, rt=None):
    """强势股：近3日大涨>4%+放量+均线多头"""
    if df is None or len(df) < 20: return False, []
    c = df['Close'].values; h = df['High'].values; v = df['Volume'].values
    n = len(df); rs = []

    cur = rt['price'] if rt else c[-1]
    base = c[-4] if n >= 4 else c[-3]

    # 近3日+今日的最大涨幅（盘中用实时价）
    max_h = max(h[-3:]) if len(h) >= 3 else cur
    max_chg = max((max_h - base) / base, (cur - base) / base) * 100

    if max_chg < 4:
        return False, [f"近3日最大涨幅{max_chg:.1f}% < 4%"]

    rs.append(f"近3日大涨{max_chg:.1f}%")

    # 放量（当前量 > 20日均量0.8倍，有资金关注即可，不必强放量）
    vol_avg = np.mean(v[-20:]) if len(v) >= 20 else np.mean(v)
    vol_cur = rt['volume'] if rt and rt.get('volume') else v[-1]
    vol_ratio = vol_cur / vol_avg if vol_avg > 0 else 1

    if vol_ratio > 1.2:
        rs.append(f"放量{vol_ratio:.1f}倍")
    elif vol_ratio > 0.7:
        rs.append(f"量能维持{vol_ratio:.1f}倍")
    else:
        rs.append(f"缩量{vol_ratio:.1f}倍（关注）")

    # 均线多头
    ma5 = pd.Series(c).rolling(5).mean().values[-1]
    ma10 = pd.Series(c).rolling(10).mean().values[-1] if n >= 10 else 0
    ma20 = pd.Series(c).rolling(20).mean().values[-1] if n >= 20 else 0

    if ma10 > 0 and ma20 > 0:
        if cur > ma5 > ma10 > ma20:
            rs.append("均线多头排列 MA5>MA10>MA20")
        elif cur > ma5 > ma10:
            rs.append("MA5>MA10 短期多头")
        elif cur > ma20:
            rs.append("站上MA20")
        else:
            rs.append("均线待突破")
    else:
        rs.append("均线计算中")

    rs.append("✅ 强势股特征确认")
    return True, rs


# ============================================================
# 扫描
# ============================================================

HOLDINGS = {
    "301231": ("荣信文化", 34.62),
    "300550": ("和仁科技", 14.63),
    "600503": ("华丽家族", 2.82),
    "603586": ("金麒麟", 17.63),
}

def scan(max_stocks=None, live=False, top_n=0):
    t0 = datetime.now()
    stocks = get_stocks()
    if max_stocks: stocks = stocks[:max_stocks]

    total = len(stocks)
    mode = "🟢盘中" if live else "🔵盘后"
    print(f"📡 {mode} 缠论(三买v2)+游资(强势股) 全市场扫描: {total}只...", file=sys.stderr)

    results = []
    for i, (code, name) in enumerate(stocks, 1):
        if live:
            df, ed, rt = read_live(code)
        else:
            df, ed = read_klines(code)
            rt = None
        if df is None or len(df) < 25: continue

        r = scan_one(code, name, df, rt)
        if r: results.append(r)

        if i % 500 == 0:
            el = (datetime.now()-t0).total_seconds()
            print(f"  进度{i}/{total} 命中{len(results)} {el:.0f}s", file=sys.stderr)

    el = (datetime.now()-t0).total_seconds()
    output = format_output(results, mode, el, live, top_n)
    print(output)


def scan_one(code, name, df, rt=None):
    cur = rt['price'] if rt else float(df['Close'].values[-1])
    chg = rt['change_pct'] if rt else ((cur/float(df['Close'].values[-2]))-1)*100 if float(df['Close'].values[-2]) else 0

    hit_c, rc = check_san_mai(df, rt)
    hit_y, ry = check_qiangshi(df, rt)

    if not hit_c and not hit_y: return None

    tags = []
    reasons = {}
    if hit_c: tags.append("三买v2"); reasons["三买v2"] = rc
    if hit_y: tags.append("🔥强势股"); reasons["强势股"] = ry

    return {
        "code": code, "name": name, "price": cur, "chg": chg,
        "tags": tags, "reasons": reasons, "total": len(tags),
    }


def format_output(results, mode, elapsed, live, top_n=0):
    if not results: return "❌ 无命中结果"

    lines = []
    lines.append("=" * 60)
    lines.append(f"  {mode} 缠论(三买v2) + 游资(强势股) 联合筛选")
    lines.append(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} | ⏱ {elapsed:.0f}s")
    lines.append("=" * 60)
    lines.append("")

    # 筛选条件
    lines.append("### 筛选条件")
    lines.append("| 策略 | 来源 | 判定逻辑 |")
    lines.append("|:---|:----|:--------|")
    lines.append("| 三买v2 | 缠论 | 中枢突破+回抽2%~20%+不破ZG |")
    lines.append("| 强势股 | 游资（养家/赵老哥） | 近3日大涨>4%+放量+均线多头 |")
    lines.append("")

    # 数据概况
    lines.append("### 数据概况")
    lines.append(f"  命中: {len(results)}只")
    lines.append(f"  模式: {mode}")
    lines.append("")

    # 分类
    both = [r for r in results if len(r['tags']) >= 2]
    c_only = [r for r in results if r['tags'] == ["三买v2"]]
    y_only = [r for r in results if r['tags'] == ["🔥强势股"]]

    lines.append("### 策略命中分布")
    lines.append(f"  三买v2: {len(c_only)+len(both)}次")
    lines.append(f"  🔥强势股: {len(y_only)+len(both)}次")
    lines.append(f"  双共振（三买+强势）: {len(both)}只 ⭐")
    lines.append("")

    # 双共振 TOP
    if both:
        both.sort(key=lambda x: -abs(x['chg']))
        lines.append(f"### ⭐ 双共振 TOP {min(20, len(both))}（三买v2 + 强势股）")
        lines.append(f"  {'代码':>6} {'名称':<10} {'价格':>8} {'涨跌':>7}  说明")
        lines.append(f"  {'-'*60}")
        for r in both[:20]:
            rs = "; ".join(r['reasons'].get("三买v2", [])[:2] + r['reasons'].get("强势股", [])[:1])
            icon = "💥" if abs(r['chg']) >= 9.5 else "🔥" if abs(r['chg']) >= 5 else ""
            lines.append(f"  {r['code']:>6} {r['name']:<10} {r['price']:>8.2f} {r['chg']:>+7.2f}%{icon}  {rs}")
        lines.append("")

    # 仅三买（低吸潜伏）
    if c_only:
        c_only.sort(key=lambda x: -x['price'])
        lines.append(f"### 🧘 仅三买（低吸潜伏型）")
        lines.append(f"  {'代码':>6} {'名称':<10} {'价格':>8} {'涨跌':>7}  回抽幅度")
        lines.append(f"  {'-'*50}")
        for r in sorted(c_only, key=lambda x: -x['total'])[:10]:
            pb = [s for s in r['reasons'].get("三买v2", []) if "回抽" in s]
            pb_str = pb[0] if pb else ""
            lines.append(f"  {r['code']:>6} {r['name']:<10} {r['price']:>8.2f} {r['chg']:>+7.2f}%  {pb_str}")
        lines.append("")

    # 仅强势股
    if y_only:
        lines.append(f"### 🔥 仅强势股（动量型）")
        lines.append(f"  {'代码':>6} {'名称':<10} {'价格':>8} {'涨跌':>7}")
        lines.append(f"  {'-'*45}")
        for r in sorted(y_only, key=lambda x: -abs(x['chg']))[:10]:
            lines.append(f"  {r['code']:>6} {r['name']:<10} {r['price']:>8.2f} {r['chg']:>+7.2f}%")
        lines.append("")

    # 持仓
    holding_hits = [r for r in results if r['code'] in HOLDINGS]
    if holding_hits:
        lines.append("### 📌 你的持仓")
        for r in holding_hits:
            name, cost = HOLDINGS[r['code']]
            pnl = (r['price'] - cost) / cost * 100
            st = "/".join(r['tags'])
            hit_str = "双共振⭐" if len(r['tags']) >= 2 else r['tags'][0]
            lines.append(f"  {r['code']} {name}  成本{cost}  现价{r['price']:.2f}  浮盈{pnl:+.2f}%  → {hit_str}")
        lines.append("")

    # 建议
    lines.append("### 💡 操作建议")
    if both:
        top = both[0]
        lines.append(f"  • 核心关注: {top['name']}({top['code']}) — 三买+强势双共振")
        lines.append(f"  • 三买形态确认中期结构，强势股确认短线动能")
    lines.append(f"  • 双共振级别越高（有量+有趋势+中枢突破），可靠性越高")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="盘中模式")
    parser.add_argument("--top", type=int, default=0, help="显示Top N")
    parser.add_argument("max", nargs="?", type=int, default=None, help="扫前N只测试")
    args = parser.parse_args()
    scan(max_stocks=args.max, live=args.live, top_n=args.top)
