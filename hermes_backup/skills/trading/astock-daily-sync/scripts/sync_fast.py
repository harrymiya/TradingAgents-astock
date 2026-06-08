#!/usr/bin/env python3
"""
快速增量同步：收盘后将当天腾讯日线数据写入SQLite。
使用 INSERT OR REPLACE 确保不会产生重复数据。

用法:
  python3 sync_fast.py                          # 自动同步DB最晚日+1到昨天
  python3 sync_fast.py 2026-06-08               # 同步指定日期
  python3 sync_fast.py 2026-06-06 2026-06-08    # 同步日期范围
  python3 sync_fast.py --batch 50               # 分批并发，每批50只（默认）
"""
import sys, os, time, json, urllib.request
from datetime import datetime, timedelta

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")


def get_db_latest_date():
    """获取DB中最晚日期"""
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("SELECT MAX(date) FROM daily_klines")
        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def get_db_stats():
    """获取DB统计"""
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("SELECT COUNT(*) FROM daily_klines")
        klines = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(DISTINCT code) FROM daily_klines")
        stocks = cur.fetchone()[0]
        cur = conn.execute("SELECT MIN(date), MAX(date) FROM daily_klines")
        dr = cur.fetchone()
        conn.close()
        return {"klines": klines, "stock_with_klines": stocks,
                "date_range": (dr[0] or "", dr[1] or "")}
    except Exception:
        return {"klines": 0, "stock_with_klines": 0, "date_range": ("", "")}


def get_stocks_for_sync():
    """获取需要同步的股票列表（排除科创板/北交所）"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("""
        SELECT DISTINCT d.code, COALESCE(s.name, '') FROM daily_klines d
        LEFT JOIN stocks s ON d.code = s.code
        ORDER BY d.code
    """)
    stocks = cur.fetchall()
    conn.close()
    # 过滤
    filtered = [(n, c) for n, c in stocks
                if not c.startswith('83') and not c.startswith('87')
                and not c.startswith('4') and not c.startswith('688')]
    return filtered


def fetch_tencent_kline_full(code):
    """从腾讯HTTP拉取全部800天日K线（前复权）
    返回 [{date, open, high, low, close, volume, amount}, ...]
    """
    prefix = "sh" if code.startswith("6") else "sz"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,800,qfq"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    })
    resp = urllib.request.urlopen(req, timeout=10)
    text = resp.read().decode('utf-8')
    data = json.loads(text)
    
    # 解析腾讯返回的复杂嵌套结构
    def _dig(obj, *keys):
        for k in keys:
            if isinstance(obj, dict) and k in obj:
                obj = obj[k]
            else:
                return None
        return obj
    
    code_key = f"{prefix}{code}"
    top = data.get("data") or data.get(code_key) or data
    # 可能 top 已经是 code_key 下的内容
    if isinstance(top, dict) and code_key in top:
        top = top[code_key]
    
    # 查找日线数组（可能是 day 或 qfqday）
    days = None
    for key in ("qfqday", "day", "klines"):
        if isinstance(top, dict) and key in top:
            days = top[key]
            break
    
    # 如果嵌套更深一层
    if not days and isinstance(top, dict):
        for key in ("data", "list", "items"):
            if key in top:
                inner = top[key]
                if isinstance(inner, dict):
                    for k2 in ("qfqday", "day", "klines", "kline"):
                        if k2 in inner:
                            days = inner[k2]
                            break
                break
    
    if not days or not isinstance(days, list):
        return []
    
    klines = []
    for item in days:
        if not isinstance(item, (list, tuple)) or len(item) < 5:
            continue
        try:
            vol = float(item[5]) if len(item) > 5 and item[5] else 0
            amt = float(item[6]) if len(item) > 6 and item[6] else 0
            if amt == 0 and vol > 0:
                amt = vol * 100 * (float(item[1]) + float(item[2])) / 2
            klines.append({
                "date": str(item[0]),
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "volume": vol,
                "amount": amt,
            })
        except (ValueError, IndexError):
            continue
    
    return klines


def save_klines_batch(code, klines):
    """批量保存K线（INSERT OR REPLACE去重）"""
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = []
        for k in klines:
            rows.append((
                code,
                k["date"],
                k["open"], k["high"], k["low"],
                k["close"], k["volume"], k["amount"],
            ))
        conn.executemany(
            """INSERT OR REPLACE INTO daily_klines 
               (code, date, open, high, low, close, volume, amount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows
        )
        conn.commit()
        conn.close()
        return len(rows)
    except Exception:
        return 0


def save_klines_single(code, kline):
    """保存单条K线"""
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT OR REPLACE INTO daily_klines 
               (code, date, open, high, low, close, volume, amount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, kline["date"], kline["open"], kline["high"],
             kline["low"], kline["close"], kline["volume"], kline["amount"])
        )
        conn.commit()
        conn.close()
        return 1
    except Exception:
        return 0


def sync_incremental(start_date=None, end_date=None, batch_size=50):
    """增量同步指定日期范围"""
    import sqlite3
    
    # 确定日期范围
    today = datetime.now().strftime("%Y-%m-%d")
    if end_date is None:
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    if start_date is None:
        latest = get_db_latest_date()
        if latest:
            start_date = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start_date = "2026-04-01"  # 全量
    
    # 如果 start_date > end_date，说明没有新数据需要同步
    if start_date > end_date:
        print(f"ℹ️  DB最新 {latest}，无需同步（{start_date} > {end_date}）")
        return True
    
    # 检查是否为交易日（粗略：跳过周末）
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    ed = datetime.strptime(end_date, "%Y-%m-%d")
    if sd.weekday() >= 5 and ed.weekday() >= 5:
        print(f"ℹ️  周末跳过: {start_date} ~ {end_date}")
        return True
    
    print(f"📝 增量同步: {start_date} ~ {end_date}")
    print(f"   目标日期: {(ed - sd).days + 1}天")
    
    # 检查哪些日期已有数据
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT DISTINCT date FROM daily_klines WHERE date >= ? AND date <= ?",
        (start_date, end_date)
    )
    existing_dates = {r[0] for r in cur.fetchall()}
    conn.close()
    
    print(f"   已有数据日期: {sorted(existing_dates) if existing_dates else '无'}")
    
    # 获取股票列表
    stocks = get_stocks_for_sync()
    total = len(stocks)
    print(f"   股票数量: {total}只")
    
    # 分批同步
    written_count = 0
    failed_stocks = []
    
    for batch_start in range(0, total, batch_size):
        batch = stocks[batch_start:batch_start + batch_size]
        synced = 0
        failed = 0
        batch_written = 0
        
        for name, code in batch:
            try:
                klines = fetch_tencent_kline_full(code)
                if not klines:
                    continue
                # 过滤目标日期范围
                target = [k for k in klines if start_date <= k["date"] <= end_date]
                if not target:
                    continue
                # 只保存没有的日期
                to_save = [k for k in target if k["date"] not in existing_dates]
                if to_save:
                    n = save_klines_batch(code, to_save)
                    if n > 0:
                        batch_written += n
                    synced += 1
                else:
                    pass  # 数据已存在，跳过
            except Exception as e:
                failed += 1
                if len(failed_stocks) < 10:
                    failed_stocks.append(code)
        
        written_count += batch_written
        elapsed = time.time()
        
        # 显示进度
        pct = min(100, (batch_start + len(batch)) * 100 // total)
        since_start = time.time() - (getattr(sync_incremental, '_t0', time.time()))
        print(f"  [{batch_start + len(batch):>5d}/{total}] {pct:>2d}% "
              f"写入{batch_written}条 | "
              f"失败{failed} | "
              f"{since_start:.0f}s")
        
        # 跨批次间隔
        if batch_start + batch_size < total:
            time.sleep(0.5)
    
    sync_incremental._t0 = time.time()
    
    # 最终统计
    stats = get_db_stats()
    print(f"\n✅ 同步完成!")
    print(f"   新增写入: {written_count}条K线")
    print(f"   数据库: {stats['stock_with_klines']}只股票, {stats['klines']}条K线")
    print(f"   日期范围: {stats['date_range'][0]} ~ {stats['date_range'][1]}")
    if failed_stocks:
        print(f"   失败股票({len(failed_stocks)}只): {failed_stocks[:5]}...")
    
    return True


if __name__ == "__main__":
    args = sys.argv[1:]
    
    start = None
    end = None
    batch_size = 50
    
    if args and args[0] == "--batch":
        if len(args) > 1:
            batch_size = int(args[1])
        args = args[2:]
    
    if args:
        start = args[0]
        end = args[1] if len(args) > 1 else start
    
    sync_incremental(start, end, batch_size)
