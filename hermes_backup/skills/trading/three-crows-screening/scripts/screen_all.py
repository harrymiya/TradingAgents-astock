#!/usr/bin/env python3
"""
三阴选股 - 全市场扫描脚本

从新浪/腾讯HTTP接口获取A股数据，全量扫描三阴选股信号。

用法:
    cd /home/harrydolly/code/TradingAgents-astock
    source .venv/bin/activate
    python3 /path/to/screen_all.py
    
选项:
    --start YYYY-MM-DD  数据起始日 (默认: 2026-05-01)
    --end   YYYY-MM-DD  数据截止日 (默认: 当天)
    --codes 指定代码列表，逗号分隔
"""

import sys
import os
import argparse
import pandas as pd
from io import StringIO

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from three_crows import three_black_crows_screen, is_valid_ticker

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)


def get_data_from_a_stock(code, start, end):
    from tradingagents.dataflows.a_stock import get_stock_data
    return get_stock_data(code, start, end)


def get_default_pool():
    return [
        ("招商银行", "600036"), ("工商银行", "601398"), ("建设银行", "601939"),
        ("农业银行", "601288"), ("中国银行", "601988"), ("兴业银行", "601166"),
        ("中国平安", "601318"), ("交通银行", "601328"),
        ("贵州茅台", "600519"), ("五粮液", "000858"), ("泸州老窖", "000568"),
        ("山西汾酒", "600809"), ("洋河股份", "002304"),
        ("美的集团", "000333"), ("格力电器", "000651"), ("海尔智家", "600690"),
        ("立讯精密", "002475"), ("歌尔股份", "002241"),
        ("北方华创", "002371"), ("韦尔股份", "603501"), ("士兰微", "600460"),
        ("宁德时代", "300750"), ("比亚迪", "002594"), ("阳光电源", "300274"),
        ("恒瑞医药", "600276"), ("迈瑞医疗", "300760"), ("药明康德", "603259"),
        ("中兴通讯", "000063"), ("中际旭创", "300308"),
        ("海康威视", "002415"), ("中科曙光", "603019"), ("科大讯飞", "002230"),
        ("中航沈飞", "600760"), ("航发动力", "600893"),
        ("汇川技术", "300124"), ("三一重工", "600031"),
        ("国电南瑞", "600406"), ("许继电气", "000400"),
        ("紫金矿业", "601899"), ("洛阳钼业", "603993"),
        ("通威股份", "600438"), ("隆基绿能", "601012"),
        ("万科A", "000002"), ("保利发展", "600048"),
        ("中信证券", "600030"), ("东方财富", "300059"),
        ("中国石油", "601857"), ("中国石化", "600028"),
        ("中国神华", "601088"), ("陕西煤业", "601225"),
        ("上汽集团", "600104"), ("长城汽车", "601633"),
        ("顺丰控股", "002352"), ("京沪高铁", "601816"),
        ("海螺水泥", "600585"), ("东方雨虹", "002271"),
        ("伊利股份", "600887"), ("海天味业", "603288"),
        ("牧原股份", "002714"), ("中国中免", "601888"),
        ("万华化学", "600309"), ("长江电力", "600900"),
        ("紫光股份", "000938"), ("用友网络", "600588"),
        ("宝钢股份", "600019"), ("中国建筑", "601668"),
        ("中国移动", "600941"), ("中国电信", "601728"),
    ]


def main():
    parser = argparse.ArgumentParser(description="三阴选股全市场扫描")
    parser.add_argument("--start", default="2026-05-01", help="数据起始日期")
    parser.add_argument("--end", default=None, help="数据截止日期")
    parser.add_argument("--codes", default=None, help="指定代码列表，逗号分隔")
    parser.add_argument("--verbose", action="store_true", default=True)
    args = parser.parse_args()

    from datetime import datetime
    end_date = args.end or datetime.now().strftime("%Y-%m-%d")

    if args.codes:
        pool = [(c, c) for c in args.codes.split(",")]
    else:
        pool = get_default_pool()

    pool = [(n, c) for n, c in pool if is_valid_ticker(c, n)]

    print(f"📡 三阴选股 - 全市场扫描")
    print(f"   数据范围: {args.start} ~ {end_date}")
    print(f"   候选池: {len(pool)}只\n")

    hits = []
    total = len(pool)

    for i, (name, code) in enumerate(pool):
        if args.verbose and (i + 1) % 30 == 0:
            print(f"   进度: {i+1}/{total}")
        try:
            csv_str = get_data_from_a_stock(code, args.start, end_date)
            if not csv_str or len(csv_str) < 50:
                continue
            df = pd.read_csv(StringIO(csv_str), comment='#')
            if len(df) < 10:
                continue
            if three_black_crows_screen(df):
                cur = float(df['Close'].values[-1])
                chg_t = ((cur / float(df['Close'].values[-2])) - 1) * 100
                chg_5 = ((cur / float(df['Close'].values[-6])) - 1) * 100 if len(df) > 6 else 0
                hits.append({"name": name, "code": code, "price": cur, "chg_today": chg_t, "chg_5d": chg_5})
                print(f"  ✅ {name}({code}) 价{cur:.2f} 当日{chg_t:+.2f}% 近5日{chg_5:+.2f}%")
                for j in range(5, 0, -1):
                    d = df.iloc[-j]
                    print(f"     T-{j} {d['Date']} O{float(d['Open']):.2f} H{float(d['High']):.2f} L{float(d['Low']):.2f} C{float(d['Close']):.2f}")
        except Exception as e:
            pass

    print(f"\n{'='*50}")
    print(f"扫描完成: {total}只 -> 命中 {len(hits)}只")
    for h in hits:
        print(f"  {h['name']}({h['code']}) 价{h['price']:.2f} 当日{h['chg_today']:+.1f}% 近5日{h['chg_5d']:+.1f}%")


if __name__ == "__main__":
    main()
