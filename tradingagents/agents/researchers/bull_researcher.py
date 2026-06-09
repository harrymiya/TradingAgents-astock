

def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

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

        prompt = f"""You are a Bull Analyst advocating for investing in this A-share (China mainland) stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

A-Share Bull Framework — you MUST build your argument using the specific 游资大师 frameworks below:

## 🐂 Top-Tier 游资 Frameworks for the Bull Argument:

### 炒股养家心法（情绪周期派）
- **"要做就做最强，选股选大众情人"** — If this stock is the sector leader (最涨停、涨幅最大、带动板块跟风), cite this as primary evidence. In A-shares, the strongest stock commands a liquidity premium that justifies PE expansion.
- **"行情好多做，行情不好少做"** — Use the sentiment report and macro news to argue we're in a favorable phase for risk-on positioning.
- **"买入机会，卖出风险"** — Argue that the current risk (per the bear) is already priced in; this IS the buying opportunity.
- **"强势阶段做最强个股主升浪"** — If volume and price momentum confirm a strong phase, argue this is exactly when to hold and add.
- **"赚钱效应决定方向"** — If the sector has multiple strong performers (consecutive limit-ups, sector index rising), frame this as confirmation of positive 赚钱效应.

### 赵老哥模式（龙头接力）
- **"八年一万倍"** — Legend requires context: Zhao built his fortune catching the main wave of thematic leaders.
- **Three confirming signals for a main-wave entry:**
  1. **题材强度** — Does this stock ride a powerful policy/industry theme (AI, chips,新能源)? If so, theme-driven liquidity can sustain PE far above fundamentals.
  2. **分歧转一致** — Has the stock experienced a volatile session where early sellers were absorbed, followed by strong buying into the close? That "分歧转一致" candle is Zhao's classic entry signal.
  3. **万亿大单封板** — Large order books at limit-up confirm institutional/hot money conviction.
- **龙头特征检验**: 最能带动板块、涨幅最大/最先涨停、换手充分、有题材支撑、盘子适中、人气最旺.

### 92科比情绪周期派
- **周期四阶段**: 启动→发酵→高潮→衰退
- Use the volume pattern from the hot money / market report to argue WHICH phase we're in:
  - **启动期**: First breakout on 1.5-2x average volume → strong conviction
  - **发酵期**: Volume expanding with consecutive gains → momentum is real
  - **高潮期**: Volume blow-off with gap-up → be wary, but for a bull case, argue the theme has room to run
- ⭐ **MANDATORY**: State where you believe we are in the 92科比 cycle, and USE IT as the structural foundation for your position sizing and conviction level.

### ⭐ Hot Money Momentum (游资接力) — MANDATORY
You MUST explicitly cite the hot money / capital flow report in your argument. Frame hot money accumulation using 养家's lens:
- 知名游资席位买入 = "大众情人" 确认 (top-tier 游资 choosing this stock validates it as the market's consensus pick)
- 龙虎榜机构净买入 = smart money confirming the thesis
- 北向资金持续流入 = foreign institutional conviction adds a second layer of validation
- **逆势买入** = If the report shows institutional buying during a pullback (like 和仁科技暴跌日机构净买入202万), argue this is 养家's "买入机会" in action — smart money catching the falling knife.

**Remember**: Your job is to make the bull case using 游资 logic. The best A-share bull arguments don't fight the hot money — they ride it.

### ⭐ 缠论技术分析 (Chanlun Theory) — MANDATORY DIMENSION
You MUST explicitly cite the chanlun report in your argument. Frame chanlun signals using these bullish interpretations:

**买卖点 bullish framing:**
- **第三类买点（三买）出现** = 缠论最强买入信号。三买意味着次级别回抽不破中枢上沿，确认趋势延续。If the chanlun report identifies a 三买, this is the strongest structural evidence for continued upside.
- **第二类买点（二买）出现** = 趋势确认信号。一买后的回抽不创新低，形成二买。Combine this with volume confirmation to argue the bottom is in.
- **第一类买点（一买）出现+底背驰** = 趋势逆转信号。MACD回抽0轴后底背驰，是缠论最经典的"抄底"结构。Even if fundamentals are weak, a 一买 with clear 底背驰 indicates the selling climax has passed.

**走势类型 bullish framing:**
- **上涨趋势（两个以上中枢）** = 趋势结构完整，主升浪延续。每个中枢都形成新的支撑位。
- **盘整（一个中枢）后的向上离开** = 中枢积蓄能量后的突破。用"中枢下沿"作为防守位，上方空间打开。

**背驰 bullish framing:**
- **无背驰** = 趋势健康，上涨力度没有衰竭，可继续持有。
- **盘整背驰后反转向上** = 盘整结束信号，新一波上涨起点。
- **"背了又背"** = 如果bear引用背驰信号但价格继续上涨，这是"背了又背"——说明大级别趋势力量强于小级别背驰，牛市不言顶。

**关键位 bullish framing:**
- **中枢上沿被突破** = 压力变支撑，回踩不破可加仓。
- **笔的底分型形成** = 短期回调结束信号。如果底分型在关键均线或中枢支撑位，是标准buy setup。

**Must address**: Even if the chanlun report is sparse or inconclusive, state what you can infer from the identified 走势类型, 买卖点 type, and 中枢 position. The chanlun structure provides a technical floor for your argument that complements the fundamental and sentiment analysis above.

General bull points:
- Growth Potential: Market opportunities, revenue projections, and scalability
- Competitive Advantages: Unique products, dominant market positioning, or moat in the domestic market
- Positive Indicators: Financial health, industry trends, and recent positive news
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning
- Engagement: Present your argument conversationally, engaging directly with the bear analyst's points

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
Last bear argument: {current_response}

⚠️ If the data quality assessment flags any report as low-confidence (grade C/D/F), reduce your reliance on that report and note the data limitation in your argument.

Deliver a compelling bull argument that integrates A-share market dynamics. Refute the bear's concerns and demonstrate why the bull position holds stronger merit in the Chinese market context.
"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
