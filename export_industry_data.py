#!/usr/bin/env python3
"""
从DB导出全部产业链数据为React可用的JSON格式
兼容现有 industry_data.json 的格式
"""
import sqlite3, os, json

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')
OUT_PATH = os.path.expanduser('~/code/TradingAgents-astock/industry-map/src/data/industry_data.json')

db = sqlite3.connect(DB_PATH)

# 获取所有产业链（排除企查查链中股票数为0的）
chains = db.execute('''
    SELECT ic.id, ic.name, ic.description,
           (SELECT COUNT(DISTINCT cs.code) FROM chain_stocks cs 
            JOIN chain_links cl ON cs.link_id = cl.id WHERE cl.chain_id = ic.id) as stock_cnt
    FROM industry_chains ic
    ORDER BY ic.id
''').fetchall()

# 获取stock_industries表做行业映射
industry_map = {}
try:
    rows = db.execute('SELECT code, industry_l1 FROM stock_industries').fetchall()
    for code, ind in rows:
        industry_map[code] = ind or ''
except:
    pass

# 获取所有股票的行业信息（从stock_industries）
stock_industry = {}
try:
    rows = db.execute('SELECT code, industry_l1, industry_l2 FROM stock_industries').fetchall()
    for code, l1, l2 in rows:
        stock_industry[code] = {'l1': l1 or '', 'l2': l2 or ''}
except:
    pass

# 从chain_link_deps获取上下游关系
link_deps = {}  # link_id -> {'upstream': [link_names], 'downstream': [link_names]}
try:
    rows = db.execute('''
        SELECT d.link_id, d.depends_on_link_id, cl.name as link_name, cl2.name as dep_name
        FROM chain_link_deps d
        JOIN chain_links cl ON d.link_id = cl.id
        JOIN chain_links cl2 ON d.depends_on_link_id = cl2.id
    ''').fetchall()
    for link_id, dep_id, link_name, dep_name in rows:
        if link_id not in link_deps:
            link_deps[link_id] = {'upstream': [], 'downstream': []}
        link_deps[link_id]['upstream'].append(dep_name)
        if dep_id not in link_deps:
            link_deps[dep_id] = {'upstream': [], 'downstream': []}
        link_deps[dep_id]['downstream'].append(link_name)
except:
    pass

result = {}

for ch_id, ch_name, ch_desc, stock_cnt in chains:
    if stock_cnt == 0:
        continue
    
    # 获取环节列表（按sort_order排序）
    links = db.execute(
        'SELECT id, name, level, description, barrier, localization_rate, sort_order '
        'FROM chain_links WHERE chain_id=? ORDER BY sort_order',
        (ch_id,)).fetchall()
    
    links_dict = {}
    
    for lk_id, lk_name, lk_level, lk_desc, lk_barrier, lk_local, lk_sort in links:
        safe_name = lk_name if lk_name and lk_name.strip() else f"环节{lk_id}"
        
        # 获取该环节的股票（最多30只）
        stocks = db.execute(
            'SELECT code FROM chain_stocks WHERE link_id=? LIMIT 30',
            (lk_id,)).fetchall()
        codes = [s[0] for s in stocks]
        
        # 获取上下游
        deps = link_deps.get(lk_id, {'upstream': [], 'downstream': []})
        
        links_dict[safe_name] = {
            "上游": deps['upstream'],
            "下游": deps['downstream'],
            "壁垒": lk_barrier or 3,
            "国产化率": lk_local or 50,
            "股票": codes,
            "描述": lk_desc or '',
            "level": lk_level,
        }
    
    if not links_dict:
        continue
    
    # 对没有上下游数据的链，按排序顺序自动推断（前一个环节是上游，后一个是下游）
    link_names = list(links_dict.keys())
    has_deps = any(links_dict[n]['上游'] or links_dict[n]['下游'] for n in link_names)
    
    if not has_deps and len(link_names) > 1:
        # 按sort_order自动建立链式上下游
        for i in range(len(link_names) - 1):
            upstream = link_names[i]
            downstream = link_names[i + 1]
            if downstream not in links_dict[upstream]['下游']:
                links_dict[upstream]['下游'].append(downstream)
            if upstream not in links_dict[downstream]['上游']:
                links_dict[downstream]['上游'].append(upstream)
    
    result[ch_name] = {
        "描述": ch_desc or '',
        "环节": links_dict,
    }

db.close()

# 收集feat数据（每只股票最新一行）
print("\n收集feat数据...")
feat_data = {}
# 重新打开DB连接读feat
db2_read = sqlite3.connect(DB_PATH)
try:
    # 获取所有涉及股票的最新feat记录
    all_codes_list = list(set(c for v in result.values() 
                                for s in v['环节'].values() 
                                for c in s['股票']))
    if all_codes_list:
        # 对每只股票取最新一条feat
        for code in all_codes_list:
            row = db2_read.execute('''
                SELECT pos_20d, ma20_pct, vr_5, ret3, amp
                FROM feat WHERE code=? ORDER BY date DESC LIMIT 1
            ''', (code,)).fetchone()
            if row:
                pos = row[0] or 50
                ma20_pct = row[1] or 0
                vr5 = row[2] or 0
                ret3 = row[3] or 0
                amp = row[4] or 0
                
                # 计算超买超卖指标 (基于pos_20d)
                # pos_20d < 20 = 超卖, > 80 = 超买
                if pos < 20:
                    rsi_signal = -2  # 超卖
                    rsi_label = '超卖'
                elif pos < 35:
                    rsi_signal = -1
                    rsi_label = '偏卖'
                elif pos > 80:
                    rsi_signal = 2  # 超买
                    rsi_label = '超买'
                elif pos > 65:
                    rsi_signal = 1
                    rsi_label = '偏买'
                else:
                    rsi_signal = 0
                    rsi_label = '中性'
                
                # S3综合评分 (基于S3策略逻辑)
                s3_score = 0
                s3_label = ''
                if pos < 20 and -15 < ma20_pct < -5:
                    s3_score = 85
                    s3_label = 'S3超跌反弹'
                elif pos < 30 and ma20_pct < -5:
                    s3_score = 70
                    s3_label = '接近超跌'
                elif pos > 80:
                    s3_score = 20
                    s3_label = '高位风险'
                else:
                    s3_score = 50
                    s3_label = '正常'
                
                # 综合评分
                composite = 50
                if rsi_signal == -2: composite += 20  # 超卖是机会
                elif rsi_signal == -1: composite += 10
                elif rsi_signal == 2: composite -= 15  # 超买是风险
                elif rsi_signal == 1: composite -= 5
                if ma20_pct < -10: composite += 10
                elif ma20_pct > 10: composite -= 10
                composite = max(0, min(100, composite))
                
                feat_data[code] = {
                    'pos_20d': pos,
                    'ma20_pct': round(ma20_pct, 2),
                    'vr_5': round(vr5, 2),
                    'amp': round(amp, 2),
                    'rsi': rsi_signal,
                    'rsi_label': rsi_label,
                    's3_score': s3_score,
                    's3_label': s3_label,
                    'composite': composite,
                }
    print(f"  获取了 {len(feat_data)} 只feat数据")
except Exception as e:
    print(f"  feat获取失败: {e}")

# 在result中加入_feat字段
result['_feat'] = feat_data
db2_read.close()

# 写入JSON
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# 统计（排除_feat元数据）
chain_values = {k: v for k, v in result.items() if k != '_feat'}
total_chains = len(chain_values)
total_links = sum(len(v['环节']) for v in chain_values.values())
total_stocks = sum(len(s['股票']) for v in chain_values.values() for s in v['环节'].values())
total_unique_codes = len(set(c for v in chain_values.values() for s in v['环节'].values() for c in s['股票']))

print(f"✅ 导出完成!")
print(f"   产业链: {total_chains} 条")
print(f"   环节: {total_links} 个")
print(f"   股票关联: {total_stocks} 条")
print(f"   唯一股票: {total_unique_codes} 只")
print(f"   feat数据: {len(feat_data)} 只")
print(f"   大小: {os.path.getsize(OUT_PATH)/1024/1024:.1f} MB")

print(f"\n=== 产业链列表 ===")
for name, data in sorted(chain_values.items()):
    link_cnt = len(data['环节'])
    stock_cnt = sum(len(s['股票']) for s in data['环节'].values())
    has_deps = any(s['上游'] or s['下游'] for s in data['环节'].values())
    dep_flag = "↑↓" if has_deps else "-"
    print(f"  {dep_flag} {name:30s} {link_cnt}环节, {stock_cnt}股票")
