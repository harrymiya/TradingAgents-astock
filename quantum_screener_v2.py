#!/usr/bin/env python3
"""
quantum_screener_v2.py — 8维度量化选股器 v2

基于TradingAgents框架的8位分析师逻辑对v1版的评估和改进:
1. 情绪维度 修复：连跌天数判断使用了ret1(未来数据)，改为用chg(当日)
2. 事件维度 强化：异动判断增加振幅>8%的活跃股加分
3. 基本面维度 重写：用MA20偏离代替S3胜率作为质量代理
4. 缠论维度 修复：连跌天数计算bug
5. 策略阈值调整：总分标准降低（当前市场环境下合理分数28-35）
"""

import sqlite3
import os
import sys
from datetime import datetime
from collections import defaultdict
import math

DB = os.path.expanduser("~/.hermes/astock_data.db")


# ============================================================
# 8维评分函数（v2改进版）
# ============================================================

def score_market(kline_60d):
    """市场分析师 v2 — 权重调整：位置比均线更重要"""
    if not kline_60d or len(kline_60d) < 20:
        return 0, "数据不足"
    
    closes = [r[4] for r in kline_60d]
    volumes = [r[5] for r in kline_60d]
    chgs = [r[6] for r in kline_60d if r[6] is not None]
    last = kline_60d[-1]
    
    price = last[4]
    score = 0
    details = []
    
    # 1. 位置 (0-4分) ← 提升权重
    high_20d = max(closes[-20:])
    low_20d = min(closes[-20:])
    pos_20d = (price - low_20d) / (high_20d - low_20d) * 100 if high_20d != low_20d else 50
    
    pos_score = 0
    if pos_20d < 10: pos_score = 4       # 极度超卖
    elif pos_20d < 20: pos_score = 3     # 超卖
    elif pos_20d < 30: pos_score = 2     # 偏低
    elif pos_20d < 50: pos_score = 1     # 中位
    
    score += pos_score
    details.append(f"位置{pos_score}/4 ({pos_20d:.0f})")
    
    # 2. 均线趋势 (0-3分)
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20
    
    ma_score = 0
    if price > ma5: ma_score += 1
    if ma5 > ma10: ma_score += 1
    if ma10 > ma20: ma_score += 1
    score += ma_score
    details.append(f"均线{ma_score}/3")
    
    # 3. MACD (0-2分)
    ema12 = sum(closes[-12:]) / 12
    ema26 = sum(closes[-26:]) / 26 if len(closes) >= 26 else sum(closes) / len(closes)
    dif = ema12 - ema26
    
    macd_score = 0
    if dif > 0: macd_score += 1
    if len(closes) >= 5:
        ema12_5 = sum(closes[-6:-1]) / 5
        ema26_5 = sum(closes[-21:-16]) / 5 if len(closes) >= 21 else ema12_5
        dif_5 = ema12_5 - ema26_5
        if dif > dif_5: macd_score += 1
    score += macd_score
    details.append(f"MACD{macd_score}/2")
    
    # 4. 量价配合 (0-1分)
    avg_vol = sum(volumes) / len(volumes)
    latest_vol = volumes[-1]
    vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 1
    
    vol_score = 0
    if chgs and chgs[-1] > 0 and vol_ratio > 0.8:
        vol_score = 1  # 上涨带量
    score += vol_score
    details.append(f"量价{vol_score}/1")
    
    return score, "; ".join(details)


def score_sentiment(kline_60d):
    """情绪分析师 v2 — 修复连跌天数的计算"""
    if not kline_60d or len(kline_60d) < 15:
        return 0, "数据不足"
    
    chgs = [r[6] for r in kline_60d if r[6] is not None]
    last = kline_60d[-1]
    
    score = 0
    details = []
    
    # 1. RSI(14) (0-3分)
    gains = []
    losses = []
    for i in range(1, min(15, len(chgs)+1)):
        if chgs[-i] > 0:
            gains.append(chgs[-i])
        else:
            losses.append(abs(chgs[-i]))
    
    avg_gain = sum(gains) / max(len(gains), 1)
    avg_loss = sum(losses) / max(len(losses), 0.01)
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    
    rsi_score = 0
    if rsi < 25: rsi_score = 3
    elif rsi < 35: rsi_score = 2
    elif rsi < 45: rsi_score = 1
    
    score += rsi_score
    details.append(f"RSI{rsi:.0f}/{rsi_score}/3")
    
    # 2. 连跌天数 (0-3分) ← 修复：用chg判断，不是ret1
    cons_down = 0
    for c in reversed(chgs[-10:] if len(chgs) >= 10 else chgs):
        if c < 0: cons_down += 1
        else: break
    
    down_score = 0
    if cons_down >= 5: down_score = 3
    elif cons_down >= 3: down_score = 2
    elif cons_down >= 2: down_score = 1
    
    score += down_score
    details.append(f"连跌{cons_down}d/{down_score}/3")
    
    # 3. 波动率 (0-2分)
    amps = [r[7] for r in kline_60d if r[7] is not None]
    recent_amps = amps[-10:] if len(amps) >= 10 else amps
    avg_amp = sum(recent_amps) / len(recent_amps) if recent_amps else 0
    
    amp_score = 0
    if avg_amp > 5: amp_score = 2       # 活跃
    elif avg_amp > 3: amp_score = 1     # 正常
    
    score += amp_score
    details.append(f"波动{amp_score}/2({avg_amp:.1f}%)")
    
    # 4. 近3日涨速 (0-2分)
    if len(chgs) >= 3:
        recent = chgs[-3:]
        if all(c > 0 for c in recent):
            score += 2
            details.append("3连涨+2")
        elif sum(recent) > 5:
            score += 1
            details.append("涨幅>5%+1")
    
    return score, "; ".join(details)


def score_events(cur, code, kline_60d):
    """事件分析师 v2 — 增加振幅活跃度"""
    score = 0
    details = []
    
    # 1. 近期涨停/跌停 (0-2分)
    cur.execute("""
        SELECT chg FROM feat WHERE code = ? AND date >= date('now', '-20 days')
        AND chg IS NOT NULL ORDER BY date DESC
    """, (code,))
    chgs = [r[0] for r in cur.fetchall()]
    
    limit_ups = sum(1 for c in chgs if c >= 9.5)
    limit_downs = sum(1 for c in chgs if c <= -9.5)
    
    event_score = 0
    if limit_ups >= 2: event_score = 2
    elif limit_ups == 1: event_score = 1
    if limit_downs > 0: event_score = max(0, event_score - 1)  # 跌停扣分
    
    score += event_score
    det = f"{'🔥'*limit_ups}{'💥'*limit_downs}" if limit_ups or limit_downs else "平静"
    details.append(f"异动{event_score}/2 ({det})")
    
    # 2. 振幅活跃度 (0-2分) ← 新增
    if kline_60d and len(kline_60d) >= 5:
        amps = [r[7] for r in kline_60d[-5:] if r[7] is not None]
        if amps:
            avg_amp_5 = sum(amps) / len(amps)
            amp_score = 0
            if avg_amp_5 > 6: amp_score = 2
            elif avg_amp_5 > 4: amp_score = 1
            score += amp_score
            details.append(f"活跃{amp_score}/2({avg_amp_5:.1f}%)")
    
    # 3. 近3日方向 (0-2分)
    recent_chgs = chgs[:3] if len(chgs) >= 3 else chgs
    up_count = sum(1 for c in recent_chgs if c > 0)
    dir_score = 0
    if up_count >= 2: dir_score = 2
    elif up_count >= 1: dir_score = 1
    score += dir_score
    details.append(f"方向{dir_score}/2")
    
    return score, "; ".join(details)


def score_fundamentals(cur, code, name, kline_60d):
    """基本面分析师 v2 — 用价格位置和历史反弹质量评估"""
    score = 0
    details = []
    
    if not kline_60d or len(kline_60d) < 20:
        return 0, "数据不足"
    
    closes = [r[4] for r in kline_60d]
    price = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    ma20_pct = (price - ma20) / ma20 * 100
    
    # 1. 价格安全边际 (0-3分)
    # 越远离MA20(下方) = 越便宜
    if ma20_pct < -15: score += 3
    elif ma20_pct < -10: score += 2
    elif ma20_pct < -5: score += 1
    elif ma20_pct > 15: score += 0  # 太贵了
    details.append(f"价格偏{ma20_pct:.0f}%/3")
    
    # 2. S3历史质量 (0-3分)
    cur.execute("""
        SELECT COUNT(*) as cnt,
               SUM(CASE WHEN ret5 > 0 THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0) as wr5,
               AVG(ret5) as avg_r5
        FROM feat WHERE code = ? AND pos_20d < 20 AND chg >= 3 AND chg < 7 
          AND vr_5 >= 1.2 AND vr_5 < 2.5 AND ma20_pct < -8 AND ret5 IS NOT NULL
    """, (code,))
    r = cur.fetchone()
    if r and r[0] >= 2:
        cnt, wr5, avg_r5 = r[0], (r[1] or 0) * 100, r[2] or 0
        if wr5 > 70 and avg_r5 > 3: score += 3
        elif wr5 > 55: score += 2
        elif wr5 > 40: score += 1
        details.append(f"S3{r[0]}次/胜率{wr5:.0f}%/收益{avg_r5:+.1f}%/3")
    
    # 3. 下跌空间评估 (0-2分)
    # 近60日最低点
    low_60d = min(closes)
    drawdown = (price - low_60d) / low_60d * 100
    if abs(drawdown) < 5:  # 已经在底部附近
        score += 2
        details.append(f"近底{drawdown:.0f}%+2")
    
    return score, "; ".join(details) if details else "暂无数据"


def score_policy(cur, code, name):
    """政策分析师 v2 — 强化小盘加分"""
    score = 0
    details = []
    
    # 1. 题材匹配（从名称）
    keywords = {
        "科技": 1, "智能": 1, "信息": 1, "通信": 1, "数字": 1,
        "医药": 1, "生物": 1, "能源": 1, "新材": 1, "光电": 1,
        "微电": 1, "半导": 2, "芯片": 2, "航": 1, "军工": 1,
        "机器": 2, "数据": 1, "软件": 1, "互联": 1, "传媒": 1,
    }
    matched = [kw for kw in keywords if kw in name]
    for kw in matched:
        score += keywords[kw]
    if matched:
        details.append(f"题材{'+'.join(matched)}")
    
    # 2. 板块属性
    if code.startswith("30"):
        score += 1
        details.append("创业板+1")
    elif code.startswith("68"):
        score += 1
        details.append("科创板+1")
    
    # 3. 小盘加分（用成交额估算流通市值）
    if kline_60d := None:
        pass
    # 简化：用最近60日平均成交额判断大小盘
    # v2改为代码前缀+价格粗略判断
    if kline_60d and len(kline_60d) > 0:
        price = kline_60d[-1][4]
        if price < 20:
            score += 1
            details.append(f"低价{price:.0f}+1")
        if price < 10:
            score += 1
            details.append("超低价+1")
    
    return score, "; ".join(details) if details else "无题材"


def score_hot_money(kline_60d):
    """游资分析师 v2 — 更严格的量能判断"""
    if not kline_60d or len(kline_60d) < 10:
        return 0, "数据不足"
    
    volumes = [r[5] for r in kline_60d]
    chgs = [r[6] for r in kline_60d if r[6] is not None]
    
    score = 0
    details = []
    
    avg_vol = sum(volumes) / len(volumes)
    peak_vol_5 = max(volumes[-5:]) / avg_vol if avg_vol > 0 else 1
    
    # 1. 量能爆发 (0-3分)
    vol_score = 0
    if peak_vol_5 > 3: vol_score = 3
    elif peak_vol_5 > 2: vol_score = 2
    elif peak_vol_5 > 1.5: vol_score = 1
    score += vol_score
    details.append(f"量爆{vol_score}/3({peak_vol_5:.1f}x)")
    
    # 2. 连涨 (0-2分)
    last_chgs = chgs[-5:] if len(chgs) >= 5 else chgs
    cons_up = 0
    for c in reversed(last_chgs):
        if c > 0: cons_up += 1
        else: break
    
    streak_score = 0
    if cons_up >= 3: streak_score = 2
    elif cons_up == 2: streak_score = 1
    score += streak_score
    details.append(f"连涨{streak_score}/2({cons_up}d)")
    
    # 3. 振幅活跃 (0-2分)
    amps = [r[7] for r in kline_60d if r[7] is not None]
    recent_amps = amps[-5:] if len(amps) >= 5 else amps
    avg_amp = sum(recent_amps) / len(recent_amps) if recent_amps else 0
    if avg_amp > 5: score += 2;
    details.append(f"振幅{avg_amp:.1f}%/2")
    
    # 4. 缩量回调潜力 (0-1分)
    last_vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1
    if cons_up == 0 and last_vol_ratio < 0.8 and chgs and chgs[-1] < 0:
        score += 1
        details.append("缩量回调+1")
    
    return score, "; ".join(details)


def score_lockup(cur, code):
    """解禁分析师 — 中性，等数据源接入"""
    return 5, "暂无解禁(中性5分)"


def score_chanlun(kline_60d):
    """缠论分析师 v2 — 修复连跌天数bug + 底背驰加强"""
    if not kline_60d or len(kline_60d) < 20:
        return 0, "数据不足"
    
    closes = [r[4] for r in kline_60d]
    lows = [r[3] for r in kline_60d]
    highs = [r[2] for r in kline_60d]
    chgs = [r[6] for r in kline_60d if r[6] is not None]
    
    score = 0
    details = []
    
    # 1. 分型 (0-3分)
    l3_lows = lows[-3:]
    l3_highs = highs[-3:]
    
    is_bottom = (l3_lows[1] <= l3_lows[0] and l3_lows[1] <= l3_lows[2] and
                 l3_highs[1] <= l3_highs[0] and l3_highs[1] <= l3_highs[2])
    
    is_top = (l3_highs[1] >= l3_highs[0] and l3_highs[1] >= l3_highs[2] and
              l3_lows[1] >= l3_lows[0] and l3_lows[1] >= l3_lows[2])
    
    if is_bottom:
        score += 2
        details.append("底分型+2")
    elif is_top:
        # 顶分型不扣分了，只是不加
        details.append("顶分型+0")
    else:
        score += 1
        details.append("无分型+1")
    
    # 2. 底背驰 (0-3分) ← 用跌幅对比
    if len(chgs) >= 10:
        recent_down = sum(abs(c) for c in chgs[-5:] if c < 0)
        prev_down = sum(abs(c) for c in chgs[-10:-5] if c < 0)
        if prev_down > 0 and recent_down < prev_down * 0.6:
            score += 3
            details.append(f"强底背驰+3({recent_down:.1f}<{prev_down:.1f}*0.6)")
        elif prev_down > 0 and recent_down < prev_down * 0.8:
            score += 2
            details.append(f"底背驰+2({recent_down:.1f}<{prev_down:.1f}*0.8)")
        elif prev_down > 0 and recent_down <= prev_down:
            score += 1
            details.append(f"弱底背驰+1({recent_down:.1f}<={prev_down:.1f})")
        else:
            details.append("无背驰")
    
    # 3. MA20偏离 (0-2分)
    ma20 = sum(closes[-20:]) / 20
    cur_p = closes[-1]
    ma20_pct = (cur_p - ma20) / ma20 * 100
    
    if ma20_pct < -15: score += 2
    elif ma20_pct < -8: score += 1
    details.append(f"MA20偏{ma20_pct:.0f}%/2")
    
    # 4. 连跌修复 (0-2分) ← 修复：用chg序列
    cons_down = 0
    for c in reversed(chgs[-10:] if len(chgs) >= 10 else chgs):
        if c < 0: cons_down += 1
        else: break
    if cons_down >= 4: score += 2
    elif cons_down >= 2: score += 1
    if cons_down >= 2:
        details.append(f"连跌{cons_down}d/{'+2' if cons_down>=4 else '+1'}")
    
    return score, "; ".join(details)


# ============================================================
# 扫描引擎
# ============================================================

def scan_stock(code, name, kline_60d=None):
    """对单只股票执行8维度评分（v2）"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    if kline_60d is None:
        cur.execute("""
            SELECT date, open, high, low, close, volume, chg, amp, vr_5, pos_20d, ma20_pct
            FROM feat WHERE code = ? AND date >= date('now', '-90 days')
            ORDER BY date
        """, (code,))
        kline_60d = cur.fetchall()
    
    if not kline_60d or len(kline_60d) < 10:
        conn.close()
        return None
    
    scores = {}
    
    s1, d1 = score_market(kline_60d)
    scores["市场"] = (s1, d1)
    
    s2, d2 = score_sentiment(kline_60d)
    scores["情绪"] = (s2, d2)
    
    s3, d3 = score_events(cur, code, kline_60d)
    scores["事件"] = (s3, d3)
    
    s4, d4 = score_fundamentals(cur, code, name, kline_60d)
    scores["基本面"] = (s4, d4)
    
    s5, d5 = score_policy(cur, code, name)
    scores["政策"] = (s5, d5)
    
    s6, d6 = score_hot_money(kline_60d)
    scores["游资"] = (s6, d6)
    
    s7, d7 = score_lockup(cur, code)
    scores["解禁"] = (s7, d7)
    
    s8, d8 = score_chanlun(kline_60d)
    scores["缠论"] = (s8, d8)
    
    total = sum(v[0] for v in scores.values())
    
    conn.close()
    
    return {
        "code": code,
        "name": name,
        "price": kline_60d[-1][4],
        "chg": kline_60d[-1][6],
        "total": total,
        "scores": scores,
    }


# ============================================================
# 策略引擎 v2 — 更细化的阈值
# ============================================================

def get_strategy_v2(total, scores):
    """策略决策 v2 — 基于TradingAgents辩论逻辑的加权决策"""
    
    market_s = scores.get("市场", (0, ""))[0]
    sentiment_s = scores.get("情绪", (0, ""))[0]
    events_s = scores.get("事件", (0, ""))[0]
    fund_s = scores.get("基本面", (0, ""))[0]
    policy_s = scores.get("政策", (0, ""))[0]
    hm_s = scores.get("游资", (0, ""))[0]
    chanlun_s = scores.get("缠论", (0, ""))[0]
    
    # 维度加权
    weighted = (market_s * 1.5 + sentiment_s * 1.2 + 
                events_s * 1.0 + fund_s * 1.3 + 
                policy_s * 0.8 + hm_s * 1.2 + 
                chanlun_s * 1.5)
    
    reasons = []
    
    # ---- 买入判定 ----
    # 1. 主升浪追击：多维度共振
    if total >= 35 and market_s >= 5 and hm_s >= 5 and chanlun_s >= 4:
        return {
            "action": "BUY 🟢",
            "position": "30-40%",
            "hold_days": "T+10（主升浪持有）",
            "stop_loss": "-7%",
            "reason": "多维度共振，趋势+资金+缠论确认"
        }
    
    # 2. S3超跌反弹：位置低+超卖+缠论支撑
    if (chanlun_s >= 4 or market_s >= 3) and sentiment_s >= 2 and fund_s >= 2:
        if market_s >= 3:  # 位置低
            return {
                "action": "BUY 🟢",
                "position": "15-25%",
                "hold_days": "T+5（超跌反弹）",
                "stop_loss": "-5%",
                "reason": "超卖区域+缠论底部结构+位置够低"
            }
    
    # 3. 题材潜伏：政策+基本面+位置
    if policy_s >= 3 and total >= 28 and market_s >= 2:
        return {
            "action": "BUY 🟡",
            "position": "10-15%",
            "hold_days": "T+10~T+20（题材潜伏）",
            "stop_loss": "-7%",
            "reason": "政策支撑+位置偏低+基本面安全边际"
        }
    
    # ---- 中性判定 ----
    if total >= 26:
        return {
            "action": "HOLD ⚪",
            "position": "持有不变",
            "hold_days": "观察",
            "stop_loss": "已有止损不变",
            "reason": "评分中性，不操作等待方向"
        }
    
    # ---- 卖出判定 ----
    if total >= 20:
        return {
            "action": "REDUCE ⚠️",
            "position": "减至30%",
            "hold_days": "反弹减仓",
            "stop_loss": "MA20清仓",
            "reason": "多项维度偏弱，控制风险"
        }
    
    return {
        "action": "SELL 🔴",
        "position": "清仓",
        "hold_days": "不参与",
        "stop_loss": "触及即走",
        "reason": "多个维度全面弱势，不参与"
    }


# ============================================================
# 主入口
# ============================================================

def scan_top_n(top_n=15, use_v1=False):
    """全市场扫描"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # 获取最新的200只候选（用伏笔活跃股）
    cur.execute("""
        SELECT f.code, s.name
        FROM feat f JOIN stocks s ON f.code = s.code
        WHERE f.date = (SELECT MAX(date) FROM feat)
          AND f.code NOT LIKE '688%' AND s.name NOT LIKE '%ST%'
          AND f.vr_5 IS NOT NULL
        ORDER BY f.vr_5 DESC
        LIMIT 300
    """)
    candidates = cur.fetchall()
    conn.close()
    
    print(f"\n扫描{len(candidates)}只活跃股...")
    
    results = []
    for code, name in candidates:
        r = scan_stock(code, name)
        if r:
            results.append(r)
    
    results.sort(key=lambda x: -x["total"])
    
    # TOP N展示
    print(f"\n{'='*85}")
    print(f"  🏆 8维度量化选股 v2 — TOP {min(top_n, len(results))}")
    print(f"{'='*85}")
    print(f"{'#':>3} {'代码':>6} {'名称':<10} {'总分':>4} {'市':>3} {'情':>3} {'事':>3} {'基':>3} {'政':>3} {'游':>3} {'解':>3} {'缠':>3} 策略")
    print(f"  {'─'*75}")
    
    dims = ["市场", "情绪", "事件", "基本面", "政策", "游资", "解禁", "缠论"]
    
    for i, r in enumerate(results[:top_n]):
        st = get_strategy_v2(r["total"], r["scores"])
        dim_vals = [r["scores"].get(d, (0,""))[0] for d in dims]
        print(f"  {i+1:>3} {r['code']:>6} {r['name']:<10} {r['total']:>4}/80 "
              f"{' '.join(f'{v:>3}' for v in dim_vals)}  {st['action']} {st['position']}")
    
    # 详情
    print(f"\n{'='*85}")
    print(f"  📋 策略详情")
    print(f"{'='*85}")
    
    for i, r in enumerate(results[:top_n]):
        st = get_strategy_v2(r["total"], r["scores"])
        print(f"\n  {i+1}. {r['code']} {r['name']} ({r['total']}/80)")
        print(f"     操作: {st['action']} | {st['position']} | {st['hold_days']} | 止损{st['stop_loss']}")
        print(f"     理由: {st['reason']}")
        for d in dims:
            v, det = r["scores"].get(d, (0, ""))
            bar = "█" * v + "░" * (10 - v)
            print(f"    {d}: {bar} {v}/10 {det}")
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--holdings":
        holdings = [
            ("301231", "荣信文化", 34.62),
            ("300608", "思特奇", None),
            ("605128", "上海沿浦", None),
        ]
        
        print(f"{'='*60}")
        print(f"  持仓分析 v2")
        print(f"{'='*60}")
        
        for code, name, cost in holdings:
            r = scan_stock(code, name)
            if not r:
                print(f"\n  {code} {name}: 数据不足")
                continue
            st = get_strategy_v2(r["total"], r["scores"])
            pnl = f"{(r['price']-cost)/cost*100:+.1f}%" if cost else "N/A"
            
            print(f"\n  ▶ {code} {name} ({pnl})")
            print(f"    总分: {r['total']}/80 → {st['action']} {st['position']}")
            print(f"    理由: {st['reason']}")
            
            dims = ["市场", "情绪", "事件", "基本面", "政策", "游资", "解禁", "缠论"]
            for d in dims:
                v, det = r["scores"].get(d, (0, ""))
                bar = "█" * v + "░" * (10 - v)
                print(f"    {d}: {bar} {v}/10 {det}")
    else:
        scan_top_n(15)
