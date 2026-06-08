---
name: three-crows-screening
description: 通达信三阴选股公式的Python实现——涨停启动→3天缩量回调→今日企稳，全市场扫描（排除ST/科创板/北交所/次新股）。从SQLite数据库读取K线，不拉在线接口。
version: 3.1.0
tags:
  - 选股
  - 三阴
  - 技术分析
  - 通达信
  - A股
related_skills:
  - astock-daily-sync
  - chanlun-framework
  - chanlun-stock-screening
---

# 三阴选股（three-crows-screening）v3.0

## 用途

把通达信的三阴选股公式转成 Hermes 可执行的 Python 脚本。从 SQLite 数据库读取日线K线，**绝不调用在线接口**。

数据由 `astock-daily-sync` skill 维护，每日收盘后自动同步。

---

## 快速使用

### 1️⃣ 全市场扫描（数据库版，推荐）

```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
python3 ~/.hermes/skills/trading/three-crows-screening/scripts/screen_from_db.py
```

→ **4685只股票，~12秒完成，零在线请求**

### 2️⃣ 单只股票分析

```bash
python3 ~/.hermes/skills/trading/three-crows-screening/scripts/single_stock.py 002575
python3 ~/.hermes/skills/trading/three-crows-screening/scripts/single_stock.py 000586
```

### 3️⃣ 每日自动扫描（cronjob）

已配置工作日下午4点自动执行：
1. `astock-daily-sync` → 增量同步数据
2. `three-crows-screening` → 三阴选股全市场扫描
3. 结果自动发到此聊天

---

## 脚本列表

```
~/.hermes/skills/trading/three-crows-screening/scripts/
├── three_crows.py          # 核心选股函数（严格对照通达信公式）
├── screen_from_db.py       # 全市场数据库扫描 ⭐ 推荐使用
├── screen_all.py           # (旧版) 候选池在线扫描 — 保留作fallback
├── single_stock.py         # 单只股票分析（数据库版）
├── chanlun_screener.py         # 缠论选股器（底分型+底背驰/关键K线突破/三买v2/线段逆驰）
└── chanlun_and_three_crows.py  # 缠论+三阴联合扫描（推荐，含标准输出格式）
```

---

## 数据源

```
路径: ~/.hermes/astock_data.db
模块: /home/harrydolly/code/TradingAgents-astock/tradingagents/dataflows/astock_db.py

扫描链路:
  screen_from_db.py → astock_db.get_klines() → SQLite → DataFrame → three_crows.py
                     ↑ 绝不调用在线接口

缺数据fallback（688科创板/新股未同步时）:
  东财push2his HTTP API:
  https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.{code}&fields2=f51,f52,f53,f54,f55,f56,f57,f58&klt=101&fqt=1&end=20500101&lmt=120
  返回格式: CSV行, 字段顺序=日期,开盘,收盘,最高,最低,成交量(手),成交额,振幅,涨跌幅,涨跌额,换手率
```

⚠️ **注意**：新浪HTTP接口不返回 `Amount`（成交额）列。数据库扫描时如果 `Amount` 全为0，自动用 `Volume * 100 * (Open+Close) / 2` 估算成交额。

---

## 数据库状态查询

```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
python3 -c "
from tradingagents.dataflows.astock_db import get_db_stats
stats = get_db_stats()
print(f'股票: {stats[\"stocks\"]}只')
print(f'有日线: {stats[\"stock_with_klines\"]}只')
print(f'日线条数: {stats[\"klines\"]}条')
print(f'日期: {stats[\"date_range\"][0]} ~ {stats[\"date_range\"][1]}')
"
```

---

## 历史结果

| 扫描日期 | 方式 | 扫描数 | 命中 |
|---------|------|--------|------|
| 2026-06-05 | 在线接口（首次） | 4685 | 16只 |
| 2026-06-05 | 数据库版 v3.0 | 4685 | 16只 ✅ 完全一致 |

### 16只命中股（2026-06-05）

汇源通信(000586) 南山控股(002314) 东山精密(002384) 嘉欣丝绸(002404)
群兴玩具(002575) 麦格米特(002851) 意华股份(002897) 金时科技(002951)
阿莱德(301419) 世纪恒通(301428) 达利凯普(301566) 华微电子(600360)
鸿远电子(603267) 火炬电子(603678) 继峰股份(603997) 圣泉集团(605589)

---

## 架构

```
┌───────────────────────────────────────┐
│    sync_close.py（mootdx通达信TCP）     │  专职收盘同步
│    ~/.hermes/scripts/sync_close.py     │
│    15:05 cronjob, 约5分钟全量4370只     │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌───────────────────────────────────┐
│     daily_klines 表 (SQLite)       │  
│     ~/.hermes/astock_data.db       │
└────────┬──────────────────────────┘
         │
         ├──────────────────────────────────┐
         ▼                                   ▼
┌─────────────────────┐   ┌──────────────────────────────┐
│ 三阴/缠论/游资扫描    │   │ 每日深度研究(daily_research)  │
│ DB本地，不拉在线接口  │   │ 主线→产业链→精选→工具库      │
└─────────────────────┘   └──────────────────────────────┘
```

## 数据同步（重要更新）

**收盘同步已从 `sync_to_db.py`（新浪API）迁移到 `sync_close.py`（mootdx通达信TCP）：**

| 脚本 | 接口 | 速度 | 位置 |
|:----|:----|:----|:----|
| `sync_close.py` ⭐ | mootdx通达信TCP | ~5分钟全量 | `~/.hermes/scripts/sync_close.py` |
| `sync_to_db.py` ❌旧 | 新浪API（已失效） | — | 仅作参考 |

mootdx服务器从 `~/文档/游资/connect.cfg` 读取，最快的是 `202.108.253.139:80`（22ms）。

---

## 通达信原公式

详见 `references/formula-translation-reference.md`。

排除规则：
- ST / *ST（名称检查）
- 4开头（新三板）
- 83/87开头（北交所）
- 688开头（科创板）
- 次新股（数据需覆盖180个交易日以上）

形态特征：
```
T-4    T-3        T-2        T-1         T(今天)
┌─────┬──────────┬──────────┬──────────┬──────────┐
│     │  涨停     │   阴线    │   阴线    │   阴线   │
│ 前  │  放量    │   放量    │   缩量    │   续缩   │
│ 一  │收盘距涨停 │  量>T-3   │  量<T-2   │  量<T-1   │
│ 日  │  <1%     │          │          │ 企稳信号 │
└─────┴──────────┴──────────┴──────────┴──────────┘
```

---

## 注意事项

- 数据库扫描时 Amount=0 会自动估算成交额（新浪接口不返回Amount）
- 数据不足的股票（`screen_from_db.py` 会报告"数据不足"数量），运行 `astock-daily-sync` 的 `sync_to_db.py --full` 补全
- 北交所(83/87)和新三板(4开头)默认跳过
- 如果在 scrcpy/电脑上直接跑，确保 `.venv` 激活 + `source /etc/profile`（DeepSeek key 在 `/etc/profile` 里）
- screen_all.py 是旧的在线接口版，已弃用

## 相关skill

- `astock-daily-sync` — 数据同步（本skill的数据上游）
- `chanlun-stock-screening` — 全市场选股筛查引擎（含chanlun_screener.py缠论选股器）
- `youzi-screening` — 游资短线选股（强信号/低吸/反包，与缠论策略互补）
- `portfolio-monitor` — 持仓监控日报（依赖本skill的缠论策略函数）
