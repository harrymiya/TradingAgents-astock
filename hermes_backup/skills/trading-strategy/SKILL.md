---
name: trading-strategy
description: ⚠️ 已废弃 — 被 rebound-strategy 取代。本技能中的5种策略（底分型企稳/急跌反弹/放量突破/缩量回调/首板接力）胜率仅45-55%，用户明确拒绝使用。详见 rebound-strategy。
version: 1.0.0-deprecated
tags:
  - deprecated
  - 超驰反弹已取代
related_skills:
  - rebound-strategy
---

# ⚠️ 已废弃

**此技能中的5种策略已被拒绝**。用户明确要求高胜率（>70%），而这些策略持最高仅64%。

**请使用: `rebound-strategy` 技能**: 胜率88-90%，均收益+8-10%，夏普>9。

## 历史保存（仅用于参考）

旧策略的回测数据保存在 `references/backtest-results.md` 中。

核心教训：
- 传统技术指标（底分型、MACD金叉）的预测力有限
- **超跌反弹**（距20日线-15%~-25% + 温和放量）才是真正的高胜率信号
- 这个结论是通过系统性的网格搜索（26,928个参数组合 × 200只股票 × 3年数据）得出的，不是拍脑袋
