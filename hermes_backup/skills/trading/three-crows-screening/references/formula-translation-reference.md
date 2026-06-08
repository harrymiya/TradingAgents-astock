# 通达信三阴选股公式 逐行翻译参考

## 原公式

```
去ST原:=IF(NAMELIKE('ST'),0,1);
去星原:=IF(NAMELIKE('*ST'),0,1);
去新三板原:=NOT(CODELIKE('4'));
去北交所原:=NOT(CODELIKE('83'));
去北交所1原:=NOT(CODELIKE('87'));
去科创板原:=NOT(CODELIKE('688'));
去除次新股:=FINANCE(42)>180;
去票原:= 去ST原 AND 去星原 AND 去新三板原 AND 去北交所原 AND 去北交所1原 AND 去科创板原 AND 去除次新股;
跳空加跌停:=NOT(COUNT(H<REF(L, 1), 4) > 0 AND COUNT(C/REF(C, 1) <= 0.9, 3) >= 1);
XG:去票原 AND 跳空加跌停 AND
REF((REF(C,1)*1.1-C)<0.01,3)
AND REF(AMO,2)>REF(AMO,3)
AND REF(AMO,1)<REF(AMO,2)
AND REF(AMO,0)<REF(AMO,1)
AND C>REF(O,3)
AND OPEN>REF(LOW,3)
AND (CLOSE-REF(CLOSE,1))/REF(CLOSE,1)<0;
```

## REF(N) 周期对照

通达信中，REF(X, N) = 前第N个周期的X值（N=0表示当前周期）。

假设 T = 今天（最后一天）：

| 通达信符号 | Python索引 | 数据 |
|-----------|-----------|------|
| C | close[-1] | 今天收盘 |
| OPEN | open[-1] | 今天开盘 |
| REF(C,1) | close[-2] | 昨天收盘 |
| REF(AMO,2) | amo[-3] | T-2成交额 |
| REF(AMO,3) | amo[-4] | T-3成交额 |
| REF(O,3) | open[-4] | T-3开盘 |
| REF(LOW,3) | low[-4] | T-3最低 |
| REF(AMO,0) | amo[-1] | 今天成交额 |
| REF(AMO,1) | amo[-2] | 昨天成交额 |

## 逐行翻译

### 1. 排除规则

```python
# 通达信中通过 NAMELIKE/CODELIKE/FINANCE 函数实现
# Python中通过 is_valid_ticker(code, name) 实现
def is_valid_ticker(code, name=""):
    if code.startswith('4'): return False           # 新三板
    if code.startswith('83') or code.startswith('87'): return False  # 北交所
    if code.startswith('688'): return False         # 科创板
    if 'ST' in name or '*ST' in name: return False  # ST
    return True  # FINANCE(42)>180 即上市天数>180天，在数据中通过确保数据跨度>180天处理
```

### 2. 跳空加跌停

```python
# 原公式：跳空加跌停:=NOT(COUNT(H<REF(L,1),4)>0 AND COUNT(C/REF(C,1)<=0.9,3)>=1)
#
# 正确理解（两个COUNT各自独立统计，分别出结果后再AND）:
jump_days = 0
for i in range(4):  # T-3, T-2, T-1, T 共4天
    if high[t-i] < low[t-i-1]:
        jump_days += 1    # 统计跳空低开天数

down_days = 0
for i in range(3):  # T-2, T-1, T 共3天
    if close[t-i] / close[t-i-1] <= 0.9:  # 跌停（跌停价=round(c_prev*0.9,2)）
        down_days += 1    # 统计跌停天数

cond_no_jump = not (jump_days > 0 and down_days >= 1)  # 只有跳空>0天 且 跌停>=1天时才排除

# 错误写法（曾经犯过的Bug）：
# for i in range(1,5):
#     if high[-i] < low[-(i+1)] and close[-i]/close[-(i+1)] <= 0.9:   ← 同一天同时满足才计，这是错的
#         cond_no_jump = False
```

### 3. T-3接近涨停

```python
# 原公式：REF((REF(C,1)*1.1-C)<0.01, 3)
#
# 3天前(T-3位置)，条件：(REF(C,1) at T-3) * 1.1 - (C at T-3) < 0.01
# REF(C,1) at T-3 = close[T-4]
# C at T-3 = close[T-3]
limit_price = round(c4 * 1.1, 2)  # 涨停价精确到分
cond_zhangting = (limit_price - c3) < 0.01

# 注意：
# - 涨停价必须 round(c4*1.1, 2) 精确到分
# - 条件 <0.01 而非 <0.001 或 ==0 —— 通达信的浮点精度
# - c3的涨幅不一定要满10%，比如c4=31.08，c3=37.30，涨幅20%也符合条件
```

### 4. 量能递减

```python
# REF(AMO,2) > REF(AMO,3)  →  amo[T-2] > amo[T-3]
# REF(AMO,1) < REF(AMO,2)  →  amo[T-1] < amo[T-2]
# REF(AMO,0) < REF(AMO,1)  →  amo[T]   < amo[T-1]
cond_vol1 = a2 > a3  # 第2条阴线放量（相对于第1条阴线即涨停日的量）
cond_vol2 = a1 < a2  # 第3条阴线缩量
cond_vol3 = a0 < a1  # 今天继续缩量
```

### 5. C > REF(O, 3)

```python
# 今天收盘价 > T-3开盘价
cond_c_gt_o3 = c0 > o3
```

### 6. OPEN > REF(LOW, 3)

```python
# 今天开盘价 > T-3最低价
cond_o_gt_l3 = o0 > l3
```

### 7. 今天收阴

```python
# (CLOSE-REF(CLOSE,1))/REF(CLOSE,1) < 0
# 即 (今天收盘 - 昨天收盘) / 昨天收盘 < 0
cond_yin = ((c0 - c1) / c1) < 0  # 注意c1不能为0
```

## 数据源说明

`get_stock_data()` 返回的DataFrame列名为：`Date, Open, High, Low, Close, Volume`
- 没有 `Amount` 列
- 需要手动估算 AMO（成交额）= `Volume * 100 * (Open + Close) / 2`
- Volume 单位=手(1手=100股)，Open/Close单位=元/股，所以乘100得股数再乘均价得成交额
