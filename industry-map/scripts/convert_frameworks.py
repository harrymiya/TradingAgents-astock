#!/usr/bin/env python3
"""将frameworks/*.json转换为前端直接可用的格式，融合stocks.json中的公司数据"""
import json, os, glob

FRAMEWORKS_DIR = os.path.expanduser('~/code/TradingAgents-astock/frameworks')
OUTPUT_DIR = os.path.expanduser('~/code/TradingAgents-astock/industry-map/src/data')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'frameworks_data.json')
STOCKS_FILE = os.path.join(FRAMEWORKS_DIR, 'stocks.json')
NAME_MAP_FILE = os.path.join(OUTPUT_DIR, 'stock_names.json')

def convert():
    # 加载stocks映射
    stocks_map = {}
    name_map = {}
    if os.path.exists(STOCKS_FILE):
        with open(STOCKS_FILE) as f:
            sd = json.load(f)
        for k, v in sd.items():
            if k.startswith('_'):
                if k == '_name_map':
                    name_map = v
            else:
                stocks_map[k] = v
        print(f'已加载stocks.json: {len(stocks_map)}个产业链的股票映射, {len(name_map)}只公司名称')
    
    result = {}
    
    for fpath in sorted(glob.glob(os.path.join(FRAMEWORKS_DIR, '*.json'))):
        fname = os.path.basename(fpath)
        if fname == 'stocks.json':
            continue
        with open(fpath) as f:
            raw = json.load(f)
        
        nodes_map = {}
        for n in raw['nodes']:
            nodes_map[n['id']] = {
                'name': n['fname'],
                'lev': n.get('lev', ''),
                'fixed': n.get('fixed', False),
                'fx': n.get('fx', 0),
                'fy': n.get('fy', 0),
            }
        
        # 找root节点名
        root_name = '未命名'
        for nid, n in nodes_map.items():
            if n['lev'] == 'root':
                root_name = n['name']
                break
        
        chain_key = root_name or fname.replace('.json', '')
        
        # 一级节点（tagE）
        level1 = []
        for nid, n in nodes_map.items():
            if n['lev'] == 'tagE':
                level1.append({
                    'id': nid,
                    'name': n['name'],
                    'fx': n['fx'],
                    'fy': n['fy'],
                })
        level1.sort(key=lambda x: x['fx'])
        
        # 二级节点（tagF）
        level2_map = {}
        for nid, n in nodes_map.items():
            if n['lev'] == 'tagF':
                # 查是否有股票数据
                chain_stocks = stocks_map.get(chain_key, {})
                codes = chain_stocks.get(n['name'], [])
                # 把股票代码+名称都带上
                stock_with_names = []
                for c in codes:
                    stock_with_names.append({
                        'code': c,
                        'name': name_map.get(c, c),
                    })
                level2_map[n['name']] = {
                    'name': n['name'],
                    'stocks': stock_with_names,
                }
        
        # 从edges解析归属关系
        section_children = {}
        for section in level1:
            section_children[section['name']] = []
        
        flow_links = []
        
        for e in raw['edges']:
            fn = nodes_map.get(e['from'], {}).get('name', '')
            tn = nodes_map.get(e['to'], {}).get('name', '')
            if not fn or not tn:
                continue
            if fn in section_children and tn in level2_map:
                section_children[fn].append(tn)
            elif fn in section_children and tn in section_children:
                flow_links.append({'from': fn, 'to': tn})
        
        industry = {
            'name': root_name or fname.replace('.json', ''),
            'source': fname,
            'sections': [],
        }
        
        for section in level1:
            children = section_children.get(section['name'], [])
            links = []
            for child_name in children:
                info = level2_map.get(child_name, {'name': child_name, 'stocks': []})
                links.append(info)
            industry['sections'].append({
                'name': section['name'],
                'links': links,
            })
        
        industry['flows'] = flow_links
        result[chain_key] = industry
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    # 保存名称映射
    if name_map:
        with open(NAME_MAP_FILE, 'w') as f:
            json.dump(name_map, f, ensure_ascii=False, indent=2)
        print(f'已保存名称映射 → {NAME_MAP_FILE}')
    
    total_stocks = 0
    total_links = 0
    print(f'\n已转换 {len(result)} 个产业链 → {OUTPUT_FILE}')
    for name, ind in result.items():
        sec_count = len(ind['sections'])
        link_count = sum(len(s['links']) for s in ind['sections'])
        stock_count = sum(len(l['stocks']) for s in ind['sections'] for l in s['links'])
        total_stocks += stock_count
        total_links += link_count
        print(f'  {name:12s}: {sec_count}个一级, {link_count}个二级, {stock_count}只股票')

if __name__ == '__main__':
    convert()
