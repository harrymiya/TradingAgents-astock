#!/usr/bin/env python3
"""A股日线数据增量同步脚本。

专职：从新浪/腾讯HTTP接口拉取最新日线K线，存入SQLite数据库。
每次只拉缺失日期，已存在的数据秒跳过。

用法:
    # 首次全量同步（所有股票拉最近60个交易日）
    cd /home/harrydolly/code/TradingAgents-astock
    source .venv/bin/activate
    python3 /path/to/sync_to_db.py --full

    # 每日增量同步（只拉最新数据）
    python3 /path/to/sync_to_db.py

    # 指定日期范围
    python3 /path/to/sync_to_db.py --start 2026-06-01 --end 2026-06-07

    # 只同步特定股票
    python3 /path/to/sync_to_db.py --codes 000001,000002,600000
"""

import sys
import os
import argparse
import time
from datetime import datetime, timedelta

# 项目路径
PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

# 数据库模块
from tradingagents.dataflows.astock_db import (
    DB_PATH,
    get_stock_list,
    save_stock_list,
    save_klines,
    get_missing_dates,
    get_db_stats,
    init_db,
)
from tradingagents.dataflows.a_stock import get_stock_data


def fetch_stock_list_from_sina():
    """从新浪获取全市场股票列表"""
    print("📡 正在从新浪获取全市场股票列表...")
    import urllib.request
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/StockService.getStockNames"
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=30)
    data = resp.read().decode('gbk')
    
    stocks = []
    for item in data.split('","'):
        parts = item.strip('"[]').split(',')
        if len(parts) >= 2:
            name, code = parts[0], parts[1]
            name = name.strip('"')
            code = code.strip('"\'')
            if code.isdigit() and len(code) == 6:
                stocks.append((name, code))
    
    print(f"  获取到 {len(stocks)} 只股票")
    return stocks


def sync_all_stocks(start_date, end_date, codes=None, max_stocks=None, skip_existing=True, verbose=True):
    """全市场增量同步"""
    # 先初始化数据库
    init_db()
    
    # 获取股票列表
    if codes:
        # 指定股票
        db_stocks = get_stock_list()
        db_map = {s[0]: s[1] for s in db_stocks}
        stocks = []
        for c in codes:
            c = c.strip()
            if c in db_map:
                stocks.append((db_map[c], c))
            else:
                stocks.append((c, c))
    else:
        # 同步最新的股票列表到数据库
        print("📝 更新股票列表...")
        sina_stocks = fetch_stock_list_from_sina()
        save_stock_list(sina_stocks)
        stocks = get_stock_list()
    
    if max_stocks:
        stocks = stocks[:max_stocks]
    
    total = len(stocks)
    print(f"\n{'='*60}")
    print(f"  A股日线数据同步")
    print(f"  目标: {total} 只股票")
    print(f"  日期: {start_date} ~ {end_date}")
    print(f"  跳过已有: {'✅' if skip_existing else '❌'}")
    print(f"{'='*60}\n")
    
    synced = 0
    skipped = 0
    failed = 0
    start_time = time.time()
    
    for i, (name, code) in enumerate(stocks, 1):
        # 跳过北交所和科创板（数据意义不大）
        if code.startswith('83') or code.startswith('87') or code.startswith('4'):
            skipped += 1
            continue
        
        if skip_existing:
            existing = get_missing_dates(code, start_date, end_date)
            if existing:
                skip_dates = len(existing)
                if verbose and (i % 500 == 0 or i == 1 or i == total):
                    progress_pct = (time.time() - start_time) / i * (total - i) if i > 0 else 0
                    remaining_min = progress_pct / 60 if progress_pct > 0 else 0
                    print(f"  [{i}/{total}] {name}({code}) — 已有{skip_dates}天数据，跳过")
                    if i % 500 == 0:
                        elapsed = time.time() - start_time
                        print(f"    同步进度: {i}/{total} 已同步{synced}只 已跳过{skipped}只 耗时{elapsed:.0f}s 预估剩余{remaining_min:.0f}分钟")
                skipped += 1
                continue
        
        try:
            csv_str = get_stock_data(code, start_date, end_date)
            if csv_str and len(csv_str) > 50:
                from io import StringIO
                import pandas as pd
                df = pd.read_csv(StringIO(csv_str), comment='#')
                
                # ⚠️ 新浪HTTP接口不返回Amount(成交额)列
                # CSV列名: Date, Open, High, Low, Close, Volume
                # 用 Volume*100*(Open+Close)/2 估算成交额
                has_amount = 'Amount' in df.columns
                klines = []
                for _, row in df.iterrows():
                    vol = float(row['Volume']) if 'Volume' in row else 0
                    op = float(row['Open'])
                    cl = float(row['Close'])
                    if has_amount:
                        amt = float(row['Amount']) if not pd.isna(row.get('Amount', 0)) else 0
                    else:
                        amt = vol * 100 * (op + cl) / 2
                    klines.append({
                        'date': str(row['Date']),
                        'open': op,
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'close': cl,
                        'volume': vol,
                        'amount': amt,
                    })
                
                save_klines(code, klines)
                synced += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            if verbose:
                pass  # 静默失败太多，不打印
        
        if verbose and (i % 200 == 0 or i == total):
            elapsed = time.time() - start_time
            print(f"  进度: [{i}/{total}] 已同步{synced}只 失败{failed}只 跳过{skipped}只 已用{elapsed:.0f}s")
    
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  同步完成!")
    print(f"  处理: {total} 只")
    print(f"  同步: {synced} 只")
    print(f"  失败: {failed} 只")
    print(f"  跳过: {skipped} 只")
    print(f"  耗时: {elapsed:.0f} 秒 ({elapsed/60:.1f} 分钟)")
    
    # 打印统计
    stats = get_db_stats()
    print(f"\n  数据库状态:")
    print(f"    股票总数: {stats['stocks']} 只")
    print(f"    已有日线: {stats['stock_with_klines']} 只")
    print(f"    日线条数: {stats['klines']} 条")
    print(f"    日期范围: {stats['date_range'][0]} ~ {stats['date_range'][1]}")
    print(f"{'='*60}")
    
    return synced, failed, skipped


def main():
    parser = argparse.ArgumentParser(description="A股日线数据增量同步")
    parser.add_argument("--full", action="store_true", help="首次全量同步（拉最近60个交易日）")
    parser.add_argument("--start", default=None, help="数据起始日 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="数据截止日 YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=60, help="拉取的交易日天数（默认60）")
    parser.add_argument("--codes", default=None, help="指定股票代码，逗号分隔")
    parser.add_argument("--max", type=int, default=None, help="最多同步多少只（调试用）")
    parser.add_argument("--verbose", action="store_true", default=True)
    args = parser.parse_args()
    
    # 计算日期范围
    today = datetime.now().strftime("%Y-%m-%d")
    
    if args.full:
        # 首次全量：从今日往前推60个交易日（约3个月）
        start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        end = today
        print("🔄 全量同步模式 — 拉取近3个月数据")
    else:
        # 增量同步：检查数据库最新日期，从最新+1天到今天
        stats = get_db_stats()
        if stats['date_range'][1]:
            latest = stats['date_range'][1]
            # 最新日期 + 1天
            latest_dt = datetime.strptime(latest, "%Y-%m-%d")
            start = (latest_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        end = today
        print(f"🔄 增量同步模式 — 从{start}拉到{end}")
    
    if args.start:
        start = args.start
    if args.end:
        end = args.end
    
    codes = args.codes.split(',') if args.codes else None
    
    sync_all_stocks(
        start_date=start,
        end_date=end,
        codes=codes,
        max_stocks=args.max,
        skip_existing=not args.full,  # 增量模式跳过已有
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
