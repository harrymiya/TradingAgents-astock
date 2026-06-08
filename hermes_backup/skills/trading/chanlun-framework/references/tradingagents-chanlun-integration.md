# TradingAgents-Astock 缠论集成参考

> 项目路径：`/home/harrydolly/code/TradingAgents-astock/`
> 上游项目：[simonlin1212/TradingAgents-astock](https://github.com/simonlin1212/TradingAgents-astock)
> 基座：TauricResearch/TradingAgents（65K Stars）

## 架构概览

TradingAgents-Astock 是 8 Agent 多智能体投研框架（LangGraph）：

```
股票输入 → 7个Analyst(串行) → 缠论Analyst(第8位) → Quality Gate
  → Bull/Bear辩论(多回合) → Research Manager → Trader 
  → 三方风险辩论(Agg/Cons/Neut) → Portfolio Manager → 最终决策
```

## 缠论作为第8位 Analyst

### 文件结构
```
tradingagents/
├── dataflows/
│   └── chanlun/                    # 缠论数据层
│       ├── __init__.py             # analyze_chanlun() 主入口
│       ├── chanlun_core.py         # 数据模型 (KLine/Fractal/Bi/ZhongShu/BuySellPoint)
│       ├── chanlun_bi.py           # 笔划分算法
│       ├── chanlun_zhongshu.py     # 中枢识别算法
│       └── chanlun_beichi.py       # 背驰判断 + 买卖点
├── agents/
│   ├── analysts/
│   │   └── chanlun_analyst.py      # 缠论 Analyst Agent (LangChain节点)
│   └── utils/
│       └── chanlun_tools.py        # 4个LangChain @tool
```

### 算法调用链路
```
analyze_chanlun(klines, ticker, trade_date)
  ├── compute_bi(klines)          → 笔划分 (包含处理+分型+笔)
  ├── find_zhongshu(bis)          → 中枢识别 (ZG/ZD/GG/DD)
  ├── detect_beichi(bis, zhongshu, klines)  → MACD背驰判断
  ├── detect_second_buy_sell(bis, points, zhongshu) → 二类买卖点
  └── detect_third_buy_point(bis, zhongshu)        → 三类买点
```

### 笔划分关键参数
- `min_bi_kline_count`: 笔的最少K线数（默认4）
- 包含关系处理：上涨趋势取高高，下跌趋势取低低
- 分型过滤：连续同向分型取更极端的

### 背驰判断阈值
- 离开笔面积 < 进入笔面积的 **70%** → 背驰信号
- 离开笔面积 < 进入笔面积的 **50%** → 强背驰
- DIF/DEA 回抽 0 轴 → 置信度从0.4提升至0.7

### 图集成
- 位置：在 lockup Analyst 之后、Quality Gate 之前
- 节点名称：`Chanlun Analyst` / `tools_chanlun` / `Msg Clear Chanlun`
- 选择方式：`selected_analysts=[..., "chanlun"]`
- State 字段：`chanlun_report` (str)、`chanlun_buy_point` (str)、`chanlun_sell_point` (str)

### 配置 DeepSeek 作为 LLM
```python
from tradingagents.default_config import DEFAULT_CONFIG
config = dict(DEFAULT_CONFIG)
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-chat"
config["quick_think_llm"] = "deepseek-chat"
# 通过 DEEPSEEK_API_KEY 环境变量传入API key
```

项目原生支持 DeepSeek（`_PROVIDER_CONFIG` 已预配），无需改代码。

### 运行方式
```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
DEEPSEEK_API_KEY=sk-your-key python3 << 'EOF'
from tradingagents.graph.trading_graph import TradingAgentsGraph
graph = TradingAgentsGraph(
    selected_analysts=["market","social","news","fundamentals",
                       "policy","hot_money","lockup","chanlun"]
)
result = graph.propagate("000063", "2026-06-05")
print(result)
EOF
```

## 依赖安装
```bash
pip install -e ".[google]" -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install langgraph-checkpoint-sqlite -i https://pypi.tuna.tsinghua.edu.cn/simple
```

中国用户加上清华镜像可避免超时。
