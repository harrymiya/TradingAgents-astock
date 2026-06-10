#!/usr/bin/env python3
"""
批量提取PDF目录中跟A股产业链强相关的文本内容。
排除：消费/营销/电商/白皮书(非产业)/宏观报告等
"""
import fitz  # PyMuPDF
import os, re, sys, json, time

HOME = os.path.expanduser('~')
BASE_DIR = os.path.join(HOME, '文档/产业链')
OUT_DIR = os.path.join(HOME, 'industry_pdf_extracted')

# 相关关键词：PDF文件名包含这些才提取（A股产业链相关）
CORE_KEYWORDS = [
    '产业链', '上下游', 'AI', '算力', '半导体', '芯片', '机器人', '人形',
    '新能源', '光伏', '风电', '储能', '电池', '智能驾驶', '自动驾驶',
    '低空经济', '商业航天', '卫星', '稀土', '3D打印', '数控机床',
    '覆铜板', 'CCL', '光通信', 'PCB', 'AI眼镜', '数据要素',
    '数字经济', '网络安全', '物联网', '云计算', '消费电子',
    '医疗器械', '创新药', '医药', '中药', '化工', '煤炭',
    '电力', '特高压', '军工', '航空航天', '发动机',
    '汽车', '乘用车', '汽车零部件', '银发经济', '脑机接口',
    'PET', 'PVC', 'Mini LED', '具身智能', 'CPO',
    '词元经济', '新质生产力', 'IDC', 'Agent', 'OpenClaw',
    '黄金产业', '煤炭产业链', '能源', '光伏生产设备',
    '光储充', '机械设备', '机器人产业链', '显示屏',
    '新型显示', '虚拟现实', 'VR', '医疗机器人',
    '体外诊断', '网络安全', '食品饮料',
    '中药行业', '石油化工', '环保产业链',
    '有色金属', '钢铁', '建材', '5G',
    'EDA', '高端装备', '数控', '激光',
    '边缘计算', '大数据', '区块链',
    '工业机器人', '空天装备', '服务器',
    '储能类', '光通信', '汽车轻量化',
    '消费电子', '智能物联', '智能视觉',
]

# 排除关键词
EXCLUDE_KEYWORDS = [
    '电商', '直播', '营销', '小红书', '抖音', '快手', '飞瓜',
    '白皮书(?!产业链)', '风味图谱', '服饰', '美妆', '燕麦',
    '银行理财', '人群白皮书', '年货', '春节消费',
    '人力实践', '校园', '财务数智化', '可转债',
    '品牌出海', '人群', '社交KOL',
]

def should_extract(filename):
    """判断是否值得提取"""
    lower = filename.lower()
    for exc in EXCLUDE_KEYWORDS:
        if exc.lower().replace('(?!产业链)', '') in lower:
            # 如果排除词包含'产业链'且文件也包含产业链，不排除
            if '产业链' not in exc:
                return False
    for kw in CORE_KEYWORDS:
        if kw.lower() in lower:
            return True
    return False


def extract_pdf_text(pdf_path):
    """提取PDF文本内容"""
    try:
        doc = fitz.open(pdf_path)
        text_parts = []
        for i, page in enumerate(doc):
            txt = page.get_text()
            if txt.strip():
                text_parts.append(f"=== 第{i+1}页 ===\n{txt}")
            # 只提取前30页（大部分产业链报告核心内容在前30页）
            if i >= 29:
                break
        doc.close()
        return '\n'.join(text_parts)
    except Exception as e:
        return f"[ERROR] {pdf_path}: {e}"


def extract_chain_info(text, filename):
    """
    从文本中提取产业链结构信息：
    - 产业链名称
    - 上中下游公司名称
    - 公司之间的关系
    """
    # 先标记这是哪个文件来的
    info = {
        'source_file': filename,
        'chains': [],
        'companies': [],
        'relationships': []
    }
    
    lines = text.split('\n')
    
    # 寻找产业链相关段落
    current_section = None
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        # 检测产业链标题
        if re.search(r'[上中下]游', line) or '产业链' in line:
            info['chains'].append({
                'text': line,
                'context': lines[max(0,i-2):i+5]
            })
        
        # 检测公司名（上市公司）
        # 匹配"XX公司"、"XX股份"、"XX科技"、"XX集团"、"XX电子"等
        company_matches = re.findall(r'[\u4e00-\u9fff]{2,8}(?:公司|股份|科技|集团|电子|医药|能源|智能|光电|通信|材料|装备|制造|汽车|电力|化工|生物|医疗|信息|软件|创新)', line)
        # 过滤太短的匹配
        company_matches = [c for c in company_matches if len(c) >= 3]
        for c in company_matches:
            info['companies'].append({
                'name': c,
                'context': line
            })
    
    return info


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    
    # 收集所有PDF
    all_pdfs = []
    for month in ['01', '02', '03', '04', '05', '06']:
        month_dir = os.path.join(BASE_DIR, f'2026年{month}月更新全景图产业链行业分析')
        if os.path.isdir(month_dir):
            for f in sorted(os.listdir(month_dir)):
                if f.endswith('.pdf'):
                    full = os.path.join(month_dir, f)
                    all_pdfs.append((month, f, full))
    
    print(f"总计 {len(all_pdfs)} 个PDF文件")
    
    # 筛选核心PDF
    core_pdfs = [(m, f, p) for m, f, p in all_pdfs if should_extract(f)]
    print(f"核心产业链相关PDF: {len(core_pdfs)} 个")
    for m, f, p in core_pdfs:
        print(f"  20{m}: {f}")
    
    # 提取文本
    results = []
    for month, fname, fpath in core_pdfs:
        print(f"\n提取: {fname} ...")
        text = extract_pdf_text(fpath)
        out_txt = os.path.join(OUT_DIR, fname.replace('.pdf', '.txt'))
        with open(out_txt, 'w', encoding='utf-8') as f:
            f.write(text)
        chars = len(text)
        info = extract_chain_info(text, fname)
        results.append(info)
        print(f"  {chars} 字符, {len(info['chains'])} 个产业链提及, {len(info['companies'])} 个公司")
    
    # 保存结构化信息
    with open(os.path.join(OUT_DIR, '_chain_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 完成! 提取了 {len(core_pdfs)} 个PDF")
    print(f"文本保存在: {OUT_DIR}")
    print(f"结构摘要: {OUT_DIR}/_chain_summary.json")

if __name__ == '__main__':
    main()
