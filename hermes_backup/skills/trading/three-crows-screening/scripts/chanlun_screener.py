#!/usr/bin/env python3
"""
缠论选股器 — 从缠论108课中提取的量化选股策略

策略列表:
  1. 底分型+底背驰选股 (第一类买点基础版)
  2. 关键K线突破选股 (第79课：分型辅助操作)
  3. 简化三买选股 (中枢突破+回抽不破ZG)
  4. 分型强弱+三阴确认 (和三阴选股联动)

所有策略从 SQLite 数据库读取K线，不拉在线接口。
数据库由 astock-daily-sync skill 维护。

用法:
    cd /home/harrydolly/code/TradingAgents-astock
    source .venv/bin/activate

    # 全市场扫描底分型+底背驰
    python3 chanlun_screener.py --strategy di_fenxing_beichi --all

    # 扫描三买（全市场）
    python3 chanlun_screener.py --strategy san_mai --all

    # 单只股票分析所有策略
    python3 chanlun_screener.py --stock 002575

    # 指定日期
    python3 chanlun_screener.py --strategy san_mai --all --date 2026-06-05
"""

import sys
import os
import argparse
import numpy as np
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

import sqlite3
import pandas as pd

from tradingagents.dataflows.astock_db import (
    DB_PATH,
    get_stock_list,
    get_klines,
    get_db_stats,
    save_scan_result,
)


# ============================================================
# 工具函数
# ============================================================

def read_klines(code, lookback_days=90):
    """从数据库读取K线，估算成交额"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT MAX(date) FROM daily_klines")
    latest = c.fetchone()
    if not latest or not latest[0]:
        conn.close()
        return None, None
    end_date = latest[0]
    start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=lookback_days)
    start_date = start_dt.strftime("%Y-%m-%d")
    
    c.execute("""SELECT date, open, high, low, close, volume, amount 
                 FROM daily_klines WHERE code = ? AND date >= ? AND date <= ?
                 ORDER BY date""", (code, start_date, end_date))
    rows = c.fetchall()
    conn.close()
    
    if not rows or len(rows) < 20:
        return None, None
    
    df = pd.DataFrame(rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Amount'])
    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount']:
        df[col] = df[col].astype(float)
    
    # 估算成交额
    if df['Amount'].sum() == 0:
        df['Amount'] = df['Volume'] * 100 * (df['Open'] + df['Close']) / 2
    
    return df, end_date


def get_stock_name(code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM stocks WHERE code = ?", (code,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else code


def calc_macd(df, fast=12, slow=26, signal=9):
    """计算MACD指标"""
    close = df['Close'].values.astype(float)
    ema_fast = pd.Series(close).ewm(span=fast).mean().values
    ema_slow = pd.Series(close).ewm(span=slow).mean().values
    dif = ema_fast - ema_slow
    dea = pd.Series(dif).ewm(span=signal).mean().values
    macd = 2 * (dif - dea)
    return dif, dea, macd


def is_valid_ticker(code, name=""):
    """同三阴选股排除规则"""
    code = code.strip()
    if not code or not code.isdigit() or len(code) != 6:
        return False
    if code[0] == '4':
        return False
    if code.startswith('83') or code.startswith('87'):
        return False
    if code.startswith('688'):
        return False
    if name and ('ST' in name or '*ST' in name):
        return False
    return True


# ============================================================
# 策略1: 底分型 + MACD底背驰
# ============================================================

def check_fenxing(high, low, i):
    """检查第i根K线是否为分型
    
    顶分型: i-1, i, i+1 三根K线
    - 顶分型: high[i]是最高, low[i]不是最低（或者也是最高）
    - 底分型: low[i]是最低, high[i]不是最高
    """
    if i < 1 or i >= len(high) - 1:
        return None
    
    h1, h2, h3 = high[i-1], high[i], high[i+1]
    l1, l2, l3 = low[i-1], low[i], low[i+1]
    
    # 顶分型：中间最高
    if h2 > h1 and h2 > h3 and l2 > l1 and l2 > l3:
        return 'top'
    # 底分型：中间最低
    if l2 < l1 and l2 < l3 and h2 < h1 and h2 < h3:
        return 'bottom'
    return None


def check_beichi(df, lookback=30):
    """检查最后几根K线是否有底背驰
    
    条件:
    1. 最近出现底分型
    2. MACD绿柱面积比前一次缩小
    3. DIF不创新低（或明显回升）
    """
    if df is None or len(df) < lookback:
        return False, []
    
    close = df['Close'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    
    dif, dea, macd = calc_macd(df)
    
    reasons = []
    n = len(df)
    
    # 1. 检查最近5根K线是否有底分型
    fenxing_found = False
    fenxing_idx = -1
    for i in range(n - 3, n):
        result = check_fenxing(high, low, i)
        if result == 'bottom':
            fenxing_found = True
            fenxing_idx = i
            reasons.append(f"底分型在第{fenxing_idx}根K线")
            break
    
    if not fenxing_found:
        return False, ["无底分型"]
    
    # 2. 找前后两段下跌的MACD绿柱面积
    # 从底分型往前找两个明显的MACD低点
    macd_vals = macd[:n]  # 全量
    
    # 找最近一段MACD在0以下的区域（底分型前的下跌段）
    seg_start = max(0, fenxing_idx - 20)
    
    # 计算最近一段的绿柱面积
    recent_negative = macd_vals[seg_start:fenxing_idx+1]
    recent_area = abs(sum(recent_negative[recent_negative < 0]))
    
    # 找前一段（更早的下跌段）
    prev_start = max(0, seg_start - 30)
    prev_seg = macd_vals[prev_start:seg_start]
    prev_area = abs(sum(prev_seg[prev_seg < 0])) if len(prev_seg) > 5 else 0
    
    # 3. 判断是否背驰：后一段绿柱面积 < 前一段
    if prev_area > 0 and recent_area > 0:
        area_ratio = recent_area / prev_area
        reasons.append(f"MACD绿柱面积: 后段{recent_area:.0f} / 前段{prev_area:.0f} = {area_ratio:.2f}")
        
        if area_ratio < 0.9:
            # 检查DIF是否也在回升
            dif_recent = dif[seg_start:fenxing_idx+1]
            dif_prev = dif[prev_start:seg_start]
            
            dif_new_low = dif_recent.min() < dif_prev.min() - 0.1
            if not dif_new_low:
                reasons.append(f"DIF未创新低 ✓")
                return True, reasons
            else:
                reasons.append(f"DIF创新低，但面积缩小，属弱势背驰")
                return True, reasons
    
    return False, reasons


def check_guanjian_kline(df):
    """第79课：关键K线分型突破选股
    
    条件:
    1. 最近出现底分型
    2. 底分型第三根K线（确认K线）的收盘 > 第一根K线的最高
    → 强底分型，大概率成笔
    """
    if df is None or len(df) < 20:
        return False, []
    
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    close = df['Close'].values.astype(float)
    open_ = df['Open'].values.astype(float)
    reasons = []
    n = len(df)
    
    # 找最近的底分型
    for i in range(n - 3, n):
        result = check_fenxing(high, low, i)
        if result == 'bottom':
            # 检查第三根K线是否站上第一根最高
            if close[i+1] > high[i-1]:
                # 强底分型
                reasons.append(f"强底分型: C3({close[i+1]:.2f}) > H1({high[i-1]:.2f})")
                
                # 进一步：检查是否站上5日均线
                ma5 = pd.Series(close).rolling(5).mean().values
                if close[i+1] > ma5[i+1]:
                    reasons.append(f"站上MA5({ma5[i+1]:.2f})")
                
                # 检查成交量是否放大
                vol = df['Volume'].values.astype(float)
                vol_ma5 = pd.Series(vol).rolling(5).mean().values
                if vol[i+1] > vol_ma5[i+1] * 1.5:
                    reasons.append(f"成交量放大{vol[i+1]/vol_ma5[i+1]:.1f}倍")
                
                return True, reasons
    
    return False, ["无关键底分型"]


# ============================================================
# 策略4: 线段逆驰（素论独创概念）
# ============================================================

def check_nichi(df):
    """线段逆驰 — 基于素论的逆驰概念
    
    素论核心思想：走势结构运行到"契合状态"后，反向动力产生。
    相比传统背驰，逆驰更强调：
    
    **线段逆驰（短线反转信号）**
    特征：
    - 下降逆驰（下跌→上涨）：
      ① 次级别线段上升角度≥45度
      ② 连续阳线冲击
      ③ 成交量放大
      ④ MACD红柱异常放大，高度/面积超过段内其他上攻
    
    - 上升逆驰（上涨→下跌）：
      ① 次级别下跌角度≥50度
      ② 突如其来的大阴线（甚至跌停）
      ③ 成交量过分放大
      ④ MACD强势背驰
    
    **中枢逆驰（趋势反转信号）**
    特征：
    - 背驰段后向相反方向逐步搭建同级别中枢
    - 原线段运行趋势明显被削弱
    
    **三种动能验证**：
    1. 运行动能—MACD面积对比
    2. 空间势能—距离中枢的位置+反向角度
    3. 成区势能—成本集中度（需更多数据）
    
    **短线安全条件**（来自素论）：
    - 处于5F向上走势类型中或相应级别的逆驰阶段
    - 背驰段不宜短线建仓（防止系统性风险）
    - 涨停板上少于3只股票（ST除外）不开仓
    
    日线级别实现：
    1. 检测最近是否有底分型（反转信号起点）
    2. 检查MACD是否出现"红柱异常放大"（下降逆驰特征）
    3. 检查成交量是否明显放大
    4. 检查下跌角度是否≥45度（次级别）
    """
    if df is None or len(df) < 30:
        return False, []
    
    close = df['Close'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    vol = df['Volume'].values.astype(float)
    dif, dea, macd = calc_macd(df)
    reasons = []
    n = len(df)
    
    # 1. 检查最近5根K线是否有底分型
    fenxing_idx = -1
    for i in range(n - 3, n):
        result = check_fenxing(high, low, i)
        if result == 'bottom':
            fenxing_idx = i
            break
    
    if fenxing_idx < 0:
        # 放宽：看最后一天是否收阳且靠近10日低点
        if close[-1] > close[-2] and min(low[-10:]) >= min(low[-30:-10]).min() * 0.98:
            reasons.append("未发现标准底分型，但有低位反弹迹象")
        else:
            return False, ["无底分型或反转信号"]
    
    if fenxing_idx >= 0:
        reasons.append(f"底分型在第{fenxing_idx}根K线")
    
    # 2. 下降逆驰特征①：MACD红柱异常放大
    # 找最近一段MACD由负转正区域（红柱面积）
    macd_vals = macd[:n]
    
    # 从底分型往前看最近一段MACD在0以下的区域
    start = max(0, n - 15)
    recent_positive = macd_vals[start:]
    recent_pos_area = sum(recent_positive[recent_positive > 0])
    
    # 前一段（更早的）红柱区域
    prev_start = max(0, start - 20)
    prev_positive = macd_vals[prev_start:start]
    prev_pos_area = sum(prev_positive[prev_positive > 0]) if len(prev_positive) > 5 else 0
    
    # 用MACD来衡量下跌段的强度——找最近一段下跌段的MACD绿柱面积
    recent_negative = macd_vals[start:min(n, fenxing_idx+2)]
    recent_neg_area = abs(sum(recent_negative[recent_negative < 0]))
    
    prev_negative = macd_vals[prev_start:start]
    prev_neg_area = abs(sum(prev_negative[prev_negative < 0])) if len(prev_negative) > 5 else 1
    
    # 下降逆驰特征③：成交量放大
    vol_ma5 = pd.Series(vol).rolling(5).mean().values
    vol_ma20 = pd.Series(vol).rolling(20).mean().values
    recent_vol = vol[-5:].mean() if n >= 5 else vol[-1]
    vol_ratio = recent_vol / vol_ma20[-1] if vol_ma20[-1] > 0 else 1
    
    # 判断条件
    nichi_score = 0
    
    # 条件A：MACD绿柱面积缩小（传统背驰特征）
    if prev_neg_area > 0 and recent_neg_area > 0:
        area_ratio = recent_neg_area / prev_neg_area
        if area_ratio < 0.85:
            nichi_score += 2
            reasons.append(f"✅ MACD绿柱缩小: {recent_neg_area:.0f}/{prev_neg_area:.0f} = {area_ratio:.2f}（背驰）")
        elif area_ratio < 1.0:
            nichi_score += 1
            reasons.append(f"△ 绿柱略缩小: {area_ratio:.2f}")
    
    # 条件B：最后几天红柱出现（下跌段末端出现红柱=可能反转）
    if recent_pos_area > 0:
        if recent_pos_area > prev_pos_area and prev_pos_area > 0:
            nichi_score += 2
            reasons.append(f"✅ 红柱面积放大: {recent_pos_area:.0f}（逆驰动能增强）")
        elif recent_pos_area > 0:
            nichi_score += 1
            reasons.append(f"△ 红柱出现: {recent_pos_area:.0f}")
    
    # 条件C：最后一天收阳
    if close[-1] > close[-2]:
        nichi_score += 1
        reasons.append("✅ 最后一天收阳")
    
    # 条件D：成交量放大
    if vol_ratio > 1.5:
        nichi_score += 1
        reasons.append(f"✅ 成交量放大{vol_ratio:.1f}倍（逆驰特征）")
    elif vol_ratio > 1.2:
        nichi_score += 0.5
        reasons.append(f"△ 量比{vol_ratio:.1f}")
    
    # 条件E：价格角度——检查最近下跌段是否陡峭
    if fenxing_idx >= 0:
        drop_start = max(0, fenxing_idx - 10)
        drop_high = max(high[drop_start:fenxing_idx+1])
        drop_low = min(low[drop_start:fenxing_idx+1])
        drop_range = (drop_high - drop_low) / drop_low * 100
        
        if drop_range > 15:
            # 下跌角度陡
            nichi_score += 1
            reasons.append(f"✅ 下跌段幅度{drop_range:.1f}% ≥15%，角度大（逆驰势能足）")
    
    # 条件F：空间势能——距离上一个中枢的距离
    zones = find_zones(df, min_zone_days=8, max_zone_pct=25)
    if zones:
        last_zone = zones[-1]
        dist_from_zone = (close[-1] - last_zone['zg']) / last_zone['zg'] * 100
        if dist_from_zone > -8 and dist_from_zone < 0:
            nichi_score += 1
            reasons.append(f"✅ 当前价在ZG({last_zone['zg']:.2f})附近，空间势能足")
    
    # 综合评分
    reasons.append(f"   逆驰评分: {nichi_score}/8")
    
    if nichi_score >= 4:
        reasons.append("✅ 逆驰成立！符合素论反转条件")
        return True, reasons
    elif nichi_score >= 3:
        reasons.append("⚠️ 弱逆驰信号，需次级别确认")
        return True, reasons
    
    return False, reasons


# ============================================================
# 策略2: 简化三买选股
# ============================================================

def find_zones(df, min_zone_days=8, max_zone_pct=25):
    """从K线数据中寻找中枢（价格密集区）
    
    基于缠师原意：中枢=三段次级别走势重叠区域
    简化：找价格来回震荡最密集的区域
    """
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    close = df['Close'].values.astype(float)
    n = len(df)
    
    zones = []
    i = max(0, n - 60)  # 只看最近60天
    while i < n - min_zone_days:
        segment_high = max(high[i:i+min_zone_days])
        segment_low = min(low[i:i+min_zone_days])
        segment_range = (segment_high - segment_low) / segment_low * 100
        
        if segment_range < max_zone_pct:
            # 这段是"疑似中枢"
            zones.append({
                'start': i,
                'end': i + min_zone_days,
                'zg': segment_high,
                'zd': segment_low,
                'range_pct': segment_range,
            })
            i += min_zone_days  # 跳到下一段
        else:
            i += 1
    
    return zones


def check_san_mai_v2(df):
    """第三类买点识别（改进版v2，基于缠师原文+宁波帮实战案例）
    
    缠师原文要点（来自原文+宁波帮摘录）：
    1. "第三类买点，一定要在第一个中枢后效果最好"
    2. "日线的第三类买点 = 看一个30分钟的回抽"
    3. "第三类买点的结束位置不一定是整个回拉的最低位置"
    4. "一旦出现向上的盘整背驰一定要出来"
    5. "对小级别的第三类买卖点就足以值得介入"
       （例如对周线中枢的突破，等周线的第三类买点太晚，
        用一个次级别已经足以介入）
    6. "第三类买点后一定继续向上"
    7. "中枢震荡的操作是向上盘整背驰抛，向下盘整背驰回补"
    
    第54课实战案例：
    - 缠师用1分钟图实时分析买卖点
    - 中枢形成后，第三类卖点出现→继续向下
    - 第三类买点后一定向上
    
    日线级别实现：
    1. 找最近形成的价格中枢（密集区）
    2. 确认突破（放量/涨停加速）
    3. 确认当前处于回抽阶段
    4. 回抽不破中枢上沿（ZG）
    """
    if df is None or len(df) < 30:
        return False, []
    
    close = df['Close'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    vol = df['Volume'].values.astype(float)
    open_ = df['Open'].values.astype(float)
    dif, dea, macd = calc_macd(df)
    reasons = []
    n = len(df)
    
    # 1. 找中枢
    zones = find_zones(df, min_zone_days=8, max_zone_pct=25)
    
    if not zones:
        reasons.append("未发现价格中枢（密集区）")
        # fallback: 用价格波动率最小的区域
        vola = pd.Series(high - low).rolling(10).std().values
        min_vola_idx = np.argmin(vola[-30:]) if len(vola) > 30 else 0
        min_vola_idx = n - 30 + min_vola_idx
        zg = max(high[min_vola_idx:min_vola_idx+10])
        zd = min(low[min_vola_idx:min_vola_idx+10])
        reasons.append(f"用最低波动区作为近似中枢 [{zd:.2f}, {zg:.2f}]")
    else:
        # 取最近的中枢（在最后20根K线之前形成的）
        valid_zones = [z for z in zones if z['end'] < n - 3]
        if not valid_zones:
            valid_zones = zones
        zone = valid_zones[-1]
        zg, zd = zone['zg'], zone['zd']
        reasons.append(f"中枢区间 [{zd:.2f}, {zg:.2f}] 幅度{zone['range_pct']:.1f}%")
    
    zone_high, zone_low = zg, zd
    zone_range = (zone_high - zone_low) / zone_low * 100
    
    if zone_range > 30:
        reasons.append(f"中枢幅度{zone_range:.1f}%偏大，可能不是有效中枢")
    
    # 2. 确认突破——找最后一次明显突破中枢上沿的位置
    recent_high = max(high[n-20:]) if n >= 20 else max(high)
    recent_high_idx = np.argmax(high[-20:]) + max(0, n-20) if n >= 20 else np.argmax(high)
    
    if recent_high <= zone_high * 1.01:
        reasons.append(f"未突破中枢（最高{recent_high:.2f} <= ZG{zone_high:.2f}）")
        return False, reasons
    
    # 计算突破力度
    breakout_vol = vol[recent_high_idx]
    vol_ma20 = pd.Series(vol).rolling(20).mean().values[-1]
    vol_ratio = breakout_vol / vol_ma20 if vol_ma20 > 0 else 1
    
    # 判断是否为第一个中枢（缠师：第一个中枢后三买效果最好）
    # 往前看：如果在这之前也有明显的中枢，说明这不是第一个
    earlier_zones = [z for z in zones if z['end'] < zone_low and z['range_pct'] < zone_range * 1.2]
    if len(earlier_zones) == 0:
        reasons.append("✅ 第一个中枢！三买效果最佳")
    else:
        reasons.append(f"⚠️ 第{len(earlier_zones)+1}个中枢之后（前面还有{len(earlier_zones)}个）")
    
    # 突破时放量
    reasons.append(f"突破: H={recent_high:.2f} > ZG={zone_high:.2f} 量比{vol_ratio:.1f}倍")
    
    # 3. 判断当前是否处于回抽
    idx_since_breakout = recent_high_idx
    high_after = max(high[idx_since_breakout:])
    low_after = min(low[idx_since_breakout:])
    cur_close = close[-1]
    
    # 从最高点到现在的回撤幅度
    pullback = (high_after - cur_close) / high_after * 100 if high_after > 0 else 0
    
    if pullback < 2:
        reasons.append(f"刚突破，未回抽（回撤{pullback:.1f}%）")
        return False, reasons
    
    if pullback > 20:
        reasons.append(f"回抽过深{pullback:.1f}%，可能已破位")
        return False, reasons
    
    reasons.append(f"正在回抽: 从{high_after:.2f}回撤{pullback:.1f}%")
    
    # 4. 确认三买：回抽不破中枢上沿
    # 缠师原话："只回抽不破日线中枢就可以"
    # 和"第三类买点的结束位置不一定是整个回拉的最低位置"
    if cur_close > zone_high:
        reasons.append(f"✅ 三买活跃！当前价{cur_close:.2f} > ZG{zone_high:.2f}")
        reasons.append("   回抽未破中枢，等待次级别背驰确认买点")
        return True, reasons
    elif low_after > zone_high * 0.99:
        reasons.append(f"✅ 三买成立！回抽最低{low_after:.2f} ≈ ZG{zone_high:.2f}")
        return True, reasons
    else:
        reasons.append(f"回抽已进入中枢（最低{low_after:.2f} < ZG{zone_high:.2f}），等待确认")
        # 还是有可能在延伸中，但不放行
        
    return False, reasons


# ============================================================
# 扫描引擎
# ============================================================

ALL_STRATEGIES = {
    'di_fenxing_beichi': {
        'name': '底分型+底背驰',
        'desc': '第一类买点基础版',
        'func': check_beichi,
    },
    'guanjian_kline': {
        'name': '关键K线突破',
        'desc': '第79课强底分型突破',
        'func': check_guanjian_kline,
    },
    'san_mai': {
        'name': '第三类买点(v2)',
        'desc': '中枢突破+回抽不破ZG（基于缠师原文）',
        'func': check_san_mai_v2,
    },
    'nichi': {
        'name': '线段逆驰',
        'desc': '素论逆驰—MACD红柱放大+放量+底分型',
        'func': check_nichi,
    },
}


def scan_all(strategy_name='di_fenxing_beichi', max_stocks=None, verbose=True):
    """全市场扫描指定策略"""
    strategy = ALL_STRATEGIES.get(strategy_name)
    if not strategy:
        print(f"❌ 未知策略: {strategy_name}")
        print(f"   可用策略: {', '.join(ALL_STRATEGIES.keys())}")
        return []
    
    stocks = get_stock_list()
    if max_stocks:
        stocks = stocks[:max_stocks]
    
    hits = []
    total = len(stocks)
    
    print(f"📡 缠论选股 — {strategy['name']}（{strategy['desc']}）")
    print(f"   候选池: {total}只股票")
    print(f"   数据来源: SQLite数据库\n")
    
    start_time = datetime.now()
    scanned = 0
    
    for i, (code, name) in enumerate(stocks, 1):
        if not is_valid_ticker(code, name or ""):
            continue
        
        scanned += 1
        if verbose and (i % 300 == 0):
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"   进度: {i}/{total} | 已扫{scanned}只 | 命中{len(hits)}只 | {elapsed:.0f}s")
        
        try:
            df, _ = read_klines(code)
            if df is None or len(df) < 30:
                continue
            
            hit, reasons = strategy['func'](df)
            if hit:
                cur = float(df['Close'].values[-1])
                chg = ((cur / float(df['Close'].values[-2])) - 1) * 100
                hits.append({
                    'code': code,
                    'name': name,
                    'price': cur,
                    'chg_today': chg,
                    'reasons': reasons,
                })
                if verbose:
                    print(f"  ✅ {name}({code}) 价{cur:.2f} 当日{chg:+.2f}%")
                    for r in reasons:
                        print(f"     {r}")
                        
        except Exception as e:
            if verbose:
                pass
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print(f"\n{'='*60}")
    print(f"  扫描完成: {strategy['name']}")
    print(f"  候选池: {total}")
    print(f"  有效扫描: {scanned}")
    print(f"  命中: {len(hits)}")
    print(f"  耗时: {elapsed:.1f}s")
    
    for h in hits:
        print(f"  {h['name']}({h['code']}) 价{h['price']:.2f}")
    
    return hits


def analyze_stock(code):
    """单只股票分析所有策略"""
    name = get_stock_name(code)
    df, end_date = read_klines(code)
    
    if df is None:
        print(f"❌ {name}({code}): 数据不足")
        return
    
    cur = float(df['Close'].values[-1])
    chg = ((cur / float(df['Close'].values[-2])) - 1) * 100
    
    print(f"\n{'='*60}")
    print(f"  缠论选股分析: {name}({code})")
    print(f"  最新日期: {end_date} | 价格: {cur:.2f} | 当日: {chg:+.2f}%")
    print(f"  数据: {len(df)}根K线")
    print(f"{'='*60}\n")
    
    for key, strategy in ALL_STRATEGIES.items():
        hit, reasons = strategy['func'](df)
        icon = "✅" if hit else "❌"
        print(f"  {icon} {strategy['name']} ({strategy['desc']})")
        for r in reasons:
            print(f"     {r}")
        print()


def main():
    parser = argparse.ArgumentParser(description="缠论选股器")
    parser.add_argument("--strategy", default=None, 
                        help=f"策略: {', '.join(ALL_STRATEGIES.keys())}")
    parser.add_argument("--all", action="store_true", help="全市场扫描")
    parser.add_argument("--stock", default=None, help="单只股票分析")
    parser.add_argument("--max", type=int, default=None, help="最多扫多少只")
    parser.add_argument("--list", action="store_true", help="列出所有策略")
    args = parser.parse_args()
    
    if args.list:
        print("可用策略:")
        for key, s in ALL_STRATEGIES.items():
            print(f"  {key}: {s['name']} — {s['desc']}")
        return
    
    if args.stock:
        analyze_stock(args.stock)
        return
    
    if args.strategy:
        scan_all(args.strategy, max_stocks=args.max)
        return
    
    # 默认：如果没有参数，显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
