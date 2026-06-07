#!/bin/bash
# TradingAgents-Astock 一键设置脚本
# 使用方法：
#   1. bash setup_key.sh
#   2. 粘贴你的 DeepSeek API Key
#   3. 回车

set -e

echo "================================"
echo "  TradingAgents-Astock 环境设置"
echo "================================"
echo ""

# 检查 venv
if [ ! -f ".venv/bin/activate" ]; then
    echo "❌ .venv 不存在"
    echo "   请先运行: python3 -m venv .venv"
    exit 1
fi

echo "请输入你的 DeepSeek API Key (粘贴后按回车):"
read -r USER_KEY

if [ -z "$USER_KEY" ]; then
    echo "❌ Key 不能为空"
    exit 1
fi

# 写 key 到 .venv/bin/activate 末尾（在 deactivate 函数之后）
if grep -q "DEEPSEEK_API_KEY" .venv/bin/activate; then
    # 替换已有的
    sed -i '/DEEPSEEK_API_KEY/d' .venv/bin/activate
fi
echo "" >> .venv/bin/activate
echo "# DeepSeek API Key (auto-set by setup_key.sh)" >> .venv/bin/activate
echo "export DEEPSEEK_API_KEY=\"$USER_KEY\"" >> .venv/bin/activate

# 也写一份到 .env
echo "DEEPSEEK_API_KEY=$USER_KEY" > .env

echo ""
echo "✅ Key 已写入:"
echo "   - .venv/bin/activate (source 时自动加载)"
echo "   - .env"
echo ""
echo "使用方式:"
echo "   source .venv/bin/activate"
echo "   python3 -c \"from tradingagents.graph.trading_graph import TradingAgentsGraph; ...\""
echo ""
