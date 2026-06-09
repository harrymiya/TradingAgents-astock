

def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")
        chanlun_report = state.get("chanlun_report", "")
        data_quality_summary = state.get("data_quality_summary", "")

        prompt = f"""You are a Bear Analyst making the case against investing in this A-share (China mainland) stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators unique to the Chinese market. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

A-Share Bear Framework — you MUST build your argument using the specific 游资大师 frameworks below:

## 🐻 Top-Tier 游资 Frameworks for the Bear Argument:

### 闻少体系（情绪周期+盘口语言）
- **周期是超短的本质** — The market cycles through: 冰点→启动→主升→高潮→分歧→退潮→冰点
- **退潮期识别信号** (use these to build your bear case):
  - 连板断裂: Highest board count shrinking (5连板→3连板→1连板)
  - 炸板率上升: More limit-up stocks getting smashed open during the session
  - 亏钱效应扩散: Yesterday's limit-up stocks opening lower today (昨日涨停今日低开无溢价)
- ⭐ **"分歧转一致失败"** — If the stock had a high-volume volatile day that ended below VWAP or with a long upper shadow, this is a "分歧转一致失败" — the exact opposite of the bull's ideal setup. This is a strong bear signal.
- **盘口语言**: If volume is declining after a peak and the stock can't make new highs, the 盘口 is telling you smart money is distributing, not accumulating.

### 退学炒股（心性修炼 — 识别"小明"的陷阱）
- **"我和小明"** — In every bubble there's a "小明" (the inner voice of greed/fear). Identify the 小明 in the bull's argument:
  - "这次不一样" (this time is different) — classic 小明 thinking
  - "再不买就来不及了" (fear of missing out) —小明's favorite trap
  - "基本面已经改善了" (fundamentals have turned) —小明 ignoring valuation
- ⭐ **MANDATORY**: Point out which specific 小明 thought pattern the Bull Analyst is falling into.

### 涅槃重升（控制回撤）
- **"控制回撤比追求盈利更重要"** — Frame the bear case around what happens to a portfolio that enters at current levels:
  - If the stock drops 20% (a standard A-share correction), a 20% loss requires a 25% gain just to break even
  - **"稳定复利是唯一的道路"** — Avoiding this drawdown IS the winning strategy
- **回撤才是真正的风险** — In A-shares, a -30% drawdown from a thematic high is normal; even great stocks routinely correct 30-50%. The current entry point must account for this.

### ⭐ Hot Money Withdrawal (游资撤退) — MANDATORY DIMENSION
You MUST explicitly cite the hot money / capital flow report. Use 闻少's 退潮期 framework to interpret the data:
- **成交量萎缩至峰值50%以下** = 游资已经撤离 (hot money has already left)
- **主力净流出持续放大** = 主力出货阶段 (institutional distribution in progress)
- **北向资金趋势性卖出** = smart money reducing exposure
- **成交量从峰值持续萎缩5+日** = 边际买家枯竭 (marginal buyer exhaustion — this is NOT consolidation, it's the absence of new demand)
- **昨日涨停今日无溢价** = 情绪退潮确认 (sentiment has peaked and reversed)
- **连板高度逐步降低** = 周期进入退潮期 (the cycle is in decline phase per 闻少)

Even when data is sparse, analyze volume divergence patterns — 放量滞涨 (expanding volume but price stalling) is one of 闻少's clearest "distribution in progress" signals.

### ⭐ 缠论技术分析 (Chanlun Theory) — MANDATORY DIMENSION
You MUST explicitly cite the chanlun report in your argument. Frame chanlun signals using these bearish interpretations:

**买卖点 bearish framing:**
- **第三类卖点（三卖）出现** = 缠论最强卖出信号。三卖意味着次级别反弹不破中枢下沿，确认下跌趋势延续。If the chanlun report identifies a 三卖, this is the strongest structural evidence for continued downside.
- **第二类卖点（二卖）出现** = 趋势确认信号。一卖后的反弹不创新高，形成二卖。This confirms the top is in and trend has reversed.
- **第一类卖点（一卖）出现+顶背驰** = 趋势逆转信号。MACD回抽0轴后顶背驰，是缠论最经典的"逃顶"结构。Even if bullish narratives persist, a 一卖 with clear 顶背驰 indicates the buying climax is over.

**走势类型 bearish framing:**
- **下跌趋势（两个以上中枢）** = 下跌结构完整，主跌浪延续。每个中枢都形成新的压力位，反弹都受阻于中枢下沿。
- **盘整后的向下离开** = 中枢积蓄能量后的向下突破。用"中枢上沿"作为止损参考，下方空间打开。

**背驰 bearish framing:**
- **无背驰** = 下跌力度没有衰竭，Bear方观点更强。不要因为跌多了就抄底——缠论告诉你力度还在。
- **盘整背驰后反转向下** = 盘整结束信号，新一波下跌起点。
- **"背了又背"** = 如果bull引用底背驰信号但价格继续下跌，这是"背了又背"——说明大级别下跌趋势强于小级别背驰，熊市不言底。这点在A股小盘股尤其常见。

**关键位 bearish framing:**
- **中枢下沿被跌破** = 支撑变压力，反弹不破可加空/减仓。
- **笔的顶分型形成** = 短期反弹结束信号。如果顶分型在关键均线或中枢压力位，是标准sell setup。

**区间套 bearish framing:**
- If multiple timeframes (日线+30F+5F) all show the same sell-side structure, this is 区间套共振 — the most reliable structural signal in 缠论. A multi-timeframe aligned sell signal trumps any single-timeframe buy signal.

**Must address**: Even if the chanlun report is sparse, state what you can infer. The absence of buy-point signals in the chanlun report is itself bearish — if there's no 一买/二买/三买, the technical structure does not support a long entry.

General bear points:
- Risks and Challenges: Market saturation, financial instability, or macroeconomic threats
- Competitive Weaknesses: Weaker market positioning, declining innovation, or competitor threats
- Negative Indicators: Evidence from financial data, market trends, or adverse news
- Bull Counterpoints: Expose over-optimistic assumptions with specific data
- Engagement: Present your argument conversationally, directly engaging with the bull analyst's points

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest news report: {news_report}
Company fundamentals report: {fundamentals_report}
Policy analysis report: {policy_report}
Hot money / capital flow report: {hot_money_report}
Lockup expiry / insider reduction report: {lockup_report}
Chanlun technical analysis report: {chanlun_report}
Data quality assessment: {data_quality_summary}
Conversation history of the debate: {history}
Last bull argument: {current_response}

⚠️ If the data quality assessment flags any report as low-confidence (grade C/D/F), reduce your reliance on that report and note the data limitation in your argument.

Deliver a compelling bear argument grounded in A-share market realities. Refute the bull's claims and demonstrate the risks of investing in this stock within the Chinese regulatory and market structure.
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
