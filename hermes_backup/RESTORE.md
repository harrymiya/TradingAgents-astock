# Hermes 恢复手册（人看版）

> 2026-06-09 最后更新
> 
> 如果你需要在另一台机器上重建 Hermes + TradingAgents-Astock 全套环境，按下面步骤来。

---

## 一、先知道有什么

这套系统 = 3层：

```
Hermes Agent（大脑） → TradingAgents-Astock（数据引擎） → SQLite 数据库（记忆）
     │                       │
     └── 95个 skill          └── 策略脚本（s3_scanner.py 等）
```

**重要文件位置：**

| 文件 | 位置 | 大小 |
|:----|:----|:----|
| **Hermes 备份** | `code/TradingAgents-astock/hermes_backup/` | 17MB（不含A股DB） |
| **A股数据库** | `~/.hermes/astock_data.db` | 766MB（可选，可重建） |
| **日线同步脚本** | `~/.hermes/scripts/sync_close.py` | mootdx TCP，5分钟同步全市场 |
| **特征表引擎** | `code/TradingAgents-astock/build_feat_table.py` | 3.5分钟重建 |
| **S3扫描器** | `code/TradingAgents-astock/s3_scanner.py` | 每日16:30自动跑 |
| **恢复脚本** | `code/TradingAgents-astock/hermes_backup.sh` | 每周备份用 |

---

## 二、从零恢复（15分钟）

### 第1步：安装 Hermes Agent

```bash
# 安装 Hermes（参考 hermes-agent skill 的官方文档）
pip install hermes-agent
hermes setup
# 配置：模型用 deepseek/deepseek-chat，开放所有 tools
```

### 第2步：恢复 skills + config

```bash
# 从项目备份恢复
git clone https://github.com/harrymiya/TradingAgents-astock.git
cd TradingAgents-astock

# 恢复 Hermes skills
cp -r hermes_backup/skills/* ~/.hermes/skills/

# 恢复配置
cp hermes_backup/config/config.yaml ~/.hermes/
cp hermes_backup/config/.env ~/.hermes/  # 如果有的话

# 恢复脚本
cp -r hermes_backup/scripts/* ~/.hermes/scripts/
```

### 第3步：配置 API Key

```bash
# DeepSeek API Key（必须）
export DEEPSEEK_API_KEY="sk-..."
# 建议写到 /etc/profile 或 ~/.bashrc
```

### 第4步：搭建 TradingAgents-Astock 环境

```bash
cd TradingAgents-astock
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 第5步：恢复 A股数据库（二选一）

**选项A：拷贝已有DB（快，但需要766MB文件）**
```bash
# 从旧机器拷贝 ~/.hermes/astock_data.db 到新机器的 ~/.hermes/
```

**选项B：从零重建（慢，但不需要拷贝）**
```bash
cd TradingAgents-astock
source .venv/bin/activate
python3 sync_history_all.py  # 全量拉取3.5年历史数据，约86分钟
```

### 第6步：重建特征表

```bash
python3 build_feat_table.py  # 3.5分钟
```

### 第7步：配置 cronjob

用 Hermes CLI 或如下 crontab：

```bash
# 收盘数据同步（交易日15:05）
5 15 * * 1-5 cd TradingAgents-astock && source .venv/bin/activate && python3 ~/.hermes/scripts/sync_close.py

# S3扫描（交易日16:30）
30 16 * * 1-5 cd TradingAgents-astock && source .venv/bin/activate && python3 build_feat_table.py && python3 s3_scanner.py

# 持仓监控（交易日8:30和16:30）
30 8,16 * * 1-5 cd TradingAgents-astock && source .venv/bin/activate && python3 ~/.hermes/scripts/portfolio_monitor.py
```

当然更简单的方式是用 Hermes 的 cronjob 命令配。

---

## 三、日常使用

### 每天16:30 你会收到

```
📡 S3超跌反弹 — 2026-06-08

市场状态: 极弱 (全市场均-2.92%)
信号总数: 10只

🔥 精选排行
  1 通源石油  +4.7%  评分6
  2 上海沿浦  +3.9%  评分6
  ...
```

**收到后做什么：**
1. 看信号数 — 3-15只正常，<3只说明今日市场不适合做
2. 选TOP3-5只 — 评分高的优先
3. 明天09:25开盘买入（集合竞价）
4. 持有5个交易日 → 自动卖出

### 每周备份

```bash
cd TradingAgents-astock
bash hermes_backup.sh
git add -A && git commit -m "weekly backup" && git push
```

---

## 四、工具清单

| 做什么 | 用哪个 | 怎么跑 |
|:------|:------|:-------|
| 每天扫S3信号 | `s3_scanner.py` | cronjob 16:30自动 |
| 扫三阴选股 | `three-crows-screening` skill | cronjob 16:00自动 |
| 查持仓状态 | `portfolio_monitor.py` | cronjob 8:30/16:30自动 |
| 全市场多维度 | `multi_dimension_scan.py` | 手动跑 |
| 游资+缠论联合 | `chanlun_and_youzi.py` | 手动跑 |
| 测新策略参数 | `strategy_lab.py` | 手动跑 |
| 验证策略 | `strategy_engine.py --backtest` | 手动跑 |
| 备份Hermes | `hermes_backup.sh` | 每周手动or cron |

---

## 五、注意事项

1. **DeepSeek API Key 在 /etc/profile** — 每次cronjob前需要 source
2. **mootdx TCP 连接** — 要用 connect.cfg 里的通达信服务器（在 `~/文档/游资/connect.cfg`）
3. **SQLite 不要同时写** — 同步脚本和扫描脚本不要同时跑
4. **尾盘策略已证明随机水平** — close_scanner.py 已删除，不要重新实现
5. **备份到 GitHub 需要 SSH key** — 如果 push 失败，重新加一次 key 到 GitHub
