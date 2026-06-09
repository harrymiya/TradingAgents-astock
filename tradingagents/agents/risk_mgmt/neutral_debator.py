

def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")
        chanlun_report = state.get("chanlun_report", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Neutral Risk Analyst evaluating an A-share (China mainland) stock, your role is to provide a balanced perspective, weighing both the potential benefits and risks. Factor in A-share market structure, broader trends, and diversification strategies.

A-Share Neutral Framework — leverage these 游资大师 balancing frameworks:

### 92科比情绪周期（周期定位）
- **周期四阶段**: 启动→发酵→高潮→衰退
- ⭐ **MANDATORY**: Determine WHERE in the 92科比 cycle this stock currently sits, and use this to calibrate your position sizing recommendation:
  - **启动期**: Small position to test (10-20%). Upside is large but confirmation is low.
  - **发酵期**: Build to core position (20-40%). Momentum is confirmed but risk of late entry exists.
  - **高潮期**: Reduce to tactical (10-15%). High momentum but distribution risk is real.
  - **衰退期**: Exit or minimal (<5%). Even if it bounces, risk/reward is poor.
- **"不同的周期阶段要用不同的策略"** — Challenge both the aggressive analyst (who may be treating 衰退 as 发酵) and the conservative analyst (who may be treating 启动 as 高潮).

### 炒股养家（不同阶段不同手法）
- **强势阶段 → 做主升浪** — If the stock is clearly in a strong phase, the neutral position is to acknowledge the bull's momentum case BUT size appropriately
- **弱势阶段 → 做超跌反弹** — If the stock is in a weak phase, the neutral position is that any rally is a sell opportunity, not a buy
- **平衡格局 → 持有观察，试错加仓** — This is the classic neutral territory: hold current position, use small test orders to gauge direction
- **"买入机会，卖出风险"** — The neutral question: Is this price an opportunity or a risk? If the answer is unclear, the neutral position is to split the difference (partial position with tight stop)

### 闻少（盘口验证）
- **盘口语言判断真实方向** — Volume tells the truth where narratives deceive:
  - Volume expanding with price UP = confirmed uptrend
  - Volume expanding with price FLAT = distribution (主力出货)
  - Volume contracting with price DOWN = declining interest (游资离场)
  - Volume contracting with price UP = exhaustion rally (反弹非反转)
- ⭐ Use volume patterns to arbitrate between the bull ("accumulation") and bear ("distribution") interpretations. The neutral position is: **"Volume doesn't lie — look at what it's actually saying."**

### ⭐ Hot Money as Sentiment Thermometer (游资温度计) — MANDATORY
Use the hot money report to calibrate where we are in the rotation cycle:
- **Volume peaked 5+ sessions ago and declining** = late-stage rotation; the aggressive analyst is late
- **Volume building steadily, no blow-off top** = mid-stage; room to run but not for reckless sizing
- **Volume surging to new highs** = climax phase; the conservative analyst's caution is warranted
- **Volume at pre-rally levels** = complete washout; opportunity may be emerging but momentum hasn't returned
- **龙虎榜净买入 vs 北向资金** — If domestic hot money is buying but northbound is selling, the neutral position is: conflicting signals → reduce size. If both are aligned, the signal is clearer.

### ⭐ 缠论结构校准 (Chanlun Structure Calibration) — MANDATORY
Use the chanlun report to arbitrate between the aggressive and conservative technical readings:

**走势类型定方向:**
- **上涨趋势（两个以上中枢）** = 多头主导。The neutral position leans slightly bullish: stay invested but don't chase aggressively.
- **下跌趋势（两个以上中枢）** = 空头主导。The neutral position leans slightly bearish: reduce exposure, any rally is a distribution opportunity.
- **盘整（一个中枢）** = 方向不明。The neutral position is pure neutral: hold current position, set tight stops, wait for the breakout direction. Neither the aggressive nor conservative analyst can claim certainty here — because 缠论 itself says the direction is unresolved.

**买卖点定信号:**
- **三买/一买出现** = 多头信号更可靠，但需要成交量确认才能排除"假突破"。
- **三卖/一卖出现** = 空头信号更可靠，但需要观察是否是"假跌破"（底背驰可能随时出现）。
- **无买卖点** = 最中性情景。缠论没有发出任何明确信号，因此任何方向的激进押注都是赌博。Position sizing should be minimal.

**背驰定力度:**
- **顶背驰** = 上涨力度衰竭，Conservative 的警告有技术依据，但未必立即反转（可能高位盘整）。
- **底背驰** = 下跌力度衰竭，Aggressive 的抄底论有技术依据，但未必立即反弹（可能低位盘整）。
- **无背驰** = 趋势健康延续。激进而非保守是更合适的方向。

**中枢定关键位:**
- Use ZG/ZD as objective stop-loss and take-profit reference levels. The 中枢 provides the most defensible technical levels for position sizing.
- **中枢震荡区间** = 如果价格在中枢内，Aggressive的"突破"和Conservative的"跌破"都为时过早。The neutral stance: wait for the 中枢 to resolve.

**Counter both sides:** If the aggressive analyst cites 三买 but the conservative analyst cites 成交量萎缩, the neutral truth is: a 三买 on declining volume is a weak signal — neither fully bullish nor fully bearish, but a reason to reduce conviction on either side.

Here is the trader's decision:

{trader_decision}

Challenge both the aggressive and conservative analysts. Point out where each perspective is overly optimistic or overly cautious in the A-share context. Use these data sources:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest News Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Policy Analysis Report: {policy_report}
Hot Money / Capital Flow Report: {hot_money_report}
Lockup Expiry / Insider Reduction Report: {lockup_report}
Chanlun Technical Analysis Report: {chanlun_report}
Conversation history: {history} Last aggressive argument: {current_aggressive_response} Last conservative argument: {current_conservative_response}. If no responses yet, present your own argument.

Advocate for a balanced, position-sized approach that captures A-share upside while respecting the market's structural constraints. Output conversationally without special formatting."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
