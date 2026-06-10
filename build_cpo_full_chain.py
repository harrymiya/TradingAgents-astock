#!/usr/bin/env python3
"""
构建CPO全产业链（基于cpo.json拓扑）
覆盖原材料→设备→制造→应用→配套，5级链式结构
"""
import sqlite3, os

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')
CHAIN_NAME = "CPO全产业链"

# 新的CPO拓扑结构（从cpo.json整理）
CHAIN_STRUCTURE = {
    "上游原材料": {
        "level": 0,
        "sub_links": ["硅基材料", "光芯片", "激光器", "光电探测器", "高速电芯片"]
    },
    "上游设备": {
        "level": 0,
        "sub_links": ["光刻机", "刻蚀设备", "封装设备", "测试设备", "清洗设备"]
    },
    "中游制造": {
        "level": 1,
        "sub_links": ["CPO模块制造", "光互连组件", "高速PCB板", "散热系统", "电源管理模块"]
    },
    "下游应用": {
        "level": 2,
        "sub_links": ["数据中心", "人工智能算力集群", "云计算平台", "5G通信基站", "高性能计算"]
    },
    "配套服务": {
        "level": 2,
        "sub_links": ["光学设计服务", "热管理方案", "高速信号仿真", "认证测试服务", "供应链管理"]
    }
}

# 每个子环节的股票映射
STOCK_MAP = {
    # === 上游原材料 ===
    "硅基材料": [
        ("603260", "合盛硅业"), ("688126", "沪硅产业"), ("300346", "南大光电"),
        ("688138", "清溢光电"), ("600206", "有研新材"),
    ],
    "光芯片": [
        ("688048", "长光华芯"), ("688313", "仕佳光子"), ("688498", "源杰科技"),
        ("002222", "福晶科技"), ("600703", "三安光电"), ("300323", "华灿光电"),
        ("300708", "聚灿光电"), ("688195", "腾景科技"), ("300620", "光库科技"),
    ],
    "激光器": [
        ("688048", "长光华芯"), ("688167", "炬光科技"), ("688025", "杰普特"),
        ("002222", "福晶科技"), ("300620", "光库科技"),
    ],
    "光电探测器": [
        ("688313", "仕佳光子"), ("300708", "聚灿光电"), ("002281", "光迅科技"),
    ],
    "高速电芯片": [
        ("300661", "圣邦股份"), ("688018", "乐鑫科技"), ("688041", "海光信息"),
        ("688256", "寒武纪"),
    ],

    # === 上游设备 ===
    "光刻机": [
        ("002371", "北方华创"), ("688012", "中微公司"), ("688037", "芯源微"),
    ],
    "刻蚀设备": [
        ("688012", "中微公司"), ("688120", "华海清科"), ("002371", "北方华创"),
    ],
    "封装设备": [
        ("688037", "芯源微"), ("300604", "长川科技"), ("688200", "华峰测控"),
        ("002371", "北方华创"),
    ],
    "测试设备": [
        ("300604", "长川科技"), ("688200", "华峰测控"), ("300567", "精测电子"),
        ("688037", "芯源微"),
    ],
    "清洗设备": [
        ("688082", "盛美上海"), ("603690", "至纯科技"), ("688012", "中微公司"),
    ],

    # === 中游制造 ===
    "CPO模块制造": [
        ("300308", "中际旭创"), ("300502", "新易盛"), ("000988", "华工科技"),
        ("002281", "光迅科技"), ("301205", "联特科技"), ("688205", "德科立"),
    ],
    "光互连组件": [
        ("300394", "天孚通信"), ("002897", "意华股份"), ("300570", "太辰光"),
        ("601869", "长飞光纤"), ("600522", "中天科技"), ("688668", "鼎通科技"),
    ],
    "高速PCB板": [
        ("002463", "沪电股份"), ("002916", "深南电路"),
    ],
    "散热系统": [
        ("002837", "英维克"), ("300499", "高澜股份"), ("301018", "申菱环境"),
    ],
    "电源管理模块": [
        ("300661", "圣邦股份"), ("300842", "帝科股份"), ("601208", "东材科技"),
    ],

    # === 下游应用 ===
    "数据中心": [
        ("000063", "中兴通讯"), ("600498", "烽火通信"), ("603019", "中科曙光"),
        ("300308", "中际旭创"), ("002281", "光迅科技"),
    ],
    "人工智能算力集群": [
        ("688041", "海光信息"), ("688256", "寒武纪"), ("603019", "中科曙光"),
    ],
    "云计算平台": [
        ("000063", "中兴通讯"), ("688041", "海光信息"), ("603236", "移远通信"),
    ],
    "5G通信基站": [
        ("000063", "中兴通讯"), ("600498", "烽火通信"), ("002792", "通宇通讯"),
        ("002281", "光迅科技"),
    ],
    "高性能计算": [
        ("688041", "海光信息"), ("688256", "寒武纪"), ("603019", "中科曙光"),
    ],

    # === 配套服务 ===
    "光学设计服务": [
        ("688195", "腾景科技"), ("688167", "炬光科技"), ("300620", "光库科技"),
    ],
    "热管理方案": [
        ("002837", "英维克"), ("300499", "高澜股份"), ("301018", "申菱环境"),
        ("601208", "东材科技"), ("300737", "科顺股份"),
    ],
    "高速信号仿真": [
        ("000063", "中兴通讯"), ("300661", "圣邦股份"),
    ],
    "认证测试服务": [
        ("300567", "精测电子"), ("688200", "华峰测控"),
    ],
    "供应链管理": [
        ("002281", "光迅科技"), ("600522", "中天科技"), ("600498", "烽火通信"),
    ],
}

def build_chain():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    # 1. 检查是否已存在
    existing = db.execute("SELECT id FROM industry_chains WHERE name=?", (CHAIN_NAME,)).fetchone()
    if existing:
        print(f"产业链 '{CHAIN_NAME}' 已存在 (ID={existing['id']})，先删除重建")
        chain_id = existing['id']
        db.execute("DELETE FROM chain_stocks WHERE link_id IN (SELECT id FROM chain_links WHERE chain_id=?)", (chain_id,))
        db.execute("DELETE FROM chain_link_deps WHERE link_id IN (SELECT id FROM chain_links WHERE chain_id=?)", (chain_id,))
        db.execute("DELETE FROM chain_link_deps WHERE depends_on_link_id IN (SELECT id FROM chain_links WHERE chain_id=?)", (chain_id,))
        db.execute("DELETE FROM chain_links WHERE chain_id=?", (chain_id,))
        db.execute("UPDATE industry_chains SET description=? WHERE id=?", ("CPO全产业链——原材料→设备→制造→应用→配套，5级一字链结构", chain_id))
        db.commit()
        print("   已清理旧数据")
    else:
        cursor = db.execute("INSERT INTO industry_chains (name, description) VALUES (?, ?)",
                   (CHAIN_NAME, "CPO全产业链——原材料→设备→制造→应用→配套，5级一字链结构"))
        chain_id = cursor.lastrowid
        print(f"创建新产业链 '{CHAIN_NAME}' (ID={chain_id})")

    # 2. 按顺序创建环节
    sort_order = 0
    link_id_map = {}

    for parent_name, parent_data in CHAIN_STRUCTURE.items():
        for sub_name in parent_data["sub_links"]:
            stocks = STOCK_MAP.get(sub_name, [])
            stock_codes = [s[0] for s in stocks]

            # 去重
            seen = set()
            unique_stocks = []
            for c in stock_codes:
                if c not in seen:
                    seen.add(c)
                    unique_stocks.append(c)

            level = parent_data["level"]
            if parent_name in ("上游原材料", "上游设备"):
                barrier = 4
            elif parent_name == "中游制造":
                barrier = 3
            else:
                barrier = 2

            description = f"CPO{parent_name}环节——{sub_name}"

            cursor = db.execute(
                "INSERT INTO chain_links (chain_id, name, level, description, barrier, localization_rate, sort_order) VALUES (?,?,?,?,?,?,?)",
                (chain_id, sub_name, level, description, barrier, 50, sort_order)
            )
            link_id = cursor.lastrowid
            link_id_map[sub_name] = link_id
            sort_order += 1

            for code in unique_stocks:
                db.execute("INSERT OR IGNORE INTO chain_stocks (link_id, code) VALUES (?, ?)", (link_id, code))

            print(f"  [{sort_order:2d}] {sub_name:16s} (level={level}) -> {len(unique_stocks)}只股票")

    # 3. 建立上下游依赖关系
    parent_order = ["上游原材料", "上游设备", "中游制造", "下游应用", "配套服务"]

    # 大环节间上下游
    for i in range(len(parent_order) - 1):
        current_subs = CHAIN_STRUCTURE[parent_order[i]]["sub_links"]
        next_subs = CHAIN_STRUCTURE[parent_order[i + 1]]["sub_links"]
        for cs in current_subs:
            for ns in next_subs:
                if cs in link_id_map and ns in link_id_map:
                    db.execute(
                        "INSERT OR IGNORE INTO chain_link_deps (link_id, depends_on_link_id) VALUES (?, ?)",
                        (link_id_map[ns], link_id_map[cs])
                    )

    # 同环节内上下游
    for parent_name, parent_data in CHAIN_STRUCTURE.items():
        subs = parent_data["sub_links"]
        for i in range(len(subs) - 1):
            a, b = subs[i], subs[i+1]
            if a in link_id_map and b in link_id_map:
                db.execute(
                    "INSERT OR IGNORE INTO chain_link_deps (link_id, depends_on_link_id) VALUES (?, ?)",
                    (link_id_map[b], link_id_map[a])
                )

    # 4. 统计
    stock_count = db.execute("""
        SELECT COUNT(DISTINCT code) FROM chain_stocks
        WHERE link_id IN (SELECT id FROM chain_links WHERE chain_id=?)
    """, (chain_id,)).fetchone()[0]

    link_count = db.execute("SELECT COUNT(*) FROM chain_links WHERE chain_id=?", (chain_id,)).fetchone()[0]
    dep_count = db.execute("""
        SELECT COUNT(*) FROM chain_link_deps
        WHERE link_id IN (SELECT id FROM chain_links WHERE chain_id=?)
    """, (chain_id,)).fetchone()[0]

    db.commit()
    db.close()

    print(f"\nCPO全产业链构建完成!")
    print(f"   环节: {link_count} 个")
    print(f"   股票: {stock_count} 只（去重）")
    print(f"   上下游关系: {dep_count} 条")
    print(f"   DB ID: {chain_id}")

if __name__ == "__main__":
    build_chain()
