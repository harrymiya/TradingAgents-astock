#!/usr/bin/env python3
"""
三阴选股核心算法 - 通达信三阴选股公式严格Python实现

原通达信公式:
```
去ST原:=IF(NAMELIKE('ST'),0,1);
去星原:=IF(NAMELIKE('*ST'),0,1);
去新三板原:=NOT(CODELIKE('4'));
去北交所原:=NOT(CODELIKE('83'));
去北交所1原:=NOT(CODELIKE('87'));
去科创板原:=NOT(CODELIKE('688'));
去除次新股:=FINANCE(42)>180;
去票原:= 去ST原 AND 去星原 AND 去新三板原 AND 去北交所原 AND 去北交所1原 AND 去科创板原 AND 去除次新股;

跳空加跌停:=NOT(COUNT(H<REF(L, 1), 4) > 0 AND COUNT(C/REF(C, 1) <= 0.9, 3) >= 1);

XG:去票原 AND 跳空加跌停 AND
REF((REF(C,1)*1.1-C)<0.01,3)
AND REF(AMO,2)>REF(AMO,3)
AND REF(AMO,1)<REF(AMO,2)
AND REF(AMO,0)<REF(AMO,1)
AND C>REF(O,3)
AND OPEN>REF(LOW,3)
AND (CLOSE-REF(CLOSE,1))/REF(CLOSE,1)<0;
```

用法:
    from three_crows import three_black_crows_screen, scan_stock_pool
"""

import pandas as pd
import numpy as np
from io import StringIO


def three_black_crows_screen(df: pd.DataFrame, stock_name: str = "", trade_date_index: int = -1) -> bool:
    """
    严格按通达信原公式逐行翻译的Python实现。
    
    参数:
        df: DataFrame 必须包含列: Date, Open, High, Low, Close, Volume
        stock_name: 股票名称（用于排除ST/*ST）
        trade_date_index: 指定哪一天为T（最后一天），默认-1（最后一行）
    
    返回:
        bool: True=命中选股条件
    """
    if df is None or len(df) < 10:
        return False

    close = df['Close'].values.astype(float)
    open_ = df['Open'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)

    # 成交额（AMO）: 通达信AMO=成交额(元)
    if 'Amount' in df.columns:
        amo = df['Amount'].values.astype(float)
    else:
        # Volume是手数(1手=100股)，用(Open+Close)/2估算均价
        # 成交额(元) = 股数 * 均价 = (Volume*100) * (Open+Close)/2
        amo = (df['Volume'].values.astype(float) * 100) * (
            (df['Open'].values.astype(float) + df['Close'].values.astype(float)) / 2
        )

    # 用trade_date_index定位T
    if trade_date_index < 0:
        t = len(df) + trade_date_index
    else:
        t = trade_date_index

    if t < 5:
        return False

    # === T及之前各日的索引 ===
    # T  = t
    # T-1 = t-1
    # T-2 = t-2
    # T-3 = t-3
    # T-4 = t-4

    c0 = close[t];   o0 = open_[t];   h0 = high[t];   l0 = low[t];   a0 = amo[t]
    c1 = close[t-1]; o1 = open_[t-1]; h1 = high[t-1]; l1 = low[t-1]; a1 = amo[t-1]
    c2 = close[t-2]; o2 = open_[t-2]; h2 = high[t-2]; l2 = low[t-2]; a2 = amo[t-2]
    c3 = close[t-3]; o3 = open_[t-3]; h3 = high[t-3]; l3 = low[t-3]; a3 = amo[t-3]
    c4 = close[t-4]; o4 = open_[t-4]; h4 = high[t-4]; l4 = low[t-4]; a4 = amo[t-4]

    # =========================================================
    # 条件组1: 排除规则（在调用方已实现is_valid_ticker，这里也做）
    # 注意：FINANCE(42)在通达信中=上市天数
    # 我们通过传入stock_name检查ST，但次新股检查需外部提供上市天数
    # =========================================================
    cond_no_st = not ('ST' in (stock_name or '') or '*ST' in (stock_name or ''))

    # =========================================================
    # 条件: 跳空加跌停
    # 原公式: 跳空加跌停:=NOT(COUNT(H<REF(L, 1), 4) > 0 AND COUNT(C/REF(C, 1) <= 0.9, 3) >= 1);
    #
    # COUNT(H<REF(L, 1), 4) > 0
    #   → 最近4天(从T-3到T)中，有几天出现 H < 前日L (跳空低开且全天不回补)
    #
    # COUNT(C/REF(C, 1) <= 0.9, 3) >= 1
    #   → 最近3天(从T-2到T)中，有几天出现 C/REF(C,1) <= 0.9 (跌停)
    #
    # 只有当 跳空>0天 AND 跌停>=1天 同时满足时，NOT取反排除
    # =========================================================
    jump_days = 0
    for i in range(4):  # 检查T-3, T-2, T-1, T 共4天
        idx = t - i
        if idx > 0:
            if high[idx] < low[idx - 1]:
                jump_days += 1

    down_days = 0
    for i in range(3):  # 检查T-2, T-1, T 共3天
        idx = t - i
        if idx > 0 and close[idx - 1] > 0:
            if close[idx] / close[idx - 1] <= 0.9:
                down_days += 1

    cond_no_jump = not (jump_days > 0 and down_days >= 1)

    # =========================================================
    # REF((REF(C,1)*1.1-C)<0.01, 3)
    # 在T-3这天：前日收盘(REF(C,1) at T-3) = close[T-4], 除权价处理
    # 涨停价 = round(c4 * 1.1, 2)
    # 条件：涨停价 - c3 < 0.01
    # =========================================================
    limit_price = round(c4 * 1.1, 2)
    cond_zhangting = (limit_price - c3) < 0.01

    # =========================================================
    # 量能递减:
    # REF(AMO,2) > REF(AMO,3)  → amo[T-2] > amo[T-3]
    # REF(AMO,1) < REF(AMO,2)  → amo[T-1] < amo[T-2]
    # REF(AMO,0) < REF(AMO,1)  → amo[T]   < amo[T-1]
    # =========================================================
    cond_vol1 = a2 > a3
    cond_vol2 = a1 < a2
    cond_vol3 = a0 < a1

    # =========================================================
    # C > REF(O, 3)  → close[T] > open[T-3]
    # =========================================================
    cond_c_gt_o3 = c0 > o3

    # =========================================================
    # OPEN > REF(LOW, 3)  → open[T] > low[T-3]
    # =========================================================
    cond_o_gt_l3 = o0 > l3

    # =========================================================
    # (CLOSE-REF(CLOSE,1))/REF(CLOSE,1) < 0
    # 今日收阴：(c0 - c1) / c1 < 0
    # =========================================================
    cond_yin = ((c0 - c1) / c1) < 0 if c1 != 0 else False

    all_conditions = [
        cond_no_st,
        cond_no_jump,
        cond_zhangting,
        cond_vol1,
        cond_vol2,
        cond_vol3,
        cond_c_gt_o3,
        cond_o_gt_l3,
        cond_yin,
    ]

    return all(all_conditions)


def is_valid_ticker(code: str, name: str = "") -> bool:
    """
    排除规则（对应通达信）：
    - ST / *ST  (通过name检查)
    - 4开头（新三板）
    - 83/87开头（北交所）
    - 688开头（科创板）
    - 次新股：调用方确保数据范围足够大（至少180个交易日）
    """
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


def scan_stock_pool(stock_list, get_data_func, start_date="2026-05-01", end_date="2026-06-07",
                     name_map=None, verbose=False):
    hits = []
    total = len(stock_list)

    for i, item in enumerate(stock_list):
        if isinstance(item, tuple):
            name, code = item
        else:
            code = str(item)
            name = name_map.get(code, code) if name_map else code

        if not is_valid_ticker(code, name):
            continue

        if verbose and (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{total}")

        try:
            csv_str = get_data_func(code, start_date, end_date)
            if not csv_str or len(csv_str) < 50:
                continue

            df = pd.read_csv(StringIO(csv_str), comment='#')
            if len(df) < 10:
                continue

            if three_black_crows_screen(df, stock_name=name):
                cur = float(df['Close'].values[-1])
                chg_t = ((cur / float(df['Close'].values[-2])) - 1) * 100
                chg_5 = ((cur / float(df['Close'].values[-6])) - 1) * 100 if len(df) > 6 else 0

                hits.append({
                    "name": name, "code": code, "price": cur,
                    "chg_today": chg_t, "chg_5d": chg_5,
                })

                if verbose:
                    print(f"  ✅ {name}({code}) 价{cur:.2f} 当日{chg_t:+.2f}% 近5日{chg_5:+.2f}%")
        except Exception as e:
            if verbose:
                print(f"  ❌ {name}({code}): {str(e)[:60]}")

    return hits


def format_results(hits):
    if not hits:
        return "❌ 当前无股票满足三阴选股条件"

    lines = [f"\n{'='*60}", "  📡 三阴选股扫描结果", f"{'='*60}"]
    lines.append(f"\n{'标的':8s} {'代码':7s} {'价格':>8s} {'当日':>7s} {'近5日':>7s}")
    lines.append('-' * 45)
    for h in hits:
        lines.append(f"{h['name']:6s} {h['code']:6s} {h['price']:>8.2f} {h['chg_today']:>+6.1f}% {h['chg_5d']:>+6.1f}%")
    lines.append(f"\n共扫描，命中{len(hits)}只")
    return "\n".join(lines)
