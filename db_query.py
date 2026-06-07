#!/usr/bin/env python3
"""SQLite数据库命令行工具 - 查询A股数据库"""
import sys, sqlite3, json

DB_PATH = "/home/harrydolly/.hermes/astock_data.db"

def print_table(headers, rows):
    if not rows:
        print("(无数据)")
        return
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, v in enumerate(row):
            w = len(str(v))
            if w > col_widths[i]:
                col_widths[i] = w
    sep = "+" + "+".join("-" * (w+2) for w in col_widths) + "+"
    header_row = "| " + " | ".join(h.center(col_widths[i]) for i, h in enumerate(headers)) + " |"
    print(sep)
    print(header_row)
    print(sep)
    for row in rows:
        data_row = "| " + " | ".join(str(v).ljust(col_widths[i]) for i, v in enumerate(row)) + " |"
        print(data_row)
    print(sep)
    print(f"共 {len(rows)} 行")

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 db_query.py tables                    # 查看所有表")
        print("  python3 db_query.py sql \"SELECT ...\"         # 执行SQL")
        print("  python3 db_query.py hits                      # 查看最近扫描结果")
        print("  python3 db_query.py stock 000333              # 查看某只股票K线")
        print("  python3 db_query.py stats                     # 数据库统计")
        print("  python3 db_query.py search 三阴               # 搜索股票")
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cmd = sys.argv[1]
    
    if cmd == "tables":
        c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in c.fetchall()]
        print("数据库表:")
        for t in tables:
            c.execute(f"SELECT sql FROM sqlite_master WHERE name='{t}'")
            sql = c.fetchone()[0]
            print(f"\n  {t}:")
            print(f"    {sql}")
    
    elif cmd == "sql":
        sql = " ".join(sys.argv[2:])
        try:
            c.execute(sql)
            if sql.strip().upper().startswith("SELECT"):
                headers = [desc[0] for desc in c.description]
                rows = c.fetchall()
                print_table(headers, rows)
            else:
                conn.commit()
                print(f"执行成功，影响 {conn.total_changes} 行")
        except Exception as e:
            print(f"错误: {e}")
    
    elif cmd == "hits":
        c.execute("""SELECT scan_date, code, name, price, chg_today, zt_chg 
                     FROM scan_cache ORDER BY scan_date DESC, price""")
        rows = c.fetchall()
        if rows:
            print_table(["扫描日期", "代码", "名称", "价格", "当日涨跌", "涨停涨幅"], 
                       [(r[0], r[1], r[2], f"{r[3]:.2f}", f"{r[4]:+.1f}%", f"{r[5]:.1f}%") for r in rows])
        else:
            print("暂无扫描结果")
    
    elif cmd == "stock":
        code = sys.argv[2]
        c.execute("SELECT name FROM stocks WHERE code=?", (code,))
        name_row = c.fetchone()
        name = name_row[0] if name_row else code
        print(f"\n{name}({code}) 最近10条K线:")
        print(f"{'日期':12s} {'开盘':>8s} {'最高':>8s} {'最低':>8s} {'收盘':>8s} {'成交量':>10s}")
        print("-" * 60)
        c.execute("""SELECT date, open, high, low, close, volume 
                     FROM daily_klines WHERE code=? ORDER BY date DESC LIMIT 10""", (code,))
        for row in c.fetchall():
            print(f"{row[0]:12s} {row[1]:>8.2f} {row[2]:>8.2f} {row[3]:>8.2f} {row[4]:>8.2f} {row[5]:>10.0f}")
        c.execute("SELECT COUNT(*) FROM daily_klines WHERE code=?", (code,))
        cnt = c.fetchone()[0]
        print(f"\n共 {cnt} 条K线数据")
    
    elif cmd == "stats":
        c.execute("SELECT COUNT(*) FROM stocks")
        stocks = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT code) FROM daily_klines")
        with_data = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM daily_klines")
        total_k = c.fetchone()[0]
        c.execute("SELECT MIN(date), MAX(date) FROM daily_klines")
        dr = c.fetchone()
        c.execute("SELECT COUNT(*) FROM scan_cache")
        scans = c.fetchone()[0]
        print(f"数据库统计:")
        print(f"  股票总数: {stocks}只")
        print(f"  有日线数据的: {with_data}只")
        print(f"  日线总条数: {total_k}条")
        print(f"  日期范围: {dr[0]} ~ {dr[1]}")
        print(f"  扫描结果: {scans}条")
    
    elif cmd == "search":
        keyword = sys.argv[2]
        c.execute("SELECT code, name FROM stocks WHERE name LIKE ? OR code LIKE ? LIMIT 20",
                 (f"%{keyword}%", f"%{keyword}%"))
        rows = c.fetchall()
        if rows:
            print(f"搜索'{keyword}'结果:")
            print_table(["代码", "名称"], rows)
        else:
            print(f"未找到匹配'{keyword}'的股票")
    
    conn.close()

if __name__ == "__main__":
    main()
