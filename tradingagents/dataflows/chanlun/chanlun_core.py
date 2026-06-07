"""
缠论核心数据模型与常量
========================
Chan Theory (缠中说禅) core data types and constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# K 线相关
# ---------------------------------------------------------------------------

@dataclass
class KLine:
    """标准 K 线数据"""
    date: str          # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float


# ---------------------------------------------------------------------------
# 分型 (Fractal / 顶底分型)
# ---------------------------------------------------------------------------

class FractalType:
    TOP = "top"          # 顶分型
    BOTTOM = "bottom"    # 底分型

    ALL = (TOP, BOTTOM)


@dataclass
class Fractal:
    """缠论分型：顶分型或底分型"""
    type: str                    # FractalType.TOP or BOTTOM
    index: int                   # 在 K 线序列中的位置
    date: str                    # 中间 K 线日期
    high: float                  # 顶分型最高 / 底分型最高
    low: float                   # 顶分型最低 / 底分型最低
    strength: float = 0.0        # 分型强度（区间幅度）


# ---------------------------------------------------------------------------
# 笔 (Bi)
# ---------------------------------------------------------------------------

@dataclass
class Bi:
    """缠论笔：连接一个底分型和一个顶分型的走势段"""
    start_index: int             # 起始分型在 K 线序列中的位置
    end_index: int               # 结束分型位置
    start_date: str
    end_date: str
    direction: str               # "up" or "down"
    start_price: float
    end_price: float
    high: float                  # 笔的最高价
    low: float                   # 笔的最低价
    amplitude: float = 0.0       # 笔的幅度 (abs(end - start) / start)
    fractal_count: int = 0       # 笔内包含的分型数

    @property
    def is_up(self) -> bool:
        return self.direction == "up"

    @property
    def is_down(self) -> bool:
        return self.direction == "down"

    @property
    def body(self) -> float:
        return abs(self.end_price - self.start_price)

    @property
    def middle(self) -> float:
        return (self.high + self.low) / 2


# ---------------------------------------------------------------------------
# 线段 (Segment / 段)
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """缠论线段：由三笔或以上组成的高级走势段"""
    start_index: int
    end_index: int
    start_date: str
    end_date: str
    direction: str               # "up" or "down"
    start_price: float
    end_price: float
    high: float
    low: float
    bi_list: List[Bi] = field(default_factory=list)
    amplitude: float = 0.0


# ---------------------------------------------------------------------------
# 中枢 (ZhongShu / Pivot)
# ---------------------------------------------------------------------------

@dataclass
class ZhongShu:
    """缠论中枢：至少三段重叠的价格区间
    
    ┌──── ZG (中枢上沿) ────┐
    │       中枢区间         │
    └──── ZD (中枢下沿) ────┘
    
    GG = 中枢内所有笔的最高点
    DD = 中枢内所有笔的最低点
    """
    start_index: int
    end_index: int
    start_date: str
    end_date: str
    zg: float                    # 中枢上沿 (中枢区间高)
    zd: float                    # 中枢下沿 (中枢区间低)
    gg: float                    # 中枢最高点
    dd: float                    # 中枢最低点
    direction: str = ""          # 中枢方向（中枢本身无方向，记录生成方向）
    bi_indices: List[int] = field(default_factory=list)  # 构成中枢的笔索引
    segment_indices: List[int] = field(default_factory=list)  # 构成中枢的段索引

    @property
    def range(self) -> float:
        """中枢区间宽度"""
        return self.zg - self.zd

    @property
    def is_expanding(self) -> bool:
        """中枢是否在扩展中（通过是否有重合判断）"""
        return abs(self.gg - self.dd) > self.range * 2


# ---------------------------------------------------------------------------
# 背驰 (BeiChi / Divergence)
# ---------------------------------------------------------------------------

@dataclass
class BeiChiSignal:
    """背驰信号"""
    bi_index: int                # 笔索引
    bi_start: str                # 笔起始日期
    bi_end: str                  # 笔结束日期
    direction: str               # "up" or "down"
    type: str = ""               # "trend" (趋势背驰), "range" (盘整背驰)
    strength: str = ""           # "strong", "medium", "weak"
    confidence: float = 0.0      # 置信度 0.0~1.0
    description: str = ""        # 描述


# ---------------------------------------------------------------------------
# 买卖点 (Buy/Sell Point)
# ---------------------------------------------------------------------------

@dataclass
class BuySellPoint:
    """缠论三类买卖点"""
    # ---
    # Buy points
    FIRST_BUY = "一买"           # 趋势背驰后的第一类买点
    SECOND_BUY = "二买"          # 一买后回调不破前低（空中加油）
    THIRD_BUY = "三买"           # 突破中枢后回踩不回到中枢（强中强唇吻）
    # ---
    # Sell points
    FIRST_SELL = "一卖"          # 趋势背驰后的第一类卖点
    SECOND_SELL = "二卖"         # 一卖后反弹不破前高
    THIRD_SELL = "三卖"          # 跌破中枢后反弹不回到中枢

    type: str                    # 买卖点类型
    index: int                   # 在 K 线序列中的位置
    date: str
    price: float
    level: str = ""              # 级别（日线/30F/5F）
    confidence: float = 0.0      # 置信度
    description: str = ""


# ---------------------------------------------------------------------------
# 完整缠论分析结果
# ---------------------------------------------------------------------------

@dataclass
class ChanLunResult:
    """缠论分析的完整输出"""
    ticker: str
    trade_date: str

    # 分型列表
    fractals: List[Fractal] = field(default_factory=list)
    # 笔列表
    bi_list: List[Bi] = field(default_factory=list)
    # 线段列表
    segments: List[Segment] = field(default_factory=list)
    # 中枢列表
    zhongshu_list: List[ZhongShu] = field(default_factory=list)
    # 背驰信号
    beichi_signals: List[BeiChiSignal] = field(default_factory=list)
    # 买卖点
    buy_sell_points: List[BuySellPoint] = field(default_factory=list)
    # 当前走势判断
    trend_type: str = ""         # "up_trend", "down_trend", "consolidation"
    current_level: str = ""      # 当前中枢级别

    # 关键支撑阻力位
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)

    def to_markdown_report(self) -> str:
        """生成可读的缠论分析报告 Markdown"""
        lines = [
            f"## 缠论技术分析报告",
            f"",
            f"**标的**: {self.ticker}  |  **分析日期**: {self.trade_date}",
            f"**当前走势**: {self.trend_type}  |  **级别**: {self.current_level or '待确认'}",
            f"",
        ]

        # 顶底分型
        tops = [f for f in self.fractals if f.type == FractalType.TOP]
        bottoms = [f for f in self.fractals if f.type == FractalType.BOTTOM]
        lines.append(f"### 分型")
        lines.append(f"- 顶分型: {len(tops)} 个  |  底分型: {len(bottoms)} 个")
        lines.append("")

        # 笔
        lines.append(f"### 笔 ({len(self.bi_list)})")
        if self.bi_list:
            for b in self.bi_list[-8:]:  # 最近8笔
                arrow = "↑" if b.is_up else "↓"
                lines.append(
                    f"- {arrow} {b.start_date}→{b.end_date} "
                    f"[{b.start_price:.2f}→{b.end_price:.2f}] "
                    f"幅度: {b.amplitude:.2%}"
                )
        lines.append("")

        # 中枢
        lines.append(f"### 中枢 ({len(self.zhongshu_list)})")
        for i, zs in enumerate(self.zhongshu_list[-5:]):  # 最近5个
            lines.append(
                f"- 中枢 #{i + 1}: {zs.start_date}→{zs.end_date} "
                f"ZG={zs.zg:.2f} ZD={zs.zd:.2f} "
                f"区间={zs.range:.2f}"
            )
        lines.append("")

        # 背驰
        lines.append(f"### 背驰信号 ({len(self.beichi_signals)})")
        for s in self.beichi_signals:
            emoji = "⚠️" if s.strength in ("strong", "medium") else "ℹ️"
            lines.append(
                f"- {emoji} [{s.type}] {s.direction} 笔 "
                f"置信度: {s.confidence:.0%} — {s.description}"
            )
        lines.append("")

        # 买卖点
        lines.append(f"### 买卖点信号 ({len(self.buy_sell_points)})")
        for pt in self.buy_sell_points:
            emoji = "🟢" if "买" in pt.type else "🔴"
            lines.append(
                f"- {emoji} **{pt.type}** @ {pt.date} "
                f"价格: {pt.price:.2f} "
                f"置信度: {pt.confidence:.0%}"
            )
        if not self.buy_sell_points:
            lines.append("- 当前无明确买卖点信号")
        lines.append("")

        # 支撑阻力
        lines.append(f"### 关键位")
        if self.support_levels:
            lines.append(f"- 支撑位: {', '.join(f'{s:.2f}' for s in self.support_levels[:3])}")
        if self.resistance_levels:
            lines.append(f"- 阻力位: {', '.join(f'{r:.2f}' for r in self.resistance_levels[:3])}")

        return "\n".join(lines)
