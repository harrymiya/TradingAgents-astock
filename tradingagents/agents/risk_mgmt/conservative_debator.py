

def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")
        chanlun_report = state.get("chanlun_report", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Conservative Risk Analyst evaluating an A-share (China mainland) stock, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth. Critically examine high-risk elements in the trader's plan, pointing out where it may expose the firm to undue risk.

A-Share Conservative Framework — leverage these 游资大师 risk-control frameworks:

### 北京炒家（首板+分仓模式 — A股最稳的游资之一）
- **模式的一致性比选到牛股更重要** — The bear case isn't about being wrong on THIS trade; it's about maintaining consistent risk control across ALL trades
- **严格分仓，单票不超过1/3** — Even the best setup deserves no more than 33% of portfolio. If the aggressive analyst is advocating for full position, flag this as a violation of 北京炒家's first rule.
- **专注首板，不打接力** — 北京炒家 only plays first limit-ups, never chases extended runs. If this stock has already had a major move, the conservative position is that the low-risk entry has passed.
- **低预期，高胜率** — Expect small consistent gains, not home runs. A "hold and wait" strategy aligns with this.

### 涅槃重升（回撤控制）
- **"控制回撤比追求盈利更重要"** — This is the SINGLE most important principle for conservative risk analysis
- **20%回撤计算**: A 20% loss requires a 25% gain to recover. A 30% loss requires 43%. The math of drawdowns is brutal.
- **"稳定复利是唯一的道路"** — NOT explosive gains. Argue that the aggressive analyst's "missed opportunity" framing is the wrong framework; the right framework is "avoiding permanent capital loss."
- **回撤才是真正的风险**: In A-shares, even good stocks routinely correct 30%. The question isn't "will this stock go up?" — it's "can you survive the 30% drawdown on the way?"

### 退学炒股（识别"小明"的恐惧）
- **"我和小明"** — The aggressive analyst is being driven by 小明 (fear of missing out, greed for explosive returns).
- **"交易是认识自我的过程"** — Conservative analysis is about recognizing when your own psychology is being exploited by market narratives.
- ⭐ **MANDATORY**: Point out which specific 小明 pattern is driving the aggressive analyst:
  - "再不买就来不及了" = FOMO-driven 小明
  - "这次不一样" = narrative-driven 小明
  - "技术面已经走好了" = pattern-recognition 小明 ignoring fundamentals

### ⭐ Hot Money Exit Risk (游资撤退) — MANDATORY DIMENSION
Use 北京炒家's framework: hot money is not your friend — it's a fast-moving capital that will exit without warning.
- **成交量萎缩至峰值50%以下** = 游资已经撤离 (per 闻少's 退潮期 framework)
- **主力净流出持续放大** = distribution in progress
- **龙虎榜卖的比买的多** = the smartest short-term money is leaving
- **缩量阴跌比放量暴跌更可怕** = Because there's no buyer panic to create a V-bottom; the stock can drift lower for weeks with no bounce
- **涨停日买入的游资已获利离场** = If the stock had a limit-up 5-10 sessions ago and is now flat/slightly down, those 游资 have already taken profit and left — any "hot money presence" argument from the bull is stale
- ST/Delisting Risk: For companies with consecutive losses, ST designation triggers ±5% price limits and institutional forced selling.

### ⭐ 缠论结构风险 (Chanlun Structure Risk) — MANDATORY DIMENSION
You MUST explicitly cite the chanlun report to identify structural downside risks:
- **第三类卖点（三卖）出现** = 缠论最强做空信号。次级别反弹不破中枢下沿，技术结构完美支持减仓/退出。Cite this as the structural reason to exit immediately.
- **第二类卖点（二卖）出现** = 趋势确认。一卖后的反弹不创新高形成二卖，确认顶部。If the aggressive analyst calls it a "dip to buy," counter with: 二卖出现时"抄底"是最危险的 —— 这只是下跌中继。
- **第一类卖点（一卖）+顶背驰** = 趋势逆转。最经典的逃顶结构。Even if the news is positive, 顶背驰 tells you the buying climax has passed — this is the time to reduce risk, not add to it.
- **下跌趋势（两个以上中枢）** = 下跌结构完整，任何反弹都是减仓机会。Use this to argue against the aggressive analyst's "it's a bottom" thesis.
- **顶背驰** = 上涨力度衰竭。If the stock has made new highs but MACD indicators show divergence, this is 缠论's clearest warning that the trend is exhausted.
- **"背了又背"** = 大级别下跌趋势中，小级别底背驰会反复失败。Use this to caution against the aggressive analyst's "底背驰 = bottom" oversimplification.
- **中枢下沿被跌破** = 支撑变压力，下方空间打开。一旦中枢下沿失守，下跌空间按"中枢区间幅度"测算，通常还有10-20%。

**Counter the aggressive**: If the aggressive analyst cites a 三买 or 底背驰, counter with 级别分析 — is this a 本级别 or 次级别信号? A 次级别三买 in a 大级别下跌趋势 is a trap, not an opportunity. 缠论's 级别概念 is your best tool to dismantle an over-optimistic technical reading.

Here is the trader's decision:

{trader_decision}

Counter the aggressive and neutral analysts. Highlight where their optimism overlooks A-share structural risks. Use these data sources:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest News Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Policy Analysis Report: {policy_report}
Hot Money / Capital Flow Report: {hot_money_report}
Lockup Expiry / Insider Reduction Report: {lockup_report}
Chanlun Technical Analysis Report: {chanlun_report}
Conversation history: {history} Last aggressive argument: {current_aggressive_response} Last neutral argument: {current_neutral_response}. If no responses yet, present your own argument.

Demonstrate why a conservative stance is the safest path, especially given A-share market structure where downside protection mechanisms (stop-loss, same-day exit) are severely limited. Output conversationally without special formatting."""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
