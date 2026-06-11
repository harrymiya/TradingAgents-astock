#!/usr/bin/env python3
"""
重建宇树(人形机器人)产业链 + 新建AI算力产业链
两个都是3个一级节点(去掉下游应用) + 挂载A股公司
然后重新生成frameworks_data.json
"""
import json
import os
import sys

FRAMEWORKS_DIR = os.path.expanduser('~/code/TradingAgents-astock/frameworks')
OUTPUT_DIR = os.path.expanduser('~/code/TradingAgents-astock/industry-map/src/data')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'frameworks_data.json')

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 1. 宇树（人形机器人）产业链 - 3个一级
# ============================================================
# 去掉下游应用+配套服务，只保留：上游原材料 → 上游核心部件 → 中游制造

YU_SHU_SECTIONS = {
    "上游原材料": [
        "金属材料", "电子元器件", "传感器", "电池", "精密轴承",
    ],
    "上游核心部件": [
        "伺服电机", "减速器", "控制器", "嵌入式系统", "视觉模块",
    ],
    "中游制造": [
        "机器人本体", "整机装配", "自动化测试", "软件系统集成", "质量检测",
    ],
}

YU_SHU_STOCKS = {
    # === 上游原材料 ===
    "金属材料": [
        ("600019", "宝钢股份"), ("000825", "太钢不锈"), ("002540", "亚太科技"),
        ("600114", "东睦股份"), ("002182", "宝武镁业"),
    ],
    "电子元器件": [
        ("002475", "立讯精密"), ("603005", "晶方科技"), ("600183", "生益科技"),
        ("002138", "顺络电子"), ("603986", "兆易创新"), ("300661", "圣邦股份"),
    ],
    "传感器": [
        ("300124", "汇川技术"), ("002747", "埃斯顿"), ("300007", "汉威科技"),
        ("603662", "柯力传感"), ("688582", "芯动联科"),
    ],
    "电池": [
        ("300750", "宁德时代"), ("002074", "国轩高科"), ("300438", "鹏辉能源"),
        ("688005", "容百科技"), ("300014", "亿纬锂能"),
    ],
    "精密轴承": [
        ("300718", "长盛轴承"), ("002046", "国机精工"), ("601177", "杭齿前进"),
        ("603100", "川仪股份"), ("002553", "南方精工"),
    ],
    # === 上游核心部件 ===
    "伺服电机": [
        ("300124", "汇川技术"), ("688320", "禾川科技"), ("002747", "埃斯顿"),
        ("603728", "鸣志电器"), ("002896", "中大力德"),
    ],
    "减速器": [
        ("688017", "绿的谐波"), ("002472", "双环传动"), ("300904", "威力传动"),
        ("002896", "中大力德"), ("603915", "国茂股份"),
    ],
    "控制器": [
        ("300124", "汇川技术"), ("603015", "弘讯科技"), ("002747", "埃斯顿"),
        ("688320", "禾川科技"), ("002527", "新时达"),
    ],
    "嵌入式系统": [
        ("603160", "汇顶科技"), ("688018", "乐鑫科技"), ("300661", "圣邦股份"),
        ("002049", "紫光国微"), ("688041", "海光信息"),
    ],
    "视觉模块": [
        ("002415", "海康威视"), ("002236", "大华股份"), ("688225", "亚信安全"),
        ("300790", "宇瞳光学"), ("688322", "奥比中光"),
    ],
    # === 中游制造 ===
    "机器人本体": [
        ("300024", "机器人"), ("002527", "新时达"), ("002747", "埃斯顿"),
        ("688160", "步科股份"), ("002009", "天奇股份"),
    ],
    "整机装配": [
        ("300024", "机器人"), ("002527", "新时达"), ("603728", "鸣志电器"),
        ("688017", "绿的谐波"),
    ],
    "自动化测试": [
        ("688200", "华峰测控"), ("300567", "精测电子"), ("300604", "长川科技"),
        ("688082", "盛美上海"),
    ],
    "软件系统集成": [
        ("002230", "科大讯飞"), ("688111", "金山办公"), ("300496", "中科创达"),
        ("688568", "中科星图"),
    ],
    "质量检测": [
        ("300012", "华测检测"), ("300887", "谱尼测试"), ("002967", "广电计量"),
        ("300416", "苏试试验"),
    ],
}

# ============================================================
# 2. AI算力产业链 - 3个一级
# ============================================================
# AI算力：上游芯片(算力芯片/存储/光模块) → 中游设备(服务器/交换机/散热) → 下游算力平台(IDC/云/边缘)

AI_SECTIONS = {
    "上游芯片": [
        "AI训练芯片", "AI推理芯片", "高带宽存储HBM", "光模块与光芯片", "GPU封装基板",
    ],
    "中游设备": [
        "AI服务器", "高速交换机", "液冷散热系统", "高功率电源", "数据中心光互连",
    ],
    "下游算力平台": [
        "数据中心运营", "云计算平台", "边缘计算", "算力调度平台", "AI推理服务平台",
    ],
}

AI_STOCKS = {
    # === 上游芯片 ===
    "AI训练芯片": [
        ("688041", "海光信息"), ("688256", "寒武纪"), ("603986", "兆易创新"),
        ("002049", "紫光国微"), ("688008", "澜起科技"),
    ],
    "AI推理芯片": [
        ("688041", "海光信息"), ("688256", "寒武纪"), ("688008", "澜起科技"),
        ("300672", "国科微"), ("300661", "圣邦股份"),
    ],
    "高带宽存储HBM": [
        ("603986", "兆易创新"), ("688110", "东芯股份"), ("300672", "国科微"),
        ("002185", "华天科技"), ("600584", "长电科技"),
    ],
    "光模块与光芯片": [
        ("300308", "中际旭创"), ("300502", "新易盛"), ("301205", "联特科技"),
        ("688048", "长光华芯"), ("688498", "源杰科技"),
    ],
    "GPU封装基板": [
        ("002916", "深南电路"), ("002463", "沪电股份"), ("603005", "晶方科技"),
        ("600584", "长电科技"), ("002185", "华天科技"),
    ],
    # === 中游设备 ===
    "AI服务器": [
        ("000977", "浪潮信息"), ("603019", "中科曙光"), ("000063", "中兴通讯"),
        ("002415", "海康威视"),
    ],
    "高速交换机": [
        ("000063", "中兴通讯"), ("600498", "烽火通信"), ("300502", "新易盛"),
        ("002281", "光迅科技"),
    ],
    "液冷散热系统": [
        ("002837", "英维克"), ("300499", "高澜股份"), ("301018", "申菱环境"),
        ("688075", "安旭生物"),
    ],
    "高功率电源": [
        ("300661", "圣邦股份"), ("688352", "颀中科技"), ("002518", "科士达"),
        ("002227", "奥特迅"),
    ],
    "数据中心光互连": [
        ("300394", "天孚通信"), ("300570", "太辰光"), ("601869", "长飞光纤"),
        ("600522", "中天科技"), ("002897", "意华股份"),
    ],
    # === 下游算力平台 ===
    "数据中心运营": [
        ("300442", "润泽科技"), ("300383", "光环新网"), ("600845", "宝信软件"),
        ("000977", "浪潮信息"),
    ],
    "云计算平台": [
        ("000063", "中兴通讯"), ("688111", "金山办公"), ("600845", "宝信软件"),
        ("300442", "润泽科技"),
    ],
    "边缘计算": [
        ("688018", "乐鑫科技"), ("300496", "中科创达"), ("688568", "中科星图"),
        ("002230", "科大讯飞"),
    ],
    "算力调度平台": [
        ("000977", "浪潮信息"), ("603019", "中科曙光"), ("688111", "金山办公"),
        ("600845", "宝信软件"),
    ],
    "AI推理服务平台": [
        ("002230", "科大讯飞"), ("688256", "寒武纪"), ("688041", "海光信息"),
        ("300454", "深信服"),
    ],
}

# ============================================================
# 3. 构建完整的stocks.json
# ============================================================

def build_stocks_map(sections_map, stocks_map):
    """将环节名→股票映射转为stocks.json格式"""
    result = {}
    name_map = {}
    for section_name, link_names in sections_map.items():
        for link_name in link_names:
            stocks = stocks_map.get(link_name, [])
            result[link_name] = [s[0] for s in stocks]
            for code, name in stocks:
                name_map[code] = name
    return result, name_map

# 宇树
yu_stocks_map, yu_names = build_stocks_map(YU_SHU_SECTIONS, YU_SHU_STOCKS)
# AI算力
ai_stocks_map, ai_names = build_stocks_map(AI_SECTIONS, AI_STOCKS)

# 合并到stocks.json
new_stocks = {
    "宇树": yu_stocks_map,
    "AI算力": ai_stocks_map,
    "_name_map": {},
}
new_stocks["_name_map"].update(yu_names)
new_stocks["_name_map"].update(ai_names)

# 还要保留cpo的
stocks_path = os.path.join(FRAMEWORKS_DIR, 'stocks.json')
if os.path.exists(stocks_path):
    with open(stocks_path) as f:
        old = json.load(f)
    for k, v in old.items():
        if k.startswith('_'):
            if k == '_name_map':
                new_stocks['_name_map'].update(v)
        elif k not in ('cpo', '宇树', 'AI算力'):
            new_stocks[k] = v

with open(stocks_path, 'w') as f:
    json.dump(new_stocks, f, ensure_ascii=False, indent=2)

print(f"✅ stocks.json: 宇树({sum(len(v) for v in yu_stocks_map.values())}只/{len(yu_stocks_map)}环节) + AI算力({sum(len(v) for v in ai_stocks_map.values())}只/{len(ai_stocks_map)}环节)")
print(f"   总去重公司: {len(new_stocks['_name_map'])}只")

# ============================================================
# 4. 生成宇树.json骨架（3段结构）
# ============================================================

def generate_uuid(seed, idx):
    """生成固定UUID风格的ID"""
    import hashlib
    h = hashlib.md5(f"yushu-{seed}-{idx}".encode()).hexdigest()
    return f"{h[:20]}-{h[20:32]}"

# 生成节点
nodes = []
edges = []

# root
root_id = "yushu-root-00000000000000000000"
nodes.append({
    "id": root_id, "fname": "宇树", "org": None, "tags": [],
    "fixed": False, "fx": 0, "fy": 0, "lev": "root",
    "status": 1, "meta": {},
    "linkTime": "2026-06-11 12:00:00", "updateTime": "2026-06-11T12:00:00",
    "position": None, "userId": 23709, "listed": None, "priority": 0,
    "description": "人形机器人全产业链", "url": None, "aiGraphRank": None,
    "aiPreferredType": None, "userPreferredType": 0, "userConfirmed": True,
})

section_ids = {}
link_ids = {}

# 3个一级节点，从左到右
sections_pos = {
    "上游原材料": -300,
    "上游核心部件": 0,
    "中游制造": 300,
}

for si, (sec_name, children) in enumerate(YU_SHU_SECTIONS.items()):
    sec_id = f"yushu-sec-{generate_uuid('sec', si)[:36]}"
    section_ids[sec_name] = sec_id
    nodes.append({
        "id": sec_id, "fname": sec_name, "org": "string", "tags": [],
        "fixed": True, "fx": sections_pos[sec_name], "fy": 0, "lev": "tagE",
        "status": 1, "meta": {},
        "linkTime": "2026-06-11 12:00:00", "updateTime": "2026-06-11T12:00:00",
        "position": None, "userId": 23709, "listed": None, "priority": 0,
        "description": "", "url": "", "aiGraphRank": None,
        "aiPreferredType": None, "userPreferredType": 0, "userConfirmed": True,
    })
    edges.append({
        "from": root_id, "to": sec_id,
        "userConfirmed": True, "status": 1,
        "meta": {"automatic": True, "smooth": 0, "userMarkedInvisible": 0},
    })
    
    for ci, child_name in enumerate(children):
        cid = f"yushu-link-{generate_uuid(child_name, ci)[:36]}"
        link_ids[child_name] = cid
        nodes.append({
            "id": cid, "fname": child_name, "org": "", "tags": [],
            "fixed": False, "fx": 0, "fy": 0, "lev": "tagF",
            "status": 1, "meta": {
                "edgeMeta": {"text2text": True},
                "iconMeta": {"shape": "circle", "rectHeight": 180, "rectWidth": 180},
            },
            "linkTime": "2026-06-11 12:00:00", "updateTime": "2026-06-11T12:00:00",
            "position": None, "userId": 23709, "listed": None, "priority": 0,
            "description": "", "url": "", "aiGraphRank": None,
            "aiPreferredType": None, "userPreferredType": 0, "userConfirmed": True,
        })
        edges.append({
            "from": sec_id, "to": cid,
            "userConfirmed": True, "status": 1,
            "meta": {"automatic": True, "smooth": 0, "userMarkedInvisible": 0},
        })

# 连接一级节点之间的流（上游原材料→上游核心部件→中游制造）
prev_sec = None
for sec_name in ["上游原材料", "上游核心部件", "中游制造"]:
    if prev_sec:
        edges.append({
            "from": section_ids[prev_sec], "to": section_ids[sec_name],
            "userConfirmed": True, "status": 1,
            "meta": {"automatic": True, "smooth": 0, "userMarkedInvisible": 0},
        })
    prev_sec = sec_name

yu_tree = {
    "viewInfo": {
        "id": "yushu-v3-20260611",
        "name": "宇树",
        "description": "人形机器人产业链——上游原材料→上游核心部件→中游制造",
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "tags": ["人形机器人", "机器人"],
        "updateTime": "2026-06-11 12:00:00",
        "ownerNick": "-",
        "ownerId": 23709,
    },
    "edges": edges,
    "nodes": nodes,
}

yu_path = os.path.join(FRAMEWORKS_DIR, '宇树.json')
with open(yu_path, 'w') as f:
    json.dump(yu_tree, f, ensure_ascii=False, indent=2)
print(f"✅ 宇树.json → {len(nodes)}节点/{len(edges)}边, 3个一级, 15个二级")

# ============================================================
# 5. 生成AI算力.json骨架（3段结构）
# ============================================================

def generate_ai_uuid(seed, idx):
    import hashlib
    h = hashlib.md5(f"ai-{seed}-{idx}".encode()).hexdigest()
    return f"{h[:20]}-{h[20:32]}"

ai_nodes = []
ai_edges = []

# root
ai_root_id = "ai-root-00000000000000000000"
ai_nodes.append({
    "id": ai_root_id, "fname": "AI算力", "org": None, "tags": [],
    "fixed": False, "fx": 0, "fy": 0, "lev": "root",
    "status": 1, "meta": {},
    "linkTime": "2026-06-11 12:00:00", "updateTime": "2026-06-11T12:00:00",
    "position": None, "userId": 23709, "listed": None, "priority": 0,
    "description": "AI算力全产业链——AI训练推理芯片→服务器设备→算力平台", "url": None,
    "aiGraphRank": None, "aiPreferredType": None, "userPreferredType": 0,
    "userConfirmed": True,
})

ai_sections_pos = {
    "上游芯片": -300,
    "中游设备": 0,
    "下游算力平台": 300,
}

ai_sec_ids = {}
ai_link_ids = {}

for si, (sec_name, children) in enumerate(AI_SECTIONS.items()):
    sec_id = f"ai-sec-{generate_ai_uuid('sec', si)[:36]}"
    ai_sec_ids[sec_name] = sec_id
    ai_nodes.append({
        "id": sec_id, "fname": sec_name, "org": "string", "tags": [],
        "fixed": True, "fx": ai_sections_pos[sec_name], "fy": 0, "lev": "tagE",
        "status": 1, "meta": {},
        "linkTime": "2026-06-11 12:00:00", "updateTime": "2026-06-11T12:00:00",
        "position": None, "userId": 23709, "listed": None, "priority": 0,
        "description": "", "url": "", "aiGraphRank": None,
        "aiPreferredType": None, "userPreferredType": 0, "userConfirmed": True,
    })
    ai_edges.append({
        "from": ai_root_id, "to": sec_id,
        "userConfirmed": True, "status": 1,
        "meta": {"automatic": True, "smooth": 0, "userMarkedInvisible": 0},
    })
    
    for ci, child_name in enumerate(children):
        cid = f"ai-link-{generate_ai_uuid(child_name, ci)[:36]}"
        ai_link_ids[child_name] = cid
        ai_nodes.append({
            "id": cid, "fname": child_name, "org": "", "tags": [],
            "fixed": False, "fx": 0, "fy": 0, "lev": "tagF",
            "status": 1, "meta": {
                "edgeMeta": {"text2text": True},
                "iconMeta": {"shape": "circle", "rectHeight": 180, "rectWidth": 180},
            },
            "linkTime": "2026-06-11 12:00:00", "updateTime": "2026-06-11T12:00:00",
            "position": None, "userId": 23709, "listed": None, "priority": 0,
            "description": "", "url": "", "aiGraphRank": None,
            "aiPreferredType": None, "userPreferredType": 0, "userConfirmed": True,
        })
        ai_edges.append({
            "from": sec_id, "to": cid,
            "userConfirmed": True, "status": 1,
            "meta": {"automatic": True, "smooth": 0, "userMarkedInvisible": 0},
        })

# 一级节点之间的流
prev_sec = None
for sec_name in ["上游芯片", "中游设备", "下游算力平台"]:
    if prev_sec:
        ai_edges.append({
            "from": ai_sec_ids[prev_sec], "to": ai_sec_ids[sec_name],
            "userConfirmed": True, "status": 1,
            "meta": {"automatic": True, "smooth": 0, "userMarkedInvisible": 0},
        })
    prev_sec = sec_name

ai_tree = {
    "viewInfo": {
        "id": "ai-v1-20260611",
        "name": "AI算力",
        "description": "AI算力全产业链——AI训练推理芯片→服务器设备→算力平台",
        "nodeCount": len(ai_nodes),
        "edgeCount": len(ai_edges),
        "tags": ["AI", "算力", "芯片"],
        "updateTime": "2026-06-11 12:00:00",
        "ownerNick": "-",
        "ownerId": 23709,
    },
    "edges": ai_edges,
    "nodes": ai_nodes,
}

ai_path = os.path.join(FRAMEWORKS_DIR, 'AI算力.json')
with open(ai_path, 'w') as f:
    json.dump(ai_tree, f, ensure_ascii=False, indent=2)
print(f"✅ AI算力.json → {len(ai_nodes)}节点/{len(ai_edges)}边, 3个一级, 15个二级")

# ============================================================
# 6. 运行convert.py重新生成frameworks_data.json
# ============================================================
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from convert_frameworks import convert

# 也需要更新CPO stock数据
# 之前 CPO 的 stocks 数据还在 stocks.json 里（来自 add_stocks.py 写入）
# cpo的数据应该由旧 stocks.json 带过来（但旧 stocks.json 已被我们覆盖了！）
# 所以需要从 add_stocks.py 里重新拿 CPO 的数据

# 加载旧的 stocks.json 中的 CPO 数据
# 由于我们上面覆盖了，现在直接从 add_stocks.py 重新包含 cpo
sys.path.insert(0, os.path.expanduser('~/code/TradingAgents-astock/industry-map/scripts'))

import importlib.util
spec = importlib.util.spec_from_file_location("add_stocks",
    os.path.expanduser('~/code/TradingAgents-astock/industry-map/scripts/add_stocks.py'))
add_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(add_mod)

# 重新构建包含cpo+宇树+AI算力的完整stocks.json
cpo_map = add_mod.stocks_to_json(add_mod.CPO_STOCKS)
cpo_names = add_mod.build_name_map(add_mod.CPO_STOCKS)

final_stocks = {
    "cpo": cpo_map,
    "宇树": yu_stocks_map,
    "AI算力": ai_stocks_map,
    "_name_map": {},
}
final_stocks["_name_map"].update(cpo_names)
final_stocks["_name_map"].update(yu_names)
final_stocks["_name_map"].update(ai_names)

with open(stocks_path, 'w') as f:
    json.dump(final_stocks, f, ensure_ascii=False, indent=2)

print(f"✅ stocks.json 完整版: cpo({sum(len(v) for v in cpo_map.values())}只/{len(cpo_map)}环节)"
      f" + 宇树({sum(len(v) for v in yu_stocks_map.values())}只/{len(yu_stocks_map)}环节)"
      f" + AI算力({sum(len(v) for v in ai_stocks_map.values())}只/{len(ai_stocks_map)}环节)")
print(f"   总去重公司: {len(final_stocks['_name_map'])}只")

# 运行convert
print("\n🔄 运行convert_frameworks.py...")
convert()
print("\n🎉 全部完成!")
