"""
缠论技术分析师 (Chanlun Analyst)
=================================
第八位 Analyst，在主流7个Analyst之后运行。
基于缠中说禅理论体系进行技术面深度分析。

分析流程：
1. 获取 K 线数据（日线 + 30分钟）
2. 笔划分 + 包含关系处理
3. 中枢识别
4. MACD 背驰判断
5. 三类买卖点识别
6. 多级别联动分析
7. 输出缠论报告
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_stock_data,
)
from tradingagents.agents.utils.chanlun_tools import (
    get_chanlun_full_report,
    get_chanlun_bi,
    get_chanlun_zhongshu,
    get_chanlun_beichi,
)
from tradingagents.dataflows.config import get_config


def create_chanlun_analyst(llm):
    """创建缠论技术分析师节点。
    
    该分析师在主流分析师完成基本面/消息面分析后执行，
    专注缠论技术面分析。
    """

    def chanlun_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_stock_data,
            get_chanlun_bi,
            get_chanlun_zhongshu,
            get_chanlun_beichi,
            get_chanlun_full_report,
        ]

        config = get_config()

        system_message = (
            "你是一位精通 **缠中说禅技术分析理论** 的 A 股技术分析师。\n"
            "你的任务是使用缠论体系对目标 A 股进行完整技术分析。\n\n"
            
            "## 缠论分析框架\n"
            "分析必须遵循以下 7 层步骤：\n\n"
            
            "### 第一步：获取数据\n"
            "调用 `get_stock_data` 获取日线 K 线数据（至少 200 根）。\n\n"
            
            "### 第二步：缠论笔划分\n"
            "调用 `get_chanlun_bi` 传入 K 线数据，自动完成：\n"
            "- 包含关系处理（上涨取高高，下跌取低低）\n"
            "- 顶底分型识别\n"
            "- 笔的划分\n\n"
            
            "### 第三步：中枢识别\n"
            "调用 `get_chanlun_zhongshu` 识别所有中枢：\n"
            "- 标准中枢：三段重叠\n"
            "- 中枢延伸/扩张/新生判断\n"
            "- ZG/ZD/GG/DD 位置\n\n"
            
            "### 第四步：背驰判断\n"
            "调用 `get_chanlun_beichi` 进行：\n"
            "- 趋势背驰判断（两个以上中枢后的力度衰竭）\n"
            "- 盘整背驰判断\n"
            "- MACD 辅助确认（黄白线回抽 0 轴是前提）\n\n"
            
            "### 第五步：完整报告\n"
            "调用 `get_chanlun_full_report` 获取整合报告。\n\n"
            
            "### 第六步：多级别联动分析\n"
            "如果数据充足，对日线和 30F/5F 级别做区间套分析。\n\n"
            
            "### 第七步：撰写分析报告\n"
            "整合以上分析，输出结构化的缠论分析报告。\n\n"
            
            "## 缠论核心心法（必须牢记）\n"
            "- **第一类买点**：都在 0 轴之下背驰形成的\n"
            "- **第二类买点**：都是第一次上 0 轴后回抽确认形成的\n"
            "- 没有回抽 0 轴就不存在本级别背驰\n"
            "- **背了又背**的深层原因：误把次级别回抽当本级别背驰\n"
            "- 宁卖早、不卖晚\n"
            "- 跌只能考虑买，涨只能考虑卖\n"
            "- 级别是节奏的关键\n\n"
            
            "## A 股特殊须知\n"
            "- 涨跌停制度：主板 ±10%，科创板/创业板 ±20%，ST ±5%\n"
            "- T+1 交易：当日买入次日才能卖出\n"
            "- A 股强势股 RSI 可长期维持在 60-80 区间\n"
            "- A 股「量在价先」规律显著\n\n"
            
            "## 输出要求\n"
            "报告末尾附 Markdown 表格汇总以下内容：\n"
            "| 维度 | 信号 | 置信度 | 说明 |\n"
            "|------|------|--------|------|\n"
            "| 当前走势 | 上涨趋势/下跌趋势/盘整 | - | 走势类型判断 |\n"
            "| 买卖点 | 一买/二买/三买/无 | XX% | 出现位置 |\n"
            "| 中枢位置 | ZG/ZD | - | 关键位 |\n"
            "| 背驰 | 有/无 | XX% | 类型 |\n"
            "| 支撑/阻力 | 价格位 | - | 关键位 |\n"
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "chanlun_report": report,
        }

    return chanlun_analyst_node
