#!/usr/bin/env python3
"""
CPO产业链JSON——保持原始4段骨架（上游→中游→下游，不含配套）
  上游原材料 → 上游设备 → 中游制造 → 下游应用
用专业知识补充每个环节的A股公司
"""
import json, os

FRAMEWORKS_DIR = os.path.expanduser('~/code/TradingAgents-astock/frameworks')

# 一级节点（4个，从左到右）
SECTIONS = [
    {
        "name": "上游原材料",
        "fx": -300, "fy": 0,
        "links": [
            {
                "name": "硅基材料",
                "stocks": ["688126", "300346", "600206", "603260"]
            },
            {
                "name": "光芯片",
                "stocks": ["688048", "688498", "688313", "002222", "300620"]
            },
            {
                "name": "激光器",
                "stocks": ["688048", "688167", "688025", "002222", "300620"]
            },
            {
                "name": "光电探测器",
                "stocks": ["688313", "300708", "002281"]
            },
            {
                "name": "高速电芯片",
                "stocks": ["300661", "688041", "688256"]
            },
        ]
    },
    {
        "name": "上游设备",
        "fx": -50, "fy": 0,
        "links": [
            {
                "name": "光刻机",
                "stocks": ["002371", "688012", "688037"]
            },
            {
                "name": "刻蚀设备",
                "stocks": ["688012", "688120", "002371"]
            },
            {
                "name": "封装设备",
                "stocks": ["688037", "300604", "688200", "002371"]
            },
            {
                "name": "测试设备",
                "stocks": ["300604", "688200", "300567", "688037"]
            },
            {
                "name": "清洗设备",
                "stocks": ["688082", "603690", "688012"]
            },
        ]
    },
    {
        "name": "中游制造",
        "fx": 200, "fy": 0,
        "links": [
            {
                "name": "CPO模块制造",
                "stocks": ["300308", "300502", "000988", "002281", "301205", "688205"]
            },
            {
                "name": "光互连组件",
                "stocks": ["300394", "002897", "300570", "601869", "600522"]
            },
            {
                "name": "高速PCB板",
                "stocks": ["002463", "002916"]
            },
            {
                "name": "散热系统",
                "stocks": ["002837", "300499", "301018"]
            },
            {
                "name": "电源管理模块",
                "stocks": ["300661", "688352"]
            },
        ]
    },
]

STOCK_NAMES = {
    "688126": "沪硅产业", "300346": "南大光电", "600206": "有研新材", "603260": "合盛硅业",
    "688048": "长光华芯", "688498": "源杰科技", "688313": "仕佳光子", "002222": "福晶科技", "300620": "光库科技",
    "688167": "炬光科技", "688025": "杰普特",
    "300708": "聚灿光电", "002281": "光迅科技", "300661": "圣邦股份", "688041": "海光信息", "688256": "寒武纪",
    "002371": "北方华创", "688012": "中微公司", "688037": "芯源微", "688120": "华海清科",
    "300604": "长川科技", "688200": "华峰测控", "300567": "精测电子",
    "688082": "盛美上海", "603690": "至纯科技",
    "300308": "中际旭创", "300502": "新易盛", "000988": "华工科技",
    "301205": "联特科技", "688205": "德科立",
    "300394": "天孚通信", "002897": "意华股份", "300570": "太辰光", "601869": "长飞光纤", "600522": "中天科技",
    "002463": "沪电股份", "002916": "深南电路",
    "002837": "英维克", "300499": "高澜股份", "301018": "申菱环境",
    "688352": "颀中科技",
}

import uuid

def make_id():
    return uuid.uuid4().hex[:20] + '-' + uuid.uuid4().hex[:12]

nodes = []
edges = []

# root节点
root_id = make_id()
nodes.append({
    "id": root_id, "fname": "CPO全产业链", "org": None, "tags": [], "fixed": False,
    "fx": 0, "fy": 0, "lev": "root", "status": 1, "meta": {},
    "linkTime": "2026-06-11 12:00:00", "updateTime": "2026-06-11T12:00:00",
    "position": None, "userId": 23709, "listed": None, "priority": 0,
    "description": "", "url": None, "aiGraphRank": None, "aiPreferredType": None,
    "userPreferredType": 0, "userConfirmed": True,
})

section_ids = []
for sec in SECTIONS:
    sec_id = make_id()
    section_ids.append((sec['name'], sec_id))
    nodes.append({
        "id": sec_id, "fname": sec['name'],
        "org": "string", "tags": [], "fixed": True,
        "fx": sec['fx'], "fy": sec['fy'], "lev": "tagE", "status": 1, "meta": {},
        "linkTime": "2026-06-11 12:00:00", "updateTime": "2026-06-11T12:00:00",
        "position": None, "userId": 23709, "listed": None, "priority": 0,
        "description": "", "url": "", "aiGraphRank": None, "aiPreferredType": None,
        "userPreferredType": 0, "userConfirmed": True,
    })
    edges.append({
        "from": root_id, "to": sec_id,
        "userConfirmed": True, "status": 1,
        "meta": {"automatic": True, "smooth": 0, "userMarkedInvisible": 0}
    })
    for link in sec['links']:
        link_id = make_id()
        nodes.append({
            "id": link_id, "fname": link['name'],
            "org": "", "tags": [], "fixed": False, "fx": 0, "fy": 0, "lev": "tagF", "status": 1,
            "meta": {"edgeMeta": {"text2text": True}, "iconMeta": {"shape": "circle", "rectHeight": 180, "rectWidth": 180}},
            "linkTime": "2026-06-11 12:00:00", "updateTime": "2026-06-11T12:00:00",
            "position": None, "userId": 23709, "listed": None, "priority": 0,
            "description": "", "url": "", "aiGraphRank": None, "aiPreferredType": None,
            "userPreferredType": 0, "userConfirmed": True,
        })
        edges.append({
            "from": sec_id, "to": link_id,
            "userConfirmed": True, "status": 1,
            "meta": {"automatic": True, "smooth": 0, "userMarkedInvisible": 0}
        })

# 一级间箭头
for i in range(len(SECTIONS) - 1):
    edges.append({
        "from": section_ids[i][1], "to": section_ids[i+1][1],
        "userConfirmed": True, "status": 1,
        "meta": {"automatic": True, "smooth": 0, "userMarkedInvisible": 0}
    })

cpo = {
    "viewInfo": {
        "id": make_id(), "name": "CPO全产业链",
        "description": "CPO及其上游——原材料→设备→制造→应用",
        "nodeCount": len(nodes), "edgeCount": len(edges),
        "tags": ["[]"], "updateTime": "2026-06-11 12:00:00",
        "ownerNick": "-", "ownerId": 23709,
    },
    "edges": edges, "nodes": nodes,
}

out_path = os.path.join(FRAMEWORKS_DIR, 'cpo.json')
with open(out_path, 'w') as f:
    json.dump(cpo, f, ensure_ascii=False, indent=2)

print(f"✅ CPO全产业链已重写!")
print(f"   一级节点: {len(SECTIONS)}个")
for s in SECTIONS:
    print(f"     {s['name']}: {len(s['links'])}个环节")
total_stocks = set()
for s in SECTIONS:
    for l in s['links']:
        total_stocks.update(l['stocks'])
print(f"   去重股票: {len(total_stocks)}只")

# stocks.json
stocks_out = {"CPO全产业链": {}}
for s in SECTIONS:
    for l in s['links']:
        stocks_out["CPO全产业链"][l['name']] = l['stocks']
stocks_out["_name_map"] = STOCK_NAMES
stocks_path = os.path.join(FRAMEWORKS_DIR, 'stocks.json')
if os.path.exists(stocks_path):
    with open(stocks_path) as f:
        old = json.load(f)
    if '宇树' in old:
        stocks_out['宇树'] = old['宇树']
with open(stocks_path, 'w') as f:
    json.dump(stocks_out, f, ensure_ascii=False, indent=2)
print(f"   stocks.json已更新")
