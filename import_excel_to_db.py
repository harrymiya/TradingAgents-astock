#!/usr/bin/env python3
"""
将Excel产业链JSON导入DB

从 _excel_summary.json 读取55个产业链的12,637家is_listed公司，
匹配到 stock_industries 表的 code（A股上市公司），建立 industry_chains/chain_links/chain_stocks 记录。

匹配策略：
1. 从 listing 字段提取A股市场代码（创业板/沪主板/深主板/科创板/北交所 + 6位代码）
2. 对于"股权/战略融资"等没有显式代码的，用公司名模糊匹配到 stock_industries 表
3. 不引入不在 stock_industries 表中的代码（确保只关联已覆盖的A股公司）
"""

import json
import re
import sqlite3
import os
from collections import defaultdict

# ==================== CONFIG ====================
DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")
JSON_PATH = os.path.expanduser("~/industry_pdf_extracted/_excel_summary.json")

# A股市场前缀（仅包含A股交易所）
A_SHARE_MARKET_PREFIXES = {'创业板', '沪主板', '深主板', '科创板', '北交所'}
# 新三板（不视为A股，但也可尝试匹配）
NEEQ_PREFIXES = {'新三板'}

# 带市场前缀的6位代码模式
MARKET_CODE_RE = re.compile(r'(?:' + '|'.join(re.escape(p) for p in A_SHARE_MARKET_PREFIXES) + r')[（(]\s*(\d{6})\s*[）)]')


def extract_a_share_code(listing_text):
    """
    从 listing 字段提取A股代码（仅限创业板/沪主板/深主板/科创板/北交所）。
    
    Returns:
        str or None: 6位A股代码
    """
    if not listing_text:
        return None
    
    # 先找带A股市场前缀的
    m = MARKET_CODE_RE.search(listing_text)
    if m:
        return m.group(1)
    
    # 纯港股/美股/新三板上市 — 跳过
    if '港交所' in listing_text:
        return None
    if listing_text.startswith('赴美上市'):
        return None
    
    # 新三板不视为A股（但后面可作为补丁）
    
    # 股权/战略融资等 — 需要尝试名称匹配
    if listing_text in ('股权/战略融资', '未融资', '-', ''):
        return None
    
    # 上市辅导/IPO申报 — 没有代码
    if '上市辅导' in listing_text or 'IPO申报' in listing_text:
        return None
    
    # 最后尝试提取裸6位码
    six_digit_codes = re.findall(r'\b(\d{6})\b', listing_text)
    for code in six_digit_codes:
        if code[0] in ('0', '3', '6'):
            return code
    
    return None


def load_stock_industries_lookup(conn):
    """从 stock_industries 表加载 code→(l1,l2,l3) 映射"""
    c = conn.cursor()
    c.execute("SELECT code, industry_l1, industry_l2, industry_l3 FROM stock_industries")
    return {row[0]: {'l1': row[1], 'l2': row[2], 'l3': row[3]} for row in c.fetchall()}


def load_existing_chains_and_links(conn):
    """加载已存在的产业链和链节"""
    c = conn.cursor()
    c.execute("SELECT id, name FROM industry_chains")
    existing_chains = {row[1]: row[0] for row in c.fetchall()}
    
    c.execute("SELECT id, chain_id, name, level FROM chain_links")
    existing_links = {(row[1], row[2], row[3]): row[0] for row in c.fetchall()}
    
    c.execute("SELECT link_id, code FROM chain_stocks")
    existing_stocks = set((row[0], row[1]) for row in c.fetchall())
    
    return existing_chains, existing_links, existing_stocks


def build_name_code_mapping(stock_industries_lookup):
    """
    从 stock_industries 表的代码构建中文名→代码映射。
    因为我们没有直接从股票名映射到代码的表，需要用其他方式。
    这里我们从JSON中提取已知的公司名→代码关系来建立字典。
    """
    # 从 stock_industries 的代码，我们没有名称，所以这里返回空字典
    # 真正的名称映射需要从 stock_industries 表+名称表，但我们没有名称表
    # 所以name→code映射需要从DB的 stocks 表或从 mootdx 获取
    return {}


def build_name_code_from_stocks_table(conn):
    """从 stocks 表构建 name→code 映射"""
    c = conn.cursor()
    result = {}
    try:
        c.execute("SELECT code, name FROM stocks")
        for code, name in c.fetchall():
            name = name.strip().replace('\u3000', '').replace(' ', '')
            if name:
                result[name] = code
                # 也建立短名（取前几个中文字）
                chinese = ''.join(re.findall(r'[\u4e00-\u9fff]+', name))
                if chinese and chinese != name:
                    result[chinese] = code
    except Exception as e:
        print(f"  Warning: stocks table: {e}")
    return result


def fuzzy_match_company(company_name, name_code_map, fuzzy_index):
    """
    模糊匹配公司名到股票代码。
    先用精确匹配，再用前缀+包含匹配。
    """
    cleaned = company_name.replace(' ', '').replace('\u3000', '').replace('\xa0', '')
    
    # 1. 精确匹配
    if cleaned in name_code_map:
        return name_code_map[cleaned]
    
    # 提取中文部分
    chinese_chars = re.findall(r'[\u4e00-\u9fff]+', cleaned)
    if not chinese_chars:
        return None
    full_chinese = ''.join(chinese_chars)
    
    # 2. 前缀匹配（从长到短）
    for prefix_len in range(min(6, len(full_chinese)), 1, -1):
        prefix = full_chinese[:prefix_len]
        candidates = fuzzy_index.get(prefix, [])
        if len(candidates) == 1:
            return candidates[0][0]
        elif len(candidates) > 1:
            # 找最匹配的：公司名包含股票名或反之
            for code, fn in candidates:
                if fn in full_chinese or full_chinese in fn:
                    return code
    
    # 3. 包含匹配
    for code, fn in name_code_map.items():
        if fn and (fn in full_chinese or full_chinese in fn):
            return code
    
    return None


def build_fuzzy_index(name_code_map):
    """
    构建前缀模糊索引。
    key: 2~6个中文字符前缀
    value: [(code, full_name)]
    """
    index = defaultdict(list)
    for name, code in name_code_map.items():
        chinese = ''.join(re.findall(r'[\u4e00-\u9fff]+', name))
        if not chinese:
            continue
        for plen in range(2, min(7, len(chinese) + 1)):
            prefix = chinese[:plen]
            index[prefix].append((code, chinese))
    # 去重
    for k in index:
        seen = set()
        unique = []
        for item in index[k]:
            if item[0] not in seen:
                seen.add(item[0])
                unique.append(item)
        index[k] = unique
    return dict(index)


def parse_path_levels(chain_path):
    """解析 chain_path 层级，过滤广告节点"""
    parts = chain_path.split('>')
    levels = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        if any(kw in part for kw in ['官方网址', '更多数据', '众鲤数据', 'zldatas']):
            continue
        levels.append((i + 1, part))
    return levels


def main():
    print("=" * 60)
    print("导入Excel产业链数据到DB")
    print("=" * 60)
    
    # 1. 加载JSON
    print("\n[1/6] 加载JSON文件...")
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    chain_names = list(data.keys())
    print(f"  产业链数量: {len(chain_names)}")
    
    # 统计is_listed的公司
    total_listed = 0
    for cn in chain_names:
        for comp in data[cn].get('companies', []):
            if comp.get('is_listed'):
                total_listed += 1
    print(f"  is_listed=true 总数: {total_listed}")
    
    # 2. 连接DB
    print("\n[2/6] 连接DB...")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA cache_size=-8000")  # 8MB cache
    
    # 3. 加载现有数据
    print("\n[3/6] 加载现有DB数据...")
    stock_industry_codes = load_stock_industries_lookup(conn)
    print(f"  stock_industries: {len(stock_industry_codes)} 个代码")
    
    name_code_map = build_name_code_from_stocks_table(conn)
    print(f"  stocks name→code: {len(name_code_map)} 条")
    
    existing_chains, existing_links, existing_stocks = load_existing_chains_and_links(conn)
    print(f"  已有 industry_chains: {len(existing_chains)}")
    print(f"  已有 chain_links: {len(existing_links)}")
    print(f"  已有 chain_stocks: {len(existing_stocks)}")
    
    # 构建模糊匹配索引
    fuzzy_index = build_fuzzy_index(name_code_map)
    reverse_name_map = {v: k for k, v in name_code_map.items()}  # code→name
    print(f"  模糊索引: {len(fuzzy_index)} 前缀")
    
    # 4. 统计数据
    print("\n[4/6] 匹配分析（统计只做一次）...")
    
    # 统计所有listed公司按listing分类
    listing_analysis = defaultdict(int)
    for cn in chain_names:
        for comp in data[cn].get('companies', []):
            if comp.get('is_listed'):
                listing_analysis[comp.get('listing', 'N/A')] += 1
    
    a_share_by_listing = 0
    for listing, count in sorted(listing_analysis.items(), key=lambda x: -x[1]):
        code = extract_a_share_code(listing)
        if code:
            a_share_by_listing += count
    
    print(f"  listing字段含A股代码: {a_share_by_listing} / {total_listed}")
    
    # 5. 处理每个产业链
    print("\n[5/6] 处理产业链数据并导入DB...")
    stats = {
        'chains_new': 0,
        'chains_skipped': 0,
        'links_new': 0,
        'stocks_new': 0,
        'matched_by_code': 0,
        'matched_by_name': 0,
        'unmatched': 0,
        'processed_companies': 0,
    }
    
    for idx, chain_name in enumerate(chain_names):
        chain_data = data[chain_name]
        
        # 创建/获取产业链ID
        new_name = f"{chain_name}(qcc)"
        if new_name in existing_chains:
            chain_id = existing_chains[new_name]
            stats['chains_skipped'] += 1
        else:
            description = chain_data.get('description', '') or f"企查查产业链数据 - {chain_name}"
            c = conn.cursor()
            c.execute(
                "INSERT INTO industry_chains (name, description, sort_order) VALUES (?, ?, ?)",
                (new_name, description[:500], idx)
            )
            chain_id = c.lastrowid
            existing_chains[new_name] = chain_id
            stats['chains_new'] += 1
        
        # 收集该产业链下每个 path→node→[code] 的映射
        path_nodes = defaultdict(lambda: defaultdict(set))
        
        companies = chain_data.get('companies', [])
        for comp in companies:
            if not comp.get('is_listed'):
                continue
            
            name = comp.get('name', '')
            listing = comp.get('listing', '')
            chain_path = comp.get('chain_path', '')
            node = comp.get('node', '')
            
            if not chain_path or not node:
                continue
            
            stats['processed_companies'] += 1
            
            code = None
            
            # 策略1: 从 listing 提取A股代码
            extracted = extract_a_share_code(listing)
            if extracted and extracted in stock_industry_codes:
                code = extracted
                stats['matched_by_code'] += 1
            
            # 策略2: 名称模糊匹配
            if not code:
                matched = fuzzy_match_company(name, name_code_map, fuzzy_index)
                if matched and matched in stock_industry_codes:
                    code = matched
                    stats['matched_by_name'] += 1
            
            if code:
                path_nodes[chain_path][node].add(code)
            else:
                stats['unmatched'] += 1
        
        # 创建 chain_links 和 chain_stocks
        for chain_path, node_companies in path_nodes.items():
            path_levels = parse_path_levels(chain_path)
            if not path_levels:
                continue
            
            # 创建所有层级节点，并记录每级对应的link_id
            prev_link_id = None
            level_link_ids = {}  # level_num → link_id
            
            for level_num, level_name in path_levels:
                key = (chain_id, level_name, level_num)
                if key in existing_links:
                    link_id = existing_links[key]
                else:
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO chain_links (chain_id, name, level) VALUES (?, ?, ?)",
                        (chain_id, level_name, level_num)
                    )
                    link_id = c.lastrowid
                    existing_links[key] = link_id
                    stats['links_new'] += 1
                
                level_link_ids[level_name] = link_id
                prev_link_id = link_id
            
            # 关联股票到对应节点
            for node_name, codes in node_companies.items():
                # 找到节点对应的link_id
                node_link_id = None
                for level_num, level_name in path_levels:
                    if level_name == node_name:
                        node_link_id = level_link_ids.get(level_name)
                        break
                
                if not node_link_id:
                    node_link_id = prev_link_id
                
                for code in codes:
                    stock_key = (node_link_id, code)
                    if stock_key not in existing_stocks:
                        c = conn.cursor()
                        c.execute(
                            "INSERT INTO chain_stocks (link_id, code) VALUES (?, ?)",
                            (node_link_id, code)
                        )
                        existing_stocks.add(stock_key)
                        stats['stocks_new'] += 1
        
        if (idx + 1) % 10 == 0 or idx == len(chain_names) - 1:
            conn.commit()
            print(f"  [{idx+1}/{len(chain_names)}] {chain_name}: "
                  f"new_chains={stats['chains_new']}, new_links={stats['links_new']}, "
                  f"new_stocks={stats['stocks_new']}, "
                  f"matched_by_code={stats['matched_by_code']}, "
                  f"matched_by_name={stats['matched_by_name']}, "
                  f"unmatched={stats['unmatched']}")
    
    conn.commit()
    
    # 6. 最终统计
    print("\n" + "=" * 60)
    print("导入完成！最终统计")
    print("=" * 60)
    
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM industry_chains")
    total_chains = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chain_links")
    total_links = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chain_stocks")
    total_stocks = c.fetchone()[0]
    
    print(f"  处理上市公司: {stats['processed_companies']} / {total_listed}")
    print(f"  listing代码匹配: {stats['matched_by_code']}")
    print(f"  名称模糊匹配: {stats['matched_by_name']}")
    print(f"  未匹配: {stats['unmatched']}")
    print(f"  ------------")
    print(f"  新建产业链: {stats['chains_new']} (已跳过 {stats['chains_skipped']})")
    print(f"  新建链节: {stats['links_new']}")
    print(f"  新增股票关联: {stats['stocks_new']}")
    print(f"  ------------")
    print(f"  industry_chains 总数: {total_chains}")
    print(f"  chain_links 总数: {total_links}")
    print(f"  chain_stocks 总数: {total_stocks}")
    
    # 列出企查查来源的产业链
    c.execute("SELECT id, name FROM industry_chains WHERE name LIKE '%(qcc)%' ORDER BY id")
    qcc_chains = c.fetchall()
    print(f"\n  企查查产业链列表 ({len(qcc_chains)}):")
    for row in qcc_chains:
        # count links and stocks
        c.execute("SELECT COUNT(*) FROM chain_links WHERE chain_id=?", (row[0],))
        lc = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT cs.code) FROM chain_stocks cs JOIN chain_links cl ON cs.link_id=cl.id WHERE cl.chain_id=?", (row[0],))
        sc = c.fetchone()[0]
        print(f"    [{row[0]}] {row[1]} — {lc} links, {sc} stocks")
    
    conn.close()
    print("\n完成!")


def validate():
    """测试 listing 代码提取逻辑"""
    test_cases = [
        ("创业板（300597）", "300597"),
        ("沪主板（600008）", "600008"),
        ("深主板（000012）", "000012"),
        ("科创板（688001）", "688001"),
        ("北交所（430017）、新三板（430017）转板", "430017"),
        ("新三板（430005）", None),  # 新三板不视为A股
        ("沪主板（600011）、港交所（00902）", "600011"),
        ("科创板（688180）、港交所（01877）", "688180"),
        ("深主板（000333）、港交所（00300）", "000333"),
        ("创业板（300750）", "300750"),
        ("创业板（300750）、港交所（06680）", "300750"),
        ("赴港上市（00700）", None),
        ("赴美上市（BABA）", None),
        ("股权/战略融资", None),
        ("未融资", None),
        ("上市辅导、新三板（430293）", None),
        ("上市辅导终止、新三板（430222）", None),
        ("创业板IPO申报、赴港上市（01478）", None),
        ("创业板IPO申报终止、新三板（831006）", None),
        ("北交所IPO申报、新三板（430073）", None),
        ("", None),
        ("科创板（688286）、新三板（836736）", "688286"),
    ]
    
    all_pass = True
    for listing, expected in test_cases:
        result = extract_a_share_code(listing)
        status = "✓" if result == expected else "✗"
        if status == "✗":
            all_pass = False
        print(f"{status} {listing:<55s} → {result} (expected {expected})")
    
    print(f"\n{'全部通过!' if all_pass else '有失败!'}")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--validate':
        validate()
    else:
        main()
