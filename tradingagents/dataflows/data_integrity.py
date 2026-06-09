#!/usr/bin/env python3
"""
A股全市场数据完整性检查 + 自动补全
在框架分析或全市场扫描前调用，确保DB日线数据是最新的。
"""
import os, sys, sqlite3, requests, json, time
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")

def check_db_integrity(target_date=None):
    """
    检查数据库完整性，返回缺失信息。
    
    Args:
        target_date: 目标日期 YYYY-MM-DD，None=最新交易日
    
    Returns:
        dict: {missing_stocks: [...], missing_dates: {...}, is_complete: bool}
    """
    today = datetime.now()
    if target_date:
        target = target_date
    else:
        # 取数据库最新日期
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT MAX(date) FROM daily_klines")
        max_d = c.fetchone()[0]
        conn.close()
        target = max_d if max_d else today.strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 总股票数
    cur.execute("SELECT COUNT(*) FROM stocks")
    total_stocks = cur.fetchone()[0]
    
    # 有日线数据的股票数
    cur.execute("SELECT COUNT(DISTINCT code) FROM daily_klines")
    stocks_with_data = cur.fetchone()[0]
    
    # 目标日期有多少股票有数据（只统计有日线数据的股票）
    cur.execute("SELECT COUNT(*) FROM daily_klines WHERE date = ?", (target,))
    stocks_at_target = cur.fetchone()[0]
    
    # 缺目标日数据的股票（只针对有日线数据但缺最新日的）
    cur.execute("""
        SELECT DISTINCT d.code, COALESCE(s.name, '') FROM daily_klines d
        LEFT JOIN stocks s ON d.code = s.code
        WHERE d.code NOT IN (SELECT code FROM daily_klines WHERE date = ?)
        AND d.code NOT LIKE '688%'
        AND d.code NOT LIKE '4%'
        AND d.code NOT LIKE '83%'
        AND d.code NOT LIKE '87%'
        AND d.code NOT LIKE '8%'
        ORDER BY d.code
    """, (target,))
    missing_stocks = cur.fetchall()
    
    # 检查每只股票的数据记录数
    cur.execute("""
        SELECT code, COUNT(*) as cnt FROM daily_klines 
        GROUP BY code HAVING cnt < 30
        ORDER BY cnt ASC LIMIT 20
    """)
    short_stocks = cur.fetchall()
    
    conn.close()
    
    return {
        "target_date": target,
        "total_stocks": total_stocks,
        "stocks_with_data": stocks_with_data,
        "stocks_at_target": stocks_at_target,
        "missing_count": len(missing_stocks),
        "missing_stocks": missing_stocks[:20],  # 只返回前20
        "short_data_stocks": short_stocks,
        "is_complete": stocks_at_target >= stocks_with_data * 0.98  # 98%以上认为完整
    }

def sync_missing_data(missing_stocks, target_date):
    """
    从新浪HTTP补缺失的日线数据。
    missing_stocks: list of (code, name)
    target_date: str YYYY-MM-DD
    """
    from tradingagents.dataflows.astock_db import save_klines
    
    # 补数据区间：取stock已有的最新日期+1 到 target_date
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    success = 0
    fail = 0
    total = len(missing_stocks)
    
    for i, (code, name) in enumerate(missing_stocks):
        # 获取该股票已有的最新日期
        cur.execute("SELECT MAX(date) FROM daily_klines WHERE code = ?", (code,))
        last = cur.fetchone()[0]
        
        if last and last >= target_date:
            continue  # 已有数据
        
        start = last if last else "2026-04-01"
        # 需要新拉的日期范围
        print(f"  [{i+1}/{total}] {code} {name}: {start}~{target_date}", end="...", flush=True)
        
        # 从新浪HTTP拉
        try:
            # 统一处理code格式
            code_num = code.lstrip('0')
            url = f"https://quotes.sina.com.cn/usstock/api/jsonp.php/var%20_{code_num}_daily=/US_MinKService.getDailyK?symbol={code_num}&type=candle&num=120"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://finance.sina.com.cn/"
            }
            
            r = requests.get(url, headers=headers, timeout=10)
            r.encoding = 'utf-8'
            
            # Parse JSONP response
            text = r.text.strip()
            if text.startswith('var '):
                start_idx = text.index('(') + 1
                end_idx = text.rindex(')')
                json_str = text[start_idx:end_idx]
                data = json.loads(json_str)
                
                klines = []
                for item in data.get('data', []):
                    d = item[0]  # date string
                    if d < start or d > target_date:
                        continue
                    klines.append({
                        'date': d,
                        'open': float(item[1]),
                        'high': float(item[2]),
                        'low': float(item[3]),
                        'close': float(item[4]),
                        'volume': float(item[5]) * 100,  # 手→股
                        'amount': 0,  # 新浪不提供
                    })
                
                if klines:
                    save_klines(code, klines)
                    print(f" ✓ {len(klines)}条")
                    success += 1
                else:
                    print(" 无新数据")
                    success += 1  # 不需要拉也算成功
            else:
                print(f" 格式异常")
                fail += 1
        except Exception as e:
            print(f" 失败: {e}")
            fail += 1
        
        if (i+1) % 50 == 0:
            time.sleep(1)  # 每50只休息1秒
    
    conn.close()
    return success, fail

def ensure_data(target_date=None):
    """一键：检查完整性→自动补全"""
    print("=" * 60)
    print("  A股数据完整性检查")
    print("=" * 60)
    
    report = check_db_integrity(target_date)
    print(f"  目标日期: {report['target_date']}")
    print(f"  总股票: {report['total_stocks']}")
    print(f"  有日线数据: {report['stocks_with_data']}")
    print(f"  目标日有数据: {report['stocks_at_target']}")
    
    if report['is_complete']:
        print(f"\n  ✅ 数据完整 ({report['stocks_at_target']}/{report['total_stocks']})")
    else:
        print(f"\n  ⚠️ 缺失 {report['missing_count']} 只")
        if report['missing_stocks']:
            print(f"  例如：")
            for c, n in report['missing_stocks'][:5]:
                print(f"    - {c} {n}")
        
        print(f"\n  🔄 开始自动补全...")
        s, f = sync_missing_data(report['missing_stocks'], report['target_date'])
        print(f"\n  ✅ 补全完成: 成功{s}, 失败{f}")
    
    if report['short_data_stocks']:
        print(f"\n  ⚠️ {len(report['short_data_stocks'])}只股票记录数不足30条:")
        for c, cnt in report['short_data_stocks'][:5]:
            print(f"    - {c}: {cnt}条")
    
    return report

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    ensure_data(target)
