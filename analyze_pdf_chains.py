#!/usr/bin/env python3
"""
分析PDF产业链文本，提取上市公司关系和行业景气度
============================================
1. 读取 _chain_summary.json 中的公司和产业链信息
2. 用 mootdx 获取全市场A股代码映射
3. 模糊匹配公司名 → A股代码
4. 从PDF文本中提取上中下游关系
5. 提取行业景气度判断
6. 输出 _pdf_analysis.json 并统计
"""

import json
import os
import re
import sys
from collections import defaultdict, Counter

# ── paths ──
EXTRACTED_DIR = os.path.expanduser("~/industry_pdf_extracted")
SUMMARY_FILE = os.path.join(EXTRACTED_DIR, "_chain_summary.json")
OUTPUT_FILE = os.path.join(EXTRACTED_DIR, "_pdf_analysis.json")
VENV_PYTHON = os.path.expanduser("~/code/TradingAgents-astock/.venv/bin/python")

# ── 1. Load summary ──
print("=" * 60)
print("STEP 1: 加载 _chain_summary.json")
print("=" * 60)

with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
    pdf_data = json.load(f)

print(f"  共 {len(pdf_data)} 个PDF条目")

# ── 2. Get A-share stock name → code mapping via mootdx ──
print("\n" + "=" * 60)
print("STEP 2: 获取全市场A股名称→代码映射")
print("=" * 60)

def get_stock_map():
    """Get stock name to code mapping. Returns dict name->code."""
    import subprocess
    script = '''
import json, re
from mootdx.quotes import Quotes
q = Quotes.factory()
stocks = q.stocks()
result = {}
for _, row in stocks.iterrows():
    c = str(row["code"])
    name = str(row["name"]).strip().replace("\\x00", "").replace("\\u0000", "").strip()
    if not name:
        continue
    # Filter to real A-stock codes (exclude indices)
    if not re.match(r"^(000|001|002|003|600|601|603|605|688|300|301|920)\\d{3}$", c):
        continue
    # Filter out obvious index names
    if any(kw in name for kw in ["指数", "上证", "沪深", "深证", "等权", "消费", "制造"]):
        if len(name) <= 4:
            continue
    result[name] = c
print(json.dumps(result, ensure_ascii=False))
'''
    result = subprocess.run(
        [VENV_PYTHON, "-c", script],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:500]}")
        return {}
    try:
        mapping = json.loads(result.stdout.strip())
        print(f"  成功获取 {len(mapping)} 只A股代码映射")
        return mapping
    except json.JSONDecodeError as e:
        print(f"  JSON解析失败: {e}")
        print(f"  stdout前500字: {result.stdout[:500]}")
        return {}

stock_name_code_map = get_stock_map()

# Build suffix map: "宁德" -> "宁德时代" etc.
def build_name_index(name_map):
    """Build prefix-based index for fuzzy matching."""
    prefix_map = defaultdict(list)
    for name in name_map:
        for length in range(2, min(len(name) + 1, 5)):
            prefix = name[:length]
            prefix_map[prefix].append(name)
    return prefix_map

name_index = build_name_index(stock_name_code_map)

def fuzzy_match_company(company_name, min_prefix=2):
    """
    Fuzzy match a company name to A-share stock name.
    Strategy: try prefix matching from long to short.
    Returns (matched_name, code) or (None, None)
    """
    cname = company_name.strip()
    if not cname:
        return None, None
    
    # Direct match
    if cname in stock_name_code_map:
        return cname, stock_name_code_map[cname]
    
    # Try various prefix lengths (longer first for better precision)
    for plen in range(min(len(cname), 4), min_prefix - 1, -1):
        prefix = cname[:plen]
        candidates = name_index.get(prefix, [])
        if len(candidates) == 1:
            return candidates[0], stock_name_code_map[candidates[0]]
        elif len(candidates) > 1:
            # Multiple matches - try to find best one
            # Prefer exact suffix match (e.g. "宁德" matches "宁德时代" better than "宁德新能源")
            for cand in candidates:
                if cand.startswith(cname):
                    return cand, stock_name_code_map[cand]
            # If still ambiguous, return first and note ambiguity
            return candidates[0], stock_name_code_map[candidates[0]]
    
    return None, None

# ── 3. Match companies for each PDF ──
print("\n" + "=" * 60)
print("STEP 3: 匹配PDF中提取的公司名到A股代码")
print("=" * 60)

results = []
total_company_mentions = 0
matched_company_mentions = 0
matched_companies_set = set()

for pdf_entry in pdf_data:
    source_file = pdf_entry.get("source_file", "unknown")
    companies_raw = pdf_entry.get("companies", [])
    
    matched_companies = []
    seen_codes = set()
    
    for comp in companies_raw:
        name = comp.get("name", "")
        context = comp.get("context", "")
        total_company_mentions += 1
        
        # Skip non-company entries (phrases that are clearly not company names)
        # Heuristic: skip short fragments, stock exchange terms, etc.
        if len(name) < 2:
            continue
        if any(kw in name for kw in ["人工智能", "智能体", "公司", "产业链", "新一代"]):
            if len(name) < 4:
                continue
        
        matched_name, code = fuzzy_match_company(name)
        if code:
            matched_company_mentions += 1
            matched_companies_set.add(code)
            if code not in seen_codes:
                seen_codes.add(code)
                matched_companies.append({
                    "original_name": name,
                    "matched_name": matched_name,
                    "code": code,
                    "context": context[:100]
                })
    
    results.append({
        "source_file": source_file,
        "matched_companies": matched_companies,
        "matched_count": len(matched_companies)
    })
    
    if matched_companies:
        print(f"  [{source_file[:50]:50s}] {len(matched_companies)} 家公司匹配")

print(f"\n  总计公司提及: {total_company_mentions}")
print(f"  匹配到A股代码: {matched_company_mentions}")
print(f"  唯一匹配公司: {len(matched_companies_set)} 家")

# ── 4. Extract upstream/midstream/downstream relationships from PDF text ──
print("\n" + "=" * 60)
print("STEP 4: 从PDF文本提取上中下游关系")
print("=" * 60)

CHAIN_KEYWORDS = [
    "上游", "中游", "下游", "产业链", "供应商", "客户",
    "原材料", "零部件", "组件", "整机", "终端",
    "资源", "矿产", "制造", "生产", "应用",
]

RELATION_PATTERNS = [
    (r"(.+?)是(.+?)的供应商", "supplier"),
    (r"(.+?)为(.+?)提供(.+?)", "provider"),
    (r"(.+?)向(.+?)供应(.+?)", "supplier"),
    (r"(.+?)采购(.+?)", "buyer"),
    (r"(.+?)依赖(.+?)进口", "dependent"),
    (r"上游(.+?)包括(.+?)", "upstream"),
    (r"中游(.+?)包括(.+?)", "midstream"),
    (r"下游(.+?)包括(.+?)", "downstream"),
    (r"上游(.+?)涉及(.+?)", "upstream"),
    (r"中游(.+?)涉及(.+?)", "midstream"),
    (r"下游(.+?)涉及(.+?)", "downstream"),
]

def find_chain_info(text, matched_names):
    """Extract upstream/midstream/downstream information from text."""
    info = {
        "chain_mentions": [],
        "relationships": [],
        "company_role": defaultdict(list)
    }
    
    if not text:
        return info
    
    # Look for段落 containing chain keywords
    paragraphs = re.split(r'\n\s*\n', text)
    for para in paragraphs:
        para_lower = para.lower()
        if any(kw in para_lower for kw in CHAIN_KEYWORDS):
            info["chain_mentions"].append(para[:300])
            
            # Check for relationships
            for pattern, rel_type in RELATION_PATTERNS:
                for m in re.finditer(pattern, para):
                    groups = m.groups()
                    if groups:
                        info["relationships"].append({
                            "type": rel_type,
                            "text": m.group(0)[:200],
                            "full_para": para[:300]
                        })
    
    # Assign roles based on chain keywords proximity
    for name in matched_names:
        name_lower = name.lower()
        for para in paragraphs:
            if name_lower not in para.lower():
                continue
            if "上游" in para:
                info["company_role"][name].append("upstream")
            if "中游" in para:
                info["company_role"][name].append("midstream")
            if "下游" in para:
                info["company_role"][name].append("downstream")
    
    return info

for i, pdf_entry in enumerate(pdf_data):
    source_file = pdf_entry.get("source_file", "unknown")
    txt_path = os.path.join(EXTRACTED_DIR, source_file.replace(".pdf", ".txt"))
    
    matched_names = [c["matched_name"] for c in results[i]["matched_companies"]]
    
    chain_info = {"chain_mentions": [], "relationships": [], "company_role": {}}
    
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            chain_info = find_chain_info(text, matched_names)
        except Exception as e:
            print(f"  读取 {source_file} 失败: {e}")
    
    # Also use explicitly extracted chain info from summary
    for chain_entry in pdf_entry.get("chains", []):
        chain_text = chain_entry.get("text", "")
        ctx = chain_entry.get("context", [])
        combined = chain_text + " " + " ".join(ctx)
        chain_info["chain_mentions"].append(combined[:500])
    
    results[i]["chain_info"] = {
        "chain_mentions_count": len(chain_info["chain_mentions"]),
        "relationships": chain_info["relationships"][:20],
        "company_role": {k: list(set(v)) for k, v in chain_info["company_role"].items()}
    }
    
    if chain_info["chain_mentions"]:
        print(f"  [{source_file[:50]:50s}] {len(chain_info['chain_mentions'])} 条产业链提及")

# ── 5. Extract industry sentiment/prosperity ──
print("\n" + "=" * 60)
print("STEP 5: 提取行业景气度判断")
print("=" * 60)

SENTIMENT_KEYWORDS = {
    "growth": ["增长", "增速", "扩大", "提升", "增加", "上涨", "突破", "新高", "供不应求"],
    "prosperity": ["景气", "繁荣", "旺盛", "火热", "高速发展", "蓬勃发展", "爆发", "万亿", "千亿", "百亿"],
    "decline": ["下滑", "下降", "减少", "萎缩", "衰退", "低迷", "过剩", "瓶颈", "供过于求"],
    "policy": ["政策支持", "政策利好", "国家战略", "补贴", "扶持", "十四五", "碳中和", "碳达峰"],
    "scale": ["市场规模", "出货量", "装机量", "渗透率", "产值", "营收", "利润"],
}

def extract_sentiment(text):
    """Extract sentiment/prosperity judgments from text."""
    sentiments = {k: [] for k in SENTIMENT_KEYWORDS}
    
    if not text:
        return sentiments
    
    # Split into sentences
    sentences = re.split(r'[。！？\n]', text)
    
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 10:
            continue
        
        for category, keywords in SENTIMENT_KEYWORDS.items():
            for kw in keywords:
                if kw in sent:
                    # Try to find number contexts
                    numbers = re.findall(r'[\d,]+\.?[\d]*[%万亿千]?', sent)
                    sentiments[category].append({
                        "sentence": sent[:200],
                        "keyword": kw,
                        "numbers": numbers[:5]
                    })
                    break
    
    return sentiments

for i, pdf_entry in enumerate(pdf_data):
    source_file = pdf_entry.get("source_file", "unknown")
    txt_path = os.path.join(EXTRACTED_DIR, source_file.replace(".pdf", ".txt"))
    
    sentiment_info = {k: [] for k in SENTIMENT_KEYWORDS}
    
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            sentiment_info = extract_sentiment(text)
        except Exception as e:
            print(f"  读取 {source_file} 失败: {e}")
    
    results[i]["sentiment"] = {
        k: v[:10] for k, v in sentiment_info.items()
    }
    
    total_sentiments = sum(len(v) for v in sentiment_info.values())
    if total_sentiments > 0:
        # Show summary
        growth_n = len(sentiment_info["growth"])
        prosperity_n = len(sentiment_info["prosperity"])
        decline_n = len(sentiment_info["decline"])
        scale_n = len(sentiment_info["scale"])
        print(f"  [{source_file[:50]:50s}] 增长:{growth_n} 景气:{prosperity_n} 衰退:{decline_n} 规模:{scale_n}")

# ── 6. Output results ──
print("\n" + "=" * 60)
print("STEP 6: 输出结果")
print("=" * 60)

# Build statistics
total_pdfs = len(results)
pdfs_with_matches = sum(1 for r in results if r["matched_count"] > 0)
pdfs_with_chains = sum(1 for r in results if r["chain_info"]["chain_mentions_count"] > 0)

# Top matched companies across all PDFs
all_matched_codes = []
all_matched_names = []
for r in results:
    for c in r["matched_companies"]:
        all_matched_codes.append(c["code"])
        all_matched_names.append(c["matched_name"])

code_freq = Counter(all_matched_codes)
name_freq = Counter(all_matched_names)

top_companies = []
for code, cnt in code_freq.most_common(20):
    name = [n for n, c in name_freq.items() if stock_name_code_map.get(n) == code]
    top_companies.append({"code": code, "name": name[0] if name else code, "pdf_count": cnt})

# Sentiment summary
all_sentiments = {"growth": 0, "prosperity": 0, "decline": 0, "policy": 0, "scale": 0}
for r in results:
    for k in all_sentiments:
        all_sentiments[k] += len(r["sentiment"].get(k, []))

# Build final output
output = {
    "summary": {
        "total_pdfs": total_pdfs,
        "pdfs_with_company_matches": pdfs_with_matches,
        "pdfs_with_chain_mentions": pdfs_with_chains,
        "total_company_mentions": total_company_mentions,
        "matched_company_mentions": matched_company_mentions,
        "unique_matched_companies": len(matched_companies_set),
        "unique_matched_codes": len(code_freq),
        "match_rate": f"{matched_company_mentions/max(total_company_mentions,1)*100:.1f}%",
        "top_companies": top_companies,
        "sentiment_summary": {
            "growth_mentions": all_sentiments["growth"],
            "prosperity_mentions": all_sentiments["prosperity"],
            "decline_mentions": all_sentiments["decline"],
            "policy_mentions": all_sentiments["policy"],
            "scale_mentions": all_sentiments["scale"],
        }
    },
    "pdf_details": results
}

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n  输出文件: {OUTPUT_FILE}")
print(f"  文件大小: {os.path.getsize(OUTPUT_FILE):,} bytes")

# ── Final report ──
print("\n" + "=" * 60)
print("最终统计报告")
print("=" * 60)
print(f"  PDF文件总数:              {total_pdfs}")
print(f"  有公司匹配的PDF数:        {pdfs_with_matches}")
print(f"  有产业链提及的PDF数:      {pdfs_with_chains}")
print(f"  总公司提及次数:           {total_company_mentions}")
print(f"  匹配到A股代码的次数:      {matched_company_mentions}")
print(f"  匹配率:                   {matched_company_mentions/max(total_company_mentions,1)*100:.1f}%")
print(f"  唯一匹配公司数:           {len(matched_companies_set)}")
print(f"  唯一匹配代码数:           {len(code_freq)}")
print(f"\n  景气度信号:")
for k, v in all_sentiments.items():
    print(f"    {k}: {v} 条")
print(f"\n  出现次数最多的公司(TOP10):")
for tc in top_companies[:10]:
    print(f"    {tc['code']} {tc['name']}: 出现在 {tc['pdf_count']} 个PDF中")
