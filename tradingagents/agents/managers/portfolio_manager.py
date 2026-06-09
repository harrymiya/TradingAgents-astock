"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )
        hot_money_report = state.get("hot_money_report", "")
        chanlun_report = state.get("chanlun_report", "")

        hot_money_section = (
            f"\n**Hot Money / Capital Flow Context:**\n{hot_money_report}\n\n"
            "⚠️ When weighing the risk analysts' debate, factor in whether hot money is "
            "accumulating or exiting — this is a leading indicator for short-term price direction in A-shares.\n"
            if hot_money_report else ""
        )
        chanlun_section = (
            f"\n**Chanlun Technical Structure Context (缠论技术结构):**\n{chanlun_report}\n\n"
            "⚠️ When making the final decision, factor in the chanlun structure: "
            "买卖点 type (一买/二买/三买 = supports entry; 一卖/二卖/三卖 = supports exit), "
            "走势类型 (上涨趋势=hold; 下跌趋势=exit; 盘整=neutral), "
            "and 中枢 levels (key support/resistance for stop-loss and take-profit placement).\n"
            if chanlun_report else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

## 📐 游资仓位管理原则 — factor these into your final sizing decision:

### 炒股养家仓位体系
- **"行情好就多做，行情不好就少做"** — Your final rating should reflect the current market quality. If the sentiment/market report suggests a favorable environment, Overweight/Buy is more justified. If weak, Underweight/Sell.
- **"试错单感受市场情绪"** — If the evidence is mixed, prescribe test positions (small size) rather than binary all-in/all-out.
- **Buy = 奋力一击 (go all-in when conviction is highest)** — Only use Buy when both the bull debate AND the risk analysts acknowledge manageable risk.
- **Sell = 风险已至 (risk has materialized)** — Only use Sell when the bear case is overwhelming AND risk analysts agree.
- **Hold/Underweight/Overweight = 试错+观察 (test and observe)** — These are the default ratings for ambiguous situations.

### 北京炒家分仓原则
- **单票不超过1/3** — Even for Buy/Overweight ratings, specify a max position size. No rating should imply "go all-in."
- **"模式的一致性比选到牛股更重要"** — Your final decision should be consistent with the framework, not a one-off exception.

### 涅槃重升回撤原则
- **"控制回撤比追求盈利更重要"** — The final Stop Loss level must be explicit and tight enough to limit any position to a max 15-20% portfolio drawdown.
- **"稳定复利是唯一的道路"** — If the risk debate is genuinely split, default to the more conservative sizing.

---

**A-Stock Trading Constraints** (must factor into your decision):
- T+1 settlement: shares bought today cannot be sold until the next trading day
- Daily price limits: main board ±10%, STAR/ChiNext ±20%, ST stocks ±5%
- Minimum lot size: 100 shares (1 手) for main board; 200 shares for STAR/ChiNext
- Trading hours: 09:30-11:30, 13:00-15:00 (Beijing time)
- ST/delisting risk: ST or *ST status signals regulatory warning; factor into position sizing
- Margin eligibility: not all A-shares are margin-eligible; assume cash-only unless stated

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
{hot_money_section}
{chanlun_section}
**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node
