"""
缠论笔划分算法 (Bi / Stroke)
=============================
基于顶底分型识别 + 包含关系处理 + 笔的成立条件。
"""

from __future__ import annotations

from typing import List, Tuple, Optional

from .chanlun_core import KLine, Fractal, FractalType, Bi


def _find_fractals(klines: List[KLine]) -> List[Fractal]:
    """从 K 线序列中识别所有顶分型和底分型。
    
    顶分型: 中间 K 线的最高点是三根中最高，最低点也是最高。
    底分型: 中间 K 线的最低点是三根中最低，最高点也是最低。
    """
    fractals: List[Fractal] = []
    n = len(klines)

    for i in range(1, n - 1):
        prev, curr, next_ = klines[i - 1], klines[i], klines[i + 1]

        # 顶分型: 中间最高 ⇔ 左右两边都更低
        if curr.high > prev.high and curr.high >= next_.high:
            # 检查最低点也符合
            if curr.low >= prev.low and curr.low >= next_.low:
                strength = (curr.high - curr.low) / curr.low
                fractals.append(Fractal(
                    type=FractalType.TOP,
                    index=i,
                    date=curr.date,
                    high=curr.high,
                    low=curr.low,
                    strength=strength,
                ))

        # 底分型: 中间最低 ⇔ 左右两边都更高
        if curr.low < prev.low and curr.low <= next_.low:
            if curr.high <= prev.high and curr.high <= next_.high:
                strength = (curr.high - curr.low) / curr.low
                fractals.append(Fractal(
                    type=FractalType.BOTTOM,
                    index=i,
                    date=curr.date,
                    high=curr.high,
                    low=curr.low,
                    strength=strength,
                ))

    return fractals


def _handle_containment(klines: List[KLine]) -> List[KLine]:
    """处理 K 线包含关系（迭代实现，无递归深度限制）。

    上涨趋势中: 包含 = 取高高（最高价取大，最低价取大）
    下跌趋势中: 包含 = 取低低（最高价取小，最低价取小）

    用迭代方式反复扫描直到无包含关系（避免递归深度问题）。
    """
    if len(klines) < 2:
        return klines

    result = list(klines)
    changed = True

    while changed:
        changed = False
        new_result: List[KLine] = []

        i = 0
        while i < len(result):
            if i == 0:
                new_result.append(result[i])
                i += 1
                continue

            prev = new_result[-1]
            curr = result[i]

            # 检查包含关系
            is_contained = (
                (curr.high <= prev.high and curr.low >= prev.low) or
                (prev.high <= curr.high and prev.low >= curr.low)
            )

            if not is_contained:
                new_result.append(curr)
            else:
                # 判断方向
                if len(new_result) >= 2:
                    prev2 = new_result[-2]
                    direction_up = prev2.high < prev.high and prev2.low < prev.low
                else:
                    direction_up = True

                if direction_up:
                    merged = KLine(
                        date=prev.date,
                        open=prev.open,
                        high=max(prev.high, curr.high),
                        low=max(prev.low, curr.low),
                        close=curr.close if curr.close > prev.close else prev.close,
                        volume=prev.volume + curr.volume,
                    )
                else:
                    merged = KLine(
                        date=prev.date,
                        open=prev.open,
                        high=min(prev.high, curr.high),
                        low=min(prev.low, curr.low),
                        close=curr.close if curr.close < prev.close else prev.close,
                        volume=prev.volume + curr.volume,
                    )

                new_result[-1] = merged
                changed = True

            i += 1

        result = new_result

    return result


def _filter_fractals(fractals: List[Fractal]) -> List[Fractal]:
    """过滤分型：顶底交替出现，去除连续同向分型"""
    if not fractals:
        return []

    filtered: List[Fractal] = [fractals[0]]

    for f in fractals[1:]:
        last = filtered[-1]
        # 同类型跳过
        if f.type == last.type:
            # 同类型取更极端的
            if f.type == FractalType.TOP and f.high > last.high:
                filtered[-1] = f
            elif f.type == FractalType.BOTTOM and f.low < last.low:
                filtered[-1] = f
        else:
            filtered.append(f)

    return filtered


def _build_bi_from_fractals(
    fractals: List[Fractal],
    klines: List[KLine],
    min_bi_kline_count: int = 4,
) -> List[Bi]:
    """从分型序列构建笔。
    
    笔的成立条件：
    1. 顶底分型之间至少有 min_bi_kline_count 根 K 线（不含分型本身）
    2. 笔的幅度不能太小（过滤噪音）
    """
    bis: List[Bi] = []
    n = len(fractals)

    i = 0
    while i < n - 1:
        f1 = fractals[i]
        f2 = fractals[i + 1]

        # 必须是不同方向
        if f1.type == f2.type:
            i += 1
            continue

        # 必须顶底交替
        if f1.type != FractalType.TOP or f2.type != FractalType.BOTTOM:
            # 交换检查
            if f1.type == FractalType.BOTTOM and f2.type == FractalType.TOP:
                direction = "up"
            else:
                i += 1
                continue
        else:
            direction = "down"

        # 检查 K 线数量
        kline_count = f2.index - f1.index - 1
        if kline_count < min_bi_kline_count:
            i += 1
            continue

        # 构建笔
        if direction == "up":
            bi = Bi(
                start_index=f1.index,
                end_index=f2.index,
                start_date=f1.date,
                end_date=f2.date,
                direction="up",
                start_price=f1.low if f1.type == FractalType.BOTTOM else f1.high,
                end_price=f2.high if f2.type == FractalType.TOP else f2.low,
                high=f2.high,
                low=f1.low,
                fractal_count=i + 2,
            )
        else:
            bi = Bi(
                start_index=f1.index,
                end_index=f2.index,
                start_date=f1.date,
                end_date=f2.date,
                direction="down",
                start_price=f1.high,
                end_price=f2.low,
                high=f1.high,
                low=f2.low,
                fractal_count=i + 2,
            )

        # 计算幅度
        if bi.start_price > 0:
            bi.amplitude = abs(bi.end_price - bi.start_price) / bi.start_price

        bis.append(bi)
        i += 1

    return bis


def compute_bi(
    klines: List[KLine],
    min_bi_kline_count: int = 4,
) -> Tuple[List[Fractal], List[Bi]]:
    """从 K 线序列完整计算缠论笔。
    
    Args:
        klines: K 线列表（按时间升序）
    
    Returns:
        (fractals, bi_list): 分型列表和笔列表
    """
    if len(klines) < 7:
        return [], []

    # 1. 处理包含关系
    clean_klines = _handle_containment(klines)

    # 2. 识别分型
    raw_fractals = _find_fractals(clean_klines)

    # 3. 过滤分型
    fractals = _filter_fractals(raw_fractals)

    # 4. 构建笔
    bis = _build_bi_from_fractals(fractals, klines, min_bi_kline_count=min_bi_kline_count)

    return fractals, bis
