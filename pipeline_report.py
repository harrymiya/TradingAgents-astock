#!/usr/bin/env python3
"""
pipeline_report.py — 流水线完成后，调用 TradingAgents 框架对Top候选做完整多维评估报告

用法:
  python3 pipeline_report.py                          # 最新日期Top 3
  python3 pipeline_report.py --date 2026-06-09        # 指定日期
  python3 pipeline_report.py --candidates 000988,600460,601012  # 指定候选
"""

import sys, os, json, time
from datetime import datetime

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)
OUTPUT_DIR = os.path.expanduser("~/.hermes/pipeline_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DB = os.path.expanduser("~/.hermes/astock_data.db")

def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    print(f"  [{t}] {msg}")

def get_latest_date():
    import sqlite3
    conn = sqlite3.connect(DB)
    d = conn.execute("SELECT MAX(date) FROM feat").fetchone()[0]
    conn.close()
    return d

def load_candidates(target_date=None, manual_codes=None):
    """加载流水线结果或手动指定"""
    import sqlite3
    conn = sqlite3.connect(DB)
    
    if manual_codes:
        # 手动指定代码，从feat获取基本信息
        rows = conn.execute("""
            SELECT f.code, s.name, f.close, f.chg
            FROM feat f JOIN stocks s ON f.code = s.code
            WHERE f.date = ? AND f.code IN ({})
        """.format(','.join('?' for _ in manual_codes)),
            [target_date] + list(manual_codes)
        ).fetchall()
        conn.close()
        candidates = []
        for code, name, close, chg in rows:
            candidates.append({
                'code': code, 'name': name,
                'price': close, 'chg': chg,
                'strategy': '手动', 'detail': '',
                'scores': {}, 'total_score': 50
            })
        return candidates
    
    # 从流水线输出加载
    final_path = os.path.join(OUTPUT_DIR, f"{target_date}_final.json")
    stage2_path = os.path.join(OUTPUT_DIR, f"{target_date}_stage2.json")
    
    # 优先用final（含框架评分），再用stage2（无评分）
    if os.path.exists(final_path):
        with open(final_path) as f:
            return json.load(f)
    elif os.path.exists(stage2_path):
        with open(stage2_path) as f:
            return json.load(f)[:3]
    
    log("⚠️ 未找到流水线输出，从feat表加载默认候选")
    conn = sqlite3.connect(DB)
    rows = conn.execute("""
        SELECT code, name, close, chg FROM feat 
        WHERE date = ? AND code NOT LIKE '688%'
        ORDER BY chg DESC LIMIT 3
    """, (target_date,)).fetchall()
    conn.close()
    return [{'code': r[0], 'name': r[1], 'price': r[2], 'chg': r[3],
             'strategy': '默认', 'detail': '', 'scores': {}, 'total_score': 50}
            for r in rows]

def run_framework_analysis(code, name, target_date):
    """对单只股票运行TradingAgents全量分析"""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    
    log(f">>> 分析 {code} {name}...")
    
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = 3
    config["max_risk_discuss_rounds"] = 3
    config["output_language"] = "Chinese"
    config["checkpoint_enabled"] = False
    
    # 从/etc/profile重新读取API Key（Hermes环境传递截断了）
    import subprocess
    result = subprocess.run(['bash', '-c', 'source /etc/profile >/dev/null 2>&1; echo $DEEPSEEK_API_KEY'],
                          capture_output=True, text=True)
    real_key = result.stdout.strip()
    if real_key and len(real_key) > 20:
        os.environ['DEEPSEEK_API_KEY'] = real_key
        log(f"  API Key restored: {len(real_key)} chars")
    
    selected_analysts = ["market", "social", "news", "fundamentals", 
                         "policy", "hot_money", "lockup", "chanlun"]
    
    try:
        graph = TradingAgentsGraph(
            selected_analysts=selected_analysts,
            config=config,
            debug=False,
        )
        
        final_state = graph.propagate(code, target_date)
        
        if not final_state:
            log(f"⚠️ {code} 分析返回空，跳过")
            return None
        
        # 提取关键信息
        result = {
            'code': code,
            'name': name,
            'analyst_reports': {},
            'bull_history': '',
            'bear_history': '',
            'judge_decision': '',
            'risk_aggressive': '',
            'risk_conservative': '',
            'risk_neutral': '',
            'risk_judge': '',
            'trader_plan': '',
        }
        
        if final_state.get('market_report'):
            result['analyst_reports']['市场分析师'] = final_state['market_report'][:1500]
        if final_state.get('sentiment_report'):
            result['analyst_reports']['情绪分析师'] = final_state['sentiment_report'][:1500]
        if final_state.get('news_report'):
            result['analyst_reports']['新闻分析师'] = final_state['news_report'][:1500]
        if final_state.get('fundamentals_report'):
            result['analyst_reports']['基本面分析师'] = final_state['fundamentals_report'][:1500]
        if final_state.get('policy_report'):
            result['analyst_reports']['政策分析师'] = final_state['policy_report'][:1500]
        if final_state.get('hot_money_report'):
            result['analyst_reports']['游资追踪'] = final_state['hot_money_report'][:1500]
        if final_state.get('lockup_report'):
            result['analyst_reports']['解禁监控'] = final_state['lockup_report'][:1500]
        
        # Bull/Bear辩论
        debate = final_state.get('investment_debate_state', {})
        if debate:
            result['bull_history'] = debate.get('bull_history', '')[:2000]
            result['bear_history'] = debate.get('bear_history', '')[:2000]
            result['judge_decision'] = debate.get('judge_decision', '')[:2000]
        
        # 三方风险辩论
        risk = final_state.get('risk_debate_state', {})
        if risk:
            result['risk_aggressive'] = risk.get('aggressive_history', '')[:1000]
            result['risk_conservative'] = risk.get('conservative_history', '')[:1000]
            result['risk_neutral'] = risk.get('neutral_history', '')[:1000]
            result['risk_judge'] = risk.get('judge_decision', '')[:1500]
        
        # 交易计划
        if final_state.get('trader_investment_plan'):
            result['trader_plan'] = final_state['trader_investment_plan'][:1500]
        
        log(f"✅ {code} {name} 分析完成")
        return result
    
    except Exception as e:
        log(f"❌ {code} {name} 分析失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def generate_report(candidates, results, target_date):
    """生成综合评估报告"""
    print(f"\n{'='*70}")
    print(f"  📊 待选标的多维评估报告")
    print(f"  日期: {target_date}  |  候选: {len(results)}只")
    print(f"{'='*70}")
    
    for i, (cand, res) in enumerate(zip(candidates, results)):
        if not res:
            continue
        
        print(f"\n{'─'*70}")
        print(f"  #{i+1} {cand['code']} {cand['name']}")
        print(f"  策略: {cand.get('strategy','?')}  |  评分: {cand.get('total_score',50)}")
        print(f"  价格: {cand.get('price',0):.2f}  |  涨跌: {cand.get('chg','?'):+}")
        print(f"{'─'*70}")
        
        # 分析师报告摘要
        print(f"\n  🔬 分析师团队报告摘要:")
        for analyst_name, report in res.get('analyst_reports', {}).items():
            if report:
                preview = report[:200].replace('\n', ' ')
                print(f"    [{analyst_name}] {preview}...")
        
        # Bull/Bear辩论
        print(f"\n  ⚔️  Bull/Bear 辩论:")
        if res.get('bull_history'):
            lines = res['bull_history'].strip().split('\n')
            print(f"    🟢 BULL: {lines[0][:150] if lines else '—'}")
        if res.get('bear_history'):
            lines = res['bear_history'].strip().split('\n')
            print(f"    🔴 BEAR: {lines[0][:150] if lines else '—'}")
        if res.get('judge_decision'):
            print(f"    ⚖️  裁判结论: {res['judge_decision'][:300]}")
        
        # 风险辩论
        print(f"\n  🛡️  三方风险评估:")
        if res.get('risk_conservative'):
            lines = res['risk_conservative'].strip().split('\n')
            print(f"    🟦 保守派: {lines[0][:150] if len(lines) > 0 else '—'}")
        if res.get('risk_aggressive'):
            lines = res['risk_aggressive'].strip().split('\n')
            print(f"    🟥 激进派: {lines[0][:150] if len(lines) > 0 else '—'}")
        if res.get('risk_neutral'):
            lines = res['risk_neutral'].strip().split('\n')
            print(f"    ⬜ 中立派: {lines[0][:150] if len(lines) > 0 else '—'}")
        if res.get('risk_judge'):
            print(f"    🎯 风控裁判: {res['risk_judge'][:300]}")
        
        # 交易计划
        print(f"\n  💼 交易计划:")
        if res.get('trader_plan'):
            print(f"    {res['trader_plan'][:300]}")
    
    # TOP 综合排名
    print(f"\n{'='*70}")
    print(f"  🏆 综合排名")
    print(f"{'='*70}")
    print(f"  {'排名':>4} {'代码':>8} {'名称':<10} {'6维评分':>8} {'裁判结论摘要':<40}")
    print(f"  {'─'*70}")
    for i, (cand, res) in enumerate(zip(candidates, results)):
        if not res:
            continue
        judge = (res.get('judge_decision', '') or '')[:35]
        print(f"  {f'#{i+1}':>4} {cand['code']:>8} {cand['name']:<10} {cand.get('total_score',0):>8}  {judge}")
    
    print()
    
    # 保存报告
    report_path = os.path.join(OUTPUT_DIR, f"{target_date}_multi_agent_report.json")
    report_data = {
        'date': target_date,
        'timestamp': datetime.now().isoformat(),
        'candidates': candidates,
        'results': results,
    }
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
    log(f"报告已保存: {report_path}")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="多维评估报告生成")
    parser.add_argument('--date', type=str, default=None)
    parser.add_argument('--candidates', type=str, default=None)
    args = parser.parse_args()
    
    target_date = args.date or get_latest_date()
    
    # 加载候选
    manual_codes = None
    if args.candidates:
        manual_codes = [c.strip() for c in args.candidates.split(',')]
    
    candidates = load_candidates(target_date, manual_codes)
    
    if not candidates:
        print("❌ 无候选股，终止")
        sys.exit(1)
    
    print(f"\n{'='*70}")
    print(f"  🏭 待选标的多维评估报告生成器")
    print(f"  日期: {target_date}  |  候选: {len(candidates)}只")
    print(f"{'='*70}")
    for i, c in enumerate(candidates):
        print(f"  {i+1}. {c['code']} {c['name']} [{c.get('strategy','?')}] {c.get('price',0):.2f}")
    
    print(f"\n  🔄 开始调用TradingAgents框架逐个分析...")
    
    results = []
    for i, c in enumerate(candidates):
        print(f"\n  [{i+1}/{len(candidates)}]")
        t0 = time.time()
        res = run_framework_analysis(c['code'], c['name'], target_date)
        elapsed = time.time() - t0
        print(f"  ⏱ 耗时: {elapsed:.0f}s")
        results.append(res)
    
    # 生成报告
    generate_report(candidates, results, target_date)
    
    print(f"\n✅ 多维评估报告完成!")
