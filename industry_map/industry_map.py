#!/usr/bin/env python3
"""
产业链地图 — CLI入口

用法:
  industry_map 半导体                        # 截图半导体产业链（今日涨幅）
  industry_map AI算力 --metric yearChg       # 截图AI算力（年度涨幅）
  industry_map --list                        # 列出所有产业链
  industry_map --add-chain 新产业链           # 新增产业链
  industry_map --add-link 产业链名 环节名      # 新增环节
  industry_map --add-deps 产业链名:环节名=上游  # 设置依赖
  industry_map --add-stocks 产业链名:环节名 000001,600519  # 加股票
  industry_map --sync-industries             # 同步行业数据
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from industry_map.db import ChainManager, LinkManager, StockManager, IndustryManager
from industry_map.screenshot import capture

def main():
    args = sys.argv[1:]
    
    if not args:
        print("用法见: industry_map --help 或 industry_map --list")
        return
    
    cmd = args[0]
    
    if cmd == '--list' or cmd == '-l':
        chains = ChainManager.list_chains()
        print(f"\n{'='*60}")
        print(f"{'产业链':<18} {'环节':>4} {'股票':>5}")
        print(f"{'-'*60}")
        for c in chains:
            print(f"  {c['name']:<16} {c['link_count']:>4} {c['stock_count']:>5}")
        print(f"{'='*60}")
        print(f"共 {len(chains)} 个产业链")
        return
    
    if cmd == '--add-chain':
        name = args[1] if len(args) > 1 else input("产业链名: ")
        desc = args[2] if len(args) > 2 else ''
        ChainManager.create_chain(name, desc)
        print(f"✅ 新增: {name}")
        return
    
    if cmd == '--add-link':
        chain_name = args[1] if len(args) > 1 else input("产业链名: ")
        link_name = args[2] if len(args) > 2 else input("环节名: ")
        LinkManager.add_link(chain_name, link_name)
        print(f"✅ 新增环节: {chain_name} → {link_name}")
        return
    
    if cmd == '--add-deps':
        spec = args[1] if len(args) > 1 else ''
        if '=' in spec:
            parts = spec.split('=')
            lp = parts[0].split(':')
            if len(lp) == 2:
                LinkManager.add_dep(lp[0], lp[1], parts[1])
                print(f"✅ 依赖: {parts[0]} ← {parts[1]}")
        return
    
    if cmd == '--add-stocks':
        spec = args[1] if len(args) > 1 else ''
        codes = args[2] if len(args) > 2 else ''
        if ':' in spec:
            parts = spec.split(':')
            n = StockManager.add_stocks(parts[0], parts[1], codes.split(','))
            print(f"✅ 添加 {n} 只股票: {spec}")
        return
    
    if cmd == '--sync-industries':
        from industry_map.update import sync_stock_industries
        sync_stock_industries()
        return
    
    if cmd == '--sync-concepts':
        from industry_map.update import sync_concepts
        sync_concepts()
        return
    
    # 默认：截图
    chain_name = cmd
    metric = 'chg'
    if '--metric' in args:
        mi = args.index('--metric')
        if mi + 1 < len(args):
            metric = args[mi + 1]
    
    out = capture(chain_name, metric)
    if out:
        print(f"\n✅ 截图完成")
        print(f"MEDIA:{out}")

if __name__ == '__main__':
    main()
