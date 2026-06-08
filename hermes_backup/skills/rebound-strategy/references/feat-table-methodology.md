# feat 表预计算方法论 — 全量回测的新标准

## 为什么需要 feat 表？

之前的方法（`strategy_lab.py` 和 `rebound_scanner.py`）是 **Python逐只遍历**：
- 200只股票 × 800天 × 每只跑N次计算 = 重复计算8000万次
- 仅基于200只股票 → 样本偏差导致胜率**严重高估**（91.8% → 实际58.8%）
- 慢：一轮搜索需要几分钟

feat 表方法改用 **SQL窗口函数一次性计算所有特征**：

```
SQLite 窗口函数 → 3,970,309行特征（chg/vr/ma/pos/ret1..ret10）
                  ↓ 耗时 206 秒
         feat 表（索引: code, date, chg）
                  ↓
    Python内存搜索（一次拉取候选行，循环过滤）
                  ↓ 耗时 8+12 秒
         所有参数组合的胜率/频率/收益
```

## 架构

```mermaid
flowchart LR
    A[daily_klines] --> B[feat 表]
    B --> C[快速SQL: 拉候选]
    C --> D[Python内存过滤]
    D --> E[所有参数组合结果]
```

## feat 表列（共22列）

**价格特征**:
- `chg` — 当日较昨收涨跌幅(%)
- `amp` — 振幅(%)
- `vr_5` — 量比(vs 5日均量)
- `vr_20` — 量比(vs 20日均量)

**均线**:
- `ma5, ma10, ma20, ma60` — 移动平均
- `ma20_pct, ma60_pct` — 均线偏离度(%)

**位置**:
- `pos_20d` — 20日位置(0~100, 100=最高点)
- `pos_60d` — 60日位置(0~100)

**形态**:
- `down_days` — 连跌天数(1~4)
- `up_days` — 连涨天数(1~4)

**未来收益(回测用)**:
- `ret1` — 次日收益(%)
- `ret2` — 第2日收益(%)
- `ret3` — 第3日收益(%)
- `ret5` — 第5日收益(%)
- `ret10` — 第10日收益(%)

## 关键发现

### 样本偏差的严重性

| 策略 | 200只样本 | 4,973只全量 | 偏差 |
|:----|:---------:|:----------:|:----:|
| S3超跌反弹 | 91.8% | **58.8%** | +33% |
| S1连跌企稳 | 63% | **42.9%** | +20% |
| S2放量突破 | 71% | **47.0%** | +24% |

**教训**: 200只股票的样本结果不可信。必须用全量数据验证。feat 表使全量搜索成为可能（206秒建表+8秒搜索）。

### 只有超跌反弹有alpha

全量验证结论：尾盘策略（S1/S2/S4）1d胜率42.9-47.0%，接近随机水平。
只有超跌反弹S3（位0-20|涨4-8|量1.2-3）的1d胜率58.8%且收益+1.13%具有统计学意义。

## 用法

```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate

# 1. 构建/重建 feat 表（每次数据更新后需要重建）
python3 build_feat_table.py
# → 耗时 ~3.7 分钟，3,970,309 行

# 2. 搜索策略参数
python3 search_close_strategy.py
# → 耗时 ~4 分钟，搜索所有策略的60组合

# 3. 手动查询任意条件
python3 -c "
import sqlite3, os
DB = os.path.expanduser('~/.hermes/astock_data.db')
conn = sqlite3.connect(DB)
cur = conn.cursor()
# 查询任意组合的胜率
cur.execute('''
    SELECT COUNT(*), AVG(ret1), 
           SUM(CASE WHEN ret1>0 THEN 1.0 ELSE 0 END)/CAST(COUNT(*) AS REAL)*100
    FROM feat WHERE pos_20d < 20 AND chg BETWEEN 4 AND 8 AND vr_5 BETWEEN 1.2 AND 3
''')
print(cur.fetchone())
"
```

## SQL 技巧

### 窗口函数建特征（CTE + LAG/LEAD/AVG）

关键SQL模式：
```sql
WITH prices AS (
    SELECT code, date, close,
        LAG(close, 1) OVER w AS prev_close_1,
        LEAD(close, 1) OVER w AS lead_close_1
    FROM daily_klines
    WINDOW w AS (PARTITION BY code ORDER BY date)
),
base AS (
    SELECT 
        d.code, d.date, d.close,
        ROUND(CASE WHEN p.prev_close_1 > 0 
            THEN (d.close - p.prev_close_1) / p.prev_close_1 * 100 
            ELSE NULL END, 2) AS chg,
        ROUND((lead_close_1 - d.close) / d.close * 100, 2) AS ret1
    FROM daily_klines d
    JOIN prices p ON d.code = p.code AND d.date = p.date
)
SELECT * FROM base
```

### Python内存过滤（替代SQL逐条查询）

```python
# 一次拉取所有候选行
rows = fetch_candidates(cur, "chg IS NOT NULL AND ret1 IS NOT NULL")

# 在内存中循环过滤
for combo in product(*param_lists):
    matched = [r for r in rows if all(p(r) for p in predicates)]
    if len(matched) < 30: continue
    # 算胜率...
```

比SQL逐条查询快20倍（77秒 vs 160+秒），因为避免了400万行表的多次扫描。

## ⚠️ 资金回测陷阱

不要在feat表上直接做"每日买入N只/次日收盘卖出"的逐日资金模拟。这个场景会掉入以下陷阱：

### 陷阱1：收盘价买入追高

S3信号当日平均涨+4.16%（开盘→收盘），平均振幅7.91%。你在收盘价买入相当于追在当日高点上，次日的+0.85%收益不足以Cover：

- S3信号当日：开盘→收盘涨+4.16%
- 次日收益：+0.85%（扣除0.3%交易成本后+0.55%）
- 净效果：T日收盘买 → T+1收盘卖，期望收益仅+0.55%

**正确做法**: 发现信号后在盘中稍低位买入（当日涨幅3-4%时），不要追到收盘。

### 陷阱2：固定每日满仓

每天买3只、每天卖3只的固定节奏不适合S3。因为：
- 33%的交易日信号≤3只（无法满仓）
- 信号稀疏日子的胜率只有46%（不如随机）
- 被迫满仓会把期望收益拉成负

**正确做法**: 信号数量决定仓位。信号≥10/日才正常建仓。

### 陷阱3：选股偏差

全量9,412个信号你用不了这么多（每天只能买3-5只）。按chg排序选"最好的"反而是最差的——当日涨最高的次日回调概率大。

**正确做法**: 用多因子排序（涨跌幅适中+量比温和+位置够低）而不是单因子排序。

### 陷阱4：忽略持有期

S3在T+1的+0.85%勉强为正，但持有到T+3就是+2.55%/次（60.8%胜率），T+10是+4.27%/次（62.5%胜率）。T+1的微薄alpha经过交易成本稀释后变为负值，但多周期收益是明确的。

**正确做法**: 回测前先用feat表做多周期收益分位数检验。如果T+1勉强正、T+3显著正、T+5比T+3更好，说明策略本身有alpha但需要一定时间演绎。

### 推荐的回测路径

1. **第一阶段**: feat表SQL查询 → 确认T+1/T+3/T+5/T+10都有正的胜率和收益
2. **第二阶段**: 按信号数量分层分析 → S3在信号多的日子表现是否更好？
3. **第三阶段**: 按市场状态分层 → 在强势/弱势/震荡中的表现一致性
4. **第四阶段**: 简化资金估算 → 用统计近似而非逐日模拟
5. **第五阶段**: 如果以上都通过了，再做严格的逐日资金模拟（含仓位管理、止损、择时）

## 文件路径

| 文件 | 路径 |
|:----|:-----|
| feat 表构建 | `/home/harrydolly/code/TradingAgents-astock/build_feat_table.py` |
| 策略搜索 | `/home/harrydolly/code/TradingAgents-astock/search_close_strategy.py` |
| feat 表 | `~/.hermes/astock_data.db` → feat 表（3,970,309行） |
