#!/usr/bin/env python3
"""
quick_eval.py — 快速对Top候选跑TradingAgents框架深度分析
用法: python3 quick_eval.py <code1> <code2> ...
"""
import sys, os, json, time, subprocess

# Hermes把环境变量DEEPSEEK_API_KEY截断了，先删掉让框架从.env读
os.environ.pop('DEEPSEEK_API_KEY', None)
print("Removed truncated key from env, framework will read .env instead")

# 现在导入框架
PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

codes = sys.argv[1:] if len(sys.argv) > 1 else ["000988", "600460", "601012"]
target_date = "2026-06-09"

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# 获取名称
import sqlite3
conn = sqlite3.connect(os.path.expanduser("~/.hermes/astock_data.db"))
name_map = {}
for code in codes:
    row = conn.execute("SELECT name FROM stocks WHERE code=?", (code,)).fetchone()
    name_map[code] = row[0] if row else code
conn.close()

config = DEFAULT_CONFIG.copy()
config["max_debate_rounds"] = 2   # 缩短辩论轮数以节省时间
config["max_risk_discuss_rounds"] = 2
config["output_language"] = "Chinese"
config["checkpoint_enabled"] = False

selected_analysts = ["market", "news", "fundamentals", "hot_money"]

results = []
for code in codes:
    name = name_map.get(code, code)
    print(f"\n{'='*60}")
    print(f"  分析: {code} {name}")
    print(f"{'='*60}")
    
    try:
        graph = TradingAgentsGraph(
            selected_analysts=selected_analysts,
            config=config,
            debug=False,
        )
        t0 = time.time()
        final_state = graph.propagate(code, target_date)
        
        # propagate可能返回tuple (state, updates)
        if isinstance(final_state, tuple):
            final_state = final_state[0]
        
        elapsed = time.time() - t0
        
        if not final_state:
            print(f"  ⚠️ 返回空")
            results.append({'code': code, 'name': name, 'status': 'empty'})
            continue
        
        report = {
            'code': code, 'name': name,
            'market_report': final_state.get('market_report', '')[:2000],
            'news_report': final_state.get('news_report', '')[:2000],
            'fundamentals_report': final_state.get('fundamentals_report', '')[:2000],
            'hot_money_report': final_state.get('hot_money_report', '')[:2000],
        }
        
        debate = final_state.get('investment_debate_state', {})
        if debate:
            report['bull_history'] = debate.get('bull_history', '')[:2000]
            report['bear_history'] = debate.get('bear_history', '')[:2000]
            report['judge_decision'] = debate.get('judge_decision', '')[:2000]
        
        risk = final_state.get('risk_debate_state', {})
        if risk:
            report['risk_conservative'] = risk.get('conservative_history', '')[:1500]
            report['risk_aggressive'] = risk.get('aggressive_history', '')[:1500]
            report['risk_neutral'] = risk.get('neutral_history', '')[:1500]
            report['risk_judge'] = risk.get('judge_decision', '')[:2000]
        
        if final_state.get('trader_investment_plan'):
            report['trader_plan'] = final_state['trader_investment_plan'][:2000]
        
        results.append(report)
        print(f"  ✅ 完成 ({elapsed:.0f}s)")
        
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        results.append({'code': code, 'name': name, 'status': 'error', 'error': str(e)})

# 输出报告
print(f"\n\n{'='*70}")
print(f"  📊 待选标的多维评估报告")
print(f"{'='*70}")

for i, r in enumerate(results):
    if r.get('status') in ('empty', 'error'):
        continue
    
    print(f"\n{'─'*70}")
    print(f"  #{i+1} {r['code']} {r['name']}")
    print(f"{'─'*70}")
    
    # 分析师摘要
    for label, content in [
        ('📈 市场分析师', 'market_report'),
        ('📰 新闻分析师', 'news_report'),
        ('📊 基本面分析师', 'fundamentals_report'),
        ('💰 游资追踪', 'hot_money_report'),
    ]:
        if r.get(content):
            text = r[content][:300].replace('\n', ' ')
            print(f"  {label}: {text}...")
    
    # Bull/Bear
    print(f"\n  ⚔️  Bull/Bear辩论:")
    if r.get('bull_history'):
        lines = r['bull_history'].strip().split('\n')
        print(f"    🟢 BULL: {lines[0][:200]}")
    if r.get('bear_history'):
        lines = r['bear_history'].strip().split('\n')
        print(f"    🔴 BEAR: {lines[0][:200]}")
    if r.get('judge_decision'):
        print(f"    ⚖️  裁判: {r['judge_decision'][:400]}")
    
    # 风险辩论
    print(f"\n  🛡️  风险评估:")
    if r.get('risk_conservative'):
        text = r['risk_conservative'][:200].replace('\n', ' ')
        print(f"    🟦 保守: {text}")
    if r.get('risk_aggressive'):
        text = r['risk_aggressive'][:200].replace('\n', ' ')
        print(f"    🟥 激进: {text}")
    if r.get('risk_neutral'):
        text = r['risk_neutral'][:200].replace('\n', ' ')
        print(f"    ⬜ 中立: {text}")
    if r.get('risk_judge'):
        print(f"    🎯 风控: {r['risk_judge'][:400]}")
    
    # 交易计划
    if r.get('trader_plan'):
        print(f"\n  💼 交易计划: {r['trader_plan'][:400]}")

print(f"\n{'='*70}")
print(f"  🏆 综合排名")
print(f"{'='*70}")
for i, r in enumerate(results):
    if r.get('judge_decision'):
        judge_preview = r['judge_decision'][:50].replace('\n', ' ')
        print(f"  #{i+1} {r['code']} {r['name']} — {judge_preview}")

# 保存
output_path = os.path.expanduser(f"~/.hermes/pipeline_output/{target_date}_quick_report.json")
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print(f"\n📝 报告已保存: {output_path}")
