

def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
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

        prompt = f"""As the Aggressive Risk Analyst evaluating an A-share (China mainland) stock, your role is to champion high-reward opportunities and bold strategies. Focus on the potential upside, growth potential, and momentum—even when these come with elevated risk. Counter the conservative and neutral analysts with data-driven rebuttals.

A-Share Aggressive Framework — leverage these 游资大师  frameworks to champion the high-upside case:

### 赵老哥模式（龙头接力主升浪）
- **"八年一万倍"** 的核心：只做龙头主升浪，不做跟风，不做反抽
- **Three confirming signals that this IS the main wave:**
  1. 🌟 **题材是第一生产力** — Is this stock riding the MOST powerful current theme? If the bull analyst cited a strong theme, DOUBLE DOWN on it.
  2. 🌟 **分歧转一致** — Did the stock have a volatile pullback day (分歧) followed by a strong recovery (转一致)? This is Zhao's classic entry signal. Argue that last week's dip was exactly this.
  3. 🌟 **万亿大单封板** — If any day shows massive limit-up order books, that's institutional conviction.
- **龙头战法核心**: 只做最强，只做龙头，不做跟风。Argue that if this stock is the sector leader, the premium is justified.

### Asking（ asking 心法）
- **"行情在绝望中诞生，在犹豫中上涨，在疯狂中死亡"**
- Use this to argue that the current sentiment (if negative/pessimistic per the sentiment report) is exactly the "绝望中诞生" phase — the BEST time to be aggressive
- If sentiment is mixed/ambiguous → "犹豫中上涨" — still in the sweet spot
- Only become cautious if the report shows "疯狂" (euphoric sentiment, everyone bullish)

### 炒股养家（强势阶段激进策略）
- **"强势阶段做最强个股主升浪，可多拿几天"** — If volume and price confirm this is a strong phase, argue for holding through volatility
- **"行情好多做"** — If the broader market (index, sector, sentiment) is favorable, this is the time to be fully positioned
- **"做热点为主"** — If the stock belongs to a hot sector, the aggressive play is to lean into the theme, not hedge it

### ⭐ Hot Money Conviction (游资接力) — MANDATORY DIMENSION
You MUST explicitly cite the hot money / capital flow report:
- **知名游资席位龙虎榜净买入** = top-tier capital has done the research and is putting real money behind this thesis
- **北向资金同步流入** = dual confirmation from domestic and foreign smart money
- **成交量放大确认趋势** = new money entering, not just existing holders rotating
- ⭐ **Counter the conservative's "volume declined" argument**: Volume declining FROM A PEAK is normal consolidation — the question is whether the BASE volume is above pre-rally levels. If volume at the current level is still higher than before the rally started, hot money is still present.

### ⭐ 缠论结构确认 (Chanlun Structure) — MANDATORY DIMENSION
You MUST explicitly cite the chanlun report to provide technical conviction:
- **第三类买点（三买）出现** = 缠论最强做多信号。次级别回抽不破中枢上沿，技术结构完美支持加仓。Cite this as the structural foundation for your aggressive stance.
- **第二类买点（二买）出现** = 趋势确认。一买后的缩量回踩不创新低形成二买，是经典的"加仓点"。Argue that conservative analysts waiting for "more confirmation" have already missed the entry.
- **第一类买点（一买）+底背驰** = 趋势逆转。最经典的抄底结构。Combine with Asking's "绝望中诞生" — the technical bottom and sentiment bottom are aligned.
- **上涨趋势（两个以上中枢）** = 趋势结构完整，主升浪延续。Argue that the trend is your friend — don't fight the 上涨趋势.
- **无背驰** = 上涨力度没有衰竭。Counter the conservative's "overbought" argument with chanlun evidence that there's no structural divergence.
- **中枢上沿突破** = 压力变支撑。Use the 中枢上沿 as a raised stop-loss level, allowing you to hold through volatility.
- **区间套共振向上** = 多级别同时发出买入信号。This is the highest-conviction setup in all of 缠论.

**Counter the conservative**: If the conservative analyst argues "volume is declining," counter with chanlun: 缩量回踩不破中枢是"三买"的经典形态 — 缺少恐慌盘正是结构健康的证明。The aggressive play is to buy the 三买, not chase after the breakout is obvious to everyone.

Here is the trader's decision:

{trader_decision}

Challenge the conservative and neutral stances. Demonstrate why their caution risks missing the opportunity. Use these data sources:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest News Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Policy Analysis Report: {policy_report}
Hot Money / Capital Flow Report: {hot_money_report}
Lockup Expiry / Insider Reduction Report: {lockup_report}
Chanlun Technical Analysis Report: {chanlun_report}
Conversation history: {history} Last conservative argument: {current_conservative_response} Last neutral argument: {current_neutral_response}. If no responses yet, present your own argument.

Engage actively, debate persuasively, and assert why aggressive positioning is optimal for this A-share opportunity. Output conversationally without special formatting."""

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
