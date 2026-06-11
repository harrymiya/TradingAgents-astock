#!/usr/bin/env python3
"""
研究星球双圈方法论在黄金坑选股上的增量，对比当前golden_pit实现
输出：《体系化升级方案》
"""
import json

print("=" * 70)
print(" 星球双圈方法论 → 黄金坑升级需求分析")
print("=" * 70)
print()

# === 当前黄金坑缺陷 ===
current = {
    "基础筛选": "pos20<10 + ma20<-8% + vr5<1.0 + 非688+非ST",
    "产业链维度": "15个QUALITY_CHAINS列表，手动维护",
    "评分维度": "产业链质量分 + ma20偏离分 + 缩量分 + 底部分 + 实时表现",
    "补充逻辑": "市值>=30亿过滤",
    "排序": "6维评分降序 Top15",
    "推送": "每天14:30固定推送",
}

print("【当前实现】")
for k, v in current.items():
    print(f"  {k}: {v}")
print()

# === 星球增量 ===
zsxq = {
    # 谢SS - 合同负债暴增选股法
    "contract_liability": "① 合同负债环比>30%或创历史新高\n  ② 结合扣非净利润扭亏/暴增二次过滤\n  ③ 落入优质产业链优先",
    # 谢SS - 黄金坑技术面升级
    "tech": "① **60日均线不破** — 当前只用ma20，没有ma60判断\n  ② **布林钱袋变盘** — 布林收窄后的变盘信号\n  ③ **缩量见底** — 量比<0.7（当前vr5<1.0太宽）\n  ④ **机构资金流入** — GPJYVALUE(9,2,0)>GPJYVALUE(8,2,0)\n  ⑤ **位置决定性质** — 跌透了的黄金坑才有价值",
    # macro - 产业链景气度
    "industry_depth": "① 台股/海外营收映射找A股对应\n  ② 产业链景气周期（如PCB 63%CAGR、硅片3.8x用量）\n  ③ 机构研报深度覆盖\n  ④ CPO/PCB/硅片/设备/散热5大TMT赛道",
    # 操作纪律
    "discipline": "① \"利润来自持有，不是频繁交易\" — 要求持仓策略匹配\n  ② \"AI是主线，死也要死在AI上\" — 赛道聚焦\n  ③ \"预判中跟随，跟随中应变\"",
}

print("【星球方法论增量 — 当前缺失的维度】")
print()

print("-" * 70)
print("📌 缺口1：60日均线判断")
print("-" * 70)
print("  当前: ma20_pct < -8%（30日均线偏离）")
print("  星球: 60日均线不破才是真黄金坑")
print("  升级: 需要 query feat 表的 ma60_pct")
print("  条件: ma60_pct > -10%（60日均线不破）")
print()

print("-" * 70)
print("📌 缺口2：缩量标准太松")
print("-" * 70)
print("  当前: vr5 < 1.0（量比<1.0, 即缩量）")
print("  星球: 量比<0.7 才是缩量见底")
print("  升级: vr_5 < 0.7（收紧条件）")
print()

print("-" * 70)
print("📌 缺口3：布林带技术信号")
print("-" * 70)
print("  当前: 无")
print("  星球: 布林钱袋变盘")
print("  升级: 布林带收窄(宽度<15%)+股价触及下轨")
print("  计算: (upper_band - lower_band) / middle_band < 0.15")
print("  且: 收盘价 <= 下轨 * 1.02")
print("  数据源: 需要从腾讯API或feat表获取布林带")
print()

print("-" * 70)
print("📌 缺口4：机构资金流向")
print("-" * 70)
print("  当前: 无")
print("  星球: 机构线>游资线")
print("  升级: 需要东财push2资金流API")
print("  指标: 机构净流入 > 游资净流入 且 累计3日为正")
print()

print("-" * 70)
print("📌 缺口5：合同负债基本面过滤")
print("-" * 70)
print("  当前: 纯技术面")
print("  星球: 合同负债暴增+扣非净利润暴增")
print("  升级: 读取财报数据（mootdx/新浪API）")
print("  条件: 最新季报合同负债环比>30% 或 扣非净利润>50%增长")
print()

print("-" * 70)
print("📌 缺口6：产业链景气度权重")
print("-" * 70)
print("  当前: 简单分类（5分/4分/3分）")
print("  星球: 宏观景气周期+台股营收映射+外资研报")
print("  升级: 产业链权重动态化（TMT 1.2x、消费电子0.8x）")
print()

print("-" * 70)
print("📌 缺口7：操作纪律匹配")
print("-" * 70)
print("  当前: 每日推送完事")
print("  星球: '利润来自持有'要求持仓周期匹配")
print("  升级: 黄金坑信号分级（试仓→加仓→持有→出局）")
print()

print("=" * 70)
print(" 升级建议：分3阶段实施")
print("=" * 70)
print()
print("【Phase 1 — 快速升级（今天可做）】")
print("  ① ma60条件加入筛选（已有数据，加where条件）")
print("  ② vr5从<1.0收紧到<0.7")
print("  ③ 产业链权重动态化")
print()
print("【Phase 2 — 需要数据源扩展（1-2天）】")
print("  ④ 布林带信号（腾讯API可拿+标准差计算）")
print("  ⑤ 机构资金流向（东财push2已有接口）")
print("  ⑥ 合同负债数据（mootdx F10或新浪财报）")
print()
print("【Phase 3 — 体系化升级】")
print("  ⑦ 信号分级体系（黄金坑1级/2级/3级）")
print("  ⑧ 持仓周期建议（1-3个月目标）")
print("  ⑨ 大盘环境联动（弱势只做最强产业链）")
print()
