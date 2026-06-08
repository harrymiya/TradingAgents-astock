#!/usr/bin/env python3
"""
收盘日线同步：mootdx通达信TCP → SQLite
每个交易日15:05自动执行

用法:
  python3 sync_close.py                              # 自动同步最新日期
  python3 sync_close.py 2026-06-08                   # 同步指定日期
"""
import sys, os, time, sqlite3
from datetime import datetime, timedelta

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")

# 通达信服务器（从connect.cfg提取，最快的几个）
TDX_SERVERS = [
    ('202.108.253.139', 80),
    ('202.108.253.158', 80),
    ('180.153.18.170', 7709),
    ('115.238.56.198', 7709),
    ('218.75.126.9', 7709),
    ('180.153.18.172', 80),
]

# 排除前缀
EXCLUDE_PREFIXES = ('688', '4', '83', '87', '8')

def get_client(server_idx=0):
    """获取mootdx客户端，自动切换服务器"""
    from mootdx.quotes import Quotes
    ip, port = TDX_SERVERS[server_idx % len(TDX_SERVERS)]
    try:
        return Quotes.factory(market='std', tcp=(ip, port, True)), server_idx
    except Exception as e:
        if server_idx < len(TDX_SERVERS) * 2:
            time.sleep(1)
            return get_client(server_idx + 1)
        raise

def get_stock_list():
    """获取需要同步的股票列表"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("""
        SELECT DISTINCT d.code, COALESCE(s.name, '') FROM daily_klines d
        LEFT JOIN stocks s ON d.code = s.code
        WHERE d.code NOT LIKE '688%' AND d.code NOT LIKE '4%'
        AND d.code NOT LIKE '83%' AND d.code NOT LIKE '87%' AND d.code NOT LIKE '8%'
        ORDER BY d.code
    """)
    stocks = cur.fetchall()
    conn.close()
    return stocks

def get_existing(target_date):
    """查询DB中已有该日期的股票"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT DISTINCT code FROM daily_klines WHERE date=?", (target_date,))
    existing = {r[0] for r in cur.fetchall()}
    conn.close()
    return existing

def save_kline(code, date_str, row):
    """写入单条K线"""
    conn = sqlite3.connect(DB_PATH)
    try:
        vol = float(row.get('volume', 0))
        amt = float(row.get('amount', 0))
        if amt == 0 and vol > 0:
            amt = vol * 100 * (float(row.get('open', 0)) + float(row.get('close', 0))) / 2
        conn.execute(
            """INSERT OR REPLACE INTO daily_klines 
               (code, date, open, high, low, close, volume, amount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, date_str,
             float(row.get('open', 0)), float(row.get('high', 0)),
             float(row.get('low', 0)), float(row.get('close', 0)),
             vol, amt)
        )
        conn.commit()
        return True
    except Exception as e:
        return False
    finally:
        conn.close()

def sync(target_date=None):
    """主同步函数"""
    if target_date is None:
        # 默认为最新完整交易日（今天或昨天）
        today = datetime.now()
        if today.weekday() >= 5:  # 周末
            target_date = (today - timedelta(days=today.weekday() - 4)).strftime("%Y-%m-%d")
        else:
            # 如果是15:05之后，同步今天；否则同步昨天
            if today.hour > 15 or (today.hour == 15 and today.minute >= 5):
                target_date = today.strftime("%Y-%m-%d")
            else:
                target_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    
    print(f"{'='*55}")
    print(f"  收盘日线同步: {target_date}")
    print(f"  时间: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}")
    
    # 获取股票列表
    stocks = get_stock_list()
    existing = get_existing(target_date)
    to_sync = [(c, n) for c, n in stocks if c not in existing]
    
    print(f"  总股票: {len(stocks)}")
    print(f"  已有: {len(existing)}")
    print(f"  待同步: {len(to_sync)}")
    print()
    
    if not to_sync:
        print("  ✅ 全部已同步，无需操作")
        return
    
    # 获取mootdx客户端
    client, server_idx = get_client()
    ip, port = TDX_SERVERS[server_idx % len(TDX_SERVERS)]
    print(f"  服务器: {ip}:{port}")
    print()
    
    synced = 0
    failed = 0
    t0 = time.time()
    
    for i, (code, name) in enumerate(to_sync, 1):
        try:
            df = client.bars(symbol=code, frequency=9, start=0, count=200)
            if df is not None and len(df) > 0:
                target_rows = df[df.index >= target_date]
                if len(target_rows) > 0:
                    row = target_rows.iloc[-1]
                    if save_kline(code, target_date, row):
                        synced += 1
                    else:
                        failed += 1
                else:
                    failed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            # 如果连接断开，重新初始化客户端
            if 'Connection' in str(e) or 'closed' in str(e):
                try:
                    client, server_idx = get_client(server_idx + 1)
                    ip, port = TDX_SERVERS[server_idx % len(TDX_SERVERS)]
                except:
                    pass
        
        if i % 200 == 0 or i == len(to_sync):
            el = time.time() - t0
            pct = i * 100 // len(to_sync)
            eta = (el / i) * (len(to_sync) - i) / 60 if i > 0 else 0
            print(f"  [{i:>5d}/{len(to_sync)}] {pct:>2d}% 同步{synced} 失败{failed} {el:.0f}s ETA{eta:.0f}min")
    
    # 最终统计
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT COUNT(*), MAX(date) FROM daily_klines")
    cnt, maxd = cur.fetchone()
    cur2 = conn.execute("SELECT COUNT(DISTINCT code) FROM daily_klines")
    codes_cnt = cur2.fetchone()[0]
    conn.close()
    
    el = time.time() - t0
    print(f"\n{'='*55}")
    print(f"  ✅ 同步完成!")
    print(f"  同步: {synced} | 失败: {failed} | 耗时: {el:.0f}s")
    print(f"  数据库: {cnt}条日线, {codes_cnt}只股票")
    print(f"  最新日期: {maxd}")
    print(f"{'='*55}")


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    sync(date_arg)
