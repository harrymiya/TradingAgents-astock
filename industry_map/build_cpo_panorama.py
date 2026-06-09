#!/usr/bin/env python3
"""
CPO(共封装光学) 产业链全景图构建工具
—— 按技术栈分层：核心材料 → 光芯片 → 光引擎/光模块 → 连接器/温控 → 设备/封装 → 应用
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from industry_map.db import ChainManager, LinkManager, StockManager, ChainDB

# ============================================================
# CPO全景 — 按7大环节重新组织，补全所有核心公司
# ============================================================
# 核心原则：
# 1. 一家公司在产业链可能有多个位置（如天孚通信既是FA光纤阵列又是光引擎）
# 2. 先删旧链重建，避免重复
# ============================================================

CPO_CHAIN = "CPO共封装光学(全景)"

LINKS = [
    {
        "name": "核心材料(衬底/气体/靶材)",
        "level": 0,
        "barrier": 5,
        "rate": 15,
        "sort_order": 0,
        "desc": "磷化铟InP、GaAs衬底、高纯气体、溅射靶材",
        "stocks": [
            "600206", "有研新材",     # 高纯金属靶材
            "603260", "合盛硅业",     # 硅基材料
            "688138", "清溢光电",     # 掩膜版
            "300346", "南大光电",     # MO源、高纯电子特气
            "688012", "中微公司",     # 刻蚀设备材料相关
            "688126", "沪硅产业",     # 硅片/SOI衬底
        ]
    },
    {
        "name": "光芯片(EML/VCSEL/SiPh/DFB)",
        "level": 0,
        "barrier": 5,
        "rate": 15,
        "sort_order": 1,
        "desc": "高速光芯片—EML电吸收调制激光器、VCSEL垂直腔面发射激光器、硅光SiPh芯片、DFB分布反馈激光器",
        "stocks": [
            "688498", "源杰科技",     # 光芯片IDM—EML/DFB
            "688048", "长光华芯",     # 高功率激光芯片、VCSEL
            "300620", "光库科技",     # 铌酸锂调制器芯片
            "688313", "仕佳光子",     # 平面光波导PLC、AWG芯片
            "002222", "福晶科技",     # 光学晶体、非线性光学
            "688195", "腾景科技",     # 精密光学元件、镀膜
            "300708", "聚灿光电",     # 化合物半导体
            "600703", "三安光电",     # GaAs/GaN化合物半导体代工
            "300323", "华灿光电",     # 化合物半导体外延片
        ]
    },
    {
        "name": "光引擎/光模块(200G/400G/800G/1.6T)",
        "level": 1,
        "barrier": 4,
        "rate": 40,
        "sort_order": 2,
        "desc": "高速光模块—硅光引擎、EML封装、COB工艺、CPO封装",
        "stocks": [
            "300308", "中际旭创",     # 800G/1.6T全球龙头
            "300502", "新易盛",       # 400G/800G高速模块
            "002281", "光迅科技",     # 光模块+光芯片全产业链
            "000988", "华工科技",     # 光模块+激光器
            "301205", "联特科技",     # 高速光模块(800G CPO研发)
            "688205", "德科立",       # 长距离高速光模块
            "300394", "天孚通信",     # 光引擎FA/光收发组件
            "002792", "通宇通讯",     # 光模块(参股)
            "603236", "移远通信",     # 通信模组
        ]
    },
    {
        "name": "FA光纤阵列/MPO连接器/光纤光缆",
        "level": 1,
        "barrier": 3,
        "rate": 50,
        "sort_order": 3,
        "desc": "光纤阵列FA、MPO/MTP高密度连接器、保偏光纤、特种光纤光缆",
        "stocks": [
            "300394", "天孚通信",     # FA光纤阵列龙头
            "300570", "太辰光",       # MPO/MTP高密度连接器
            "002897", "意华股份",     # 高速连接器(华为供应链)
            "688668", "鼎通科技",     # 连接器组件(I/O、高速背板)
            "601869", "长飞光纤",     # 光纤预制棒/特种光纤
            "600522", "中天科技",     # 光纤光缆+海缆
            "688167", "炬光科技",     # 激光光学+光纤耦合
        ]
    },
    {
        "name": "温控/TEC/精密设备",
        "level": 2,
        "barrier": 3,
        "rate": 30,
        "sort_order": 4,
        "desc": "热电制冷TEC、液冷散热、贴片机、耦合封装设备",
        "stocks": [
            "002837", "英维克",       # 温控/液冷散热
            "300499", "高澜股份",     # 电力电子冷却
            "301018", "申菱环境",     # 精密温控/IDC冷却
            "601208", "东材科技",     # 散热基板/覆铜板
            "300737", "科顺股份",     # 散热材料
            "300842", "帝科股份",     # 导电银浆(光模块封装用)
            "688025", "杰普特",       # 光模块耦合/测试设备
        ]
    },
    {
        "name": "DSP/电芯片/SerDes",
        "level": 1,
        "barrier": 5,
        "rate": 10,
        "sort_order": 5,
        "desc": "DSP数字信号处理器、SerDes、TIA跨阻放大器、Driver驱动芯片",
        "stocks": [
            "000063", "中兴通讯",     # 5G/芯片设计(自研DSP)
            "688041", "海光信息",     # 处理器/DSP
            "688256", "寒武纪",       # AI芯片(数据中心)
            "300661", "圣邦股份",     # 模拟芯片(TIA/Driver)
            "688018", "乐鑫科技",     # 通信芯片
        ]
    },
    {
        "name": "数据中心应用/交换机/算力",
        "level": 2,
        "barrier": 3,
        "rate": 60,
        "sort_order": 6,
        "desc": "数据中心交换机、AI算力集群、CPO交换机、DCI互联",
        "stocks": [
            "000063", "中兴通讯",     # 数据中心交换机/路由器
            "600498", "烽火通信",     # 光传输/数据中心互联
            "300308", "中际旭创",     # AI算力光互联
            "688041", "海光信息",     # 国产GPU算力
            "688256", "寒武纪",       # AI加速卡
            "603019", "中科曙光",     # AI服务器/算力底座
        ]
    },
]

def build():
    """删旧链，建新全景链"""
    db = ChainDB.connect()
    cur = db.cursor()
    
    # 先检查是否已存在
    cur.execute("SELECT id FROM industry_chains WHERE name = ?", (CPO_CHAIN,))
    existing = cur.fetchone()
    if existing:
        print(f"⏭️ 链 '{CPO_CHAIN}' 已存在(id={existing['id']})，跳过重建")
        print("先删除旧的……")
        ChainManager.delete_chain(CPO_CHAIN)
        print(f"🗑️ 已删除 '{CPO_CHAIN}'")
    
    # 创建产业链
    cid = ChainManager.create_chain(CPO_CHAIN, "CPO共封装光学全景产业链——核心材料→光芯片→光模块/引擎→连接器→温控→电芯片→数据中心应用")
    print(f"✅ 创建产业链 '{CPO_CHAIN}' id={cid}")
    
    total_stocks = 0
    # 添加环节和股票
    for link in LINKS:
        lid = LinkManager.add_link(
            CPO_CHAIN, link["name"],
            level=link["level"],
            barrier=link["barrier"],
            rate=link["rate"],
            description=link["desc"],
            sort_order=link["sort_order"]
        )
        if lid:
            codes = [link["stocks"][i] for i in range(0, len(link["stocks"]), 2)]
            n = StockManager.add_stocks(CPO_CHAIN, link["name"], codes)
            total_stocks += n
            stock_list = ", ".join([f"{s[0]}:{s[1]}" for s in link["stocks"]])
            print(f"  📦 {link['name']} ({len(link['stocks'])}只) → 新增{n}只")
        else:
            print(f"  ❌ 添加环节失败: {link['name']}")
    
    # 添加依赖关系
    # DSP/电芯片 ← 光模块（电芯片驱动光模块）
    LinkManager.add_dep(CPO_CHAIN, "DSP/电芯片/SerDes", "核心材料(衬底/气体/靶材)")
    LinkManager.add_dep(CPO_CHAIN, "光芯片(EML/VCSEL/SiPh/DFB)", "核心材料(衬底/气体/靶材)")
    LinkManager.add_dep(CPO_CHAIN, "光引擎/光模块(200G/400G/800G/1.6T)", "光芯片(EML/VCSEL/SiPh/DFB)")
    LinkManager.add_dep(CPO_CHAIN, "光引擎/光模块(200G/400G/800G/1.6T)", "DSP/电芯片/SerDes")
    LinkManager.add_dep(CPO_CHAIN, "FA光纤阵列/MPO连接器/光纤光缆", "核心材料(衬底/气体/靶材)")
    LinkManager.add_dep(CPO_CHAIN, "温控/TEC/精密设备", "核心材料(衬底/气体/靶材)")
    LinkManager.add_dep(CPO_CHAIN, "温控/TEC/精密设备", "光引擎/光模块(200G/400G/800G/1.6T)")
    LinkManager.add_dep(CPO_CHAIN, "数据中心应用/交换机/算力", "光引擎/光模块(200G/400G/800G/1.6T)")
    LinkManager.add_dep(CPO_CHAIN, "数据中心应用/交换机/算力", "FA光纤阵列/MPO连接器/光纤光缆")
    LinkManager.add_dep(CPO_CHAIN, "数据中心应用/交换机/算力", "温控/TEC/精密设备")
    
    print(f"\n{'='*60}")
    print(f"✅ CPO全景产业链构建完成！")
    print(f"  链名: {CPO_CHAIN}")
    print(f"  环节: {len(LINKS)} 个")
    print(f"  股票: {total_stocks} 只（含跨环节去重前）")
    db.close()

if __name__ == '__main__':
    build()
