#!/usr/bin/env bash
# 快速扫描：缠论+游资联合全市场筛选
# 用法: bash quick_scan.sh [--live] [--holdings] [--top N]
set -e
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
exec python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py "$@"
