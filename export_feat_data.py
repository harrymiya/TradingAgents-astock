"""
补全 feat_data.json 中缺失的股票 feat 数据
从 SQLite feat 表中查询缺失股票的最新一条记录（按 date DESC），补充到 json 中

字段计算逻辑（与 export_industry_data.py 一致）：
- pos_20d, ma20_pct, vr_5, amp: 从 feat 表直接读取
- rsi/rsi_label: 基于 pos_20d 判断
- s3_score/s3_label: 基于 pos_20d 和 ma20_pct 判断
- composite: 综合评分
"""
import json
import sqlite3

DB_PATH = '/home/harrydolly/.hermes/astock_data.db'
FEAT_PATH = '/home/harrydolly/code/TradingAgents-astock/industry-map/src/data/feat_data.json'
IND_PATH = '/home/harrydolly/code/TradingAgents-astock/industry-map/src/data/industry_data.json'


def compute_feat_from_row(row):
    """根据 feat 表一行数据计算 feat_data 所需的所有字段"""
    pos = row[0] or 50
    ma20_pct = row[1] or 0
    vr5 = row[2] or 0
    amp = row[4] or 0

    # 超买超卖指标 (基于 pos_20d)
    if pos < 20:
        rsi_signal = -2
        rsi_label = '超卖'
    elif pos < 35:
        rsi_signal = -1
        rsi_label = '偏卖'
    elif pos > 80:
        rsi_signal = 2
        rsi_label = '超买'
    elif pos > 65:
        rsi_signal = 1
        rsi_label = '偏买'
    else:
        rsi_signal = 0
        rsi_label = '中性'

    # S3 综合评分
    s3_score = 50
    s3_label = '正常'
    if pos < 20 and -15 < ma20_pct < -5:
        s3_score = 85
        s3_label = 'S3超跌反弹'
    elif pos < 30 and ma20_pct < -5:
        s3_score = 70
        s3_label = '接近超跌'
    elif pos > 80:
        s3_score = 20
        s3_label = '高位风险'

    # 综合评分
    composite = 50
    if rsi_signal == -2:
        composite += 20
    elif rsi_signal == -1:
        composite += 10
    elif rsi_signal == 2:
        composite -= 15
    elif rsi_signal == 1:
        composite -= 5
    if ma20_pct < -10:
        composite += 10
    elif ma20_pct > 10:
        composite -= 10
    composite = max(0, min(100, composite))

    return {
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


def main():
    # 1. Load feat_data.json
    with open(FEAT_PATH) as f:
        feat_data = json.load(f)
    feat_codes = set(feat_data.keys())
    print(f"feat_data 已有股票: {len(feat_codes)} 只")

    # 2. Extract all stock codes from industry_data.json (handle both numeric codes and Chinese names)
    with open(IND_PATH) as f:
        ind_data = json.load(f)

    all_ind_stock_strings = set()
    for industry, info in ind_data.items():
        if '环节' in info:
            for segment, seg_info in info['环节'].items():
                if '股票' in seg_info:
                    for s in seg_info['股票']:
                        all_ind_stock_strings.add(s)

    # Connect to DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Build name->code mapping from stocks table (only numeric codes)
    cur.execute('SELECT * FROM stocks')
    name_to_code = {}
    for r in cur.fetchall():
        code, name = r[0], r[1]
        if code.isdigit() and len(code) == 6:
            name_to_code[name] = code

    # Resolve all stock identifiers to codes
    all_ind_codes = set()
    for s in all_ind_stock_strings:
        if s.isdigit() and len(s) == 6:
            all_ind_codes.add(s)
        elif s in name_to_code:
            all_ind_codes.add(name_to_code[s])
        else:
            print(f"  WARNING: 无法解析 '{s}' -> 跳过")

    print(f"industry_data 涉及股票总数: {len(all_ind_codes)} 只")

    # 3. Find missing codes
    missing_codes = sorted(all_ind_codes - feat_codes)
    print(f"缺失股票: {len(missing_codes)} 只")

    if not missing_codes:
        print("✅ 没有缺失的股票，无需补充。")
        conn.close()
        return

    for c in missing_codes:
        name = next((n for n, cd in name_to_code.items() if cd == c), '')
        print(f"  {c} ({name})")

    # 4. Query feat table for each missing code
    added = 0
    no_data = []

    for code in missing_codes:
        row = cur.execute('''
            SELECT pos_20d, ma20_pct, vr_5, ret3, amp
            FROM feat WHERE code=? ORDER BY date DESC LIMIT 1
        ''', (code,)).fetchone()

        if row:
            feat_entry = compute_feat_from_row(row)
            feat_data[code] = feat_entry
            added += 1
            name = next((n for n, cd in name_to_code.items() if cd == code), '')
            print(f"  ✅ {code} ({name}): 已补充 feat 数据")
        else:
            no_data.append(code)
            name = next((n for n, cd in name_to_code.items() if cd == code), '')
            print(f"  ⚠️ {code} ({name}): DB 中无任何数据，跳过")

    # 5. Save updated feat_data.json
    with open(FEAT_PATH, 'w', encoding='utf-8') as f:
        json.dump(feat_data, f, ensure_ascii=False, indent=2)

    conn.close()

    print(f"\n{'='*50}")
    print(f"结果汇总:")
    print(f"  - 已有: {len(feat_codes)} -> {len(feat_data)} 只")
    print(f"  - 成功补充: {added} 只")
    print(f"  - 无数据跳过: {len(no_data)} 只")
    if no_data:
        print(f"  无数据的代码:")
        for c in no_data:
            name = next((n for n, cd in name_to_code.items() if cd == c), '')
            print(f"    {c} ({name})")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
