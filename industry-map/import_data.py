#!/usr/bin/env python3
"""
导入产业链数据到数据库
从 industry_data.json 读取，写入 astock_data.db 的 industry_chains/chain_links/chain_stocks/chain_link_deps 表
"""
import json, sqlite3, sys
from pathlib import Path

DATA_FILE = Path(__file__).parent / 'src' / 'data' / 'industry_data.json'
DB_PATH = Path('/home/harrydolly/.hermes/astock_data.db')

def main():
    # 读取JSON
    with open(DATA_FILE) as f:
        data = json.load(f)
    
    db = sqlite3.connect(str(DB_PATH))
    cur = db.cursor()
    
    # 清空旧数据
    for t in ['chain_stocks', 'chain_link_deps', 'chain_links', 'industry_chains']:
        cur.execute(f"DELETE FROM {t}")
    
    # 导入每个产业链
    for order, (name, info) in enumerate(data.items()):
        cur.execute(
            "INSERT INTO industry_chains (name, description, sort_order) VALUES (?, ?, ?)",
            (name, info['描述'], order)
        )
        chain_id = cur.lastrowid
        links = info['环节']
        
        # 先插入所有环节（获取ID映射）
        link_name_to_id = {}
        for link_order, (link_name, link_data) in enumerate(sorted(links.items())):
            # 判断level
            up = link_data.get('上游', [])
            down = link_data.get('下游', [])
            if not up and down:
                level = 0  # 上游
            elif up and not down:
                level = 2  # 下游
            else:
                level = 1  # 中游
            
            cur.execute(
                """INSERT INTO chain_links (chain_id, name, level, barrier, localization_rate, description, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (chain_id, link_name, level, link_data['壁垒'], link_data['国产化率'],
                 link_data.get('描述', ''), link_order)
            )
            link_name_to_id[link_name] = cur.lastrowid
        
        # 再插入上下游依赖和股票
        for link_name, link_data in links.items():
            link_id = link_name_to_id[link_name]
            
            # 上游依赖
            for up_name in link_data.get('上游', []):
                if up_name in link_name_to_id:
                    cur.execute(
                        "INSERT OR IGNORE INTO chain_link_deps (link_id, depends_on_link_id) VALUES (?, ?)",
                        (link_id, link_name_to_id[up_name])
                    )
            
            # 股票
            for code in link_data['股票']:
                cur.execute(
                    "INSERT OR IGNORE INTO chain_stocks (link_id, code) VALUES (?, ?)",
                    (link_id, code)
                )
        
        print(f"  ✅ {name}: {len(links)}环节, {sum(len(l['股票']) for l in links.values())}只股票")
    
    db.commit()
    
    # 统计
    cur.execute("SELECT COUNT(*) FROM industry_chains")
    chains = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chain_links")
    links = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chain_stocks")
    stocks = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chain_link_deps")
    deps = cur.fetchone()[0]
    
    db.close()
    print(f"\n✅ 导入完成: {chains}个产业链, {links}个环节, {stocks}只股票关联, {deps}个上下游依赖")

if __name__ == '__main__':
    main()
