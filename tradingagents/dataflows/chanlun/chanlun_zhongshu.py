"""
缠论中枢识别算法 (ZhongShu / Pivot)
===================================
中枢 = 至少三段重叠的价格区间。
识别中枢的三种生长方式：延伸（extension）、扩张（expansion）、新生（generation）。
"""

from __future__ import annotations

from typing import List, Tuple, Optional

from .chanlun_core import Bi, ZhongShu, BuySellPoint


def _overlap(a_high: float, a_low: float, b_high: float, b_low: float) -> Tuple[float, float]:
    """返回两个区间 [low, high] 的重叠部分，无重叠返回 (0, 0)"""
    zg = min(a_high, b_high)
    zd = max(a_low, b_low)
    if zg >= zd:
        return (zd, zg)
    return (0.0, 0.0)


def _has_overlap(a_high: float, a_low: float, b_high: float, b_low: float) -> bool:
    """判断两个区间是否有重叠"""
    zg, zd = _overlap(a_high, a_low, b_high, b_low)
    return zg > zd


def find_zhongshu(bis: List[Bi], min_bi_count: int = 3) -> List[ZhongShu]:
    """从笔序列中识别中枢。

    中枢构成条件：
    - 连续三笔或以上有价格重叠
    - 起止笔的方向相同（形成区间）

    Args:
        bis: 已排序的笔列表
        min_bi_count: 中枢最少需要的笔数

    Returns:
        中枢列表（按时间排序）
    """
    if len(bis) < min_bi_count:
        return []

    zhongshu_list: List[ZhongShu] = []
    n = len(bis)

    i = 0
    while i < n - min_bi_count + 1:
        # 取前 3 笔构成初始中枢
        b1, b2, b3 = bis[i], bis[i + 1], bis[i + 2]

        # 检查笔的方向交替 (必须: 上-下-上 或 下-上-下)
        if not (b1.is_up and b2.is_down and b3.is_up) and \
           not (b1.is_down and b2.is_up and b3.is_down):
            i += 1
            continue

        def bi_range(b: Bi) -> Tuple[float, float]:
            """笔的价格区间 (高, 低)"""
            return (max(b.start_price, b.end_price), min(b.start_price, b.end_price))

        r1 = bi_range(b1)
        r2 = bi_range(b2)
        r3 = bi_range(b3)

        # 中枢区间 = 三笔区间的重叠
        zg1, zd1 = _overlap(r1[0], r1[1], r2[0], r2[1])
        if zg1 <= zd1:
            i += 1
            continue

        zg2, zd2 = _overlap(zg1, zd1, r3[0], r3[1])
        if zg2 <= zd2:
            i += 1
            continue

        # 中枢建立
        # ZG = 三笔区间高点的最小者
        # ZD = 三笔区间低点的最大者
        zg = min(r1[0], r2[0], r3[0])
        zd = max(r1[1], r2[1], r3[1])
        # GG = 三笔最高价的最高者
        gg = max(b1.high, b2.high, b3.high)
        # DD = 三笔最低价的最低者
        dd = min(b1.low, b2.low, b3.low)

        zs = ZhongShu(
            start_index=b1.start_index,
            end_index=b3.end_index,
            start_date=b1.start_date,
            end_date=b3.end_date,
            zg=zg,
            zd=zd,
            gg=gg,
            dd=dd,
            direction=b1.direction,
            bi_indices=[i, i + 1, i + 2],
        )
        zhongshu_list.append(zs)

        # 尝试延伸中枢（后续笔与中枢区间重叠）
        j = i + 3
        while j < n:
            bj = bis[j]
            bj_range = bi_range(bj)
            if _has_overlap(bj_range[0], bj_range[1], zs.zg, zs.zd):
                # 延伸：更新中枢区间
                zs.end_index = bj.end_index
                zs.end_date = bj.end_date
                zs.bi_indices.append(j)
                # 更新 GG/DD
                zs.gg = max(zs.gg, bj.high)
                zs.dd = min(zs.dd, bj.low)
                # 更新 ZG/ZD（中枢区间取所有重叠笔的区间交集）
                new_zg = min(zs.zg, bj_range[0])
                new_zd = max(zs.zd, bj_range[1])
                if new_zg >= new_zd:
                    zs.zg = new_zg
                    zs.zd = new_zd
                j += 1
            else:
                break

        i = zs.bi_indices[-1] if zs.bi_indices else i + 1

    return zhongshu_list


def find_zhongshu_by_segments(
    bis: List[Bi],
    segments: List,
    min_segment_count: int = 3,
) -> List[ZhongShu]:
    """高级别中枢识别：基于线段重叠。

    日线级别上，用几段重叠来生成更高级别中枢。
    """
    if len(segments) < min_segment_count:
        return []

    zhongshu_list: List[ZhongShu] = []

    for i in range(len(segments) - min_segment_count + 1):
        segs = segments[i:i + min_segment_count]

        ranges = [(max(s.start_price, s.end_price), min(s.start_price, s.end_price))
                  for s in segs]

        zg = min(r[0] for r in ranges)
        zd = max(r[1] for r in ranges)

        if zg > zd:
            gg = max(s.high for s in segs)
            dd = min(s.low for s in segs)

            zs = ZhongShu(
                start_index=segs[0].start_index,
                end_index=segs[-1].end_index,
                start_date=segs[0].start_date,
                end_date=segs[-1].end_date,
                zg=zg,
                zd=zd,
                gg=gg,
                dd=dd,
                direction=segs[0].direction,
                segment_indices=[i + j for j in range(min_segment_count)],
            )
            zhongshu_list.append(zs)

    return zhongshu_list


def detect_third_buy_point(
    bis: List[Bi],
    zhongshu_list: List[ZhongShu],
) -> List[dict]:
    """识别第三类买卖点：突破中枢后回踩不回到中枢。

    【缠师原文】第三类买点 = 突破 ZG 后的回调最低点 > ZD（即不回到中枢内部）
    注意：是 > ZD（中枢下沿），不是 > ZG（中枢上沿）。
    
    缠师原文说的"唇吻、飞吻、湿吻"中：
    - 唇吻（最强三买）= 回调不破 ZG（最强）
    - 飞吻（中等三买）= 回调在 ZG 和 ZD 之间但未进入中枢
    - 湿吻（弱三买）= 回调触及 ZD 但未破 DD（弱三买，需谨慎）

    Args:
        bis: 笔列表
        zhongshu_list: 中枢列表

    Returns:
        三买/三卖信号列表
    """
    signals = []
    if not zhongshu_list or len(bis) < 2:
        return signals

    latest_zs = zhongshu_list[-1]

    for bi in bis:
        if bi.start_index <= latest_zs.end_index:
            continue

        # === 第三类买点 ===
        # 向上突破 ZG 后的回踩笔
        if bi.is_up and bi.end_price > latest_zs.zg:
            for next_bi in bis:
                if next_bi.start_index <= bi.end_index:
                    continue
                if next_bi.is_down:
                    if next_bi.low <= latest_zs.zd:
                        break  # 回踩破 ZD（进入中枢）= 不是三买
                    elif next_bi.low > latest_zs.zg:
                        # 唇吻（最强三买）：回调不破 ZG
                        confidence = 0.85
                        desc = (f"三买(唇吻)：突破{latest_zs.zg:.2f}后回踩"
                               f"{next_bi.low:.2f}不破ZG，极强")
                    else:
                        # 飞吻（中等三买）：回调在 ZG-ZD 之间
                        confidence = 0.7
                        desc = (f"三买(飞吻)：突破{latest_zs.zg:.2f}后回踩"
                               f"{next_bi.low:.2f}不破ZD({latest_zs.zd:.2f})")

                    signals.append({
                        "type": BuySellPoint.THIRD_BUY,
                        "bi": bi,
                        "price": next_bi.low,
                        "date": next_bi.end_date,
                        "confidence": confidence,
                        "description": desc,
                    })
                    break

        # === 第三类卖点 ===
        # 向下跌破 ZD 后的反弹笔
        if bi.is_down and bi.end_price < latest_zs.zd:
            for next_bi in bis:
                if next_bi.start_index <= bi.end_index:
                    continue
                if next_bi.is_up:
                    if next_bi.high >= latest_zs.zd:
                        break  # 反弹回到中枢 = 不是三卖
                    else:
                        confidence = 0.7
                        desc = (f"三卖：跌破{latest_zs.zd:.2f}后反弹至"
                               f"{next_bi.high:.2f}不破ZG({latest_zs.zg:.2f})")
                        signals.append({
                            "type": BuySellPoint.THIRD_SELL,
                            "bi": bi,
                            "price": next_bi.high,
                            "date": next_bi.end_date,
                            "confidence": confidence,
                            "description": desc,
                        })
                    break

    return signals
