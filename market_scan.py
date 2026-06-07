"""
全市场选股扫描 v2 — 无HTML污染版
"""
import base64, os, json, re
os.environ['DEEPSEEK_API_KEY'] = base64.b64decode(
    b'c2stYzViNGNkYzgyNmE1NDQzNjkwMTFiMDE1NDdmMGM4ZTE='
).decode()

from io import StringIO
import pandas as pd
from datetime import datetime

from tradingagents.dataflows.a_stock import (
    get_stock_data, get_fundamentals, get_hot_stocks,
    get_northbound_flow, get_concept_blocks, get_global_news,
)
from tradingagents.dataflows.chanlun import analyze_chanlun, klines_from_dataframe

DATE = datetime.now().strftime("%Y-%m-%d")
TD = "2026-06-05"

CORE_POOL = {
    "半导体设备": {
        "北方华创": "002371",
        # "中微公司": "688012",  # 688科创板 排除
        # "拓荆科技": "688072",  # 688科创板 排除
    },
    "GPU/AI芯片": {
        # "海光信息": "688041",  # 688科创板 排除
        # "寒武纪": "688256",   # 688科创板 排除
    },
    "存储接口": {
        # "澜起科技": "688008",  # 688科创板 排除
        "兆易创新": "603986",
    },
    "半导体材料": {
        # "沪硅产业": "688126",  # 688科创板 排除
        "彤程新材": "603650",
    },
    "封测": {
        "长电科技": "600584",
        "通富微电": "002156",
    },
    "光模块": {
        "中际旭创": "300308",
        "新易盛": "300502",
        "天孚通信": "300394",
    },
    "机器人": {
        # "绿的谐波": "688017",  # 688科创板 排除
        "汇川技术": "300124",
    },
    "液冷/散热": {
        "英维克": "002837",
        "高澜股份": "300499",
    },
    "通信设备": {
        "中兴通讯": "000063",
    },
    "光学": {
        "东田微": "301183",
    },
    "光刻胶": {
        "南大光电": "300346",
        "容大感光": "300576",
        "晶瑞电材": "300655",
        "上海新阳": "300236",
    },
    "功率半导体": {
        "士兰微": "600460",
        "斯达半导": "603290",
    },
    "消费电子": {
        "立讯精密": "002475",
        "歌尔股份": "002241",
        "蓝思科技": "300433",
    },
}

def extract_field(text, field):
    """从基本面文本中提取字段值"""
    for line in text.split('\n'):
        if field in line and ':' in line:
            v = line.split(':', 1)[1].strip().replace('%', '')
            try:
                return float(v)
            except:
                pass
    return None

print("=" * 65)
print("  AI产业链全市场扫描")
print(f"  日期: {DATE} (最新交易日: {TD})")
print("=" * 65)

# 信号层
print("\n📡 景气信号")
try:
    hs = get_hot_stocks(TD)
    if isinstance(hs, list) and hs:
        print(f"  热股题材TOP5:")
        for h in hs[:5]:
            t = str(h)[:80] if isinstance(h, str) else str(h.get('name', h))[:80]
            print(f"    {t}")
except Exception as e:
    print(f"  热股: {str(e)[:50]}")

try:
    gn = get_global_news(TD)
    if isinstance(gn, list) and gn:
        print(f"  财联社快讯TOP3:")
        for n in gn[:3]:
            t = n.get('title', '') or n.get('content', '')[:80]
            print(f"    {t}")
except:
    pass

# 逐个分析
print("\n📊 个股扫描")
print(f"{'产业':<10} {'名称':<8} {'价':<8} {'PE':<8} {'换手':<6} {'笔':<4} {'中枢':<4} {'背驰':<4} {'买点':<4} {'走势'}")
print("-" * 75)

all_stocks = []
for industry, stocks in CORE_POOL.items():
    for name, code in stocks.items():
        try:
            fv = get_fundamentals(code, TD)
            ftext = fv if isinstance(fv, str) else str(fv)
            pe = extract_field(ftext, "PE (TTM)")
            pb = extract_field(ftext, "PB")
            change = extract_field(ftext, "Change")
            turnover = extract_field(ftext, "Turnover Rate")
            price = extract_field(ftext, "Price") or 0

            csv_str = get_stock_data(code, "2026-01-01", TD)
            df = pd.read_csv(StringIO(csv_str), comment="#")
            klines = klines_from_dataframe(df, date_col="Date",
                ohlc=("Open", "High", "Low", "Close", "Volume"))
            cr = analyze_chanlun(klines, ticker=code, trade_date=TD)

            bc = len(cr.bi_list)
            zc = len(cr.zhongshu_list)
            bec = len(cr.beichi_signals)
            buy = len([p for p in cr.buy_sell_points if "买" in p.type])

            all_stocks.append({
                "industry": industry, "name": name, "code": code,
                "price": price, "pe": pe or 0, "turnover": turnover or 0,
                "bi": bc, "zhongshu": zc, "beichi": bec, "buy": buy,
                "trend": cr.trend_type, "change": change or 0,
            })

            flag = ""
            if buy > 0: flag += "🟢买 "
            if bec > 0: flag += "⚠️背驰 "
            if pe and pe < 30: flag += "💰 "
            if change and abs(change) > 7: flag += "🔥 " if change > 0 else "❄️ "
            pe_s = f"{pe:.0f}" if pe else "N/A"
            print(f"{industry:<10} {name:<8} {price:<8.1f} {pe_s:<8} {turnover if turnover else 0:<6.1f} {bc:<4} {zc:<4} {bec:<4} {buy:<4} {flag or cr.trend_type[:12]}")

        except Exception as e:
            print(f"{industry:<10} {name:<8} {'❌':<8} {str(e)[:40]}")

# 排名
print("\n🏆 综合排名（买点>背驰>低PE>活跃度）")
all_stocks.sort(key=lambda x: (x["buy"] * 10 + x["beichi"] * 3 + (1 if 0 < x["pe"] < 30 else 0) * 2 + (1 if 3 < x["turnover"] < 15 else 0)), reverse=True)

print(f"{'排名':<4} {'产业':<10} {'名称':<8} {'价':<8} {'PE':<8} {'换手':<6} {'笔':<4} {'中枢':<4}")
print("-" * 60)
for i, s in enumerate(all_stocks[:10]):
    pe_s = f"{s['pe']:.0f}" if s['pe'] else "N/A"
    print(f"{i+1:<4} {s['industry']:<10} {s['name']:<8} {s['price']:<8.1f} {pe_s:<8} {s['turnover']:<6.1f} {s['bi']:<4} {s['zhongshu']:<4}")

print("\n✅ 扫描完成")
