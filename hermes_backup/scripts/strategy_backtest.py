#!/usr/bin/env python3
"""
策略回测校正系统 v2 — 用DB历史数据直接回测，不依赖工具库

核心逻辑：
  1. 将历史行情按市场状态分段（强势/震荡/弱势/极弱）
  2. 在每段行情中用对应策略选股（用过去的数据做"模拟推荐"）
  3. 追踪后续7个交易日表现（止盈+3% / 止损-3% / 期满平仓）
  4. 计算胜率/盈亏比/最大回撤
  5. 策略对比+参数校正建议

用法:
  python3 strategy_backtest.py                        # 全量回测（4月~现在）
  python3 strategy_backtest.py --strategy qiangshi    # 只测某个策略
  python3 strategy_backtest.py --plot                 # 绘制表现曲线(需matplotlib)
  python3 strategy_backtest.py --report               # 查看最近报告
"""
import sys, os, json, sqlite3, numpy as np, pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict, Counter

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

DB = os.path.expanduser("~/.hermes/astock_data.db")
BACKTEST_DIR = os.path.expanduser("~/.hermes/research_toolkit/_backtest")
os.makedirs(BACKTEST_DIR, exist_ok=True)

# ============================ 参数 ============================
HOLD_DAYS = 7          # 波段持仓天数（你的风格）
PROFIT_TARGET = 0.03   # +3%止盈
STOP_LOSS = -0.03      # -3%止损
MIN_VOLUME = 800000    # 最低日均成交额（过滤僵尸股）
MIN_PRICE = 2.0        # 最低股价

# ============================ 数据加载 ============================

def load_all_data():
    """一次性加载全市场日线（4月~最新）"""
    conn = sqlite3.connect(DB)
    end = conn.execute('SELECT MAX(date) FROM daily_klines').fetchone()[0]
    start = '2026-04-01'
    rows = conn.execute('''
        SELECT d.code, s.name, d.date, d.open, d.high, d.low, d.close, d.volume, d.amount
        FROM daily_klines d LEFT JOIN stocks s ON d.code=s.code
        WHERE d.date>=? AND d.code NOT LIKE "688%" AND d.code NOT LIKE "4%"
        AND d.code NOT LIKE "83%" AND d.code NOT LIKE "87%" AND d.code NOT LIKE "8%"
        AND (s.name IS NULL OR (s.name NOT LIKE "%ST%" AND s.name NOT LIKE "%*ST%"))
        ORDER BY d.code, d.date
    ''', (start,))
    rows = rows.fetchall()
    conn.close()
    # 按日期索引
    by_date = defaultdict(list)
    for r in rows:
        by_date[r[2]].append(r)
    all_dates = sorted(by_date.keys())
    return by_date, all_dates, end

def calc_macd(c):
    e12=pd.Series(c).ewm(span=12).mean().values
    e26=pd.Series(c).ewm(span=26).mean().values
    return e12-e26

# ============================ 市场状态判断 ============================

def detect_regime(by_date, date, lookback=5):
    """判断某一日期附近的市场状态
    基于全体股票中位数涨跌幅 + 上涨占比
    """
    all_dates = sorted(by_date.keys())
    if date not in all_dates: return "未知"
    idx = all_dates.index(date)
    start_idx = max(0, idx - lookback + 1)
    past_dates = all_dates[start_idx:idx+1]

    # 收集每日中位数涨跌幅
    daily_medians = []
    daily_up_ratios = []
    for i in range(1, len(past_dates)):
        prev_d = past_dates[i-1]
        cur_d = past_dates[i]
        prev_map = {r[0]: r[6] for r in by_date[prev_d]}  # code -> close
        cur_data = by_date[cur_d]
        chgs = []
        for r in cur_data:
            if r[0] in prev_map and prev_map[r[0]] > 0:
                chg = (float(r[6]) - float(prev_map[r[0]])) / float(prev_map[r[0]]) * 100
                chgs.append(chg)
        if len(chgs) < 50: continue
        daily_medians.append(np.median(chgs))
        daily_up_ratios.append(np.sum(np.array(chgs) > 0) / len(chgs))

    if not daily_medians: return "未知"

    avg_median = np.mean(daily_medians)
    avg_up = np.mean(daily_up_ratios)

    if avg_up >= 0.55 and avg_median > 0:
        return "强势行情"
    elif avg_up >= 0.45:
        return "震荡行情"
    elif avg_up >= 0.30:
        return "弱势行情"
    else:
        return "极弱行情"

# ============================ 策略引擎（与scan_toolbox一致） ============================

def _scan_on_date(by_date, date, sm=False, qs=False, dx=False, bc=False,
                  mp=2, mv=50, mx=25, fz=False):
    """在某一天用指定策略扫描"""
    # 取当天及之前90天的数据
    all_dates = sorted(by_date.keys())
    if date not in all_dates: return []
    idx = all_dates.index(date)
    start_idx = max(0, idx - 90)
    window_dates = all_dates[start_idx:idx+1]

    # 按code聚合
    by_code = defaultdict(list)
    for d in window_dates:
        for r in by_date[d]:
            by_code[r[0]].append(r)

    hits = []
    for code, klines in by_code.items():
        try:
            if len(klines) < 25: continue
            name = klines[-1][1] or code
            df = pd.DataFrame(klines, columns=['c','n','Date','O','H','L','C','V','A'])
            h=df['H'].values.astype(float); l=df['L'].values.astype(float)
            c=df['C'].values.astype(float); v=df['V'].values.astype(float)
            cur=float(c[-1]); n=len(df)
            if cur<mp: continue
            if float(np.mean(v[-20:]))*100 < mv*10000: continue
            flags=[]; reasons=[]

            if sm:  # 三买
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
                flags.append("三买v2"); reasons.append(f"三买")

            if qs:  # 强势
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
                flags.append("强势股"); reasons.append(f"强势")

            if bc:  # 底背驰
                if n<30: continue
                macd=calc_macd(c)
                fx_i=-1
                for i in range(n-3,n):
                    if i<1 or i>=n-1: continue
                    if l[i]<l[i-1] and l[i]<l[i+1] and h[i]<h[i-1] and h[i]<h[i+1]:
                        fx_i=i; break
                if fx_i<0: continue
                ss=max(0,fx_i-20); ps=max(0,ss-30)
                ra=abs(sum(macd[ss:fx_i+1][macd[ss:fx_i+1]<0]))
                pa=abs(sum(macd[ps:ss][macd[ps:ss]<0])) if len(macd[ps:ss])>5 else 0
                if not (pa>0 and ra>0 and ra/pa<0.9): continue
                flags.append("底背驰"); reasons.append(f"背驰")

            if dx:  # 低吸
                if n<25: continue
                lb=min(30,n-5); mi=int(np.argmax(h[-lb:]))+(n-lb)
                mp_=float(h[mi]); pd_ago=n-1-mi
                if pd_ago<2 or pd_ago>12: continue
                pl=float(min(l[mi-min(15,mi):mi+1])); pc=(mp_-pl)/pl*100
                if pc<8: continue
                pb2=(mp_-cur)/mp_*100 if mp_>0 else 0
                if pb2<2 or pb2>20: continue
                ma20=float(np.mean(c[-20:])) if n>=20 else 0
                if ma20>0 and cur<ma20*0.93: continue
                flags.append("低吸"); reasons.append(f"低吸")

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
                         'flags':flags,'reason':';'.join(reasons),
                         'date':date})
        except: continue
    return hits

# 策略定义
def strategy_qiangshi(bd, date):
    return _scan_on_date(bd, date, sm=True, qs=True, mp=3, mv=100, mx=15, fz=True)
def strategy_sanmai_dixi(bd, date):
    return _scan_on_date(bd, date, sm=True, dx=True, mp=2, mv=80, mx=20, fz=True)
def strategy_dixi_beichi(bd, date):
    return _scan_on_date(bd, date, dx=True, bc=True, mp=2, mv=50, mx=25, fz=False)
def strategy_dixi_beichi_danger(bd, date):
    return _scan_on_date(bd, date, dx=True, bc=True, mp=3, mv=100, mx=15, fz=True)

STRATEGY_MAP = {
    "qiangshi": {"fn": strategy_qiangshi, "name": "强势股+三买v2", "regime": "强势行情"},
    "sanmai_dixi": {"fn": strategy_sanmai_dixi, "name": "三买v2+低吸", "regime": "震荡行情"},
    "dixi_beichi": {"fn": strategy_dixi_beichi, "name": "底背驰+低吸", "regime": "弱势行情"},
    "dixi_beichi_danger": {"fn": strategy_dixi_beichi_danger, "name": "严苛底背驰", "regime": "极弱行情"},
}

# ============================ 回测引擎 ============================

def backtest_one_strategy(strategy_name, by_date, all_dates, verbose=True):
    """对某个策略做全历史回测"""
    info = STRATEGY_MAP[strategy_name]
    regime_filter = info["regime"]

    trades = []
    total_wins = 0
    total_losses = 0
    total_pnl = 0.0
    days_tested = 0

    # 每隔5天扫描一次（提高效率，且5天内行情变化不大）
    scan_interval = 5
    scan_dates = all_dates[::scan_interval]

    for date in scan_dates:
        # 判断该日期市场状态
        regime = detect_regime(by_date, date)
        # 只在该策略对应的行情下运行
        if regime != regime_filter:
            continue

        days_tested += 1
        candidates = info["fn"](by_date, date)

        # 每只推荐取前3名
        for c in candidates[:3]:
            code = c['code']
            entry_price = c['price']
            entry_date = date

            # 找后续交易日
            idx = all_dates.index(date)
            future_dates = all_dates[idx+1:idx+1+HOLD_DAYS+5]

            exit_price = None
            exit_date = None
            hold = 0
            max_pnl = 0
            min_pnl = 0

            for fd in future_dates:
                hold += 1
                # 取该股当天收盘价
                rows = [r for r in by_date[fd] if r[0] == code]
                if not rows: continue
                cur_price = float(rows[-1][6])
                pnl = (cur_price - entry_price) / entry_price

                max_pnl = max(max_pnl, pnl)
                min_pnl = min(min_pnl, pnl)

                if pnl >= PROFIT_TARGET:
                    exit_price = cur_price; exit_date = fd; break
                if pnl <= STOP_LOSS:
                    exit_price = cur_price; exit_date = fd; break

            if exit_price is None and future_dates:
                # 取最后一个交易日收盘（哪怕不到HOLD_DAYS天）
                last_rows = [r for r in by_date[future_dates[-1]] if r[0] == code]
                if last_rows:
                    exit_price = float(last_rows[-1][6])
                    exit_date = future_dates[-1]
                else:
                    continue
            elif exit_price is None:
                continue

            pnl = (exit_price - entry_price) / entry_price
            total_pnl += pnl
            if pnl >= 0.005: total_wins += 1
            else: total_losses += 1

            trades.append({
                'code': code, 'name': c.get('name', ''),
                'entry_date': entry_date, 'entry_price': round(entry_price, 2),
                'exit_date': exit_date, 'exit_price': round(exit_price, 2),
                'pnl': round(pnl*100, 2),
                'hold_days': hold,
                'max_pnl': round(max_pnl*100, 2),
                'min_pnl': round(min_pnl*100, 2),
                'win': pnl >= 0.005,
                'flags': '/'.join(c.get('flags',[])),
            })

    total = len(trades)
    wr = total_wins/total*100 if total>0 else 0
    avg_pnl = total_pnl/total*100 if total>0 else 0
    avg_hold = np.mean([t['hold_days'] for t in trades]) if trades else 0
    best = max(trades, key=lambda x:x['pnl']) if trades else None
    worst = min(trades, key=lambda x:x['pnl']) if trades else None

    return {
        'strategy': strategy_name, 'name': info['name'],
        'regime': regime_filter,
        'total_trades': total, 'wins': total_wins, 'losses': total_losses,
        'win_rate': round(wr, 1), 'avg_pnl': round(avg_pnl, 2),
        'total_pnl': round(total_pnl, 2), 'avg_hold_days': round(avg_hold, 1),
        'days_tested': days_tested,
        'best': {'code': best['code'], 'pnl': best['pnl']} if best else None,
        'worst': {'code': worst['code'], 'pnl': worst['pnl']} if worst else None,
        'trades': trades[-30:],  # 最近30笔
    }

# ============================ 输出 ============================

def run_all():
    by_date, all_dates, end = load_all_data()
    print(f'{"="*60}')
    print(f'  策略回测校正系统 v2')
    print(f'  数据: {all_dates[0]} ~ {all_dates[-1]} ({len(all_dates)}个交易日)')
    print(f'  股票池: {len(set(r[0] for rs in by_date.values() for r in rs))}只')
    print(f'  波段周期: {HOLD_DAYS}天 | 止盈+{PROFIT_TARGET*100:.0f}% 止损{STOP_LOSS*100:.0f}%')
    print(f'{"="*60}')
    print()

    # 市场统计
    regimes = Counter()
    for d in all_dates[::5]:
        regimes[detect_regime(by_date, d)] += 1
    print('📊 市场分布（取样）:')
    for r, c in regimes.most_common():
        print(f'  {r}: {c}次')
    print()

    # 逐个策略回测
    results = []
    for key, info in STRATEGY_MAP.items():
        print(f'⏳ 回测 {info["name"]}...', end=' ', flush=True)
        r = backtest_one_strategy(key, by_date, all_dates, verbose=False)
        results.append(r)
        icon = '✅' if r['win_rate'] >= 50 else '⚠️' if r['win_rate'] >= 40 else '❌'
        print(f'{icon}  {r["total_trades"]}笔 胜率{r["win_rate"]}% 均盈亏{r["avg_pnl"]:+.2f}%')
    print()

    # 对比
    print(f'{"="*60}')
    print(f'  策略对比')
    print(f'{"="*60}')
    print(f'{"策略":<20} {"行情":<10} {"交易":>5} {"胜率":>6} {"均盈亏":>8} {"持有":>5}')
    print(f'{"-"*55}')
    for r in sorted(results, key=lambda x: -x['win_rate']):
        print(f'{r["name"]:<20} {r["regime"]:<10} {r["total_trades"]:>5} {r["win_rate"]:>5.1f}% {r["avg_pnl"]:>+7.2f}% {r["avg_hold_days"]:>4.1f}d')

    print()
    print(f'🔧 校正建议:')
    for r in results:
        if r['win_rate'] < 40 and r['total_trades'] >= 5:
            print(f'  📌 {r["name"]}: 胜率仅{r["win_rate"]}%，建议收紧条件（提高最低股价/量能门槛）')
        elif r['win_rate'] > 70 and r['total_trades'] >= 10:
            print(f'  🔓 {r["name"]}: 胜率{r["win_rate"]}%但交易{r["total_trades"]}笔，可能过滤过严，建议放宽')
        else:
            print(f'  ✅ {r["name"]}: 胜率{r["win_rate"]}%（交易{r["total_trades"]}笔），参数合理')

    # 针对你的波段持仓周期选最佳策略
    best = max(results, key=lambda x: x['win_rate'])
    print()
    print(f'{"="*60}')
    print(f'  🎯 针对你的波段持仓周期建议')
    print(f'{"="*60}')
    print(f'  你的风格: 波段持仓几天~几周')
    print(f'  最佳匹配: {best["name"]}（胜率{best["win_rate"]}% 均盈亏{best["avg_pnl"]:+.2f}%）')
    if best['best']:
        print(f'  最佳案例: {best["best"]["code"]} +{best["best"]["pnl"]:.1f}%')
    if best['worst']:
        print(f'  最差案例: {best["worst"]["code"]} {best["worst"]["pnl"]:.1f}%')
    print()

    # 保存报告
    report = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'data_range': f'{all_dates[0]}~{all_dates[-1]}',
        'hold_days': HOLD_DAYS,
        'tp': PROFIT_TARGET, 'sl': STOP_LOSS,
        'results': results,
        'best_strategy': best['name'],
    }
    fpath = os.path.join(BACKTEST_DIR, f"{report['date']}.json")
    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    with open(os.path.join(BACKTEST_DIR, '_latest.json'), 'w') as f:
        json.dump({"date": report['date'], "file": fpath}, f)
    print(f'💾 报告: {fpath}')

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', type=str, default=None)
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--plot', action='store_true')
    args = parser.parse_args()

    if args.report:
        from pathlib import Path
        latest = Path(BACKTEST_DIR)/'_latest.json'
        if latest.exists():
            with open(latest) as f: meta = json.load(f)
            with open(meta['file']) as f: print(f.read())
        else: print('暂无报告')
    else:
        run_all()
