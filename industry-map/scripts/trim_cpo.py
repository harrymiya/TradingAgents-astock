#!/usr/bin/env python3
"""精简cpo.json：只保留CPO及其上游（上游原材料 + 上游设备）"""
import json, os

FRAMEWORKS_DIR = os.path.expanduser('~/code/TradingAgents-astock/frameworks')
CPO_PATH = os.path.join(FRAMEWORKS_DIR, 'cpo.json')

with open(CPO_PATH) as f:
    cpo = json.load(f)

# 找到要保留的一级节点ID
nodes_map = {n['id']: n for n in cpo['nodes']}
keep_level1 = {}  # name -> id
keep_level2 = set()  # id集合
for n in cpo['nodes']:
    if n['lev'] == 'tagE' and n['fname'] in ('上游原材料', '上游设备'):
        keep_level1[n['fname']] = n['id']
    if n['lev'] == 'root':
        keep_level1['root'] = n['id']

# 从edges：只保留一级→二级的归属关系和一级间箭头
keep_edges = []
for e in cpo['edges']:
    fn = nodes_map.get(e['from'], {}).get('fname', '')
    tn = nodes_map.get(e['to'], {}).get('fname', '')
    
    from_is_level1 = e['from'] in keep_level1.values()
    to_is_level1 = e['to'] in keep_level1.values()
    from_is_level2 = nodes_map.get(e['from'], {}).get('lev') == 'tagF'
    to_is_level2 = nodes_map.get(e['to'], {}).get('lev') == 'tagF'
    
    # 保留：root→一级、一级→二级、一级→一级（仅上游原材料→上游设备）
    if from_is_level1 and to_is_level2:
        keep_edges.append(e)
        keep_level2.add(e['to'])
    elif from_is_level1 and to_is_level1:
        keep_edges.append(e)

# 保留的nodes
keep_node_ids = set(keep_level1.values()) | keep_level2
# root节点
for n in cpo['nodes']:
    if n['lev'] == 'root':
        keep_node_ids.add(n['id'])

# 过滤nodes
cpo['nodes'] = [n for n in cpo['nodes'] if n['id'] in keep_node_ids]
cpo['edges'] = keep_edges

# 更新nodeCount
cpo['viewInfo']['nodeCount'] = len(cpo['nodes'])

with open(CPO_PATH, 'w') as f:
    json.dump(cpo, f, ensure_ascii=False, indent=2)

print(f'精简完成！')
print(f'  nodes: {len(cpo["nodes"])}个 (root + 2个一级 + {len(keep_level2)}个二级)')
print(f'  edges: {len(cpo["edges"])}条')
print(f'  保留的一级: {", ".join(keep_level1.keys())}')
level2_names = [nodes_map[i]['fname'] for i in keep_level2]
print(f'  保留的二级: {", ".join(sorted(level2_names))}')
