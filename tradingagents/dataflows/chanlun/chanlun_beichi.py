"""
缠论背驰判断算法 (BeiChi / Divergence)
=======================================
基于 MACD 辅助判断 + 笔力度对比。

核心原则（缠师原文）：
1. 第一类买点都是在 0 轴之下背驰形成的
2. 第一类卖点都是在 0 轴之上背驰形成的
3. 黄白线回抽 0 轴是判断本级别背驰的前提
4. 没有回抽 0 轴就不存在本级别背驰
"""

from __future__ import annotations

from typing import List, Tuple, Optional

from .chanlun_core import (
    Bi, KLine, ZhongShu, BeiChiSignal,
    BuySellPoint, Fractal, FractalType,
)


def compute_macd(klines: List[KLine], fast: int = 12, slow: int = 26, signal: int = 9):
    """计算 MACD 指标。

    Returns:
        (macd_line, signal_line, histogram, dif, dea) 列表
    """
    closes = [k.close for k in klines]
    n = len(closes)

    def ema(data, period):
        result = [data[0]]
        alpha = 2.0 / (period + 1)
        for i in range(1, len(data)):
            result.append(alpha * data[i] + (1 - alpha) * result[-1])
        return result

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    dif = [ema_fast[i] - ema_slow[i] for i in range(n)]

    dea = ema(dif, signal)
    macd_hist = [2 * (dif[i] - dea[i]) for i in range(n)]

    return dif, dea, macd_hist


def _bi_price_amplitude(bi: Bi) -> float:
    """笔的价格变动幅度"""
    return abs(bi.end_price - bi.start_price)


def _bi_macd_area(
    bi: Bi,
    macd_hist: List[float],
) -> float:
    """计算笔对应 MACD 柱子的面积（力度）"""
    return sum(abs(m) for m in macd_hist[bi.start_index:bi.end_index + 1])


def detect_beichi(
    bis: List[Bi],
    zhongshu_list: List[ZhongShu],
    klines: List[KLine],
) -> Tuple[List[BeiChiSignal], List[BuySellPoint]]:
    """检测背驰信号和买卖点。

    流程：
    1. 找到最后一个中枢
    2. 比较进入和离开中枢的笔的力度（MACD面积 + 价格幅度）
    3. 若离开笔力度小于进入笔 => 背驰

    Returns:
        (beichi_signals, buy_sell_points)
    """
    signals: List[BeiChiSignal] = []
    points: List[BuySellPoint] = []

    if len(bis) < 3 or not klines:
        return signals, points

    # 计算 MACD
    dif, dea, macd_hist = compute_macd(klines)

    # 新增：当笔数 >= 2 但不够形成中枢时，检查盘整背驰
    if len(bis) >= 2:
        _detect_range_beichi(bis, macd_hist, signals, points)

    # 对每个中枢分析
    for zs in zhongshu_list:
        # 找进入中枢的笔（中枢之前且与中枢重叠）
        entry_bi = None
        for bi in bis:
            if bi.end_index < zs.start_index:
                entry_bi = bi
            else:
                break

        # 找离开中枢的笔（中枢之后第一笔）
        exit_bi = None
        for bi in bis:
            if bi.start_index > zs.end_index:
                exit_bi = bi
                break

        if not entry_bi or not exit_bi:
            continue

        # 判断方向
        is_up_trend = exit_bi.is_up

        # 检查 DIF/DEA 是否回抽过 0 轴（背驰前提）
        zs_dif = dif[zs.start_index:zs.end_index + 1]
        if not zs_dif:
            continue

        zero_cross = any(
            (zs_dif[i] > 0 and zs_dif[i + 1] < 0) or
            (zs_dif[i] < 0 and zs_dif[i + 1] > 0)
            for i in range(len(zs_dif) - 1)
        )

        # 计算力度
        entry_area = _bi_macd_area(entry_bi, macd_hist)
        exit_area = _bi_macd_area(exit_bi, macd_hist)

        entry_price_move = _bi_price_amplitude(entry_bi)
        exit_price_move = _bi_price_amplitude(exit_bi)

        # 背驰判断：离开笔面积 < 进入笔面积
        is_beichi = exit_area < entry_area * 0.7  # 70% 阈值

        if is_beichi:
            beichi_type = "trend"
            strength = "strong" if exit_area < entry_area * 0.5 else "medium"
            confidence = 0.7 if zero_cross else 0.4

            if strength == "strong":
                confidence = 0.85 if zero_cross else 0.6

            signals.append(BeiChiSignal(
                bi_index=bis.index(exit_bi),
                bi_start=exit_bi.start_date,
                bi_end=exit_bi.end_date,
                direction="up" if is_up_trend else "down",
                type=beichi_type,
                strength=strength,
                confidence=confidence,
                description=(
                    f"{'上涨' if is_up_trend else '下跌'}背驰："
                    f"进入面积={entry_area:.1f} "
                    f"离开面积={exit_area:.1f} "
                    f"减弱{(1 - exit_area/entry_area)*100:.0f}%"
                ),
            ))

            # 生成买卖点
            if is_up_trend:
                points.append(BuySellPoint(
                    type=BuySellPoint.FIRST_SELL,
                    index=exit_bi.end_index,
                    date=exit_bi.end_date,
                    price=exit_bi.end_price,
                    level=next((str(len(zhongshu_list)) + "级中枢"), "本级"),
                    confidence=confidence,
                    description=f"趋势顶背驰，DIF{'已' if zero_cross else '未'}回抽0轴",
                ))
            else:
                points.append(BuySellPoint(
                    type=BuySellPoint.FIRST_BUY,
                    index=exit_bi.end_index,
                    date=exit_bi.end_date,
                    price=exit_bi.end_price,
                    level=next((str(len(zhongshu_list)) + "级中枢"), "本级"),
                    confidence=confidence,
                    description=f"趋势底背驰，DIF{'已' if zero_cross else '未'}回抽0轴",
                ))

    return signals, points


def _detect_range_beichi(
    bis: List[Bi],
    macd_hist: List[float],
    signals: List[BeiChiSignal],
    points: List[BuySellPoint],
):
    """检测盘整背驰（只有一个中枢或没有中枢的背驰）。

    增强逻辑：
    1. 盘整背驰至少需要 4 笔比较（不只看 2 笔）
    2. 增加价格幅度过滤（幅度 < 3% 的笔不参与，排除噪音）
    3. 盘整背驰后检查是否构成三买/三卖条件
    """
    if len(bis) < 4:
        return

    # 盘整背驰：比较相邻两笔的力度
    for i in range(1, len(bis)):
        bi_prev = bis[i - 1]
        bi_curr = bis[i]

        if bi_prev.is_up != bi_curr.is_up:
            continue

        # 幅度过滤：太小幅度的笔可能是噪音
        if bi_curr.amplitude < 0.03:
            continue

        prev_area = _bi_macd_area(bi_prev, macd_hist)
        curr_area = _bi_macd_area(bi_curr, macd_hist)

        if curr_area < prev_area * 0.7:
            confidence = 0.4
            beichi_type = "range"

            # === 盘整背驰→三买转化检测 ===
            # 如果盘整向上背驰，但之后的回踩(如果有)没有破前低
            # 且整体趋势向上 → 可能是盘整背驰转三买
            if bi_curr.is_up and i + 1 < len(bis):
                next_bi = bis[i + 1]
                if next_bi.is_down and next_bi.low > bi_curr.start_price:
                    confidence = 0.6  # 提高置信度
                    beichi_type = "range_to_third_buy"
                    signals.append(BeiChiSignal(
                        bi_index=i,
                        bi_start=bi_curr.start_date,
                        bi_end=bi_curr.end_date,
                        direction=bi_curr.direction,
                        type="range_to_third_buy",
                        strength="weak",
                        confidence=confidence,
                        description=(
                            f"盘整背驰转三买：第{i}笔MACD减弱，"
                            f"回踩{next_bi.low:.2f}不破前起点{bi_curr.start_price:.2f}"
                        ),
                    ))
                    points.append(BuySellPoint(
                        type=BuySellPoint.THIRD_BUY,
                        index=next_bi.end_index,
                        date=next_bi.end_date,
                        price=next_bi.low,
                        level="盘整",
                        confidence=confidence,
                        description=f"盘整背驰转三买：回踩{next_bi.low:.2f}不破",
                    ))
                    continue

            # 盘整背驰转三卖检测
            if bi_curr.is_down and i + 1 < len(bis):
                next_bi = bis[i + 1]
                if next_bi.is_up and next_bi.high < bi_curr.start_price:
                    confidence = 0.6
                    beichi_type = "range_to_third_sell"
                    signals.append(BeiChiSignal(
                        bi_index=i,
                        bi_start=bi_curr.start_date,
                        bi_end=bi_curr.end_date,
                        direction=bi_curr.direction,
                        type="range_to_third_sell",
                        strength="weak",
                        confidence=confidence,
                        description=(
                            f"盘整背驰转三卖：第{i}笔MACD减弱，"
                            f"反弹{next_bi.high:.2f}不破前起点{bi_curr.start_price:.2f}"
                        ),
                    ))
                    continue

            # 普通盘整背驰
            signals.append(BeiChiSignal(
                bi_index=i,
                bi_start=bi_curr.start_date,
                bi_end=bi_curr.end_date,
                direction=bi_curr.direction,
                type=beichi_type,
                strength="weak",
                confidence=confidence,
                description=f"盘整背驰：第{i}笔力度减弱({1-curr_area/prev_area:.0%})",
            ))


def detect_second_buy_sell(
    bis: List[Bi],
    points: List[BuySellPoint],
    zhongshu_list: List[ZhongShu],
) -> List[BuySellPoint]:
    """识别二买/二卖信号。

    二买 = 一买后回调不破前低（"空中加油"）
    二卖 = 一卖后反弹不破前高
    """
    second_points: List[BuySellPoint] = []

    for pt in points:
        if pt.type == BuySellPoint.FIRST_BUY:
            first_buy_price = pt.price
            for bi in bis:
                if bi.start_index >= pt.index and bi.is_up:
                    for down_bi in bis:
                        if down_bi.start_index > bi.end_index and down_bi.is_down:
                            if down_bi.low > first_buy_price:
                                second_points.append(BuySellPoint(
                                    type=BuySellPoint.SECOND_BUY,
                                    index=down_bi.end_index,
                                    date=down_bi.end_date,
                                    price=down_bi.low,
                                    level=pt.level,
                                    confidence=min(pt.confidence - 0.1, 0.7),
                                    description=f"二买：回调至{down_bi.low:.2f}不破一买{first_buy_price:.2f}",
                                ))
                            break

        elif pt.type == BuySellPoint.FIRST_SELL:
            first_sell_price = pt.price
            for bi in bis:
                if bi.start_index >= pt.index and bi.is_down:
                    for up_bi in bis:
                        if up_bi.start_index > bi.end_index and up_bi.is_up:
                            if up_bi.high < first_sell_price:
                                second_points.append(BuySellPoint(
                                    type=BuySellPoint.SECOND_SELL,
                                    index=up_bi.end_index,
                                    date=up_bi.end_date,
                                    price=up_bi.high,
                                    level=pt.level,
                                    confidence=min(pt.confidence - 0.1, 0.7),
                                    description=f"二卖：反弹至{up_bi.high:.2f}不破一卖{first_sell_price:.2f}",
                                ))
                            break

    return second_points
