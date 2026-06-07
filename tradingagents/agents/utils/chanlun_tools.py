"""
缠论分析工具函数
================
LangChain Tool 封装的缠论分析函数，供 Analyst Agent 调用。
遵循项目已有的 tool 模式（使用 @tool 装饰器）。
"""

from __future__ import annotations

from typing import Optional, List

from langchain_core.tools import tool

from tradingagents.dataflows.chanlun import (
    analyze_chanlun,
    klines_from_dataframe,
)
from tradingagents.dataflows.chanlun.chanlun_core import (
    KLine,
    ChanLunResult,
    BuySellPoint,
)


@tool
def get_chanlun_bi(klines_json: str) -> str:
    """缠论笔划分：从 K 线数据中识别顶底分型并划分笔。
    
    Args:
        klines_json: K 线数据的 JSON 字符串，每根 K 线包含
                     date/open/high/low/close/volume 字段
    
    Returns:
        笔划分结果（分型列表 + 笔列表）
    """
    try:
        import json
        data = json.loads(klines_json)
        klines = [
            KLine(**k) for k in data
        ]
        from tradingagents.dataflows.chanlun.chanlun_bi import compute_bi
        fractals, bis = compute_bi(klines)
        
        lines = [f"分型: {len(fractals)} 个"]
        for f in fractals:
            lines.append(f"  {'顶' if f.type == 'top' else '底'} @ {f.date} 价={f.high:.2f}/{f.low:.2f}")
        
        lines.append(f"\n笔: {len(bis)} 段")
        for b in bis:
            arrow = "↑" if b.is_up else "↓"
            lines.append(
                f"  {arrow} {b.start_date}→{b.end_date} "
                f"[{b.start_price:.2f}→{b.end_price:.2f}] {b.amplitude:.2%}"
            )
        
        return "\n".join(lines)
    except Exception as e:
        return f"缠论笔划分失败: {e}"


@tool
def get_chanlun_zhongshu(klines_json: str) -> str:
    """缠论中枢识别：在已有笔的基础上识别中枢的位置和区间。
    
    Args:
        klines_json: K 线数据的 JSON 字符串
    
    Returns:
        中枢分析结果
    """
    try:
        import json
        data = json.loads(klines_json)
        klines = [KLine(**k) for k in data]
        
        from tradingagents.dataflows.chanlun.chanlun_bi import compute_bi
        _, bis = compute_bi(klines)
        
        from tradingagents.dataflows.chanlun.chanlun_zhongshu import find_zhongshu
        zhongshu_list = find_zhongshu(bis)
        
        lines = [f"中枢: {len(zhongshu_list)} 个"]
        for i, zs in enumerate(zhongshu_list):
            lines.append(
                f"\n中枢 #{i+1}:"
                f"\n  区间: {zs.start_date}→{zs.end_date}"
                f"\n  ZG={zs.zg:.2f}  ZD={zs.zd:.2f}"
                f"\n  GG={zs.gg:.2f}  DD={zs.dd:.2f}"
                f"\n  区间宽度: {zs.range:.2f}"
            )
        
        return "\n".join(lines)
    except Exception as e:
        return f"缠论中枢识别失败: {e}"


@tool
def get_chanlun_beichi(klines_json: str) -> str:
    """缠论背驰判断：基于 MACD 辅助判断顶底背驰和盘整背驰。
    
    Args:
        klines_json: K 线数据的 JSON 字符串
    
    Returns:
        背驰信号分析
    """
    try:
        import json
        data = json.loads(klines_json)
        klines = [KLine(**k) for k in data]
        
        result = analyze_chanlun(klines)
        
        lines = [f"背驰信号: {len(result.beichi_signals)}"]
        for s in result.beichi_signals:
            lines.append(
                f"\n  {'⚠️' if s.strength in ('strong','medium') else 'ℹ️'} "
                f"{'上涨' if s.direction == 'up' else '下跌'}背驰"
                f"\n  类型: {s.type}  强度: {s.strength}"
                f"\n  置信度: {s.confidence:.0%}"
                f"\n  描述: {s.description}"
            )
        
        lines.append(f"\n\n买卖点信号: {len(result.buy_sell_points)}")
        for pt in result.buy_sell_points:
            emoji = "🟢" if "买" in pt.type else "🔴"
            lines.append(
                f"  {emoji} {pt.type} @ {pt.date} 价格={pt.price:.2f} "
                f"置信度: {pt.confidence:.0%}"
            )
        
        return "\n".join(lines)
    except Exception as e:
        return f"缠论背驰判断失败: {e}"


@tool
def get_chanlun_full_report(klines_json: str) -> str:
    """完整缠论技术分析报告：笔 → 中枢 → 背驰 → 买卖点一次完成。
    这是最推荐的入口，一次调用获得全部缠论分析结果。
    
    Args:
        klines_json: K 线数据的 JSON 字符串
    
    Returns:
        完整的缠论 Markdown 分析报告
    """
    try:
        import json
        data = json.loads(klines_json)
        klines = [KLine(**k) for k in data]
        
        result = analyze_chanlun(klines)
        return result.to_markdown_report()
    except Exception as e:
        return f"缠论全分析失败: {e}"
