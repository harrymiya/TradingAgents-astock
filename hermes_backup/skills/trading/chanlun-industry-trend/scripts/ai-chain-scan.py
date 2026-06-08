#!/usr/bin/env python3
"""
AI产业链实时扫描脚本 — 零依赖版
通过腾讯财经HTTP API批量获取AI产业链核心标的的实时行情。

用法：
  python3 scripts/ai-chain-scan.py                # 默认扫描AI全链
  python3 scripts/ai-chain-scan.py --focus robot   # 只扫机器人链
  python3 scripts/ai-chain-scan.py --focus chip    # 只扫芯片链
  
输出格式：
  按涨跌幅排序，标注强势/弱势，给出当日资金流向判断
"""

import urllib.request
import json
import sys

# AI产业链核心标的库（可扩展）
STOCKS = {
    # === 第一档：半导体设备（壁垒15/20）===
    "sz002371": ("北方华创", "半导体设备"),
    "sh688012": ("中微公司", "半导体设备"),
    "sh688072": ("拓荆科技", "半导体设备"),
    "sh688037": ("芯源微", "半导体设备"),
    
    # === GPU/AI芯片（壁垒17/20）===
    "sh688041": ("海光信息", "GPU芯片"),
    "sh688256": ("寒武纪", "AI芯片"),
    
    # === HBM/存储接口（壁垒14/20）===
    "sh688008": ("澜起科技", "存储接口"),
    "sh603986": ("兆易创新", "存储芯片"),
    "sz300661": ("圣邦股份", "模拟芯片"),
    
    # === 光模块（壁垒12/20）===
    "sz300308": ("中际旭创", "光模块"),
    "sz300502": ("新易盛", "光模块"),
    "sz300394": ("天孚通信", "光模块"),
    
    # === 先进封装（壁垒9/20）===
    "sh600584": ("长电科技", "先进封装"),
    "sz002156": ("通富微电", "先进封装"),
    "sh688362": ("甬矽电子", "先进封装"),
    
    # === 半导体材料（壁垒12/20）===
    "sh688126": ("沪硅产业", "半导体材料"),
    "sh688019": ("安集科技", "半导体材料"),
    "sh002409": ("雅克科技", "半导体材料"),
    
    # === 机器人核心部件（壁垒13/20）===
    "sh688017": ("绿的谐波", "机器人减速器"),
    "sz300124": ("汇川技术", "机器人"),
    "sz002472": ("双环传动", "机器人减速器"),
    "sh688160": ("步科股份", "机器人"),
    
    # === 液冷散热（壁垒9→12↑）===
    "sz002837": ("英维克", "液冷散热"),
    "sz300499": ("高澜股份", "液冷散热"),
    
    # === 通信设备/AI服务器（弱映射）===
    "sz000063": ("中兴通讯", "通信设备"),
    "sh600941": ("中国移动", "通信"),
    
    # === 下游应用 ====
    "sz002230": ("科大讯飞", "AI应用"),
    "sz002415": ("海康威视", "AI安防"),
}


def fetch_quotes(codes):
    """批量获取实时行情"""
    url = "https://qt.gtimg.cn/q=" + ",".join(codes)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")
    
    results = []
    for line in raw.strip().split("\n"):
        if not line or "=" not in line:
            continue
        parts = line.split("~")
        if len(parts) > 40:
            name = parts[1]
            code = parts[2]
            price = float(parts[3]) if parts[3] else 0
            prev_close = float(parts[4]) if parts[4] else 0
            high = float(parts[33]) if parts[33] else 0
            low = float(parts[34]) if parts[34] else 0
            change_pct = float(parts[32]) if parts[32] else 0
            pe = float(parts[39]) if parts[39] else 0
            turnover = float(parts[38]) if parts[38] else 0
            market_cap = float(parts[45]) if parts[45] else 0
            results.append((name, code, price, change_pct, pe, turnover, market_cap, high, low, prev_close))
    
    return results


def scan(focus=None):
    """执行扫描"""
    if focus:
        filtered = {k: v for k, v in STOCKS.items() if focus.lower() in v[1].lower()}
    else:
        filtered = STOCKS
    
    results = fetch_quotes(list(filtered.keys()))
    
    # 按涨跌幅排序
    results.sort(key=lambda x: -x[3])
    
    # 产出报告
    print(f"{'名称':12s} {'代码':8s} {'最新':8s} {'涨跌幅':8s} {'PE':8s} {'换手率':8s} {'市值(亿)':10s} {'环节':12s}")
    print("-" * 80)
    
    for name, code, price, chg, pe, turn, mcap, high, low, close in results:
        sector = filtered.get(code, ("", ""))[1]
        # 标记
        if chg > 5:
            tag = "🔥🔥"
        elif chg > 2:
            tag = "🔥"
        elif chg > 0:
            tag = "📈"
        elif chg > -3:
            tag = "➖"
        elif chg > -5:
            tag = "📉"
        else:
            tag = "🚨"
        
        mcap_str = f"{mcap/1e8:.0f}" if mcap > 0 else "N/A"
        print(f"{tag} {name:10s} {code:8s} {price:>7.2f} {chg:>+7.2f}% {pe:>7.1f} {turn:>7.2f}% {mcap_str:>8s} {sector:12s}")
    
    # 统计
    up = sum(1 for r in results if r[3] > 0)
    down = sum(1 for r in results if r[3] < 0)
    hot = sum(1 for r in results if r[3] > 5)
    crash = sum(1 for r in results if r[3] < -5)
    
    print(f"\n=== 摘要 ===")
    print(f"上涨: {up}  下跌: {down}  涨停: {hot}  大跌(>-5%): {crash}")
    
    # 最强板块识别
    sectors = {}
    for r in results:
        name, code, price, chg, pe, turn, mcap, high, low, close = r
        s = filtered.get(code, ("", ""))[1]
        if s not in sectors:
            sectors[s] = []
        sectors[s].append(chg)
    
    print(f"\n=== 板块强弱 ===")
    for s, chgs in sorted(sectors.items(), key=lambda x: -sum(x[1])/len(x[1])):
        avg = sum(chgs) / len(chgs)
        tag = "🔥🔥" if avg > 5 else "🔥" if avg > 2 else "📈" if avg > 0 else "📉" if avg > -3 else "🚨"
        print(f"  {tag} {s:16s} 平均涨幅: {avg:+.2f}% ({len(chgs)}只)")


if __name__ == "__main__":
    focus = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("--") else None
    if focus:
        focus = focus.lstrip("--")
    scan(focus)
