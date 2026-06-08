---
name: classic-screening
description: 经典选股——缠论(4策略)+游资(3策略)联合全市场扫描，从SQLite DB秒级扫描4685只，输出建仓信号分级排行
version: 1.0.0
tags:
  - 选股
  - 缠论
  - 游资
  - 全市场
  - 建仓信号
related_skills:
  - chanlun-stock-screening
  - youzi-screening
  - three-crows-screening
---

# 经典选股 — 缠论+游资联合全市场扫描

## 用途

跑缠论4策略 + 游资3策略 **联合全市场扫描**，从SQLite DB 4685只股票中筛选建仓信号。

## 用法

```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate

# 全市场扫描（盘后，DB历史日线）≈24s
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py

# 盘中模式（mootdx通达信TCP + 腾讯实时备用）
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py --live

# 仅分析持仓（盘中，~2s，腾讯实时）
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py --holdings --live

# 显示Top N
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py --top 30

# 只扫前N只测试
python3 ~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py 500
```

## 两种模式

### 盘后模式（默认）— DB历史日线
- 数据来源：SQLite DB（astock-daily-sync补全到最新交易日）
- 速度：24s/4685只
- 说明：DB中DB的 `daily_klines` 表，列名 date, open, high, low, close, volume, amount

### 盘中模式（--live）— mootdx通达信TCP优先
- 数据来源：DB历史 + mootdx通达信TCP + 腾讯API备用
- 速度：因单只拉腾讯API约300ms，批量约9min/全量
- mootdx速度：~0.18s/只（含完整历史），全量约5分钟（仅当天增量）
- 连接服务器：`astrocytes/connect.cfg` 中 `202.108.253.139:80`（最快22ms）
- mootdx通过 `client.get_k_data(code=c, start_date='...', end_date='...')` 拉取日K线（支持日期范围，比bars更方便）
  - 可选：低层接口 `client.bars(symbol=code, frequency=9, start=0, offset=800)` 仅拉最新800条
- 实时行情（当前价/涨跌/量/换手率）通过 `client.quotes(symbols=[code])` 获取
- mootdx失败时自动降级到腾讯API：`web.ifzq.gtimg.cn/appstock/app/fqkline/get`（日线）和 `qt.gtimg.cn`（实时行情）
- ⚠️ get_k_data 支持 科创板(688)，不支持 北交所(920) — 会报 'datetime' 错误

### 数据获取链
```
read_live(code)  # 盘中模式
├── read_klines(code)       → DB历史日线
├── fetch_live_kline_mootdx()  → mootdx通达信TCP（优先）
│   └── 失败 → fetch_live_kline() → 腾讯API（备用）
└── fetch_live_realtime_mootdx() → mootdx实时行情（优先）
    └── 失败 → fetch_live_realtime() → 腾讯API（备用）

scan_one(code, name, live=True)  # 单只扫描
├── read_live(code)  → 获取合并日线 + 实时行情
├── 遍历缠论4策略(c1~c4, 传入df和rt)
├── 遍历游资3策略(y1~y3, 传入df和rt)
└── 返回结果dict {code, name, price, chg, chanlun, youzi, ...}
```

## 输出格式（标准模板）

```
=================================================================
  [模式] 扫描标题
  日期: YYYY-MM-DD HH:MM | ⏱ NNs
=================================================================

### 筛选条件
| 大类 | 策略 | 判定逻辑 |
|:---|:----|:--------|
| 缠论 | 底分型+底背驰 | ... |
| 游资 | 游资强势股 | ... |

### 数据概况
  候选池: XXXX只 | 命中: XXX只
  模式: 🟢盘中(通达信TCP) / 🔵盘后(DB历史)

### 策略命中分布
  缠论:
    • 线段逆驰: X次
    • 三买v2: X次
    ...
  游资:
    • 游资强势股: X次
    ...

### 多策略共振 Top 20
  代码  名称   总  价格   涨跌   策略详情
  ──────────────────────────────────────
  XXXXXX XXXX 5  XX.XX +X.XX%  底分型/三买/🔥强势/反包

### 🛡️ 稳健型（缠论≥2 + 未大涨）
### 🔥 激进型（涨幅>5% + 缠论确认）
### 🎣 低吸潜伏型（游资低吸信号）
### 📌 你的持仓信号（含成本+浮盈+建议）
### 💡 操作建议
```

## 策略体系

### 缠论4策略（chanlun-stock-screening skill）

| 策略 | 函数 | 说明 |
|------|------|------|
| 底分型+底背驰 | `c1(df, rt)` | 第一类买点基础版：底分型识别 + MACD绿柱面积缩小 < 90% |
| 关键K线突破 | `c2(df, rt)` | 第79课：强底分型后C3>H1突破，放量确认 |
| 三买v2 | `c3(df, rt)` | 中枢突破+回抽2%~20%+不破ZG，基于缠师原文 |
| 线段逆驰(nichi) | `c4(df, rt)` | 素论体系：反弹3%~30%+缩量+MACD dif金叉 |

⚠️ **nichi策略问题**：当前命中率过高（2277/2587只≈88%），因为MACD金叉+反弹判断太宽松。需要收紧：
- 反弹幅度收窄到 5%~20% 或要求更低量比
- MACD dif金叉要求更严格（绝对值<0.3 而非 0.5）
- 或者加一个「均线多头」前置条件

### 游资3策略（youzi-screening skill）

| 策略 | 函数 | 哲学来源 | 说明 |
|------|------|---------|------|
| 强势股 | `y1(df, rt)` | 炒股养家/赵老哥 | 近3日大涨>4%+放量+均线多头 |
| 低吸 | `y2(df, rt)` | 爱在冰川 | 强势股回调2-12日+缩量+MA支撑 |
| 反包 | `y3(df, rt)` | 短线训练营/闻少 | 昨日上影+冲高>3%+今日涨>0.5%+放量 |

## 扫描结果分级

### 级别判定

| 梯队 | 条件 | 示例策略组合 |
|------|------|------------|
| ⭐⭐⭐ 强烈信号 | 缠论≥2 **且** 游资≥2 | 三买+逆驰 + 强势+低吸+反包 |
| ⭐⭐ 较强 | 缠论≥1 **且** 游资≥1 | 底背驰 + 反包 |
| ⭐ 关注 | 单个体系多策略 | 仅缠论3策略 或 仅游资2策略 |

### 输出字段

- 代码、名称
- 策略组合（如 "关键K线/三买v2 + 🔥强势+反包"）
- 价格、涨跌幅
- 缠游共振标记：缠论≥2 **或** 缠游同时命中

## 数据源

SQLite数据库 `~/.hermes/astock_data.db`

数据由 `astock-daily-sync` skill 在每日16:00收盘后同步。盘中数据截止到上一交易日。

## 相关文件

```bash
# 扫描脚本
~/.hermes/skills/youzi-screening/scripts/chanlun_and_youzi.py    — ⭐缠论+游资联合扫描（主入口）
# 旧版扫描脚本（分别跑）
~/.hermes/skills/trading/three-crows-screening/scripts/chanlun_screener.py  — 缠论4策略
~/.hermes/skills/youzi-screening/scripts/youzi_screener.py                  — 游资3策略
~/.hermes/skills/trading/three-crows-screening/scripts/chanlun_and_three_crows.py  — 缠论+三阴

# 收盘同步
~/.hermes/scripts/sync_close.py                                     — mootdx通达信TCP同步

# 数据库
~/.hermes/astock_data.db
/home/harrydolly/code/TradingAgents-astock/tradingagents/dataflows/astock_db.py
/home/harrydolly/code/TradingAgents-astock/tradingagents/dataflows/live_data.py

# 通达信服务器配置
/home/harrydolly/文档/游资/connect.cfg                              — 40个行情服务器
```

## 注意事项

- **不拉在线接口**——全DB本地扫描，零网络请求
- 排除规则：ST/\*ST、688科创板、4/83/87(北交所/新三板)
- 24秒/4685只，归功于纯numpy+SQLite优化
- 日均涨跌幅（chg）来自DB中的收盘价变化

## 示例输出格式

```
📊 缠论命中分布:
    线段逆驰: 573次
    三买v2: 283次
    关键K线突破: 113次
    底分型+底背驰: 37次
📊 游资命中分布:
    游资强势股: 1252次
    游资反包: 308次
    游资低吸: 279次
🎯 缠游共振: 627只
🏆 第一梯队 ⭐⭐⭐（缠论≥2+游资≥2）
  002962 五方光电  关键K线/三买v2 + 🔥强势+反包    21.65 +5.61%
  300626 华瑞股份  关键K线/三买v2 + 🔥强势+低吸    40.30 +20.01%💥
  301231 荣信文化  三买v2 + 🔥强势+低吸+反包       33.81 +3.36%
```
