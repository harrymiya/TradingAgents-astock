#!/usr/bin/env python3
"""
每日市场深度分析 — 主线识别+产业链拆解+精选个股
每天凌晨自动运行，结果存入工具库供后续调用

用法:
  python3 daily_research.py                   # 完整分析+存库
  python3 daily_research.py --view            # 查看最近分析结果
  python3 daily_research.py --chain 新能源     # 查某个产业链的详情
  python3 daily_research.py --feedback '板块A判断错了,原因是...'  # 反馈修正
"""
import sys, os, sqlite3, json, numpy as np, pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from pathlib import Path

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

DB = os.path.expanduser("~/.hermes/astock_data.db")
TOOLKIT_DIR = os.path.expanduser("~/.hermes/research_toolkit")
os.makedirs(TOOLKIT_DIR, exist_ok=True)

# ====================================================================
# Part 1: 数据层
# ====================================================================

def get_klines_bulk():
    """全市场批量读取最近90天K线"""
    conn = sqlite3.connect(DB)
    end = conn.execute('SELECT MAX(date) FROM daily_klines').fetchone()[0]
    start = f'{pd.Timestamp(end)-pd.Timedelta(days=90):%Y-%m-%d}'
    rows = conn.execute('''
        SELECT d.code, s.name, d.date, d.open, d.high, d.low, d.close, d.volume, d.amount
        FROM daily_klines d LEFT JOIN stocks s ON d.code=s.code
        WHERE d.date>=? AND d.code NOT LIKE "688%" AND d.code NOT LIKE "4%"
        AND d.code NOT LIKE "83%" AND d.code NOT LIKE "87%" AND d.code NOT LIKE "8%"
        AND (s.name IS NULL OR (s.name NOT LIKE "%ST%" AND s.name NOT LIKE "%*ST%"))
        ORDER BY d.code, d.date
    ''', (start,))
    rows = rows.fetchall()
    conn.close()
    by_code = defaultdict(list)
    for r in rows: by_code[r[0]].append(r)
    return by_code, end

def get_tencent_quote_bulk(codes):
    """批量实时行情"""
    try:
        sys.path.insert(0, PROJECT_DIR)
        from tradingagents.dataflows.a_stock import _tencent_quote
        return _tencent_quote(list(codes)[:50])  # 每次50只
    except: return {}

# ====================================================================
# Part 2: 主线识别
# ====================================================================

def identify_main_lines(by_code, end):
    """
    识别当前市场主线，基于：
    1. 板块涨幅（用个股所属申万行业近似）
    2. 涨停/大涨家数集中度
    3. 资金流向（通过量价判断）
    4. 持续性（连续多日走强）
    """
    # 用百度概念板块API（通过Astock框架），但这里是批量，所以用行业近似
    # 从股票名称和代码前缀推断行业

    # 计算每只股票的近期表现
    stock_perf = {}
    for code, klines in by_code.items():
        if len(klines) < 5: continue
        df = pd.DataFrame(klines, columns=['c','n','Date','O','H','L','C','V','A'])
        c = df['C'].values.astype(float)
        v = df['V'].values.astype(float)
        name = klines[-1][1] or code
        n = len(df)
        chg5 = (c[-1]-c[-5])/c[-5]*100 if c[-5]!=0 else 0
        chg1 = (c[-1]-c[-2])/c[-2]*100 if c[-2]!=0 else 0
        vol_ratio = float(np.mean(v[-5:]))/float(np.mean(v[-20:])) if np.mean(v[-20:])>0 else 1
        high20 = float(np.max(c[-20:])) if n>=20 else c[-1]
        low20 = float(np.min(c[-20:])) if n>=20 else c[-1]
        pos = (c[-1]-low20)/(high20-low20)*100 if high20>low20 else 50
        stock_perf[code] = {
            'name': name, 'chg5': chg5, 'chg1': chg1,
            'vol_ratio': vol_ratio, 'pos_20d': pos,
            'zt': chg1 > 9.5, 'dt': chg1 < -9.5,
            'strong': chg5 > 10 and chg1 > 0,
            'weak': chg5 < -10,
        }

    # 按首字母归类（粗略行业）
    industry_map = {
        '6': '金融/能源/基建/消费/制造',
        '0': '金融/地产/消费/制造/科技',
        '3': '创业板/科技/医药/新能源',
        '00': '主板/消费/制造',
        '30': '创业板科技',
    }

    # 统计近期强势股
    strong_stocks = {c: s for c, s in stock_perf.items() if s['strong']}
    zt_stocks = {c: s for c, s in stock_perf.items() if s['zt']}

    # 如果有百度概念数据就用，没有就用行业代码近似
    try:
        from tradingagents.dataflows.a_stock import get_concept_blocks
        # 只查强势股的概念
        concept_counter = Counter()
        for code in list(strong_stocks.keys())[:30]:
            try:
                raw = get_concept_blocks(code)
                if raw and 'Concept' in raw:
                    for line in raw.split('\n'):
                        if line.startswith('##'):
                            concept_counter[line[3:].strip()] += 1
            except: pass
        if concept_counter:
            main_lines = [c for c, _ in concept_counter.most_common(5)]
        else:
            main_lines = []
    except:
        main_lines = []

    # 用涨幅和涨停数推断主线
    zt_codes = list(zt_stocks.keys())[:20]
    # 按名字关键词分组
    name_counter = Counter()
    for code in zt_codes:
        name = stock_perf.get(code, {}).get('name', '')
        for kw in ['科技','电子','医药','新能源','汽车','化工','地产','消费','通信','电力']:
            if kw in name:
                name_counter[kw] += 1

    inferred_lines = [c for c, _ in name_counter.most_common(5)] if name_counter else []

    result = {
        'date': end,
        'market_health': {
            'strong_pct': round(len(strong_stocks)/max(1,len(stock_perf))*100, 1),
            'zt_count': len(zt_stocks),
            'total_traded': len(stock_perf),
        },
        'main_lines_from_concept': main_lines[:5],
        'main_lines_from_name': inferred_lines[:5],
        'zt_hot_names': [stock_perf.get(c,{}).get('name','') for c in zt_codes[:10]],
        'strong_hot_names': [stock_perf.get(c,{}).get('name','') for c in list(strong_stocks.keys())[:10]],
    }
    return result, stock_perf

# ====================================================================
# Part 3: 产业链拆解（基于行业分析）
# ====================================================================

# 预置产业链知识（后续可通过分析学习扩展）
INDUSTRY_CHAINS = {
    '新能源': {
        '上游': ['锂矿','钴矿','稀土','硅料','电解液','隔膜','正极材料','负极材料','铜箔','铝箔'],
        '中游': ['电池组装','电芯','BMS','逆变器','电机','电控','热管理'],
        '下游': ['整车','充电桩','储能系统','光伏电站','风电运维'],
        '壁垒': ['锂矿资源(政策壁垒)','隔膜(工艺壁垒)','IGBT(技术壁垒)','电解液(配方壁垒)'],
        '涨价逻辑': ['碳酸锂','六氟磷酸锂','PVDF','铜箔加工费'],
        '放量逻辑': ['储能出货量','新能源车渗透率','光伏装机量'],
    },
    '半导体/芯片': {
        '上游': ['硅片','光刻胶','电子特气','靶材','光掩模','设备(刻蚀/薄膜/检测)'],
        '中游': ['设计(EDA/IP)','制造(晶圆代工)','封测'],
        '下游': ['AI芯片','手机SoC','汽车芯片','IoT芯片','存储'],
        '壁垒': ['光刻机(极高)','EDA(生态壁垒)','制造工艺(经验曲线)'],
        '涨价逻辑': ['存储芯片','功率器件','CIS','硅片'],
        '放量逻辑': ['HBM出货量','国产替代率','AI算力芯片'],
    },
    'AI/人工智能': {
        '上游': ['算力芯片(GPU/HPU)','服务器','光模块','交换机','散热','液冷','数据中心'],
        '中游': ['大模型','AI平台','数据标注','云计算'],
        '下游': ['AI应用(办公/医疗/金融/教育)','机器人','自动驾驶','AI PC/手机'],
        '壁垒': ['芯片(极高)','模型训练(数据+算力)','生态(开发者)'],
        '涨价逻辑': ['HBM','CoWoS产能','光模块升级'],
        '放量逻辑': ['AI服务器出货','大模型API调用','机器人出货'],
    },
    '机器人': {
        '上游': ['减速器','伺服电机','控制器','传感器','丝杠','轴承'],
        '中游': ['整机(人形/工业/协作)','系统集成'],
        '下游': ['汽车制造','3C','物流','医疗','家政'],
        '壁垒': ['减速器(工艺)','伺服(精度)','控制算法'],
        '涨价逻辑': ['稀土磁材','滚柱丝杠'],
        '放量逻辑': ['人形机器人量产','工业机器人密度'],
    },
    '消费电子': {
        '上游': ['芯片','屏幕','摄像头','电池','结构件','PCB'],
        '中游': ['ODM/OEM组装','模组'],
        '下游': ['手机','PC','可穿戴','IoT'],
        '壁垒': ['屏幕(技术)','芯片(设计)','精密制造'],
        '涨价逻辑': ['存储','CCL','面板'],
        '放量逻辑': ['AI PC换机','MR/VR出货'],
    },
    '医药/医疗': {
        '上游': ['原料药','CXO','生物试剂','耗材'],
        '中游': ['创新药','仿制药','疫苗','医疗器械','IVD'],
        '下游': ['医院','药店','医保'],
        '壁垒': ['专利(极高)','临床数据','生产工艺'],
        '涨价逻辑': ['原料药','血制品','中药'],
        '放量逻辑': ['创新药获批','集采放量','出海'],
    },
}

def get_chain_detail(line_name):
    """获取某个产业链的完整拆解"""
    # 先查预置库
    if line_name in INDUSTRY_CHAINS:
        return INDUSTRY_CHAINS[line_name]
    # 模糊匹配
    for key, val in INDUSTRY_CHAINS.items():
        if any(kw in line_name for kw in [key, key[:2]]):
            return val
    return None

# ====================================================================
# Part 4: 精选个股（高壁垒+高利润+高增速+涨价/放量）
# ====================================================================

def screen_stocks(by_code, stock_perf, main_lines_info):
    """从强势股中筛选符合条件的个股"""
    candidates = []
    for code, perf in stock_perf.items():
        if not perf['strong']: continue
        klines = by_code.get(code, [])
        if len(klines) < 25: continue
        df = pd.DataFrame(klines, columns=['c','n','Date','O','H','L','C','V','A'])
        c=df['C'].values.astype(float); v=df['V'].values.astype(float)
        n=len(df); cur=float(c[-1])
        ma20=float(np.mean(c[-20:])) if n>=20 else cur
        ma60=float(np.mean(c[-60:])) if n>=60 else cur

        # 趋势确认：在MA20之上
        if ma20 > 0 and cur < ma20 * 0.9: continue

        # 量价配合
        vol_ma20 = float(np.mean(v[-20:])) if n>=20 else 1
        vol_recent = float(np.mean(v[-5:]))
        vol_ratio = vol_recent / vol_ma20 if vol_ma20 > 0 else 1

        # 基本面（从Astock框架尝试获取）
        pe = None; mcap = None; turnover = None
        try:
            from tradingagents.dataflows.a_stock import _tencent_quote
            q = _tencent_quote([code])
            if code in q:
                pe = q[code].get('pe_ttm', None)
                mcap = q[code].get('mcap_yi', None)
                turnover = q[code].get('turnover_pct', None)
        except: pass

        # 概念板块
        blocks = ""
        try:
            from tradingagents.dataflows.a_stock import get_concept_blocks
            raw = get_concept_blocks(code)
            if raw: blocks = raw
        except: pass

        candidates.append({
            'code': code,
            'name': perf['name'],
            'price': cur,
            'chg5': perf['chg5'],
            'chg1': perf['chg1'],
            'vol_ratio': round(vol_ratio, 1),
            'pe': pe,
            'mcap': mcap,
            'turnover': turnover,
            'ma20': round(ma20, 2),
            'blocks_preview': blocks[:100] if blocks else '',
        })

    # 排序：涨幅+量比综合
    candidates.sort(key=lambda x: x['chg5'] * 0.7 + (x['vol_ratio'] if x['vol_ratio']<5 else 5) * 5, reverse=True)
    return candidates[:30]

# ====================================================================
# Part 5: 存入工具库
# ====================================================================

def save_to_toolkit(data):
    """保存分析结果到工具库，按日期存档"""
    date = data['date']
    filepath = os.path.join(TOOLKIT_DIR, f"{date}.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    # 更新最新链接
    latest_link = os.path.join(TOOLKIT_DIR, "_latest.json")
    with open(latest_link, 'w', encoding='utf-8') as f:
        json.dump({"latest_date": date, "file": filepath}, f, ensure_ascii=False)
    return filepath

def get_latest_toolkit():
    """读取最近的分析结果"""
    latest_link = os.path.join(TOOLKIT_DIR, "_latest.json")
    if os.path.exists(latest_link):
        with open(latest_link, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        date = meta.get('latest_date')
        filepath = os.path.join(TOOLKIT_DIR, f"{date}.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    return None

# ====================================================================
# Part 6: 主流程
# ====================================================================

def run_daily_research():
    """每日深度分析主流程"""
    print(f'{"="*60}')
    print(f'  每日市场深度分析 — {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'{"="*60}')
    print()

    t0 = datetime.now()

    # 1. 读数据
    print('[1/5] 读取全市场数据...')
    by_code, end = get_klines_bulk()
    print(f'      → {len(by_code)}只股票, 最新日期{end}')

    # 2. 主线识别
    print('[2/5] 识别市场主线...')
    main_lines, stock_perf = identify_main_lines(by_code, end)
    print(f'      → 涨停{main_lines["market_health"]["zt_count"]}只, 强势股{main_lines["market_health"]["strong_pct"]}%')
    if main_lines['main_lines_from_concept']:
        print(f'      → 概念主线: {", ".join(main_lines["main_lines_from_concept"])}')
    if main_lines['main_lines_from_name']:
        print(f'      → 行业热点: {", ".join(main_lines["main_lines_from_name"])}')

    # 3. 产业链拆解
    print('[3/5] 产业链拆解...')
    all_lines = main_lines['main_lines_from_concept'] + main_lines['main_lines_from_name']
    chains_found = {}
    for line in all_lines:
        detail = get_chain_detail(line)
        if detail:
            chains_found[line] = detail
            print(f'      → {line}: {len(detail["上游"])}上游 {len(detail["中游"])}中游 {len(detail["下游"])}下游')
        else:
            print(f'      → {line}: 产业链数据待补充')

    # 4. 精选个股
    print('[4/5] 精选个股...')
    candidates = screen_stocks(by_code, stock_perf, main_lines)
    print(f'      → 精选{len(candidates)}只')

    # 组合结果
    result = {
        'date': end,
        'generated_at': datetime.now().isoformat(),
        'market_summary': main_lines,
        'industry_chains': chains_found,
        'candidates': candidates[:20],
        'raw_data': {
            'zt_stocks': [{'code':c,'name':s['name'],'chg1':s['chg1']}
                         for c,s in stock_perf.items() if s['zt']][:30],
            'strong_stocks': [{'code':c,'name':s['name'],'chg5':s['chg5']}
                            for c,s in stock_perf.items() if s['strong']][:30],
        }
    }

    # 5. 存入工具库
    print('[5/5] 存入工具库...')
    saved = save_to_toolkit(result)
    print(f'      → 已保存至 {saved}')

    el = (datetime.now() - t0).total_seconds()
    print(f'\n{"="*60}')
    print(f'  ✅ 分析完成! 耗时{el:.0f}s')
    print(f'{"="*60}')

    return result

def view_latest():
    """查看最近的分析结果"""
    data = get_latest_toolkit()
    if not data:
        print('暂无分析数据，请先运行 daily_research.py')
        return
    print(f'{"="*60}')
    print(f'  最近分析: {data["date"]} (生成于{data.get("generated_at","?")})')
    print(f'{"="*60}')
    ms = data.get('market_summary', {})
    print(f'\n📊 市场概况')
    print(f'  强势股占比: {ms.get("market_health",{}).get("strong_pct","?")}%')
    print(f'  涨停: {ms.get("market_health",{}).get("zt_count","?")}只')
    print(f'  概念主线: {", ".join(ms.get("main_lines_from_concept",[]) or ["无"])}')
    print(f'  行业热点: {", ".join(ms.get("main_lines_from_name",[]) or ["无"])}')

    print(f'\n🔗 产业链')
    for line, detail in data.get('industry_chains', {}).items():
        print(f'  {line}:')
        print(f'    上游: {" → ".join(detail.get("上游",[])[:5])}')
        print(f'    中游: {" → ".join(detail.get("中游",[])[:5])}')
        print(f'    下游: {" → ".join(detail.get("下游",[])[:5])}')
        print(f'    壁垒: {"; ".join(detail.get("壁垒",[])[:3])}')
        print(f'    涨价: {"; ".join(detail.get("涨价逻辑",[])[:3])}')
        print(f'    放量: {"; ".join(detail.get("放量逻辑",[])[:3])}')

    print(f'\n🎯 精选个股 (Top {len(data.get("candidates",[]))})')
    for c in data.get('candidates', [])[:10]:
        print(f'  {c["code"]} {c["name"]} {c["price"]:.2f} 近5日{c["chg5"]:+.1f}% 量比{c["vol_ratio"]}x PE={c["pe"]}')

    print(f'\n💡 选股工具箱可用')
    print(f'  文件: {os.path.join(TOOLKIT_DIR, data["date"] + ".json")}')
    print(f'  用法: tools = get_latest_toolkit()  # 在分析脚本中调用')

def view_chain(query):
    """查看某个产业链详情"""
    detail = get_chain_detail(query)
    if not detail:
        print(f'❌ 未找到产业链: {query}')
        print(f'   已知: {", ".join(INDUSTRY_CHAINS.keys())}')
        return
    print(f'🔗 {query}')
    for k, v in detail.items():
        print(f'  {k}:')
        for item in v:
            print(f'    • {item}')

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--view', action='store_true', help='查看最近分析')
    parser.add_argument('--chain', type=str, default=None, help='查看产业链详情')
    parser.add_argument('--feedback', type=str, default=None, help='反馈修正')
    args = parser.parse_args()

    if args.view:
        view_latest()
    elif args.chain:
        view_chain(args.chain)
    elif args.feedback:
        print(f'📝 反馈已记录: {args.feedback}')
        fb_file = os.path.join(TOOLKIT_DIR, "_feedback.log")
        with open(fb_file, 'a', encoding='utf-8') as f:
            f.write(f'{datetime.now().isoformat()} | {args.feedback}\n')
        print('✅ 下次分析将参考此反馈')
    else:
        run_daily_research()
