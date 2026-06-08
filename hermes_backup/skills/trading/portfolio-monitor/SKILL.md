---
name: portfolio-monitor
description: 持仓监控与出局/加仓信号 — 每日扫描持仓股的技术面信号+实时行情，给出明确的止盈止损建议。含cronjob自动推送。
category: trading
---

# 持仓监控 (portfolio-monitor)

## 用途

每日收盘后 + 早盘开盘后扫描指定持仓的缠论信号、游资信号和技术指标变化，判断是否需要出局或加仓。

## 工作流

### 1. 脚本路径

```bash
~/.hermes/scripts/portfolio_monitor.py
```

### 2. 运行方式

```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
python3 ~/.hermes/scripts/portfolio_monitor.py
```

### 3. 自动cronjob

已配置两条：
- **16:30** — 收盘后（依赖 `astock-daily-sync` 的 16:00 数据同步），基于已入库的日线数据跑完整技术分析
- **8:30** — 早盘开盘前，结合昨日收盘数据 + 腾讯实时行情做盘前判断

两条都推送到本聊天。使用 `cronjob(action='list')` 查看当前job状态。

### 4. 添加新持仓

编辑 `~/.hermes/scripts/portfolio_monitor.py` 中的 `PORTFOLIO` 列表：

```python
PORTFOLIO = [
    ('301231', '荣信文化', 34.62),   # (代码, 名称, 买入成本)
    ('300550', '和仁科技', 14.63),
    ('600503', '华丽家族', 2.82),
    ('603586', '金麒麟', 17.63),
]
```

## 信号规则

### 出局信号（⚠️ / 🔴）

| 条件 | 严重程度 | 操作建议 |
|------|---------|---------|
| MACD绿柱持续放大3日以上 | ⚠️ 预警 | 关注，准备减仓 |
| 跌破MA60(60日均线) | 🔴 破位 | 减半或全出 |
| 单日放量大跌超5% | 🔴 紧急 | 立即止损 |
| 连续3日收阴 | ⚠️ 弱势 | 反弹减仓 |
| 缠论所有信号消失 | ⚠️ 中性 | 持有观察但不加仓 |

### 加仓信号（💡 / 🟢）

| 条件 | 强度 | 操作建议 |
|------|------|---------|
| 放量站上MA5+涨幅>2% | 🟢 强 | 可加仓 |
| MACD金叉(DIF上穿DEA) | 🟢 趋势转好 | 加仓 |
| MACD绿柱缩短+底背离 | 🟡 反转初期 | 轻仓试错 |
| 缩量回踩MA60企稳 | 🟢 低吸点 | 加仓 |

## 数据源

### 日线K线
SQLite数据库 (`~/.hermes/astock_data.db`)，由 `astock-daily-sync` 同步。

### 实时行情
腾讯HTTP API (`qt.gtimg.cn`)，前缀 `sh` 沪/ `sz` 深：
```python
import requests
r = requests.get(f'http://qt.gtimg.cn/q={prefix}{code}', timeout=5)
parts = r.text.split('~')
price = float(parts[3])   # 现价
open_ = float(parts[5])   # 今开
high = float(parts[33])   # 最高
low = float(parts[34])    # 最低
chg = float(parts[32])    # 涨跌幅%
```

### 日K线在线fallback（数据库无数据时）
东财push2his：
```
https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.{code}&fields2=f51,f52,f53,f54,f55,f56,f57,f58&klt=101&fqt=1&end=20500101&lmt=120
```
⚠️ 东财API可能返回 `Connection aborted`，建议备用新浪API。

## 相关脚本

### `scripts/portfolio_monitor.py` — 每日持仓监控
输出每只股的盈亏、信号状态、出局/加仓判断。被cronjob调用。

### `scripts/research_report.py` — DeepSeek投研报告
采集持仓股的DB日线 + 实时行情 + 缠论/游资信号，组装成结构化提示词，调用DeepSeek生成深度分析报告。
每只股给出：走势判断、核心逻辑、风险点、止盈/止损/加仓具体价位、优先级排序。
```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
python3 ~/.hermes/skills/trading/portfolio-monitor/scripts/research_report.py
```

## 参考文档

### `references/build-signal-screening.md`
全市场建仓信号筛选工作流：
1. 第一层：SQLite数据库扫描所有股票的缠论+游资信号（30秒4685只）
2. 第二层：对精选标的用腾讯实时行情验证低开高走/量能健康
3. 输出：第一梯队(缠论+游资双确认) + 第二梯队(单体系多策略)

## 相关skill

- `astock-daily-sync` — 数据上游，必须在持仓监控前运行
- `three-crows-screening` — 共用 `chanlun_screener.py` 的缠论策略函数
- `youzi-screening` — 游资3策略函数
- `trading-knowledge-base` — 缠论/游资知识库
