#!/usr/bin/env bash
# 分析流水线 Top 3 候选股
cd /home/harrydolly/code/TradingAgents-astock
source /etc/profile  # 加载完整API Key
export DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY"

cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate

# 先用pipeline输出Top 3
python3 scan_pipeline.py --date 2026-06-09 2>&1
echo "---"
echo "流水线完成，Top 3候选已经输出到 ~/.hermes/pipeline_output/"
