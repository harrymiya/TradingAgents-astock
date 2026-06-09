#!/usr/bin/env python3
"""
全市场多维度扫描选股脚本。
将TradingAgents框架的8个Analyst维度转化为可量化的全市场筛选条件。

每个维度输出一个分数(0-10)，总分80分。
筛选流程：
  1. 从DB读取全市场日线数据
  2. 批量计算8个维度的得分
  3. 总分排序，前N只进入深度分析阶段
  4. 可手动挑选送入TradingAgents框架做完整分析
"""
import os, sys, sqlite3, math
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")

# ============================================================
# 1. 数据层：批量读取全市场K线
# ============================================================

def load_all_klines(target_date=None):
    """
    从DB读取全市场日线数据。
    
    Returns:
        dict: {code: {name, klines:[(date,o,h,l,c,v,amt)]}}
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    if target_date is None:
        cur.execute("SELECT MAX(date) FROM daily_klines")
        target_date = cur.fetchone()[0]
    
    # 获取股票列表（排除688/4/83/87/8开头）
    cur.execute("""
        SELECT code, name FROM stocks 
        WHERE code NOT LIKE '688%'
        AND code NOT LIKE '4%'
        AND code NOT LIKE '83%'
        AND code NOT LIKE '87%'
        AND code NOT LIKE '8%'
    """)
    stocks = {code: {"name": name, "klines": []} for code, name in cur.fetchall()}
    
    # 批量读取所有K线（最近90天够用）
    start_date = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=90)
    start_str = start_date.strftime("%Y-%m-%d")
    
    cur.execute("""
        SELECT code, date, open, high, low, close, volume, amount 
        FROM daily_klines 
        WHERE date >= ? AND date <= ?
        ORDER BY code, date
    """, (start_str, target_date))
    
    for code, date, o, h, l, c, v, amt in cur.fetchall():
        if code in stocks:
            stocks[code]["klines"].append((date, o, h, l, c, v, amt))
    
    conn.close()
    
    # 过滤掉数据不足30条的
    stocks = {k: v for k, v in stocks.items() if len(v["klines"]) >= 30}
    
    return stocks, target_date


# ============================================================
# 2. 各Analyst维度的量化评分函数
# ============================================================

def score_market_analyst(klines):
    """市场分析师评分：量价结构、均线排列、趋势强度 (0-10)"""
    if len(klines) < 30:
        return 0
    
    closes = [k[4] for k in klines]
    volumes = [k[5] for k in klines]
    latest = klines[-1]
    c, v = latest[4], latest[5]
    
    score = 5  # 中性基准
    
    # 均线排列（10/20/60日均线）
    ma5 = sum(closes[-5:]) / min(5, len(closes))
    ma10 = sum(closes[-10:]) / min(10, len(closes))
    ma20 = sum(closes[-20:]) / min(20, len(closes))
    
    if c > ma5 > ma10: score += 2  # 多头排列
    if c > ma10: score += 1
    if ma10 > ma20: score += 1
    if c < ma10: score -= 1
    if ma10 < ma20: score -= 1
    
    # 量比（近5日均量/近20日均量）
    vol5 = sum(volumes[-5:]) / 5
    vol20 = sum(volumes[-20:]) / 20
    vol_ratio = vol5 / vol20 if vol20 > 0 else 1
    if 1.2 < vol_ratio < 3: score += 1  # 温和放量
    if vol_ratio > 3: score -= 1  # 放量过大可能是出货
    if vol_ratio < 0.5: score -= 1  # 缩量严重
    
    # 涨跌幅
    chg_5d = (c - closes[-6]) / closes[-6] if len(closes) > 5 else 0
    if 2 < chg_5d < 15: score += 1
    if chg_5d < -5: score -= 1
    
    return max(0, min(10, score))


def score_sentiment_analyst(klines):
    """情绪分析师评分：RSI、MACD、市场情绪 (0-10)"""
    if len(klines) < 20:
        return 0
    
    closes = [k[4] for k in klines]
    c = closes[-1]
    
    score = 5
    
    # RSI(14)
    gains = []
    losses = []
    for i in range(1, 15):
        diff = closes[-i] - closes[-i-1]
        if diff >= 0: gains.append(diff)
        else: losses.append(-diff)
    avg_gain = sum(gains) / 14 if gains else 0
    avg_loss = sum(losses) / 14 if losses else 0
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - 100 / (1 + rs)
    
    if 40 < rsi < 70: score += 1  # 健康区间
    if rsi > 80: score -= 1  # 超买
    if rsi < 25: score += 1  # 超卖反弹机会
    
    # MACD
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = ema12[-1] - ema26[-1]
    dea = _ema([ema12[i] - ema26[i] for i in range(len(ema12))], 9)[-1] if len(ema12) > 9 else dif
    macd = 2 * (dif - dea)
    
    if dif > 0 and macd > 0: score += 2  # MACD多头+红柱
    if dif > 0 > macd: score += 0  # 多头但红柱收缩
    if dif < 0 < macd: score -= 1  # 空头但红柱弹起
    if dif < 0 and macd < 0: score -= 1  # 双杀
    
    return max(0, min(10, score))


def score_news_analyst(klines):
    """新闻/事件评分：近期是否有涨停、异动 (0-10)"""
    if len(klines) < 10:
        return 0
    
    score = 5
    
    # 近期是否有涨停（大概判断：涨跌幅>9.5%）
    limit_ups = 0
    for k in klines[-10:]:
        if k[4] >= k[1] * 1.095:  # close >= open * 1.095
            limit_ups += 1
    
    if limit_ups >= 2: score += 2  # 双涨停
    elif limit_ups >= 1: score += 1  # 单涨停
    
    # 近期是否有放量大阳线
    for k in klines[-5:]:
        chg = (k[4] - k[1]) / k[1]
        recent_vols = [kl[5] for kl in klines[-20:]]
        vol_ratio = k[5] / (sum(recent_vols) / len(recent_vols)) if recent_vols else 1
        if chg > 0.05 and vol_ratio > 1.5:
            score += 1
            break
    
    return max(0, min(10, score))


def score_fundamentals_analyst(sina_data=None):
    """
    基本面评分 (0-10)
    如需全市场基本面数据，需从腾讯/东财接口批量获取。
    此处暂用简单的价格/PB近似判断，留接口。
    """
    # TODO: 对接腾讯/东财批量获取PE/PB数据
    return 5  # 中性，暂不评分


def score_policy_analyst(code, target_date):
    """
    政策/题材评分 (0-10)
    检查同花顺热点股榜单，看该股是否有题材归属。
    """
    # 这需要调get_hot_stocks接口，在批量扫描时做一次缓存
    # 暂返回中性
    return 5


def score_hot_money_analyst(klines):
    """游资追踪评分：成交量异动、龙虎榜信号暗示 (0-10)"""
    if len(klines) < 20:
        return 0
    
    score = 5
    volumes = [k[5] for k in klines]
    
    # 成交量爆发指数
    vol_avg_20 = sum(volumes[-20:]) / 20
    vol_max_10 = max(volumes[-10:])
    vol_min_10 = min(volumes[-10:])
    
    if vol_max_10 > 2 * vol_avg_20: score += 2  # 有量能爆发
    if vol_min_10 < 0.5 * vol_avg_20: score += 1  # 有缩量洗盘
    
    # 量价配合
    for i in range(1, min(6, len(klines))):
        chg = (klines[-i][4] - klines[-i][1]) / klines[-i][1]
        vol_ratio = klines[-i][5] / vol_avg_20 if vol_avg_20 > 0 else 1
        if chg > 0.05 and vol_ratio > 2:  # 放量大涨 = 游资入场
            score += 2
            break
    
    # 连板潜力：连续2天以上涨幅>3%
    streak = 0
    for i in range(1, min(6, len(klines))):
        chg = (klines[-i][4] - klines[-i][1]) / klines[-i][1]
        if chg > 0.03:
            streak += 1
        else:
            break
    if streak >= 3: score += 2
    elif streak >= 2: score += 1
    
    return max(0, min(10, score))


def score_lockup_analyst(code):
    """
    解禁/减持风险评分 (0-10)
    10=无解禁压力（安全），0=解禁压顶（危险）
    """
    # 需要调get_lockup_expiry接口
    # 简化：全流通主板股票默认高分
    return 8


def score_chanlun_analyst(klines):
    """
    缠论评分：买卖点识别 (0-10)
    基于K线数据做简化缠论判断。
    """
    if len(klines) < 30:
        return 0
    
    score = 5
    closes = [k[4] for k in klines]
    highs = [k[2] for k in klines]
    lows = [k[3] for k in klines]
    
    # 简单底分型判断（最后3根K线）
    if len(klines) >= 3:
        k1, k2, k3 = klines[-3], klines[-2], klines[-1]
        # 底分型：中间最低
        if k2[3] < k1[3] and k2[3] < k3[3]:
            score += 1
        # 顶分型：中间最高
        if k2[2] > k1[2] and k2[2] > k3[2]:
            score -= 1
    
    # MACD底背驰/顶背驰简化版
    # 价格新低但MACD柱不新低 = 底背驰
    if len(closes) > 20:
        recent_low = min(closes[-5:])
        prev_low = min(closes[-10:-5])
        
        # 计算简单MACD柱
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        dif = [ema12[i] - ema26[i] for i in range(len(ema12))]
        dea = _ema(dif, 9) if len(dif) > 9 else dif
        macd_bars = [2 * (dif[i] - dea[i]) for i in range(len(dif))] if len(dif) == len(dea) else [0] * len(dif)
        
        # 看最后10根MACD柱
        if len(macd_bars) > 10:
            recent_macd_low = min(macd_bars[-5:])
            prev_macd_low = min(macd_bars[-10:-5])
            
            if recent_low < prev_low and recent_macd_low > prev_macd_low:
                score += 2  # 底背驰
            elif recent_low > prev_low and recent_macd_low < prev_macd_low:
                score -= 2  # 顶背驰
    
    return max(0, min(10, score))


# ============================================================
# 辅助函数
# ============================================================

def _ema(data, period):
    """指数移动平均"""
    if len(data) < period:
        return data[:]
    multiplier = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append((data[i] - result[-1]) * multiplier + result[-1])
    return result


# ============================================================
# 3. 主扫描函数
# ============================================================

def scan_market(target_date=None, top_n=50):
    """
    全市场多维度扫描。
    
    Args:
        target_date: 目标日期
        top_n: 返回Top N只
    
    Returns:
        list of dict: [{code, name, scores:{...}, total, rank}]
    """
    print(f"📊 全市场多维度扫描 {'('+target_date+')' if target_date else ''}...")
    
    # 第1步：检查数据完整性
    from tradingagents.dataflows.data_integrity import ensure_data
    ensure_data(target_date)
    
    # 第2步：加载全市场K线
    stocks, actual_date = load_all_klines(target_date)
    print(f"  加载 {len(stocks)} 只股票 x ~44天 = ~{len(stocks)*44}条K线")
    
    # 第3步：批量评分
    results = []
    
    for i, (code, info) in enumerate(stocks.items()):
        klines = info["klines"]
        name = info["name"]
        
        scores = {
            "market": score_market_analyst(klines),
            "sentiment": score_sentiment_analyst(klines),
            "news": score_news_analyst(klines),
            "fundamentals": score_fundamentals_analyst(),
            "policy": score_policy_analyst(code, actual_date),
            "hot_money": score_hot_money_analyst(klines),
            "lockup": score_lockup_analyst(code),
            "chanlun": score_chanlun_analyst(klines),
        }
        total = sum(scores.values())
        
        results.append({
            "code": code,
            "name": name,
            "scores": scores,
            "total": total,
        })
        
        if (i+1) % 500 == 0:
            print(f"  已扫描 {i+1}/{len(stocks)}...")
    
    # 第4步：排序
    results.sort(key=lambda x: x["total"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1
    
    top = results[:top_n]
    
    print(f"\n  ✅ 扫描完成: {len(results)}只, Top {top_n}:")
    print(f"  {'代码':<8} {'名称':<10} {'总分':<6} {'市场':<5} {'情绪':<5} {'事件':<5} {'基本':<5} {'政策':<5} {'游资':<5} {'解禁':<5} {'缠论':<5}")
    print(f"  {'-'*60}")
    for r in top[:10]:
        s = r["scores"]
        print(f"  {r['code']:<8} {r['name']:<10} {r['total']:<6} {s['market']:<5} {s['sentiment']:<5} {s['news']:<5} {s['fundamentals']:<5} {s['policy']:<5} {s['hot_money']:<5} {s['lockup']:<5} {s['chanlun']:<5}")
    
    # 第5步：保存扫描结果
    _save_scan_results(actual_date, results)
    
    return results, actual_date


def _save_scan_results(scan_date, results):
    """保存扫描结果到scan_cache表"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    for r in results[:200]:  # 只保存Top 200
        cur.execute("""
            INSERT OR REPLACE INTO scan_cache 
            (scan_date, code, name, formula_name, price, chg_today)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            scan_date, r["code"], r["name"],
            f"多维度总分{r['total']}",
            0, 0
        ))
    
    conn.commit()
    conn.close()
    print(f"  结果已保存至scan_cache (Top 200)")


def show_candidates(top_n=10, scan_date=None):
    """
    显示适合送入TradingAgents框架做深度分析的候选股票。
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    if scan_date:
        cur.execute("SELECT code, name, formula_name FROM scan_cache WHERE scan_date = ? ORDER BY formula_name DESC LIMIT ?", 
                   (scan_date, top_n))
    else:
        cur.execute("SELECT code, name, formula_name FROM scan_cache ORDER BY scan_date DESC, formula_name DESC LIMIT ?", 
                   (top_n,))
    
    rows = cur.fetchall()
    conn.close()
    
    print(f"\n🎯 推荐送入TradingAgents框架深度分析:")
    for code, name, formula in rows:
        print(f"  {code} {name} (评分: {formula})")
    
    return rows


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    
    results, date = scan_market(target, top_n)
    
    show_candidates(10, date)
