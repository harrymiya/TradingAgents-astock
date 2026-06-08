---
name: youzi-screening
description: 游资心法短线选股体系 — 基于炒股养家/92科比/赵老哥/闻少等游资心法的量化选股，包括情绪周期判断、强势股识别、低吸/反包信号
category: trading
---

# 游资短线选股 (youzi-screening)

基于18位顶级游资心法 + 情绪流龙头战法(杨楠) + 短线训练营 + 闻少盘口体系的量化选股。

## 特征

- 数据源：SQLite数据库 (`~/.hermes/astock_data.db`) + 盘中mootdx通达信TCP
- 日线级别扫描，全市场（约4700只）
- 返回中文结果，标准分层输出格式（稳健/激进/低吸分类）
- **缺数据fallback**：股票在DB中但无K线（如688科创板未被同步），使用东财push2his HTTP API获取日K线

## 数据获取策略

### mootdx 通达信TCP（盘中优先，最快）
从 `~/文档/游资/connect.cfg` 读取通达信服务器列表。已测试可用服务器：
| IP | 端口 | 延迟 |
|:---|:---:|:---:|
| 202.108.253.139 | 80 | 22ms ⭐最快 |
| 180.153.18.170 | 7709 | 42ms |
| 115.238.56.198 | 7709 | 42ms |
| 218.75.126.9 | 7709 | 56ms |

**初始化**：`Quotes.factory(market='std', tcp=('202.108.253.139', 80, True))`
- `bars()` 获取日K线（含当天数据）：`client.bars(symbol=code, frequency=9, start=0, count=120)`
- `quotes()` 获取实时行情：`client.quotes(symbols=[code])`
- 单只约115ms，全市场~9分钟（比腾讯API快3倍）
- mootdx失败自动降级到腾讯API

### 盘后DB（SQLite，批量扫描用）
`~/.hermes/astock_data.db` 的 `daily_klines` 表，不走在线接口。

## 用法

```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate

# 🟢 盘中全市场扫描（mootdx通达信TCP + 实时行情）
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py --live

# 🔵 盘后全市场扫描（只用DB历史日线）
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py

# 🏠 仅分析4只持仓（盘中优先）
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py --holdings --live

# 🎯 只看Top N
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py --top 30

# （旧版）游资单策略扫描
python3 youzi_screener.py --strategy qiangshi --all
```

## 输出标准格式（必遵）

用户要求所有扫描结果按此格式输出：

```
=================================================================
  模式 + 标题 | 日期: YYYY-MM-DD HH:MM | ⏱ Ns
=================================================================

### 筛选条件
| 大类 | 策略 | 判定逻辑 | (逐条列出7策略)

### 数据概况
  候选池: XXXX只 | 命中: XXX只 | 模式: 🟢盘中/🔵盘后

### 策略命中分布
  缠论: · 策略名: N次 ...
  游资: · 策略名: N次 ...

### 多策略共振 Top 20
  代码  名称  总  价格  涨跌   策略详情

### 🛡️ 稳健型（缠论≥2 + 未大涨）
### 🔥 激进型（涨幅>5% + 缠论确认）
### 🎣 低吸潜伏型（游资低吸信号）
### 📌 你的持仓信号（含成本/浮盈/建议）
### 💡 操作建议（核心关注+风险提示）
```

## 扫描选项

| 参数 | 说明 |
|:----|:-----|
| `--live` | 盘中模式，mootdx优先→腾讯备用 |
| `--holdings` | 仅分析4只持仓（301231/300550/600503/603586） |
| `--top N` | 只显示Top N结果 |
| 数字 | 限制扫描前N只（测试用） |

## 策略列表

### 缠论（4策略）
1. **底分型+底背驰** — 底分型确认 + MACD后段绿柱面积 < 前段90%
2. **关键K线突破** — 第79课强底分型，第三K线收盘突破第一K线最高
3. **三买v2** — 中枢突破 + 回抽2%~20% + 不破中枢上沿ZG
4. **线段逆驰(nichi)** — 反弹3%~30% + 缩量 + MACD零轴金叉

### 游资（3策略）
1. **强势股** — 养家/赵老哥：近3日大涨>4% + 放量 + 均线多头
2. **低吸** — 养家/爱在冰川：前期涨>8% + 回调2%~20% + 缩量企稳 + 均线支撑
3. **反包** — 短线训练营/闻少：昨日上影线 + 冲高>3% + 今日涨幅>0.5% + 放量

## 跨skill关系

- `three-crows-screening` → 包含缠论4策略脚本 + 三阴选股
- `chanlun-stock-screening` → 全市场筛选引擎
- `trading-knowledge-base` → 游资心法知识库（18位游资 + 情绪流 + 短线训练营）
- `portfolio-monitor` → 持仓监控（导入游资3策略函数判断加仓/出局）

## 脚本列表

```
~/.hermes/skills/youzi-screening/scripts/
├── chanlun_and_youzi.py      # 缠论+游资7策略联合扫描（支持盘中/盘后/持仓）⭐
├── chanlun_sanmai_youzi.py   # 缠论(三买v2)+游资(强势股)精筛版 — 加了3道过滤（流动性/技术面/出货形态过滤）
└── youzi_screener.py         # 旧版游资单策略扫描（保留作fallback）
```

## 关联系统级脚本（youzi-screening的扫描逻辑被以下脚本调用）

```
# 全能选股入口（推荐日常使用）
~/.hermes/scripts/scan_toolbox.py
  — 行情判断(regime) → 自动选策略 → 选股 → 持仓分析 → 工具库情报
  — 4种策略引擎代码与chanlun_and_youzi.py的4策略逻辑一致（c1-c4 + y1-y3）
  — 策略函数注册在STRATEGIES字典中

# 收盘日线同步
~/.hermes/scripts/sync_close.py
  — mootdx通达信TCP同步，0失败约5分钟全量4370只
  — cronjob: 15:05每个交易日

# 策略回测校正
~/.hermes/scripts/strategy_backtest.py
  — 用历史数据（DB已有日线）跑回测
  — 策略引擎代码与scan_toolbox一致（从_scan_on_date函数复制）
  — 胜率/盈亏比/校正建议

# 每日深度研究（凌晨4点）
~/.hermes/scripts/daily_research.py
  — 主线识别+产业链拆解+精选个股
  — 存入 ~/.hermes/research_toolkit/
```
