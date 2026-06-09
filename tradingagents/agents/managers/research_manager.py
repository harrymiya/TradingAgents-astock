"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]
        hot_money_report = state.get("hot_money_report", "")
        chanlun_report = state.get("chanlun_report", "")

        hot_money_section = (
            f"\n---\n**Hot Money / Capital Flow Report (游资与资金流向报告):**\n{hot_money_report}\n\n"
            "⚠️ You MUST incorporate this hot money / capital flow data into your rating decision. "
            "Consider: Are hot money seats accumulating or exiting? Is volume confirming or diverging from price? "
            "Are top-tier 游资 seats (like 中关村/西藏东方/赵老哥 etc.) participating? "
            "Has volume peaked and started declining significantly (游资撤退 signal)?\n---\n"
            if hot_money_report else ""
        )
        chanlun_section = (
            f"\n---\n**Chanlun Technical Analysis Report (缠论技术分析报告):**\n{chanlun_report}\n\n"
            "⚠️ You MUST incorporate this chanlun data into your rating decision. "
            "Consider: What 买卖点 type is present (一买/二买/三买/一卖/二卖/三卖)? "
            "What is the current 走势类型 (上涨趋势/下跌趋势/盘整)? "
            "Is there 背驰 (底背驰 bullish, 顶背驰 bearish, or none)? "
            "Where are the key 中枢 levels (ZG/ZD) that define support and resistance? "
            "The chanlun structure provides the technical foundation that either confirms or contradicts the fundamental and sentiment arguments above.\n---\n"
            if chanlun_report else ""
        )

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

{instrument_context}

Note: This is an A-share (China mainland) stock. Factor in regulatory policy impact, hot money / capital flow dynamics, and lockup expiry / insider reduction risks when synthesising the debate.

{hot_money_section}
{chanlun_section}

---

## 📐 游资大师评判框架 — you MUST use this to evaluate the debate:

### 炒股养家心法（情绪周期评判）
- **"赚钱效应/恐慌效应决定大势"** — Which force is dominant right now? 赚钱效应 (bulls winning) or 恐慌效应 (bears winning)?
- **"不同阶段不同手法"** — Judge whether the debate arguments match the current market phase:
  - 强势阶段: Bull's argument for taking positions has more weight
  - 弱势阶段: Bear's "avoid/exit" argument has more weight
  - 平衡格局: Neutral/position-sizing arguments have more weight
- **"买入机会，卖出风险"** — Is the current price an opportunity (bull) or a risk (bear)? Your rating should reflect which side better matches the data.
- **"试错单感受市场情绪"** — If data is ambiguous, recommend small position sizes for testing (this aligns with Underweight/Hold, not all-in Buy or Sell)

### 92科比情绪周期定位
- **MANDATORY**: State where in the 92科比 cycle this stock is: 启动→发酵→高潮→衰退
- A Buy/Overweight rating requires the cycle to be in 启动 or early 发酵
- A Sell/Underweight rating is appropriate for 高潮晚期 or 衰退
- Hold is appropriate for ambiguous cycle positioning

### 涅槃重升原则
- **"控制回撤比追求盈利更重要"** — If both bull and bear arguments have merit, the conservative choice (Underweight/Hold with tight stops) aligns with 涅槃's philosophy
- **"稳定复利是唯一的道路"** — Avoid extreme ratings (Buy/Sell) unless the evidence is overwhelming

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

Commit to a clear stance whenever the debate's strongest arguments warrant one; reserve Hold for situations where the evidence on both sides is genuinely balanced.

---

**Debate History:**
{history}""" + get_language_instruction()

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
