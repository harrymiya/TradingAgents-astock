# 网格搜索方法论 — 如何持续迭代找到更高胜率策略

## 核心流程

```
设计假设 → 参数空间 → 快速回测 → 评估排序 → 最优组合 → 全量验证 → 实盘
    ↑                                                      |
    └────────────────── 再次迭代 ←─────────────────────────┘
```

## 参数空间设计

### 3个核心因子（必选）
| 因子 | 字段名 | 典型范围 | 说明 |
|:----|:------|:---------|:-----|
| 距20日线 | `pos` | -35%~+20% | 超跌(-25~-15) / 均线附近(-5~5) / 高位(10~20) |
| 当日涨跌幅 | `chg` | -7%~+9% | 大跌(-5~-3) / 小涨(1~3) / 大涨(5~7) |
| 量比 | `vr` | 0.3~4.0倍 | 缩量(0.3~0.7) / 均量(0.8~1.2) / 放量(1.2~2.5) |

### 可选因子（按需增加）
| 因子 | 字段名 | 说明 |
|:----|:------|:-----|
| 连跌天数 | `consecutive_down` | 连跌N天后企稳 |
| 连涨天数 | `consecutive_up` | 连涨后回调 |
| 距60日线 | `pos_ma60` | 中长期位置 |
| 10日波动率 | `vol` | 低波动vs高波动 |
| 昨日涨跌幅 | `prev_chg1` | 逆势/顺势 |
| 收盘位置 | `close_pos` | 在当日K线中的位置% |

## 搜索策略

### 第1轮：粗搜（确定大致范围）
- 因子各取6-8个区间 → 最多8×8×8=512组合
- 样本: 100-200只股票
- 时间: 2023-01 ~ 2026-06（全周期）
- 目标: 找到胜率+频率平衡区域

### 第2轮：精搜（在最佳区域加密）
- 在第1轮TOP5附近加密3-5个区间
- 样本: 500只股票
- 目标: 精确找到最优参数

### 第3轮：跨周期验证（防过拟合）
- 用2023年数据训练，2024年验证
- 胜率差异<5%才算稳定

## 评分公式

```
综合得分 = 胜率 × 0.35 + 均收益×5 × 0.35 + 频率得分 × 0.30

其中 频率得分 = min(日均信号数 / 10, 1) × 50
```

这个公式平衡了胜率、收益和频率三个维度。

## 不可能三角验证

每次搜索找到最优组合后，必须检查：

| 维度 | 评价 | 标准 |
|:----|:----|:-----|
| 胜率 | 高/中/低 | >75%高, 55-75%中, <55%低 |
| 盈亏比 | 高/中/低 | >3高, 1.5-3中, <1.5低 |
| 日均信号 | 高/中/低 | >10高, 2-10中, <2低 |

如果三项中有两项高，说明这个组合突破了不可能三角——深入验证。
如果只有一项高，是正常分布——接受并与其他策略互补使用。

## 快速回测代码（迭代用）

```python
# 最小化回测模板
def quick_test(stocks, pos_r, chg_r, vr_r, hold=3):
    signals = []
    for code, bars in stocks.items():
        for i in range(21, len(bars)-hold-1):
            close = bars[i][1]; vol = bars[i][2]; prev = bars[i-1][1]
            if prev <= 0: continue
            chg = (close-prev)/prev*100
            v20 = statistics.mean([bars[j][2] for j in range(i-20,i) if bars[j][2]>0] or [1])
            vr = vol/v20 if v20>0 else 0
            ma20 = statistics.mean([bars[j][1] for j in range(i-19,i+1) if bars[j][1]>0] or [1])
            pos = (close-ma20)/ma20*100 if ma20>0 else 0
            
            if pos_r[0]<=pos<pos_r[1] and chg_r[0]<=chg<chg_r[1] and vr_r[0]<=vr<vr_r[1]:
                ret = (bars[i+hold][1]-close)/close*100
                signals.append(ret)
    return signals  # 用len(signals), wr, avg判断好坏
```

## 注意点
1. 样本量 < 30的信号数不可信
2. 全量验证必须用 feat 表（3,970,309行×4,973只），不能用200只样本外推
3. Python逐只遍历（strategy_lab.py原方法）有严重样本偏差 — 200只样本的91.8%胜率在全量下只有58.8%
4. 行情周期性变化——2023与2024的分布不同，跨年验证很重要

## feat 表方法（推荐，取代逐只遍历）

从 v2.0.0 起，策略验证采用 **feat 表预计算 + Python 内存搜索** 取代旧的 `strategy_lab.py` 逐只遍历：

```bash
# 1. 重建 feat 表（数据同步后需要）
python3 build_feat_table.py
# → 3,970,309 行, ~206秒

# 2. 搜索策略参数
python3 search_close_strategy.py
# → 全量搜索 S1/S2/S4/S3 所有组合, ~207秒

# 3. 手动查询任意条件
python3 -c "
import sqlite3, os
DB = os.path.expanduser('~/.hermes/astock_data.db')
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('''
    SELECT COUNT(*), AVG(ret1), 
           SUM(CASE WHEN ret1>0 THEN 1.0 ELSE 0 END)/CAST(COUNT(*) AS REAL)*100,
           AVG(ret3), SUM(CASE WHEN ret3>0 THEN 1.0 ELSE 0 END)/CAST(COUNT(*) AS REAL)*100
    FROM feat WHERE pos_20d < 20 AND chg BETWEEN 4 AND 8 AND vr_5 BETWEEN 1.2 AND 3
''')
print(f'信号: {r[0]:,} | 1d胜率: {r[2]:.1f}% | 1d收益: {r[1]:+.2f}% | 3d胜率: {r[4]:.1f}%')
```

