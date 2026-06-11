#!/usr/bin/env python3
"""
将 frameworks/*.json 中的新产业链（已含 name_map）
转换为 frameworks_data.json 格式（sections -> links -> stocks[{code, name}]）
并合并到 src/data/frameworks_data.json
"""
import json, os, sys

FRAMEWORKS_DIR = os.path.expanduser("~/code/TradingAgents-astock/frameworks")
FRAMEWORKS_DATA = os.path.expanduser(
    "~/code/TradingAgents-astock/industry-map/src/data/frameworks_data.json"
)

# 已有3个老产业链在 frameworks_data.json 中（CPO、宇树、AI算力）
# stocks.json 中已有全部9个产业链
# 我们要读取每个新产业链的JSON -> 转成 frameworks_data 格式 -> 追加

# 新产业链列表（已在 frameworks/ 下）
NEW_CHAINS = ["MLCC", "PCB钻针", "端侧AI", "液冷散热", "金刚石散热", "存储芯片"]

def load_frameworks_data():
    with open(FRAMEWORKS_DATA, "r", encoding="utf-8") as f:
        return json.load(f)

def save_frameworks_data(data):
    with open(FRAMEWORKS_DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_chain_json(name):
    """读取 frameworks/{name}.json，返回 {chain_name: {section: [codes]}, _name_map: {}}"""
    path = os.path.join(FRAMEWORKS_DIR, f"{name}.json")
    if not os.path.exists(path):
        print(f"  ⚠️  {path} not found, skip")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def convert_to_frameworks_format(chain_name, data):
    """将 {chain_name: {section: [codes]}, _name_map: {}} 转为
    {name, source, sections: [{name, links: [{name, stocks: [{code, name}]}]}]}
    """
    name_map = data.get("_name_map", {})
    chain_data = data.get(chain_name, data)
    # 如果顶层 key 不是 chain_name，取第一个非 _name_map 的key
    if chain_name not in chain_data:
        for key in list(data.keys()):
            if key != "_name_map":
                chain_data = data[key]
                break

    sections = {}
    for section_name, codes in chain_data.items():
        if section_name == "_name_map":
            continue
        # 按前缀分组：上游/中游/下游 或 其他
        if section_name.startswith("上游"):
            group = "上游材料"
        elif section_name.startswith("中游"):
            group = "中游设备"
        elif section_name.startswith("下游"):
            group = "下游应用"
        else:
            group = "核心环节"

        if group not in sections:
            sections[group] = []
        # 去重保持顺序
        seen = set()
        unique_codes = []
        for c in codes:
            if c not in seen:
                unique_codes.append(c)
                seen.add(c)
        stocks = [{"code": c, "name": name_map.get(c, c)} for c in unique_codes]
        sections[group].append({
            "name": section_name,
            "stocks": stocks
        })

    result_sections = []
    # 确保顺序：核心 -> 上游 -> 中游 -> 下游
    for group_name in ["核心环节", "上游材料", "中游设备", "下游应用"]:
        if group_name in sections:
            result_sections.append({
                "name": group_name,
                "links": sections[group_name]
            })

    return {
        "name": chain_name,
        "source": f"{chain_name}.json",
        "sections": result_sections
    }

def main():
    # 读取现有的 frameworks_data
    existing = load_frameworks_data()
    existing_keys = set(existing.keys())

    added = 0
    for chain_name in NEW_CHAINS:
        if chain_name in existing_keys:
            print(f"  ✓ {chain_name} already in frameworks_data.json, skip")
            continue

        data = load_chain_json(chain_name)
        if data is None:
            continue

        converted = convert_to_frameworks_format(chain_name, data)
        existing[chain_name] = converted
        print(f"  ✓ {chain_name} added ({len(converted['sections'])} sections)")
        added += 1

    if added > 0:
        save_frameworks_data(existing)
        print(f"\n✅ Added {added} new chains to frameworks_data.json")
        print(f"   Total chains: {len(existing)}")
    else:
        print("\nℹ️  No new chains to add")

    # 打印统计
    for name, info in existing.items():
        if isinstance(info, dict) and "sections" in info:
            total_links = sum(len(s["links"]) for s in info["sections"])
            total_stocks = sum(
                len(s["links"][li]["stocks"])
                for s in info["sections"]
                for li in range(len(s["links"]))
            )
            print(f"   {name}: {len(info['sections'])} sections, {total_links} links, {total_stocks} stocks")

if __name__ == "__main__":
    main()
