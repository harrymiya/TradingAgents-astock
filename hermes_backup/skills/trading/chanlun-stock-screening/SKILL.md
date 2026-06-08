---
name: chanlun-stock-screening
description: 全市场选股筛查引擎 —— 多行业批量扫描、多维度评分排序、策略分组、候选精炼
version: 1.2.0
tags:
  - 缠论
  - 选股
  - 全市场扫描
  - 行业轮动
  - 批量分析
related_skills:
  - youzi-screening
  - three-crows-screening
  - chanlun-theory
  - chanlun-market-data
  - chanlun-framework
---

# chanlun-stock-screening

## 用途

当你需要**在全市场范围内选股**时加载此 skill。

## 数据完整性

```python
from tradingagents.dataflows.data_integrity import ensure_data
ensure_data()  # 检查最新交易日数据是否完整，缺失的自动补全
```

**盘中 vs 盘后**：
- **盘中**：使用mootdx（通达信TCP）优先，腾讯API备用。从 `~/文档/游资/connect.cfg` 读取服务器列表。
- **盘后**：使用DB历史日线，16:00 cronjob增量同步。
- **分时数据不入库**，只临时获取。

## mootdx 配置（2026-06-08 更新）

之前写"mootdx不稳定"已过时。从 `connect.cfg` 找到多个可达服务器：

```
文件: ~/文档/游资/connect.cfg (GBK编码, configparser解析)
最快: 202.108.253.139:80 (22ms)
初始化: Quotes.factory(market='std', tcp=('202.108.253.139', 80, True))
```

40个服务器中约80%可达，实测180.153.18.170:7709(42ms)、115.238.56.198:7709(42ms)等均可工作。mootdx失败时自动降级到腾讯/Sina HTTP。

## 推荐扫描命令

### 缠论+游资联合扫描（当前最完整）

```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate

# 盘后全市场
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py

# 盘中全市场（mootdx实时数据）
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py --live

# 持仓分析
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py --holdings --live

# 显示Top 30
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py --top 30
```

输出格式7节：筛选条件→数据概况→策略分布→共振Top→稳健型→激进型→低吸型→持仓信号→操作建议

### 旧版缠论单策略扫描

```bash
python3 ~/.hermes/skills/trading/three-crows-screening/scripts/chanlun_screener.py --strategy san_mai --all
python3 ~/.hermes/skills/trading/three-crows-screening/scripts/chanlun_screener.py --stock 002575
```

### 缠论+三阴联合扫描

```bash
python3 ~/.hermes/skills/trading/three-crows-screening/scripts/chanlun_and_three_crows.py
```

## 运行时注意

- 在 terminal 中通过 heredoc（`<< 'PYEOF'`）运行 Python 批量脚本
- 记得 `cd` 到项目目录并 `source .venv/bin/activate`
- 批量扫描脚本所在路径以绝对路径给出（不要用相对路径）
