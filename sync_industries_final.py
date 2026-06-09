#!/usr/bin/env python3
"""
行业数据同步 - 单线程稳定版
每100只重新建立mootdx连接，避免连接泄漏
使用默认连接（自动选最快服务器）
"""
import sqlite3, os, re, sys, time

DB = '/home/harrydolly/.hermes/astock_data.db'
sys.path.insert(0, '/home/harrydolly/code/TradingAgents-astock')
from mootdx.quotes import Quotes

def get_industry(code):
    """获取单只股票的行业分类"""
    f10 = Quotes.factory(market='std').F10(code, 'industry_analysis')
    hys = f10.get('行业分析', '') if isinstance(f10, dict) else str(f10)
    l1 = l2 = l3 = None
    if isinstance(hys, str):
        for line in hys.split('\n'):
            m = re.search(r'所属研究行业[：:]\s*([^\r\n(]+)', line)
            if m:
                parts = re.split(r'[/\uFF0F]', m.group(1).strip())
                parts = [p.strip().lstrip(':') for p in parts if p.strip()]
                if len(parts) >= 1: l1 = parts[0]
                if len(parts) >= 2: l2 = parts[1]
                if len(parts) >= 3: l3 = parts[2]
                break
            m2 = re.search(r'所属行业[：:]\s*([^\r\n(]+)', line)
            if m2:
                parts = re.split(r'[/\uFF0F]', m2.group(1).strip())
                parts = [p.strip().lstrip(':') for p in parts if p.strip()]
                if len(parts) >= 1: l1 = parts[0]
                break
    return l1, l2, l3

def main():
    # 获取需要处理的股票
    conn = sqlite3.connect(DB)
    codes = [r[0] for r in conn.execute(
        "SELECT DISTINCT f.code FROM feat f "
        "WHERE f.code NOT LIKE '688%' "
        "AND f.code NOT LIKE '4%' "
        "AND f.code NOT LIKE '83%' AND f.code NOT LIKE '87%' "
        "AND f.code NOT IN (SELECT code FROM stock_industries) "
        "ORDER BY f.code"
    ).fetchall()]
    conn.close()
    
    total = len(codes)
    print(f'📡 需要同步: {total}只股票', flush=True)
    if not codes:
        print('✅ 全部已同步', flush=True)
        return
    
    conn = sqlite3.connect(DB)
    conn.execute('PRAGMA synchronous=OFF')
    conn.execute('PRAGMA cache_size=-64000')
    
    t0 = time.time()
    success = 0
    batch_success = 0
    
    for j, code in enumerate(codes):
        # 每100只重新建立连接（防止连接泄漏）
        if j % 100 == 0:
            # 重新预热
            if j > 0:
                conn.commit()
            try:
                dummy = Quotes.factory(market='std')
                dummy.F10('000001', 'industry_analysis')  # 预热
            except:
                pass
        
        try:
            # 每只股票新连接（mootdx内部会复用TCP连接池）
            l1, l2, l3 = get_industry(code)
            
            if l1 or l2 or l3:
                conn.execute(
                    "INSERT OR REPLACE INTO stock_industries (code, industry_l1, industry_l2, industry_l3, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                    (code, l1, l2, l3)
                )
                success += 1
                batch_success += 1
        except Exception as e:
            pass
        
        if (j+1) % 100 == 0 or j+1 == total:
            conn.commit()
            elapsed = time.time() - t0
            rate = (j+1) / max(elapsed, 1)
            remain_s = (total-j-1) / max(rate, 1)
            per_stock = elapsed / max(j+1, 1)
            print(f'[{j+1:>6}/{total}] {100*(j+1)//total:>2}%  成功{success}只  {elapsed:.0f}s  ETA{remain_s/60:.0f}min  {rate:.2f}只/s  {per_stock:.1f}s/只', flush=True)
    
    conn.commit()
    conn.close()
    elapsed = time.time() - t0
    print(f'✅ 完成! 成功{success}/{total}只 总耗时{elapsed:.0f}s ({elapsed/60:.1f}min)', flush=True)

if __name__ == '__main__':
    main()
