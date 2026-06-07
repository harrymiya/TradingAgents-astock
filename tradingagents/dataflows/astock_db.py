#!/usr/bin/env python3
"""
A股日线数据库 - SQLite增量存储
"""
import sqlite3, os, json
from datetime import datetime, timedelta

DB_PATH = "/home/harrydolly/.hermes/astock_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 股票基本信息表
    c.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            code TEXT PRIMARY KEY,
            name TEXT,
            market TEXT,
            added_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # 日线K线表（用code+date做唯一键）
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_klines (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            amount REAL,
            PRIMARY KEY (code, date)
        )
    """)
    
    # 扫描结果缓存表
    c.execute("""
        CREATE TABLE IF NOT EXISTS scan_cache (
            scan_date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            formula_name TEXT,
            price REAL,
            chg_today REAL,
            zt_date TEXT,
            zt_chg REAL,
            PRIMARY KEY (scan_date, code)
        )
    """)
    
    # 索引
    c.execute("CREATE INDEX IF NOT EXISTS idx_kline_code ON daily_klines(code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kline_date ON daily_klines(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kline_code_date ON daily_klines(code, date)")
    
    conn.commit()
    conn.close()
    print(f"数据库已初始化: {DB_PATH}")

def get_stock_list(conn=None):
    """获取数据库中的股票列表"""
    close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        close = True
    c = conn.cursor()
    c.execute("SELECT code, name FROM stocks ORDER BY code")
    rows = c.fetchall()
    if close:
        conn.close()
    return rows

def save_stock_list(stocks):
    """批量保存股票列表 (stocks格式: list of (name, code))"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executemany(
        "INSERT OR IGNORE INTO stocks (code, name) VALUES (?, ?)",
        [(code, name) for name, code in stocks]
    )
    conn.commit()
    conn.close()

def get_missing_dates(code, start_date, end_date):
    """获取某只股票缺失的日期范围"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT date FROM daily_klines 
        WHERE code = ? AND date >= ? AND date <= ?
        ORDER BY date
    """, (code, start_date, end_date))
    existing = {row[0] for row in c.fetchall()}
    conn.close()
    return existing

def save_klines(code, klines_data):
    """批量保存K线数据"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    rows = []
    # klines_data: list of dicts with date, open, high, low, close, volume, amount
    for k in klines_data:
        rows.append((
            code,
            k.get('date', k.get('Date', '')),
            float(k.get('open', k.get('Open', 0))),
            float(k.get('high', k.get('High', 0))),
            float(k.get('low', k.get('Low', 0))),
            float(k.get('close', k.get('Close', 0))),
            float(k.get('volume', k.get('Volume', 0))),
            float(k.get('amount', k.get('Amount', 0))) if k.get('amount', k.get('Amount', 0)) else 0,
        ))
    
    c.executemany(
        """INSERT OR REPLACE INTO daily_klines (code, date, open, high, low, close, volume, amount)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        rows
    )
    conn.commit()
    conn.close()

def get_klines(code, start_date, end_date):
    """从数据库读取K线"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT date, open, high, low, close, volume, amount
        FROM daily_klines
        WHERE code = ? AND date >= ? AND date <= ?
        ORDER BY date
    """, (code, start_date, end_date))
    rows = c.fetchall()
    conn.close()
    return rows

def save_scan_result(scan_date, results):
    """保存扫描结果"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for r in results:
        c.execute(
            """INSERT OR REPLACE INTO scan_cache 
               (scan_date, code, name, formula_name, price, chg_today, zt_date, zt_chg)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (scan_date, r['code'], r['name'], r.get('formula', '三阴选股'),
             r['price'], r['chg_today'], r.get('zt_date', ''), r.get('zt_chg', 0))
        )
    conn.commit()
    conn.close()

def get_latest_scan(scan_date):
    """获取某次扫描结果"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT code, name, price, chg_today, zt_chg FROM scan_cache
        WHERE scan_date = ?
        ORDER BY chg_today
    """, (scan_date,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_db_stats():
    """数据库统计"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM stocks")
    stocks_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM daily_klines")
    klines_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT code) FROM daily_klines")
    kline_stocks = c.fetchone()[0]
    c.execute("SELECT MIN(date), MAX(date) FROM daily_klines")
    date_range = c.fetchone()
    conn.close()
    return {
        "stocks": stocks_cnt,
        "klines": klines_cnt,
        "stock_with_klines": kline_stocks,
        "date_range": date_range
    }

if __name__ == "__main__":
    init_db()
    print(get_db_stats())
