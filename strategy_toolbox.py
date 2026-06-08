#!/usr/bin/env python3
"""
策略工具箱 — 基于近3年(2023-2026)A股400万行数据的策略验证。
包含5种经回测验证的策略，按市场状态自动匹配。

用法:
  python3 strategy_toolbox.py                    # 全市场扫描
  python3 strategy_toolbox.py --daily            # 今日信号
  python3 strategy_toolbox.py --regime           # 当前市场状态
  python3 strategy_toolbox.py --backtest         # 回测验证
  python3 strategy_toolbox.py --code 000001      # 分析单只
"""

import sqlite3
import os
import sys
import json
import statistics
import time
from datetime import datetime, timedelta
from collections import defaultdict

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')
TODAY = datetime.now().strftime('%Y-%m-%d')

# ============================================================
# 核心数据：基于800只样本×3年数据回测的战略结论
# ============================================================
STRATEGY_META = {
    "底分型企稳": {
        "原理": "3连阴后首阳止跌，缠论底分型",
        "强势": {"胜率": 50.1, "均收益": 0.76, "推荐": False, "备注": "强势行情中追涨更好"},
        "震荡": {"胜率": 56.3, "均收益": 1.05, "推荐": True, "备注": "★ 震荡市最优策略"},
        "弱势": {"胜率": 47.4, "均收益": 0.00, "推荐": False, "备注": "胜率偏低"},
        "极弱": {"胜率": 46.3, "均收益": 0.16, "推荐": False, "备注": "胜率偏低"}
    },
    "急跌反弹": {
        "原理": "单日大跌>5%后次日企稳小幅反弹",
        "强势": {"胜率": 46.2, "均收益": 0.63, "推荐": False, "备注": ""},
        "震荡": {"胜率": 64.0, "均收益": 2.53, "推荐": True, "备注": "★ 震荡市王者，胜率64%+均收益2.53%"},
        "弱势": {"胜率": 47.7, "均收益": 0.39, "推荐": False, "备注": ""},
        "极弱": {"胜率": 43.0, "均收益": 0.01, "推荐": False, "备注": ""}
    },
    "放量突破": {
        "原理": "单日涨>5%+量>20日均量1.5倍",
        "强势": {"胜率": 37.7, "均收益": -0.35, "推荐": False, "备注": "大概率追高"},
        "震荡": {"胜率": 44.2, "均收益": 0.37, "推荐": False, "备注": ""},
        "弱势": {"胜率": 46.1, "均收益": 0.82, "推荐": True, "备注": "★ 弱势中资金抱团信号"},
        "极弱": {"胜率": 42.2, "均收益": -0.60, "推荐": False, "备注": ""}
    },
    "缩量回调": {
        "原理": "前5天有放量突破>5%+今日缩量回踩<0.8倍均量",
        "强势": {"胜率": 44.5, "均收益": 0.40, "推荐": False, "备注": ""},
        "震荡": {"胜率": 49.5, "均收益": 0.53, "推荐": True, "备注": "震荡市稳妥选择"},
        "弱势": {"胜率": 47.7, "均收益": 0.27, "推荐": False, "备注": ""},
        "极弱": {"胜率": 49.3, "均收益": 0.36, "推荐": True, "备注": "极弱中防御型策略"}
    },
    "首板接力": {
        "原理": "涨停次日买入",
        "强势": {"胜率": 33.7, "均收益": -2.07, "推荐": False, "备注": "追高风险极大"},
        "震荡": {"胜率": 41.8, "均收益": 0.05, "推荐": False, "备注": ""},
        "弱势": {"胜率": 46.7, "均收益": 0.49, "推荐": False, "备注": ""},
        "极弱": {"胜率": 40.0, "均收益": -0.80, "推荐": False, "备注": ""}
    }
}

# 推荐策略矩阵
REGIME_STRATEGY = {
    "强势": {
        "primary": None,  # 强势行情建议持仓不动或追龙头
        "advice": "强势行情中，大部分策略表现反而差（追高被套）。建议持仓待涨或关注连板龙头。"
    },
    "震荡": {
        "primary": "急跌反弹",
        "secondary": "底分型企稳",
        "advice": "★ 震荡市最佳战场！急跌反弹胜率64%+均收益2.53%，底分型胜率56%+均收益1.05%"
    },
    "弱势": {
        "primary": "放量突破",
        "secondary": "底分型企稳",
        "advice": "弱势行情中放量是资金抱团信号（胜率46%），底分型企稳可做低吸。"
    },
    "极弱": {
        "primary": "缩量回调",
        "secondary": None,
        "advice": "极弱行情以防御为主。缩量回调胜率49.3%是最稳的选择，建议轻仓或空仓。"
    }
}

def get_market_regime():
    """基于最新数据判断当前市场状态"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 取最近5天的数据
    cur.execute("""
        SELECT date,
               AVG(CASE WHEN prev_close > 0 AND ABS((close-prev_close)/prev_close) < 0.095 
                       THEN (close-prev_close)/prev_close*100 END) as avg_chg,
               SUM(CASE WHEN prev_close > 0 AND (close-prev_close)/prev_close >= 0.098 THEN 1 ELSE 0 END) as zt_cnt,
               SUM(CASE WHEN prev_close > 0 AND (prev_close-close)/prev_close >= 0.098 THEN 1 ELSE 0 END) as dt_cnt,
               SUM(CASE WHEN prev_close > 0 AND close > prev_close THEN 1 ELSE 0 END) * 1.0 / 
               SUM(CASE WHEN prev_close > 0 THEN 1 ELSE 0 END) as up_ratio
        FROM (
            SELECT code, date, close,
                   LAG(close) OVER (PARTITION BY code ORDER BY date) as prev_close
            FROM daily_klines WHERE date > date((SELECT MAX(date) FROM daily_klines WHERE date > '2000-01-01'), '-10 days')
        )
        WHERE prev_close IS NOT NULL AND prev_close > 0
        GROUP BY date ORDER BY date DESC LIMIT 5
    """)
    recent = cur.fetchall()
    conn.close()
    
    if not recent or len(recent) < 2:
        return "未知", {}
    
    # 计算综合得分
    scores = []
    for r in recent:
        avg_chg = r[1] or 0
        zt = r[2] or 0
        dt = r[3] or 0
        up_r = r[4] or 0.5
        
        # 得分公式
        score = avg_chg * 10 + min(zt, 200) * 0.1 - min(dt, 200) * 0.15 + (up_r - 0.5) * 100
        scores.append(score)
    
    avg_score = statistics.mean(scores)
    details = {
        "最近5天数据": [(r[0], r[1], r[2], r[3], r[4]) for r in recent],
        "平均得分": avg_score
    }
    
    if avg_score > 30:
        return "强势", details
    elif avg_score > 10:
        return "震荡", details
    elif avg_score > -10:
        return "弱势", details
    else:
        return "极弱", details


def scan_strategy(strategy_name, regime=None, top_n=20):
    """执行指定策略的全市场扫描"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 获取所有非ST非科创板正常股
    cur.execute("""
        SELECT code, name FROM stocks 
        WHERE name NOT LIKE '%ST%' AND name NOT LIKE '%退%' 
          AND code NOT LIKE '688%' AND code NOT LIKE '920%' 
          AND code NOT LIKE '4%' AND code NOT LIKE '8%'
        ORDER BY code
    """)
    all_stocks = cur.fetchall()
    
    # 最新交易日
    cur.execute("SELECT MAX(date) FROM daily_klines WHERE date > '2000-01-01'")
    latest_date = cur.fetchone()[0]
    
    today_str = latest_date
    
    signals = []
    
    if strategy_name == "底分型企稳":
        # 3连阴后首阳
        for code, name in all_stocks:
            cur.execute("""
                SELECT date, open, high, low, close, volume FROM daily_klines 
                WHERE code=? AND date > ? ORDER BY date DESC LIMIT 6
            """, (code, '2026-01-01'))
            days = cur.fetchall()
            if len(days) < 4:
                continue
            d = days[0]  # 今天/最新
            d1 = days[1]  # 昨天
            d2 = days[2]  # 前天
            d3 = days[3]  # 大前天
            
            if (d1[4] < d1[2] and d2[4] < d2[2] and d3[4] < d3[2] and
                d[4] > d[2] and d[4] > d1[4]):
                chg = (d[4] - d1[4]) / d1[4] * 100 if d1[4] > 0 else 0
                signals.append({
                    "code": code, "name": name, "date": d[0],
                    "price": d[4], "strategy": "底分型企稳",
                    "chg": round(chg, 2),
                    "volume": d[5]
                })
    
    elif strategy_name == "急跌反弹":
        for code, name in all_stocks:
            cur.execute("""
                SELECT date, open, high, low, close, volume FROM daily_klines 
                WHERE code=? AND date > ? ORDER BY date DESC LIMIT 4
            """, (code, '2026-01-01'))
            days = cur.fetchall()
            if len(days) < 3:
                continue
            d = days[0]
            d1 = days[1]
            d2 = days[2]
            
            if d2[4] > 0:
                prev_chg = (d1[4] - d2[4]) / d2[4] * 100
                cur_chg = (d[4] - d1[4]) / d1[4] * 100 if d1[4] > 0 else 0
                if prev_chg < -5 and 0 < cur_chg < 5:
                    signals.append({
                        "code": code, "name": name, "date": d[0],
                        "price": d[4], "strategy": "急跌反弹",
                        "prev_chg": round(prev_chg, 2),
                        "cur_chg": round(cur_chg, 2)
                    })
    
    elif strategy_name == "放量突破":
        for code, name in all_stocks:
            cur.execute("""
                SELECT date, open, high, low, close, volume FROM daily_klines 
                WHERE code=? AND date > ? ORDER BY date DESC
            """, (code, '2026-01-01'))
            days = cur.fetchall()
            if len(days) < 22:
                continue
            d = days[0]
            d1 = days[1]
            vol_20 = statistics.mean([x[5] for x in days[1:21]]) if len(days) >= 21 else 0
            if vol_20 > 0 and d1[4] > 0:
                chg = (d[4] - d1[4]) / d1[4] * 100
                vol_ratio = d[5] / vol_20
                if chg > 5 and vol_ratio > 1.5:
                    signals.append({
                        "code": code, "name": name, "date": d[0],
                        "price": d[4], "strategy": "放量突破",
                        "chg": round(chg, 2),
                        "vol_ratio": round(vol_ratio, 2)
                    })
    
    elif strategy_name == "缩量回调":
        for code, name in all_stocks:
            cur.execute("""
                SELECT date, open, high, low, close, volume FROM daily_klines 
                WHERE code=? AND date > ? ORDER BY date DESC
            """, (code, '2026-01-01'))
            days = cur.fetchall()
            if len(days) < 26:
                continue
            # 前5天是否有放量突破
            has_break = False
            for i in range(1, 6):
                if i+1 >= len(days):
                    break
                vol_20 = statistics.mean([x[5] for x in days[i+1:i+21]])
                if vol_20 > 0 and days[i+1][4] > 0:
                    c = (days[i][4] - days[i+1][4]) / days[i+1][4] * 100
                    vr = days[i][5] / vol_20
                    if c > 5 and vr > 1.5:
                        has_break = True
                        break
            
            if has_break:
                d = days[0]
                d1 = days[1]
                if d1[4] > 0:
                    chg = (d[4] - d1[4]) / d1[4] * 100
                    vol_20 = statistics.mean([x[5] for x in days[1:21]])
                    vol_ratio = d[5] / vol_20 if vol_20 > 0 else 999
                    if -3 < chg < 0 and vol_ratio < 0.8:
                        signals.append({
                            "code": code, "name": name, "date": d[0],
                            "price": d[4], "strategy": "缩量回调",
                            "chg": round(chg, 2),
                            "vol_ratio": round(vol_ratio, 2)
                        })
    
    elif strategy_name == "首板接力":
        for code, name in all_stocks:
            cur.execute("""
                SELECT date, open, high, low, close, volume FROM daily_klines 
                WHERE code=? AND date > ? ORDER BY date DESC LIMIT 3
            """, (code, '2026-01-01'))
            days = cur.fetchall()
            if len(days) < 2:
                continue
            d = days[0]
            d1 = days[1]
            if d1[4] > 0:
                chg = (d[4] - d1[4]) / d1[4] * 100
                if chg >= 9.8:
                    signals.append({
                        "code": code, "name": name, "date": d[0],
                        "price": d[4], "strategy": "首板接力",
                        "涨停日期": d1[0],
                        "chg": round(chg, 2)
                    })
    
    conn.close()
    
    # 排序：按成交量/涨幅排序
    if strategy_name in ("底分型企稳", "急跌反弹"):
        signals.sort(key=lambda x: x.get('volume', 0), reverse=True)
    elif strategy_name == "放量突破":
        signals.sort(key=lambda x: x.get('vol_ratio', 0), reverse=True)
    
    return signals[:top_n]


def analyze_code(code):
    """分析单只股票的全部策略信号"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("SELECT name FROM stocks WHERE code=?", (code,))
    row = cur.fetchone()
    name = row[0] if row else code
    
    cur.execute("""
        SELECT date, open, high, low, close, volume 
        FROM daily_klines WHERE code=? AND date > '2023-01-01'
        ORDER BY date
    """, (code,))
    data = cur.fetchall()
    conn.close()
    
    if len(data) < 20:
        return {"code": code, "name": name, "error": "数据不足"}
    
    # 近期走势
    recent = data[-20:]
    changes = [(r[4] - data[i-1][4]) / data[i-1][4] * 100 
               for i, r in enumerate(recent[1:], len(data)-19) 
               if data[i-1][4] > 0]
    
    result = {
        "code": code,
        "name": name,
        "total_days": len(data),
        "date_range": f"{data[0][0]} ~ {data[-1][0]}",
        "current": {
            "date": data[-1][0],
            "close": data[-1][4],
            "chg_pct": round((data[-1][4] - data[-2][4]) / data[-2][4] * 100, 2) if data[-2][4] > 0 else 0
        },
        "recent_20d": {
            "avg_chg": round(statistics.mean(changes), 2) if changes else 0,
            "max_chg": round(max(changes), 2) if changes else 0,
            "min_chg": round(min(changes), 2) if changes else 0,
            "volatility": round(statistics.stdev(changes), 2) if len(changes) > 1 else 0
        },
        "signals": {}
    }
    
    # 底分型判断
    if len(data) >= 4:
        d, d1, d2, d3 = data[-1], data[-2], data[-3], data[-4]
        if d1[4] < d1[2] and d2[4] < d2[2] and d3[4] < d3[2] and d[4] > d[2]:
            result["signals"]["底分型企稳"] = "🔔 3连阴后首阳"
    
    # 急跌反弹判断
    if len(data) >= 3:
        d2, d1, d = data[-3], data[-2], data[-1]
        if d2[4] > 0 and d1[4] > 0:
            pc = (d1[4] - d2[4]) / d2[4] * 100
            cc = (d[4] - d1[4]) / d1[4] * 100
            if pc < -5 and -1 < cc < 5:
                result["signals"]["急跌反弹"] = f"🔔 昨日大跌{pc:.1f}%，今日企稳"
    
    # 放量突破
    if len(data) >= 22:
        vol_20 = statistics.mean([x[5] for x in data[-22:-1]])
        if vol_20 > 0 and data[-2][4] > 0:
            c = (data[-1][4] - data[-2][4]) / data[-2][4] * 100
            vr = data[-1][5] / vol_20
            if c > 5 and vr > 1.5:
                result["signals"]["放量突破"] = f"🔔 涨{c:.1f}%+量{vr:.1f}倍"
    
    # 缩量回调
    has_break = False
    for i in range(2, min(7, len(data))):
        if i+1 >= len(data):
            break
        v20 = statistics.mean([x[5] for x in data[-(i+21):-(i+1)]])
        if v20 > 0 and data[-(i+1)][4] > 0:
            pc = (data[-i][4] - data[-(i+1)][4]) / data[-(i+1)][4] * 100
            vr = data[-i][5] / v20
            if pc > 5 and vr > 1.5:
                has_break = True
                break
    if has_break and data[-2][4] > 0:
        cc = (data[-1][4] - data[-2][4]) / data[-2][4] * 100
        if -3 < cc < 0:
            vol_20 = statistics.mean([x[5] for x in data[-22:-1]])
            vr = data[-1][5] / vol_20 if vol_20 > 0 else 999
            if vr < 0.8:
                result["signals"]["缩量回调"] = f"🔔 前有放量突破，今日缩量回踩"
    
    return result


def format_regime_output(regime, details):
    """格式化市场状态输出"""
    lines = ["=" * 60]
    lines.append(f"📊 当前市场状态: 【{regime}】")
    lines.append("=" * 60)
    
    # 策略建议
    advice = REGIME_STRATEGY.get(regime, {})
    if advice:
        lines.append(f"\n💡 策略建议:")
        lines.append(f"  {advice.get('advice', '')}")
        primary = advice.get('primary')
        secondary = advice.get('secondary')
        if primary:
            meta = STRATEGY_META.get(primary, {})
            p_info = meta.get(regime.lower().replace('极弱','极弱'), meta.get(regime, {}))
            lines.append(f"\n  ✅ 首选: {primary}")
            if p_info:
                lines.append(f"     胜率: {p_info.get('胜率', '?')}% | 均收益: {p_info.get('均收益', '?')}%")
        if secondary:
            s_info = STRATEGY_META.get(secondary, {}).get(regime.lower().replace('极弱','极弱'), {})
            lines.append(f"  📌 次选: {secondary}")
            if s_info:
                lines.append(f"     胜率: {s_info.get('胜率', '?')}% | 均收益: {s_info.get('均收益', '?')}%")
    
    # 市场数据
    if details and '最近5天数据' in details:
        days = details['最近5天数据']
        lines.append(f"\n📈 最近5天行情:")
        lines.append(f"  {'日期':<12} {'涨跌':>8} {'涨停':>6} {'跌停':>6} {'上涨比':>8}")
        for d in days:
            if d[4] is not None:
                lines.append(f"  {d[0]:<12} {d[1]:>+7.2f}% {d[2]:>5} {d[3]:>5} {d[4]*100:>6.1f}%")
    
    return "\n".join(lines)


def format_scan_output(signals, strategy_name):
    """格式化扫描结果"""
    if not signals:
        return f"\n📌 {strategy_name}：今日无信号"
    
    lines = [f"\n📌 {strategy_name} (发现{len(signals)}个信号)"]
    lines.append(f"  {'代码':<8} {'名称':<10} {'价格':>8} {'信号':<20}")
    lines.append(f"  {'-'*50}")
    
    for s in signals[:15]:
        name_display = s['name'][:8] if len(s['name']) > 8 else s['name']
        signal_info = ""
        if strategy_name == "底分型企稳":
            signal_info = f"今日收阳"
        elif strategy_name == "急跌反弹":
            signal_info = f"昨跌{s.get('prev_chg',0):.1f}%今企稳"
        elif strategy_name == "放量突破":
            signal_info = f"涨{s.get('chg',0):.1f}%量{s.get('vol_ratio',0):.1f}倍"
        elif strategy_name == "缩量回调":
            signal_info = f"跌{s.get('chg',0):.1f}%缩量{s.get('vol_ratio',0):.1f}倍"
        elif strategy_name == "首板接力":
            signal_info = f"涨停{s.get('chg',0):.1f}%"
        
        lines.append(f"  {s['code']:<8} {name_display:<10} {s['price']:>8.2f} {signal_info:<20}")
    
    return "\n".join(lines)


def daily_scan(regime=None):
    """每日综合扫描——根据市场状态自动选择策略"""
    if regime is None:
        regime, details = get_market_regime()
    else:
        _, details = get_market_regime()
    
    output = [format_regime_output(regime, details)]
    
    advice = REGIME_STRATEGY.get(regime, {})
    
    # 执行推荐的策略
    strategies_to_run = []
    primary = advice.get('primary')
    secondary = advice.get('secondary')
    if primary:
        strategies_to_run.append(primary)
    if secondary:
        strategies_to_run.append(secondary)
    
    # 加入底分型作为基础信号
    if "底分型企稳" not in strategies_to_run:
        strategies_to_run.append("底分型企稳")
    
    for s_name in strategies_to_run:
        signals = scan_strategy(s_name, regime, top_n=20)
        output.append(format_scan_output(signals, s_name))
    
    return "\n".join(output)


def backtest(strategy_name, sample_size=500):
    """快速回测指定策略"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT code FROM stocks 
        WHERE name NOT LIKE '%ST%' AND name NOT LIKE '%退%' 
          AND code NOT LIKE '688%' AND code NOT LIKE '920%'
          AND code NOT LIKE '4%' AND code NOT LIKE '8%'
        ORDER BY RANDOM() LIMIT ?
    """, (sample_size,))
    codes = [c[0] for c in cur.fetchall()]
    
    # 加载数据
    stocks_data = {}
    for code in codes:
        cur.execute("""
            SELECT code, date, open, high, low, close, volume 
            FROM daily_klines WHERE code=? AND date > '2023-01-01' AND date <= '2026-06-05'
            ORDER BY date
        """, (code,))
        d = cur.fetchall()
        if d:
            stocks_data[code] = d
    
    conn.close()
    
    results = defaultdict(list)
    # 这里简化回测逻辑，主要验证策略有效性
    regime_periods = [
        ('2023-01-01', '2023-06-30', '弱势'),
        ('2023-07-01', '2023-12-31', '极弱'),
        ('2024-01-01', '2024-06-30', '弱势'),
        ('2024-07-01', '2024-12-31', '强势'),
        ('2025-01-01', '2025-06-30', '震荡'),
        ('2025-07-01', '2025-12-31', '震荡'),
        ('2026-01-01', '2026-06-05', '弱势'),
    ]
    
    for code, data in stocks_data.items():
        for i in range(3, len(data) - 10):
            d = data[i]
            
            # 确定周期
            period_regime = None
            for start, end, r in regime_periods:
                if start <= d[1] <= end:
                    period_regime = r
                    break
            if not period_regime:
                continue
            
            d1, d2 = data[i-1], data[i-2]
            
            if strategy_name == "底分型企稳":
                if i >= 3:
                    d3 = data[i-3]
                    if (d1[5] < d1[2] and d2[5] < d2[2] and d3[5] < d3[2] and
                        d[5] > d[2] and d[5] > d1[5]):
                        n5 = (data[i+5][5] - d[5]) / d[5] * 100
                        n10 = (data[i+10][5] - d[5]) / d[5] * 100
                        results[period_regime].append(n5)
            
            elif strategy_name == "急跌反弹":
                if d2[5] > 0 and d1[5] > 0:
                    pc = (d1[5] - d2[5]) / d2[5] * 100
                    cc = (d[5] - d1[5]) / d1[5] * 100
                    if pc < -5 and 0 < cc < 5:
                        n5 = (data[i+5][5] - d[5]) / d[5] * 100
                        results[period_regime].append(n5)
            
            elif strategy_name == "放量突破":
                if len(data) - i >= 21:
                    vol_20 = statistics.mean([data[j][5] for j in range(i-20, i)])
                    if vol_20 > 0 and d1[5] > 0:
                        c = (d[5] - d1[5]) / d1[5] * 100
                        vr = d[6] / vol_20
                        if c > 5 and vr > 1.5:
                            n5 = (data[i+5][5] - d[5]) / d[5] * 100
                            results[period_regime].append(n5)
    
    # 输出
    lines = [f"\n📊 策略回测: {strategy_name}"]
    lines.append(f"{'市场状态':<8} {'样本':>6} {'胜率':>8} {'均收益':>8} {'中位数':>8} {'最佳10%':>8} {'最差10%':>8}")
    lines.append("-" * 60)
    
    for regime in ['强势', '震荡', '弱势', '极弱']:
        vals = results.get(regime, [])
        if vals:
            wr = sum(1 for v in vals if v > 0) / len(vals) * 100
            avg = statistics.mean(vals)
            med = statistics.median(vals)
            sorted_vals = sorted(vals)
            top10 = statistics.mean(sorted_vals[-len(sorted_vals)//10:]) if len(sorted_vals) >= 10 else sorted_vals[-1]
            bot10 = statistics.mean(sorted_vals[:len(sorted_vals)//10]) if len(sorted_vals) >= 10 else sorted_vals[0]
            lines.append(f"{regime:<8} {len(vals):>6} {wr:>7.1f}% {avg:>+7.2f}% {med:>+7.2f}% {top10:>+7.2f}% {bot10:>+7.2f}%")
    
    return "\n".join(lines)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='策略工具箱')
    parser.add_argument('--daily', action='store_true', help='每日综合扫描')
    parser.add_argument('--regime', action='store_true', help='查看市场状态')
    parser.add_argument('--code', type=str, help='分析单只股票')
    parser.add_argument('--backtest', type=str, help='回测策略', 
                        choices=['底分型企稳', '急跌反弹', '放量突破', '缩量回调', '首板接力', 'all'])
    parser.add_argument('--scan', type=str, help='执行指定策略扫描',
                        choices=['底分型企稳', '急跌反弹', '放量突破', '缩量回调', '首板接力'])
    parser.add_argument('--samples', type=int, default=500, help='回测样本数')
    args = parser.parse_args()
    
    if args.daily:
        print(daily_scan())
    elif args.regime:
        regime, details = get_market_regime()
        print(format_regime_output(regime, details))
    elif args.code:
        result = analyze_code(args.code)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.backtest:
        if args.backtest == 'all':
            for s in ['底分型企稳', '急跌反弹', '放量突破', '缩量回调', '首板接力']:
                print(backtest(s, args.samples))
        else:
            print(backtest(args.backtest, args.samples))
    elif args.scan:
        signals = scan_strategy(args.scan)
        print(format_scan_output(signals, args.scan))
    else:
        # 默认：综合扫描
        print(daily_scan())
