#!/usr/bin/env python3
"""
策略实验室 — 快速设计→回测→评估→迭代的闭环工具。

三步工作流：
  1. design   设计策略（信号条件）
  2. backtest 回测验证
  3. evaluate 评估+排名+存档

用法:
  python3 strategy_lab.py list                    # 查看所有已存档策略
  python3 strategy_lab.py design --name "超跌反弹v1" --conditions '{"chg":[-5,-3],"vr":[1.2,2.0],"pos":[-25,-10]}' --hold 5
  python3 strategy_lab.py backtest --name "超跌反弹v1"  
  python3 strategy_lab.py grid                    # 自动网格搜索
  python3 strategy_lab.py grid --output best10    # 输出TOP10组合
  python3 strategy_lab.py show --name "超跌反弹v1"  # 查看策略详情
"""

import sqlite3, os, sys, json, time, statistics, math, itertools, re
from datetime import datetime
from collections import defaultdict, OrderedDict

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')
STORE_PATH = os.path.expanduser('~/.hermes/strategy_lab.json')
TRADE_DAYS_PER_YEAR = 245

# ========== 数据层 ==========

def load_data(sample_size=800):
    """加载股票日线数据"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT code, date, open, high, low, close, volume
        FROM daily_klines WHERE date > '2023-01-01' AND date <= '2026-06-05'
        ORDER BY code, date
    """)
    rows = cur.fetchall()
    
    stocks = {}
    for r in rows:
        stocks.setdefault(r[0], []).append(r)
    
    cur.execute("SELECT code FROM stocks WHERE name NOT LIKE '%ST%' AND name NOT LIKE '%退%' AND code NOT LIKE '688%' AND code NOT LIKE '920%' AND code NOT LIKE '4%' AND code NOT LIKE '8%'")
    normal = set(c[0] for c in cur.fetchall())
    conn.close()
    
    # 只取数据量足够的
    sample = [s for s in normal if s in stocks and len(stocks[s]) > 200]
    if sample_size and sample_size < len(sample):
        import random
        random.seed(42)
        sample = random.sample(sample, sample_size)
    
    return {c: stocks[c] for c in sample}

def compute_features(data, i):
    """计算时刻i的所有技术指标"""
    if i < 21 or i >= len(data):
        return None
    
    d = data[i]
    d1 = data[i-1]
    if d1[5] <= 0:
        return None
    
    chg = (d[5] - d1[5]) / d1[5] * 100
    
    # 均量
    vol_20 = statistics.mean([data[j][6] for j in range(i-20, i)])
    vol_ratio = d[6] / vol_20 if vol_20 > 0 else 0
    
    # 均线位置
    ma5 = statistics.mean([data[j][5] for j in range(max(0,i-4), i+1)])
    ma10 = statistics.mean([data[j][5] for j in range(max(0,i-9), i+1)])
    ma20 = statistics.mean([data[j][5] for j in range(max(0,i-19), i+1)])
    ma60 = statistics.mean([data[j][5] for j in range(max(0,i-59), i+1)])
    
    # 相对位置
    pos = (d[5] - ma20) / ma20 * 100 if ma20 > 0 else 0
    pos_ma5 = (d[5] - ma5) / ma5 * 100 if ma5 > 0 else 0
    pos_ma60 = (d[5] - ma60) / ma60 * 100 if ma60 > 0 else 0
    
    # 波动率
    chgs = [(data[j][5] - data[j-1][5]) / data[j-1][5] * 100 for j in range(max(1,i-9), i+1) if data[j-1][5] > 0]
    volatility = statistics.stdev(chgs) if len(chgs) > 1 else 0
    
    # 前几天的涨幅
    prev_chg1 = (d1[5] - data[i-2][5]) / data[i-2][5] * 100 if i >= 2 and data[i-2][5] > 0 else 0
    prev_chg2 = (data[i-2][5] - data[i-3][5]) / data[i-3][5] * 100 if i >= 3 and data[i-3][5] > 0 else 0
    prev_chg3 = (data[i-3][5] - data[i-4][5]) / data[i-4][5] * 100 if i >= 4 and data[i-4][5] > 0 else 0
    
    # 连跌天数
    consecutive_down = 0
    for j in range(i-1, max(0, i-10)-1, -1):
        if data[j][5] < data[j-1][5] if j > 0 else False:
            consecutive_down += 1
        else:
            break
    
    # 连涨天数
    consecutive_up = 0
    for j in range(i-1, max(0, i-10)-1, -1):
        if data[j][5] > data[j-1][5] if j > 0 else False:
            consecutive_up += 1
        else:
            break
    
    # 高低点
    high_20 = max(data[j][3] for j in range(max(0,i-19), i+1))
    low_20 = min(data[j][4] for j in range(max(0,i-19), i+1))
    pos_in_20 = (d[5] - low_20) / (high_20 - low_20) * 100 if high_20 > low_20 else 50
    
    # 成交额占20日比
    vol_in_20 = (d[6] - min(data[j][6] for j in range(max(0,i-19), i+1))) / \
                (max(data[j][6] for j in range(max(0,i-19), i+1)) - min(data[j][6] for j in range(max(0,i-19), i+1)) + 1) * 100
    
    return {
        'chg': chg,
        'vr': vol_ratio,
        'pos': pos,
        'pos_ma5': pos_ma5,
        'pos_ma60': pos_ma60,
        'vol': volatility,
        'prev_chg1': prev_chg1,
        'prev_chg2': prev_chg2,
        'prev_chg3': prev_chg3,
        'consecutive_down': consecutive_down,
        'consecutive_up': consecutive_up,
        'pos_in_20': pos_in_20,
        'vol_in_20': vol_in_20,
        'high_20': high_20,
        'low_20': low_20,
        'ma5': ma5,
        'ma10': ma10,
        'ma20': ma20,
        'ma60': ma60,
        'price': d[5],
        'volume': d[6],
        'date': d[1],
        'code': d[0],
    }


def match_condition(feat, field, op, value):
    """匹配单个条件"""
    if feat is None or field not in feat:
        return False
    v = feat[field]
    if op == '>': return v > value
    elif op == '<': return v < value
    elif op == '>=': return v >= value
    elif op == '<=': return v <= value
    elif op == 'between': return value[0] <= v < value[1]
    elif op == 'outside': return v < value[0] or v >= value[1]
    return False


def match_strategy(feat, conditions):
    """匹配完整策略"""
    # conditions = {field: (op, value), ...}
    # 或 conditions = {'AND': [...], 'OR': [...]}
    if feat is None:
        return False
    
    if isinstance(conditions, dict) and ('AND' in conditions or 'OR' in conditions):
        if 'AND' in conditions:
            return all(match_strategy(feat, c) for c in conditions['AND'])
        elif 'OR' in conditions:
            return any(match_strategy(feat, c) for c in conditions['OR'])
    
    # 简单条件
    for field, spec in conditions.items():
        if field in ('AND', 'OR'):
            continue
        if isinstance(spec, tuple) and len(spec) == 2:
            op, value = spec
            if not match_condition(feat, field, op, value):
                return False
        elif isinstance(spec, list) and len(spec) == 2:
            # 默认between
            lo, hi = spec
            if not (lo <= feat.get(field, -9999) < hi):
                return False
        else:
            if feat.get(field) != spec:
                return False
    return True


# ========== 策略定义与存储 ==========

def load_store():
    if os.path.exists(STORE_PATH):
        with open(STORE_PATH) as f:
            return json.load(f)
    return {"strategies": {}, "experiments": []}

def save_store(store):
    os.makedirs(os.path.dirname(STORE_PATH) or '.', exist_ok=True)
    with open(STORE_PATH, 'w') as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def design_strategy(name, conditions, hold_days=5, description="", tags=None):
    """设计并保存一个策略"""
    store = load_store()
    
    strategy = {
        "name": name,
        "description": description,
        "conditions": conditions,
        "hold_days": hold_days,
        "tags": tags or [],
        "created": datetime.now().isoformat(),
        "backtests": [],
    }
    
    store["strategies"][name] = strategy
    save_store(store)
    print(f"✅ 策略 '{name}' 已创建")
    return strategy


# ========== 回测引擎 ==========

def run_backtest(strategy_name, data, hold_days=None, progress=False):
    """回测指定策略"""
    store = load_store()
    if strategy_name not in store["strategies"]:
        print(f"❌ 策略 '{strategy_name}' 不存在")
        return None
    
    strategy = store["strategies"][strategy_name]
    conditions = strategy["conditions"]
    hold = hold_days or strategy["hold_days"]
    
    signals = []
    
    total = sum(len(d) for d in data.values())
    processed = 0
    
    for code, bars in data.items():
        for i in range(21, len(bars) - max(hold + 1, 11)):
            feat = compute_features_corrected(bars, i)
            processed += 1
            
            if progress and processed % 50000 == 0:
                print(f"  进度: {processed}/{total}")
            
            if match_strategy(feat, conditions):
                # 未来收益
                if i + hold < len(bars):
                    ret = (bars[i+hold][5] - feat['price']) / feat['price'] * 100
                    max_drawdown = min(((bars[j][4] - feat['price']) / feat['price'] * 100) for j in range(i, min(i+hold+1, len(bars))))
                    max_runup = max(((bars[j][3] - feat['price']) / feat['price'] * 100) for j in range(i, min(i+hold+1, len(bars))))
                    
                    signals.append({
                        'code': code,
                        'date': feat['date'],
                        'price': feat['price'],
                        'ret': ret,
                        'max_dd': max_drawdown,
                        'max_ru': max_runup,
                        'win': 1 if ret > 0 else 0,
                    })
                    
                    if len(signals) >= 200000:  # 安全限制
                        break
        
        if len(signals) >= 200000:
            break
    
    # 计算结果
    if not signals:
        return {"name": strategy_name, "signals": 0, "hold_days": hold, "win_rate": 0, "avg_ret": 0, "avg_dd": 0}
    
    wins = [s for s in signals if s['win']]
    rets = [s['ret'] for s in signals]
    dds = [s['max_dd'] for s in signals]
    rus = [s['max_ru'] for s in signals]
    
    wr = len(wins) / len(signals) * 100
    avg = statistics.mean(rets)
    med = statistics.median(rets)
    best = max(rets)
    worst = min(rets)
    avg_dd = statistics.mean(dds)
    
    # 夏普
    if len(rets) > 1 and statistics.stdev(rets) > 0:
        sharpe = (avg / 100) / (statistics.stdev(rets) / 100) * math.sqrt(TRADE_DAYS_PER_YEAR / hold)
    else:
        sharpe = 0
    
    # 盈亏比
    avg_win = statistics.mean([s['ret'] for s in signals if s['ret'] > 0]) if any(s['ret'] > 0 for s in signals) else 0
    avg_loss = statistics.mean([s['ret'] for s in signals if s['ret'] < 0]) if any(s['ret'] < 0 for s in signals) else 0
    profit_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 999
    
    # 最佳10% / 最差10%
    sorted_rets = sorted(rets)
    n = max(1, len(sorted_rets) // 10)
    top10 = statistics.mean(sorted_rets[-n:])
    bot10 = statistics.mean(sorted_rets[:n])
    
    # 连续最大亏损
    max_loss_streak = 0
    current_streak = 0
    for s in signals:
        if s['ret'] < 0:
            current_streak += 1
            max_loss_streak = max(max_loss_streak, current_streak)
        else:
            current_streak = 0
    
    result = {
        "name": strategy_name,
        "hold_days": hold,
        "signal_count": len(signals),
        "win_rate": round(wr, 2),
        "avg_return": round(avg, 3),
        "median_return": round(med, 3),
        "best_return": round(best, 2),
        "worst_return": round(worst, 2),
        "sharpe_ratio": round(sharpe, 2),
        "profit_loss_ratio": round(profit_ratio, 2),
        "max_drawdown_avg": round(avg_dd, 2),
        "top10_avg": round(top10, 2),
        "bottom10_avg": round(bot10, 2),
        "max_loss_streak": max_loss_streak,
        "sample_size": len(signals) if len(signals) < 2000 else f"{len(signals):,}",
    }
    
    # 保存回测结果
    strategy.setdefault("backtests", []).append(result)
    store["strategies"][strategy_name] = strategy
    save_store(store)
    
    return result


def compute_features_corrected(bars, i):
    """为指定的bars数组计算特征"""
    if i < 21 or i >= len(bars):
        return None
    
    d = bars[i]
    d1 = bars[i-1]
    if d1[5] <= 0:
        return None
    
    chg = (d[5] - d1[5]) / d1[5] * 100
    
    # 防0值
    def safe_mean(vals):
        vals = [v for v in vals if v > 0]
        return statistics.mean(vals) if vals else 1
    
    vol_20 = safe_mean([bars[j][6] for j in range(i-20, i)])
    vol_ratio = d[6] / vol_20 if vol_20 > 0 else 0
    
    ma5 = safe_mean([bars[j][5] for j in range(max(0,i-4), i+1)])
    ma20 = safe_mean([bars[j][5] for j in range(max(0,i-19), i+1)])
    ma60 = safe_mean([bars[j][5] for j in range(max(0,i-59), i+1)])
    
    pos = (d[5] - ma20) / ma20 * 100 if ma20 > 0 else 0
    pos_ma60 = (d[5] - ma60) / ma60 * 100 if ma60 > 0 else 0
    
    # 波动率
    chgs = [(bars[j][5] - bars[j-1][5]) / bars[j-1][5] * 100 for j in range(max(1,i-9), i+1) if bars[j-1][5] > 0]
    volatility = statistics.stdev(chgs) if len(chgs) > 1 else 0
    
    # 昨日涨幅
    prev_chg1 = (bars[i-1][5] - bars[i-2][5]) / bars[i-2][5] * 100 if i >= 2 and bars[i-2][5] > 0 else 0
    
    # 连跌天数
    consecutive_down = 0
    for j in range(i-1, max(0, i-10), -1):
        if bars[j][5] < bars[j-1][5]:
            consecutive_down += 1
        else:
            break
    
    # 连涨天数
    consecutive_up = 0
    for j in range(i-1, max(0, i-10), -1):
        if bars[j][5] > bars[j-1][5]:
            consecutive_up += 1
        else:
            break
    
    # 20日高低位置
    high_20 = max(bars[j][3] for j in range(max(0,i-19), i+1))
    low_20 = min(bars[j][4] for j in range(max(0,i-19), i+1))
    pos_in_20 = (d[5] - low_20) / (high_20 - low_20) * 100 if high_20 > low_20 else 50
    
    return {
        'chg': chg, 'vr': vol_ratio, 'pos': pos, 'pos_ma60': pos_ma60,
        'vol': volatility, 'prev_chg1': prev_chg1,
        'consecutive_down': consecutive_down, 'consecutive_up': consecutive_up,
        'pos_in_20': pos_in_20, 'ma5': ma5, 'ma20': ma20, 'ma60': ma60,
        'price': d[5], 'volume': d[6], 'date': d[1], 'code': d[0],
        'high_20': high_20, 'low_20': low_20
    }


# ========== 网格搜索 ==========

def grid_search(param_grid, hold_days=5, sample_size=600, min_signals=80, top_n=10):
    """
    网格搜索最佳参数组合
    param_grid = {
        'chg': [(-5,-3), (-3,-1), (-1,1), ...],
        'vr': [(0.3,0.7), (0.7,1.2), ...],
        'pos': [(-30,-20), (-20,-10), ...],
        ...
    }
    """
    print(f"🔬 网格搜索开始...")
    print(f"  参数空间: { {k: len(v) for k, v in param_grid.items()} }")
    print(f"  样本: {sample_size}只, 持有{hold_days}天")
    
    data = load_data(sample_size)
    total_combs = 1
    for v in param_grid.values():
        total_combs *= len(v)
    print(f"  总组合: {total_combs:,}")
    
    results = []
    combo_idx = 0
    
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    
    for combination in itertools.product(*values):
        combo_idx += 1
        conditions = {}
        for k, v in zip(keys, combination):
            conditions[k] = list(v)
        
        # 回测
        signals = []
        for code, bars in data.items():
            for i in range(21, len(bars) - hold_days - 1):
                feat = compute_features_corrected(bars, i)
                if match_strategy(feat, conditions):
                    if i + hold_days < len(bars):
                        ret = (bars[i+hold_days][5] - feat['price']) / feat['price'] * 100
                        signals.append({
                            'code': code,
                            'ret': ret,
                            'win': 1 if ret > 0 else 0,
                        })
                        if len(signals) >= 50000:
                            break
            if len(signals) >= 50000:
                break
        
        if len(signals) < min_signals:
            continue
        
        wr = sum(s['win'] for s in signals) / len(signals) * 100
        avg_ret = statistics.mean([s['ret'] for s in signals])
        
        # 夏普
        rets = [s['ret'] for s in signals]
        sharpe = 0
        if len(rets) > 1 and statistics.stdev(rets) > 0:
            sharpe = (avg_ret/100) / (statistics.stdev(rets)/100) * math.sqrt(TRADE_DAYS_PER_YEAR / hold_days)
        
        # 综合得分
        score = wr * 0.4 + avg_ret * 10 * 0.3 + sharpe * 10 * 0.3
        
        results.append({
            'conditions': conditions,
            'signals': len(signals),
            'wr': round(wr, 1),
            'avg_ret': round(avg_ret, 2),
            'sharpe': round(sharpe, 2),
            'score': round(score, 1),
        })
        
        if combo_idx % 20 == 0:
            print(f"  已搜索{combo_idx}/{total_combs}... 找到{len(results)}个有效组合")
    
    # 排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # 保存
    store = load_store()
    store["experiments"].append({
        "timestamp": datetime.now().isoformat(),
        "param_grid": {k: len(v) for k, v in param_grid.items()},
        "sample_size": sample_size,
        "hold_days": hold_days,
        "results_count": len(results),
        "top_result": results[0] if results else None,
    })
    save_store(store)
    
    # 打印TOP
    print(f"\n{'='*80}")
    print(f"🏆 网格搜索结果 TOP {top_n} (共{len(results)}个有效组合)")
    print(f"{'#'*80}")
    print(f"{'条件':<55} {'信号':>6} {'胜率':>7} {'均收':>8} {'夏普':>7} {'得分':>7}")
    print("-"*80)
    
    for r in results[:top_n]:
        cond_str = " ".join(f"{k}:{v[0]:.0f}-{v[1]:.0f}" for k, v in r['conditions'].items() 
                          if k in ('chg','vr','pos','prev_chg1','pos_ma60'))
        print(f"{cond_str:<55} {r['signals']:>6} {r['wr']:>6.1f}% {r['avg_ret']:>+7.2f}% {r['sharpe']:>6.2f} {r['score']:>6.1f}")
    
    # 保存TOP5到策略库
    for i, r in enumerate(results[:5]):
        name = f"grid_v{i+1}_{datetime.now().strftime('%m%d_%H%M')}"
        design_strategy(name, r['conditions'], hold_days, 
                       description=f"网格搜索TOP{i+1}: 胜率{r['wr']}% 均收{r['avg_ret']}%",
                       tags=["grid", f"score_{r['score']}"])
    
    return results


# ========== CLI ==========

def format_result(result):
    """格式化回测结果"""
    if result is None:
        return ""
    lines = [
        f"\n📊 策略回测: {result['name']} (持有{result['hold_days']}天)",
        "=" * 55,
        f"  信号数:  {result.get('signal_count', result.get('signals', 0))}",
    ]
    if 'win_rate' in result:
        lines += [
            f"  胜率:    {result['win_rate']:.1f}%",
            f"  均收益:  {result['avg_return']:+.2f}%",
            f"  中位数:  {result.get('median_return', 0):+.2f}%",
            f"  夏普比:  {result.get('sharpe_ratio', 0)}",
            f"  盈亏比:  {result.get('profit_loss_ratio', 0):.2f}",
            f"  最大回撤: {result.get('max_drawdown_avg', 0):.1f}%",
            f"  最佳:    {result.get('best_return', 0):+.1f}%",
            f"  最差:    {result.get('worst_return', 0):+.1f}%",
            f"  TOP10%:  {result.get('top10_avg', 0):+.1f}%",
            f"  BOT10%:  {result.get('bottom10_avg', 0):+.1f}%",
        ]
    return "\n".join(lines)


def list_strategies():
    store = load_store()
    if not store["strategies"]:
        print("📂 策略库为空")
        return
    
    print(f"📂 策略库 (共{len(store['strategies'])}个)")
    print(f"{'名称':<25} {'信号':>8} {'胜率':>8} {'均收':>8} {'持有':>5} {'夏普':>6}")
    print("-"*65)
    for name, s in sorted(store["strategies"].items()):
        bts = s.get("backtests", [])
        last = bts[-1] if bts else None
        if last:
            sig = last.get('signal_count', last.get('signals', 0))
            wr = last.get('win_rate', 0)
            avg = last.get('avg_return', 0)
            hold = last.get('hold_days', s['hold_days'])
            shrp = last.get('sharpe_ratio', 0)
            print(f"{name:<25} {sig:>6} {wr:>7.1f}% {avg:>+7.2f}% {hold:>4}d {shrp:>6.2f}")
        else:
            print(f"{name:<25} {'-':>8} {'-':>8} {'-':>8} {s['hold_days']:>4}d {'-':>6}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='策略实验室')
    sub = parser.add_subparsers(dest='cmd')
    
    # design
    p_design = sub.add_parser('design')
    p_design.add_argument('--name', required=True)
    p_design.add_argument('--conditions', required=True, help='JSON格式条件')
    p_design.add_argument('--hold', type=int, default=5)
    p_design.add_argument('--desc', default='')
    
    # backtest
    p_bt = sub.add_parser('backtest')
    p_bt.add_argument('--name', required=True)
    p_bt.add_argument('--hold', type=int, default=None)
    p_bt.add_argument('--samples', type=int, default=600)
    
    # grid
    p_grid = sub.add_parser('grid')
    p_grid.add_argument('--samples', type=int, default=400)
    p_grid.add_argument('--hold', type=int, default=5)
    p_grid.add_argument('--min', type=int, default=60, help='最低信号数')
    p_grid.add_argument('--top', type=int, default=10)
    
    # show
    p_show = sub.add_parser('show')
    p_show.add_argument('--name', required=True)
    
    # list
    sub.add_parser('list')
    
    args = parser.parse_args()
    
    if args.cmd == 'list':
        list_strategies()
    
    elif args.cmd == 'design':
        conditions = json.loads(args.conditions)
        design_strategy(args.name, conditions, args.hold, args.desc)
    
    elif args.cmd == 'backtest':
        data = load_data(args.samples)
        result = run_backtest(args.name, data, args.hold, progress=True)
        print(format_result(result))
    
    elif args.cmd == 'grid':
        print("🏗️  开始构建参数空间...")
        param_grid = {
            'chg': [(-8,-5), (-5,-3), (-3,-1), (-1,1), (1,3), (3,5), (5,8), (8,12)],
            'vr': [(0.3,0.6), (0.6,0.9), (0.9,1.3), (1.3,1.8), (1.8,2.5), (2.5,4.0)],
            'pos': [(-30,-20), (-20,-15), (-15,-10), (-10,-5), (-5,0), (0,5), (5,10), (10,20)],
        }
        results = grid_search(param_grid, args.hold, args.samples, args.min, args.top)
    
    elif args.cmd == 'show':
        store = load_store()
        if args.name in store["strategies"]:
            s = store["strategies"][args.name]
            print(json.dumps(s, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 策略 '{args.name}' 不存在")
    
    else:
        list_strategies()
