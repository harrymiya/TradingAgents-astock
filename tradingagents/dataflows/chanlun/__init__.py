"""
缠论分析主入口 (ChanLun Analyzer)
=================================
串联笔 → 中枢 → 背驰 → 买卖点的完整分析流程。
"""

from __future__ import annotations

from typing import List, Optional

from .chanlun_core import KLine, ChanLunResult
from .chanlun_bi import compute_bi
from .chanlun_zhongshu import find_zhongshu, detect_third_buy_point
from .chanlun_beichi import (
    detect_beichi,
    detect_second_buy_sell,
)


def analyze_chanlun(
    klines: List[KLine],
    ticker: str = "",
    trade_date: str = "",
    min_bi_kline_count: int = 4,
) -> ChanLunResult:
    """对给定 K 线序列执行完整缠论分析。
    
    Args:
        klines: K 线数据（日线或更小周期），按时间升序
        ticker: 股票代码
        trade_date: 分析日期
        min_bi_kline_count: 笔的最少 K 线数
    
    Returns:
        ChanLunResult: 完整的缠论分析结果
    """
    result = ChanLunResult(ticker=ticker, trade_date=trade_date)

    if len(klines) < 10:
        result.trend_type = "数据不足"
        return result

    # 1. 计算笔
    fractals, bis = compute_bi(klines, min_bi_kline_count=min_bi_kline_count)
    result.fractals = fractals
    result.bi_list = bis

    if not bis:
        # 笔数量为零或仅 1-2 笔时依然输出原始分型统计
        if len(fractals) >= 2:
            tops = [f for f in fractals if f.type == FractalType.TOP]
            bottoms = [f for f in fractals if f.type == FractalType.BOTTOM]
            result.trend_type = (
                f"无法划分完整笔（仅{len(bis)}笔，但原始分型"
                f"顶{len(tops)}底{len(bottoms)}个可用）"
            )
            # 即使没有完整笔，也基于分型给出关键位
            if bottoms:
                prices = [f.low for f in bottoms]
                result.support_levels = sorted(set(prices))[:3]
            if tops:
                prices = [f.high for f in tops]
                result.resistance_levels = sorted(set(prices), reverse=True)[:3]
        else:
            result.trend_type = f"无法划分笔（分型数={len(fractals)}，数据量可能不足）"
        return result

    # 2. 寻找中枢
    zhongshu_list = find_zhongshu(bis)
    result.zhongshu_list = zhongshu_list

    # 3. 判断当前走势
    result.trend_type = _classify_trend(bis, zhongshu_list)
    result.current_level = _detect_level(zhongshu_list)

    # 4. 检测背驰和买卖点
    beichi_signals, buy_sell_points = detect_beichi(bis, zhongshu_list, klines)
    result.beichi_signals = beichi_signals
    result.buy_sell_points = buy_sell_points

    # 5. 检测二类买卖点
    second_points = detect_second_buy_sell(bis, buy_sell_points, zhongshu_list)
    result.buy_sell_points.extend(second_points)

    # 6. 检测三类买卖点
    third_signals = detect_third_buy_point(bis, zhongshu_list)
    for sig in third_signals:
        from .chanlun_core import BuySellPoint
        result.buy_sell_points.append(BuySellPoint(
            type=sig["type"],
            index=sig["bi"].end_index,
            date=sig["date"],
            price=sig["price"],
            level=result.current_level,
            confidence=sig["confidence"],
            description=sig["description"],
        ))

    # 7. 计算支撑阻力
    result.support_levels = _calculate_support_levels(bis, zhongshu_list)
    result.resistance_levels = _calculate_resistance_levels(bis, zhongshu_list)

    return result


def _classify_trend(bis, zhongshu_list) -> str:
    """判断当前走势类型"""
    if len(bis) < 2:
        return "盘整（笔不足）"

    last_bi = bis[-1]

    if len(zhongshu_list) >= 2:
        # 两个以上中枢 = 趋势
        zs1, zs2 = zhongshu_list[-2], zhongshu_list[-1]
        if zs2.zg > zs1.zg and zs2.zd > zs1.zd:
            return "上涨趋势"
        elif zs2.zg < zs1.zg and zs2.zd < zs1.zd:
            return "下跌趋势"
        else:
            return "中枢扩展中"

    if len(zhongshu_list) == 1:
        zs = zhongshu_list[-1]
        if last_bi.end_price > zs.zg:
            return "盘整向上离开中枢"
        elif last_bi.end_price < zs.zd:
            return "盘整向下离开中枢"
        else:
            return "盘整（在中枢内震荡）"

    return "未形成中枢（盘整）"


def _detect_level(zhongshu_list) -> str:
    """判断当前分析级别"""
    count = len(zhongshu_list)
    if count == 0:
        return ""
    elif count <= 2:
        return "本级别"
    elif count <= 4:
        return "本级别（中枢延伸中）"
    else:
        return "高级别（中枢扩张）"


def _calculate_support_levels(bis, zhongshu_list) -> List[float]:
    """计算关键支撑位"""
    levels = []

    # 中枢下沿是重要支撑
    for zs in zhongshu_list:
        levels.append(zs.zd)
        levels.append(zs.dd)

    # 最近向下笔的终点也是支撑
    for bi in reversed(bis):
        if bi.is_down and bi.end_price not in levels:
            levels.append(bi.end_price)
            break

    # 取最近3个支撑
    supports = sorted(set(levels))
    return supports[:3] if supports else []


def _calculate_resistance_levels(bis, zhongshu_list) -> List[float]:
    """计算关键阻力位"""
    levels = []

    # 中枢上沿是重要阻力
    for zs in zhongshu_list:
        levels.append(zs.zg)
        levels.append(zs.gg)

    # 最近向上笔的终点也是阻力
    for bi in reversed(bis):
        if bi.is_up and bi.end_price not in levels:
            levels.append(bi.end_price)
            break

    supports = sorted(set(levels), reverse=True)
    return supports[:3] if supports else []


def klines_from_dataframe(df, date_col="date", ohlc=None) -> List[KLine]:
    """从 pandas DataFrame 转换为 KLine 列表。
    
    Args:
        df: 包含 K 线数据的 DataFrame
        date_col: 日期列名（默认 "date"）
        ohlc: (open, high, low, close, volume) 列名元组
    """
    if ohlc is None:
        ohlc = ("open", "high", "low", "close", "volume")

    open_col, high_col, low_col, close_col, volume_col = ohlc

    klines = []
    for _, row in df.iterrows():
        date = str(row.get(date_col, ""))
        if not date:
            continue
        klines.append(KLine(
            date=date,
            open=float(row[open_col]),
            high=float(row[high_col]),
            low=float(row[low_col]),
            close=float(row[close_col]),
            volume=float(row[volume_col]) if volume_col in row else 0,
        ))

    return klines
