# TradingAgents/graph/setup.py

from typing import Any, Dict, List
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic

    def setup_graph(
        self,
        selected_analysts: List[str] = None,
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts: List of analyst types to include. Options are:
                - "market": Market analyst (technical analysis)
                - "social": Social media / sentiment analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
                - "policy": Policy analyst (A-stock specific)
                - "hot_money": Hot money / capital flow tracker (A-stock specific)
                - "lockup": Lockup expiry / reduction watcher (A-stock specific)
                - "chanlun": Chanlun technical analyst (缠论 A-stock specific, NEW)
        """
        if selected_analysts is None:
            selected_analysts = [
                "market", "social", "news", "fundamentals",
                "policy", "hot_money", "lockup",
            ]

        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # -----------------------------------------------------------------------
        # Build analyst/tool/delete nodes from the selected list
        # -----------------------------------------------------------------------
        analyst_nodes: Dict[str, Any] = {}
        delete_nodes: Dict[str, Any] = {}
        tool_node_map: Dict[str, ToolNode] = {}

        for atype in selected_analysts:
            if atype == "market":
                analyst_nodes["market"] = create_market_analyst(self.quick_thinking_llm)
                delete_nodes["market"] = create_msg_delete()
                tool_node_map["market"] = self.tool_nodes["market"]

            elif atype == "social":
                analyst_nodes["social"] = create_social_media_analyst(self.quick_thinking_llm)
                delete_nodes["social"] = create_msg_delete()
                tool_node_map["social"] = self.tool_nodes["social"]

            elif atype == "news":
                analyst_nodes["news"] = create_news_analyst(self.quick_thinking_llm)
                delete_nodes["news"] = create_msg_delete()
                tool_node_map["news"] = self.tool_nodes["news"]

            elif atype == "fundamentals":
                analyst_nodes["fundamentals"] = create_fundamentals_analyst(self.quick_thinking_llm)
                delete_nodes["fundamentals"] = create_msg_delete()
                tool_node_map["fundamentals"] = self.tool_nodes["fundamentals"]

            elif atype == "policy":
                analyst_nodes["policy"] = create_policy_analyst(self.quick_thinking_llm)
                delete_nodes["policy"] = create_msg_delete()
                tool_node_map["policy"] = self.tool_nodes["policy"]

            elif atype == "hot_money":
                analyst_nodes["hot_money"] = create_hot_money_tracker(self.quick_thinking_llm)
                delete_nodes["hot_money"] = create_msg_delete()
                tool_node_map["hot_money"] = self.tool_nodes["hot_money"]

            elif atype == "lockup":
                analyst_nodes["lockup"] = create_lockup_watcher(self.quick_thinking_llm)
                delete_nodes["lockup"] = create_msg_delete()
                tool_node_map["lockup"] = self.tool_nodes["lockup"]

            elif atype == "chanlun":
                # NEW: 缠论技术分析师
                from tradingagents.agents.analysts.chanlun_analyst import create_chanlun_analyst
                from tradingagents.agents.utils.chanlun_tools import (
                    get_chanlun_full_report,
                    get_chanlun_bi,
                    get_chanlun_zhongshu,
                    get_chanlun_beichi,
                )
                analyst_nodes["chanlun"] = create_chanlun_analyst(self.quick_thinking_llm)
                delete_nodes["chanlun"] = create_msg_delete()
                tool_node_map["chanlun"] = ToolNode([
                    get_chanlun_full_report,
                    get_chanlun_bi,
                    get_chanlun_zhongshu,
                    get_chanlun_beichi,
                ])

        # -----------------------------------------------------------------------
        # Common nodes
        # -----------------------------------------------------------------------
        quality_gate_node = create_quality_gate(self.quick_thinking_llm)
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)

        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        # -----------------------------------------------------------------------
        # Build workflow
        # -----------------------------------------------------------------------
        workflow = StateGraph(AgentState)

        # Register analyst nodes
        for atype in analyst_nodes:
            workflow.add_node(f"{atype.capitalize()} Analyst", analyst_nodes[atype])
            workflow.add_node(f"Msg Clear {atype.capitalize()}", delete_nodes[atype])
            workflow.add_node(f"tools_{atype}", tool_node_map[atype])

        # Register common nodes
        workflow.add_node("Quality Gate", quality_gate_node)
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # -----------------------------------------------------------------------
        # Edges: analysts in sequence → Quality Gate → Bull/Bear debate → Risk debate
        # -----------------------------------------------------------------------
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        for i, atype in enumerate(selected_analysts):
            current = f"{atype.capitalize()} Analyst"
            current_tools = f"tools_{atype}"
            current_clear = f"Msg Clear {atype.capitalize()}"

            workflow.add_conditional_edges(
                current,
                getattr(self.conditional_logic, f"should_continue_{atype}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current)

            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i+1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Quality Gate")

        # Quality Gate → Bull/Bear debate
        workflow.add_edge("Quality Gate", "Bull Researcher")

        # Bull ↔ Bear debate → Research Manager
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
        )

        # Research Manager → Trader → Risk debate
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")

        # Aggressive ↔ Conservative ↔ Neutral debate → Portfolio Manager
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Conservative Analyst": "Conservative Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Neutral Analyst": "Neutral Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Aggressive Analyst": "Aggressive Analyst", "Portfolio Manager": "Portfolio Manager"},
        )

        workflow.add_edge("Portfolio Manager", END)

        return workflow
