# Hermes Agent 初始化上下文

> 本文件是 AGENTS.md — 给下一个 Hermes Agent 看的完整上下文。
> 2026-06-09 最后更新
> 
> 你被唤醒后的第一件事：读这个文件，了解你是谁、用户是谁、有什么工具、要怎么工作。

---

## 一、你现在在哪里

你的工作目录：**`/home/harrydolly/code/TradingAgents-astock/`**

这是 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 的 A 股特化 fork。项目已有完整的数据层和 Agent 框架。

### 重要路径

| 路径 | 用途 |
|:----|:----|
| `~/.hermes/` | Hermes 根目录（skills/ config.yaml .env） |
| `~/.hermes/astock_data.db` | A股日线数据库（3,975,282行，766MB） |
| `~/.hermes/skills/trading/` | 所有交易相关 skill |
| `~/.hermes/scripts/` | 定时任务脚本 |
| `code/TradingAgents-astock/` | 项目代码 + 策略脚本 |
| `code/TradingAgents-astock/hermes_backup/` | Hermes 完整备份（95个skill） |
| `~/文档/游资/connect.cfg` | 通达信 TCP 服务器列表 |

---

## 二、用户是谁

- **身份**：A股个人投资者，缠论+盛京剑客价值投资深入研究
- **风格**：系统化、数据驱动、要求精确
- **偏好**：中文交流，喜欢体系化思考，不接受模糊/大概的结论
- **持仓**：4只（荣信文化301231 成本34.62、和仁科技300550 成本14.63、华丽家族600503 成本2.82、金麒麟603586 成本17.63）
- **禁忌**：不能买688科创板、不能推荐ST、不能说"可能""也许"

---

## 三、数据库

### astock_data.db

```
引擎: SQLite 3.x, 766MB
表:   daily_klines(code, date, open, high, low, close, volume, amount)
      stocks(code, name, market, added_at)
      feat(code, date, close, ..., chg, vr_5, vr_20, ma20_pct, pos_20d, ret1..ret10)
      
总行数: 3,975,282
股票数: 4,973只（有日线数据）
数据范围: 2023-01-03 ~ 2026-06-08
索引: idx_daily_code, idx_daily_date, idx_feat_search
```

**⚠️ 关键坑**：`cursor.fetchall()` 的字段顺序 — `close` 在索引6，`volume` 在索引7（不是反过来）。

### feat 表（核心特征表）

由 `build_feat_table.py` 重建，一次SQL算完所有特征：

```sql
-- 40+列，包括：
chg, amp, vr_5, vr_20,             -- 当日特征
ma5, ma10, ma20, ma60,              -- 均线
ma20_pct, ma60_pct,                 -- 均线偏离度
pos_20d, pos_60d,                   -- 位置（0=最低，100=最高）
down_days, up_days,                 -- 连跌/连涨天数
ret1, ret3, ret5, ret10             -- 未来N日收益（用于回测）
```

重建耗时约3.5分钟。每次扫描前执行。

---

## 四、策略体系（已验证）

### 🏆 主力策略：S3 超跌反弹

**核心逻辑**：深跌(MA20偏离<-8%) + 放量中阳线(chg 3-7%, vr 1.2-2.5)

| 指标 | 优化版值 | 说明 |
|:----|:--------:|:-----|
| 信号数 | 4,036/3年 | 日均5.5只 |
| 胜率 | **71.1%** | 历史验证 |
| 单次收益 | +5.22% | T+5持有 |
| 买卖节奏 | 收盘确认→次日开盘买→T+5卖 | 不追收盘价 |

**文件**：`s3_scanner.py` — 每日扫描脚本

**参数**：
```sql
WHERE pos_20d < 20          -- 20日低位
  AND chg >= 3 AND chg < 7   -- 涨3-7%（优化：上限7%不是8%）
  AND vr_5 >= 1.2 AND vr_5 < 2.5  -- 温和放量
  AND ma20_pct < -8          -- ★核心：深偏离MA20
  AND code NOT LIKE '688%'   -- 排除科创板
  AND name NOT LIKE '%ST%'   -- 排除ST
```

**评分系统**（6分满分）：
- 实体<60% → +2（温和放量）
- vr_5<2.0 → +1（不过分放量）
- pos_20d<15 → +1（位置够低）
- ma20_pct<-8 → +1（深跌）
- chg<6 → +1（不是涨停）
- 连跌≥3天 → +1（超跌企稳）

### 📊 辅助工具

| 工具 | 用途 | 位置 |
|:----|:----|:----|
| `three-crows-screening` skill | 通达信三阴选股 | skill目录 |
| `youzi-screening` skill | 游资3策略（强势/低吸/反包） | skill目录 |
| `multi_dimension_scan.py` | 8维度全市场扫描 | 项目目录 |
| `chanlun_screener.py` | 缠论4策略（底分型/背驰/三买/逆驰） | skill目录 |
| `strategy_lab.py` | 策略参数搜索 | 项目目录 |
| `strategy_engine.py` | 回测引擎 | 项目目录 |

### ❌ 已证伪的策略

- **尾盘选股(S1-S4)** — 胜率47%，随机水平
- **close_scanner.py** — 已删除
- **search_close_strategy.py** — 已删除
- **capital_simulation.py** — 回测引擎不成熟，已删除

---

## 五、Archives/备份

### hermes_backup/（项目目录内）

每周执行 `hermes_backup.sh` 生成。目录结构：

```
hermes_backup/
├── skills/          # 95个 Hermes skill（完整备份）
├── config/          # config.yaml
├── cron/            # cronjob 列表
├── scripts/         # 自定义脚本（9个）
├── memory/          # 记忆文件（不含session DB）
├── RESTORE.md       # 恢复手册（人看）
└── README.md        # 备份说明
```

**恢复命令：**
```bash
cp -r hermes_backup/skills/* ~/.hermes/skills/
cp hermes_backup/config/config.yaml ~/.hermes/
```

### GitHub

远程仓库：`git@github.com:harrymiya/TradingAgents-astock.git`
（SSH方式，需要先添加 SSH key）

---

## 六、cronjob 时间表

```
时间        | 任务                          | 脚本
-----------|-------------------------------|---------------------
工作日 09:00 | 全市场每日扫描                  | market_scan.py
工作日 15:05 | 收盘日线同步（mootdx TCP）       | sync_close.py
工作日 16:00 | 收盘同步 + 多维度扫描            | sync_fast.py
工作日 16:30 | 持仓监控日报                    | portfolio_monitor.py
工作日 16:30 | ★ S3超跌反弹扫描                | build_feat_table.py → s3_scanner.py
每周一 15:30 | A股数据库备份                   | backup_astock_db.py
```

---

## 七、已知问题和坑

### API Keys
- **DeepSeek**: 在 `/etc/profile` 中，cronjob 前需要 `source /etc/profile`
- **GitHub**: SSH key 在 `~/.ssh/id_ed25519`，需要添加到 GitHub 账号

### mootdx TCP
- 最快服务器：`202.108.253.139:80`（22ms）
- 连接配置在 `~/文档/游资/connect.cfg`
- 全市场日线同步约5分钟
- 无法获取北交所（920开头）数据

### SQLite
- 不支持并发写入 — 同步脚本和扫描脚本不能同时跑
- 766MB 完全够用，不需要换 PostgreSQL
- 重建 feat 表耗时 3.5 分钟

### 策略
- S3 的 ret1/ret3/ret5 在最新一天为 NULL（因为那是未来数据）
- S3 不是每天都有信号 — 约1/3交易日信号≤3只
- 持仓4只全部买在高点（比历史S3信号日高16-30%），这是用户未来要避免的

---

## 八、给你的指令

当你被唤醒时：

1. **先读这个文件** — 你现在正在读，做得好
2. **加载 s3-rebound-scanner skill** — `skill_view(name='s3-rebound-scanner')`
3. **查用户持仓** — 4只股票的最新状态
4. **查今日S3信号** — 如果有最新数据就扫，没有就等cronjob
5. **做每周备份** — 如果是周一或用户要求
6. **回答用户问题** — 先分析再回答，给出具体数字和结论，不说模糊的话
