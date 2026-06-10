#!/usr/bin/env python3
"""
从 DB (industry_chains / chain_links / chain_stocks / chain_link_deps)
重新生成 industry_data.json，覆盖所有 77 个产业链。

用法:
    cd /home/harrydolly/code/TradingAgents-astock/industry-map
    python3 server/build_industry_json.py
"""

import json
import os
import sqlite3

DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src",
    "data",
    "industry_data.json",
)


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_industry_data() -> dict:
    conn = connect_db()
    cur = conn.cursor()

    # 1. 所有产业链，按 sort_order 排序
    cur.execute(
        "SELECT id, name, description FROM industry_chains ORDER BY sort_order, id"
    )
    chains = cur.fetchall()

    # link_id -> name 映射
    cur.execute("SELECT id, name FROM chain_links")
    link_id_to_name: dict[int, str] = {row["id"]: row["name"] for row in cur.fetchall()}

    # 按 chain_id 分组的环节
    cur.execute(
        "SELECT id, chain_id, name, level, barrier, localization_rate, description, sort_order "
        "FROM chain_links ORDER BY sort_order"
    )
    links_by_chain: dict[int, list[sqlite3.Row]] = {}
    for row in cur.fetchall():
        links_by_chain.setdefault(row["chain_id"], []).append(row)

    # 按 link_id 分组的股票
    cur.execute("SELECT link_id, code FROM chain_stocks")
    stocks_by_link: dict[int, list[str]] = {}
    for row in cur.fetchall():
        stocks_by_link.setdefault(row["link_id"], []).append(row["code"])

    # 依赖关系
    # depends_on_link_id 是上游，link_id 是下游
    # deps_downstream[link_id] = [depends_on_link_ids] → 该环节的上游环节IDs
    # deps_upstream[depends_on_link_id] = [link_ids] → 该环节的下游环节IDs
    cur.execute("SELECT link_id, depends_on_link_id FROM chain_link_deps")
    deps_downstream: dict[int, list[int]] = {}
    deps_upstream: dict[int, list[int]] = {}
    for row in cur.fetchall():
        deps_downstream.setdefault(row["link_id"], []).append(row["depends_on_link_id"])
        deps_upstream.setdefault(row["depends_on_link_id"], []).append(row["link_id"])

    # 检查哪些 chain 有 deps 记录
    cur.execute("""
        SELECT DISTINCT l.chain_id
        FROM chain_link_deps d
        JOIN chain_links l ON d.link_id = l.id
    """)
    chains_with_deps = {row["chain_id"] for row in cur.fetchall()}

    conn.close()

    # 构建输出
    result = {}

    for chain in chains:
        chain_id = chain["id"]
        chain_name = chain["name"]
        chain_desc = chain["description"] or ""

        links = links_by_chain.get(chain_id, [])
        if not links:
            result[chain_name] = {"描述": chain_desc, "环节": {}}
            continue

        link_ids_in_chain = {link["id"] for link in links}
        has_deps = chain_id in chains_with_deps

        sections = {}
        for link in links:
            lid = link["id"]
            link_name = link["name"]

            # 解析上游/下游：只从 chain_link_deps 表获取
            # 只在同一产业链内的环节之间建立关系
            if has_deps and lid in deps_downstream:
                upstream = [
                    link_id_to_name[uid]
                    for uid in deps_downstream[lid]
                    if uid in link_ids_in_chain and uid in link_id_to_name
                ]
            else:
                upstream = []

            if has_deps and lid in deps_upstream:
                downstream = [
                    link_id_to_name[uid]
                    for uid in deps_upstream[lid]
                    if uid in link_ids_in_chain and uid in link_id_to_name
                ]
            else:
                downstream = []

            stocks = stocks_by_link.get(lid, [])

            sections[link_name] = {
                "上游": upstream,
                "下游": downstream,
                "壁垒": link["barrier"] if link["barrier"] is not None else 3,
                "国产化率": (
                    link["localization_rate"]
                    if link["localization_rate"] is not None
                    else 50
                ),
                "股票": stocks,
                "描述": link["description"] or "",
            }

        result[chain_name] = {"描述": chain_desc, "环节": sections}

    return result


def main():
    print(f"读取数据库: {DB_PATH}")
    data = build_industry_data()
    total_chains = len(data)
    total_links = sum(len(v["环节"]) for v in data.values())
    total_stocks = sum(
        len(stk)
        for v in data.values()
        for lv in v["环节"].values()
        for stk in [lv["股票"]]
    )
    print(f"产业链: {total_chains} 个")
    print(f"环节: {total_links} 个")
    print(f"股票: {total_stocks} 条")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"写入: {OUTPUT_PATH}")
    print("完成!")


if __name__ == "__main__":
    main()
