"""
industry_map/update.py — 产业链数据更新脚本

从东方财富API获取：
  1. 概念板块成分股 → 推荐可补充到产业链的股票
  2. 股票行业归属 → 更新 stock_industries 表
  3. 批量添加股票到指定环节

用法:
  python -m industry_map.update --sync-industries    # 同步股票行业归属
  python -m industry_map.update --sync-concepts      # 同步概念板块数据
  python -m industry_map.update --recommend 半导体     # 推荐可补充的股票
"""

import urllib.request, json, time, sqlite3
from pathlib import Path
from .db import ChainDB, ChainManager, StockManager

DB_PATH = Path('/home/harrydolly/.hermes/astock_data.db')

# ============================================================
# 从东财获取实时数据
# ============================================================

def fetch_concept_list():
    """获取东财所有概念板块列表"""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = "?cb=&pn=1&pz=500&po=1&np=1&fields=f12,f14&fs=m:90+t:3"
    try:
        resp = urllib.request.urlopen(url + params, timeout=10)
        text = resp.read().decode('utf-8').strip()
        if text.startswith('('): text = text[1:]
        if text.endswith(')'): text = text[:-1]
        data = json.loads(text)
        concepts = {}
        for item in data.get('data', {}).get('diff', []):
            concepts[item['f12']] = item['f14']
        print(f"✅ 东财概念板块: {len(concepts)}个")
        return concepts
    except Exception as e:
        print(f"❌ 获取概念列表失败: {e}")
        return {}

def fetch_concept_stocks(concept_code, max_pages=2):
    """获取概念板块成分股"""
    stocks = set()
    for page in range(1, max_pages + 1):
        url = (f"https://push2.eastmoney.com/api/qt/clist/get"
               f"?cb=&pn={page}&pz=500&po=1&np=1"
               f"&fields=f12,f14"
               f"&fs=b:{concept_code}+f!50")
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            text = resp.read().decode('utf-8').strip()
            if text.startswith('('): text = text[1:]
            if text.endswith(')'): text = text[:-1]
            data = json.loads(text)
            for item in data.get('data', {}).get('diff', []):
                stocks.add(str(item['f12']))
        except:
            break
        time.sleep(0.3)
    return list(stocks)

def fetch_stock_industries(codes):
    """获取股票所属行业"""
    results = {}
    for i in range(0, len(codes), 100):
        batch = codes[i:i+100]
        secids = ','.join([f"1.{c}" if c.startswith('6') else f"0.{c}" for c in batch])
        url = f"https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids={secids}&fields=f12,f14"
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode('utf-8'))
            for item in data.get('data', {}).get('diff', []):
                code = str(item.get('f12', ''))
                ind = item.get('f14', '')
                if code and ind:
                    results[code] = ind
        except Exception as e:
            print(f"  batch {i}: {e}")
        time.sleep(0.2)
    return results

# ============================================================
# 更新任务
# ============================================================

def sync_stock_industries():
    """同步产业链所有股票的行业归属"""
    db = ChainDB.connect()
    cur = db.cursor()
    
    # 获取所有涉及股票
    cur.execute("SELECT DISTINCT code FROM chain_stocks")
    codes = [r['code'] for r in cur.fetchall()]
    print(f"同步 {len(codes)} 只股票的行业归属...")
    
    industries = fetch_stock_industries(codes)
    
    added = 0
    for code, ind_name in industries.items():
        cur.execute("INSERT OR IGNORE INTO stock_industries (code, industry_name, source) VALUES (?,?,?)",
                    (code, ind_name, 'eastmoney'))
        if cur.rowcount: added += 1
    
    db.commit()
    db.close()
    print(f"✅ 新增 {added} 条行业归属")

def sync_concepts():
    """同步热门概念板块成分股到 eastmoney_concepts 表"""
    print("同步概念板块数据...")
    concepts = fetch_concept_list()
    
    # 关注的核心概念
    target_concepts = {
        "BK0984": "芯片概念", "BK1009": "算力", "BK1031": "机器人",
        "BK1032": "低空经济", "BK1079": "CPO/光通信", "BK1028": "新能源车",
        "BK1035": "AI大模型", "BK1015": "人工智能", "BK1005": "光模块",
        "BK0717": "5G/通信", "BK0477": "半导体设备", "BK1008": "存储芯片",
        "BK1049": "商业航天", "BK0676": "国防军工",
    }
    
    db = ChainDB.connect()
    cur = db.cursor()
    total = 0
    
    for code, name in target_concepts.items():
        real_name = concepts.get(code, name)
        print(f"  {real_name} ({code})...", end=' ', flush=True)
        stocks = fetch_concept_stocks(code)
        for s in stocks:
            cur.execute("INSERT OR IGNORE INTO eastmoney_concepts (code, concept, source) VALUES (?,?,?)",
                        (s, code, 'eastmoney'))
        print(f"{len(stocks)}只")
        total += len(stocks)
        time.sleep(0.3)
    
    db.commit()
    db.close()
    print(f"✅ 概念板块同步完成: {total}条")

def recommend_stocks(chain_name, min_stocks=5):
    """
    根据概念板块数据，推荐可以补充到产业链的股票
    找出在相关概念板块中但目前不在产业链里的股票
    """
    chain = ChainManager.get_chain(chain_name)
    if not chain:
        print(f"❌ 产业链 '{chain_name}' 不存在")
        return
    
    # 当前产业链已有股票
    existing = set()
    for l in chain['links']:
        existing.update(s['code'] for s in l['stocks'])
    
    # 找概念板块里的股票
    db = ChainDB.connect()
    cur = db.cursor()
    
    # 概念-产业链映射
    concept_mapping = {
        "半导体": "BK0984", "芯片": "BK0984",
        "AI算力": "BK1009", "算力": "BK1009",
        "机器人": "BK1031",
        "低空经济": "BK1032",
        "新能源": "BK1028",
        "国防军工": "BK0676",
    }
    
    concept_code = None
    for keyword, cc in concept_mapping.items():
        if keyword in chain_name or chain_name in keyword:
            concept_code = cc
            break
    
    if not concept_code:
        print(f"❌ 未找到 '{chain_name}' 对应的概念板块")
        db.close()
        return
    
    # 查概念板块中不在产业链里的股票
    cur.execute("""
        SELECT ec.code, COALESCE(s.name, ec.code) as name, si.industry_name
        FROM eastmoney_concepts ec
        LEFT JOIN stocks s ON ec.code = s.code
        LEFT JOIN stock_industries si ON ec.code = si.code
        WHERE ec.concept = ? AND ec.code NOT IN ({})
        LIMIT 50
    """.format(','.join(['?'] * len(existing))), [concept_code] + list(existing))
    
    candidates = cur.fetchall()
    db.close()
    
    print(f"\n{'='*60}")
    print(f"📋 {chain_name} — 推荐补充的股票 ({len(candidates)}只候选)")
    print(f"{'='*60}")
    for i, r in enumerate(candidates[:20]):
        print(f"  {i+1:2d}. {r['code']} {r['name']:<8} [{r['industry_name'] or ''}]")

# ============================================================
# CLI入口
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='产业链数据更新工具')
    parser.add_argument('--sync-industries', action='store_true', help='同步股票行业归属')
    parser.add_argument('--sync-concepts', action='store_true', help='同步概念板块数据')
    parser.add_argument('--recommend', help='推荐可补充的股票到指定产业链')
    args = parser.parse_args()
    
    if args.sync_industries:
        sync_stock_industries()
    elif args.sync_concepts:
        sync_concepts()
    elif args.recommend:
        recommend_stocks(args.recommend)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
