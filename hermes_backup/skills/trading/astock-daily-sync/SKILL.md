---
name: astock-daily-sync
description: A股数据策略 — 盘中实时+DB历史日线混合分析，收盘后增量同步。腾讯API直连（日线800天前复权），盘中分时不入库。
version: 2.3.0
tags:
  - 数据同步
  - 增量
  - SQLite
  - A股
  - 腾讯API
  - mootdx
related_skills:
  - three-crows-screening
  - chanlun-framework
  - chanlun-stock-screening
  - trading-strategy
---

# astock-daily-sync — A股日线数据增量同步

## 职责边界

**唯一职责：保持 SQLite 数据库里的日线数据是最新的。**

- ✅ 从数据源拉取日线K线 → 写入SQLite
- ❌ 不执行任何选股分析
- ❌ 不执行任何缠论分析
- ❌ 不分析任何股票

所有分析 skill（三阴选股、缠论框架分析、游资筛选等）都从数据库读数据。

---

## 数据库

```
路径: ~/.hermes/astock_data.db       ( /home/harrydolly/.hermes/astock_data.db )
引擎: SQLite
模块: /home/harrydolly/code/TradingAgents-astock/tradingagents/dataflows/astock_db.py

表:
  stocks(code, name, market, added_at)
    — 全市场股票列表（来自新浪，静态缓存）

  daily_klines(code, date, open, high, low, close, volume, amount)
    — 日K线，code+date 复合主键

  scan_cache(scan_date, code, name, formula_name, price, ...)
    — 扫描结果缓存（由分析 skill 写入）
```

### ⚠️ DB字段索引映射（常见坑）

`cursor.fetchall()` 返回 `daily_klines` 表的元组，字段顺序由SQL列顺序决定：

```
r[0] = code
r[1] = name (如果join了stocks表)
r[2] = date
r[3] = open
r[4] = high
r[5] = low
r[6] = close    <-- 注意！
r[7] = volume   <-- 不是close！
r[8] = amount
```

**常见错误**：直觉以为 `close` 在 r[7]，实际在 r[6]。用错会把成交量当收盘价算涨跌幅，导致收益率变成几亿%或市场判断完全错误。

---

## 数据架构：盘中实时 vs 盘后同步

```
盘中分析/扫描时:
├── 历史日线 ← SQLite DB (4371只, 收盘后同步)
├── 当天实时行情/日K ← 腾讯API (qt.gtimg.cn + 日线接口)
└── 合并 → live_data.get_data_for_analysis()

收盘后 (16:00 cronjob):
└── sync_close.py → 当天日线 INSERT OR REPLACE 写入DB
```

**盘中分时数据不入库**，只临时获取用于分析。

---

## 同步脚本

### ⭐ scripts/sync_close.py（收盘后同步 — mootdx TCP，最快）

**专职收盘同步脚本，使用mootdx通达信TCP接口，比腾讯API快3倍以上。**

位置：`/home/harrydolly/.hermes/scripts/sync_close.py`

**数据源：通达信行情服务器（从 connect.cfg 读取 40 个 IP）**

connect.cfg 位置：`/home/harrydolly/文档/游资/connect.cfg`

最快的服务器：
| IP | 端口 | 延迟 | 备注 |
|:---|:----|:----|:-----|
| 202.108.253.139 | 80 | 22ms | ⭐默认首选 |
| 202.108.253.158 | 80 | 23ms | 备用 |
| 180.153.18.170 | 7709 | 42ms | 备用 |
| 115.238.56.198 | 7709 | 42ms | 备用 |
| 218.75.126.9 | 7709 | 56ms | 备用 |
| 180.153.18.172 | 80 | 44ms | 备用 |

**用法：**
```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
python3 /home/harrydolly/.hermes/scripts/sync_close.py
python3 /home/harrydolly/.hermes/scripts/sync_close.py 2026-06-08  #指定日期
```

**同步逻辑：**
1. 自动检测DB最新日期，只同步缺失的
2. mootdx支持自动切换服务器（6个，连不上自动切下一个）
3. 每200只打一次进度
4. **0失败，约5分钟全量4370只**

**cronjob配置：**
```yaml
job_id: f9b7838fbcf9
name: 收盘日线同步
schedule: "5 15 * * 1-5"  # 每个交易日15:05
skills: [astock-daily-sync]
```

**与腾讯API sync_fast.py 对比：**
| 指标 | sync_fast.py（腾讯API） | sync_close.py（mootdx） |
|:----|:---------------------|:----------------------|
| 单只耗时 | ~300ms | **~115ms** |
| 全市场 | ~30分钟（需分批+限流） | **~5分钟** |
| 数据质量 | 量是手数，金额需估算 | 含Amount字段 ✅ |
| 稳定性 | 高（无频率限制） | 高（TCP长连接） |
| 盘中数据 | 含当天未收盘数据 | 含当天未收盘数据 ✅ |

**注意事项：**
- 如果mootdx连接断开，脚本自动切下一个服务器重新初始化客户端
- 不要在mootdx同步同时跑其他mootdx进程（TCP连接冲突）
- 盘中用mootdx拉实时行情，偶发失败会自动降级到腾讯API

### ⭐ 全量历史数据同步（sync_history_all.py — mootdx get_k_data）

**位置**：`/home/harrydolly/code/TradingAgents-astock/sync_history_all.py`

用于从零搭建数据库或补充近3年历史数据。使用 **mootdx.get_k_data(code, start_date, end_date)** 而非低层 `bars()` API：

```python
from mootdx.quotes import Quotes
client = Quotes.factory(market='std')
df = client.get_k_data(code='000001', start_date='2023-01-01', end_date='2026-06-08')
# 827行，~0.18秒
```

| 特性 | 值 |
|:----|:----|
| 支持市场 | 沪深主板 + 创业板 + **科创板(688)** |
| ❌不支持 | 北交所(920) — 报 `'datetime'` 错误 |
| 速度 | ~0.18s/stock，~1只/s，**全市场~86分钟** |
| 数据量 | ~800行/stock，全市场 ~400万行 |
| 断点续传 | 已有>600天+最早<=2023-01-01的自动跳过 |
| 日志 | 写入 `~/.hermes/sync_history.log`（后台模式可用 tail -f 追踪） |

**用法**：
```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
python3 sync_history_all.py                     # 全市场
python3 sync_history_all.py --check              # 检查数据覆盖
python3 sync_history_all.py --code 000001        # 单只
python3 sync_history_all.py --skip 100 --max 400 # 局部批次
```

**脚本策略**：
- 排除 ST/*ST/退市股（名字过滤）
- 已有 >600天 且 最早日期 <= 2023-01-01 的自动跳过
- 无数据的股票写 '1970-01-01' 空标记防反复重试

**mootdx API 完整参考**：见 `references/mootdx-api.md`

### scripts/sync_fast.py（旧版 — 腾讯API）

**用法：**
```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
python3 ~/.hermes/skills/trading/astock-daily-sync/scripts/sync_fast.py
python3 ~/.hermes/skills/trading/astock-daily-sync/scripts/sync_fast.py 2026-06-06 2026-06-08
```

**同步逻辑：**
1. 从DB已有的 `daily_klines` 表去重获取股票列表
2. 跳过688/4/83/87/8开头股票
3. 每只股票：拉800天K线 → 过滤目标日期 → INSERT OR REPLACE
4. 批量写入，每200只打一次进度

### scripts/sync_to_db.py（旧版，不使用）
新浪API已失效，仅作参考。

---

## 盘中实时数据模块

`/home/harrydolly/code/TradingAgents-astock/tradingagents/dataflows/live_data.py`

### `get_data_for_analysis(code, name, lookback_days=120)` ⭐ 主函数

```python
from tradingagents.dataflows.live_data import get_data_for_analysis, format_analysis_text

data = get_data_for_analysis("301231", "荣信文化")
# data['daily_klines'] — 合并后日线 [{date, open, high, low, close, volume, amount}]
# data['today_info'] — 盘中实时: {price, open, high, low, volume, pre_close, change, change_pct, amount, turnover(%), pe, amplitude(%)}
# data['today_kline'] — 当天日K线

print(format_analysis_text(data))
```

---

## 当前数据状态（2026-06-08 最终）

```
数据库: ~/.hermes/astock_data.db
引擎: SQLite 3.x, ~766MB
索引: idx_daily_code (code), idx_daily_date (date) — 毫秒级查询
总行数: 3,975,282行
股票数: 4,973只（有日线数据）
数据范围: 2023-01-03 ~ 2026-06-08（约828个交易日）
交易日数: ~825天/只（正常股）

数据天数分布:
  700+天: 4,798只（完整3.5年数据）
  500-700天: 65只
  100-300天: 75只
  <100天: 35只（ST/退市股，无法从mootdx获取）

4只持仓覆盖:
  301231 荣信文化: 828天 ✅
  300550 和仁科技: 823天 ✅
  600503 华丽家族: 828天 ✅
  603586 金麒麟: 828天 ✅

失败记录: 314只 = 全部920北交所股（mootdx std市场不支持）
```

---

## 注意事项

- **DB表名是 `daily_klines` 不是 `klines`**
- **live_data.py 不依赖 astock_db 模块** — 直接操作SQLite
- SQLite写锁冲突：**不要同时跑多个同步进程**
- `cursor.fetchall()` 结果中 **close在索引6，volume在索引7**（不是反过来）
- 腾讯API参考：`references/tencent-api.md`
- mootdx API参考：`references/mootdx-api.md`
- `connect.cfg`（40个通达信服务器）在 `~/文档/游资/connect.cfg`

## 备份与迁移

### DB备份
```bash
# 手动备份
python3 ~/.hermes/scripts/backup_astock_db.py

# 备份列表
python3 ~/.hermes/scripts/backup_astock_db.py --list

# 自动备份
# cronjob: 每周一 15:30（交易日），保留60天（~9个版本）
# 备份位置: ~/.hermes/backups/astock_data_YYYY-MM-DD.db
```

### Hermes完整迁移
```bash
# 轻量包（5MB，不含A股DB和state.db）
~/.hermes/scripts/package_hermes.sh --light

# 在新机器恢复
tar xzf ~/hermes_backup_*.tar.gz -C $HOME
# 然后需要:
# 1. 安装Hermes Agent
# 2. git clone TradingAgents-astock + pip install -e .
# 3. 检查config.yaml中的API Key
# 4. 检查平台Token（Feishu/Telegram可能过期）
# 5. 拷贝 astock_data.db（766MB）或重新用sync_history_all.py拉取
```

SQLite对350万行日线数据完全够用（766MB），加索引后查询毫秒级。
单用户+单cronjob场景下，SQLite是性能最优的选择（零网络开销、零配置）。
不需要换PostgreSQL。如果将来数据量>100GB或需要多进程并发写，再考虑迁移。

## 相关文件

```
~/.hermes/scripts/sync_close.py                  — ⭐收盘同步（mootdx TCP）
~/.hermes/skills/trading/astock-daily-sync/references/tencent-api.md   — 腾讯API参考
~/.hermes/skills/trading/astock-daily-sync/references/mootdx-api.md    — mootdx API参考（含sync_history_all）
/home/harrydolly/code/TradingAgents-astock/sync_history_all.py          — 全量历史同步脚本
/home/harrydolly/code/TradingAgents-astock/tradingagents/dataflows/live_data.py  — 盘中实时数据
~/.hermes/astock_data.db                                              — 数据库文件
```
