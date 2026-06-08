# Amount（成交额）缺失的处理方案

## 问题

通达信三阴选股公式使用了 `AMO`（成交额）进行量能比较：

```
REF(AMO,2) > REF(AMO,3)   → T-2放量 > T-3
REF(AMO,1) < REF(AMO,2)   → T-1缩量 < T-2
REF(AMO,0) < REF(AMO,1)   → T续缩量 < T-1
```

但新浪 HTTP 接口返回的 CSV **没有 Amount 列**（只有 Date, Open, High, Low, Close, Volume）。

## 估算方案

```python
# Volume 是手数（1手=100股）
# (Open + Close) / 2 估算当日成交均价
amount = volume * 100 * (open_price + close_price) / 2
```

## 在哪里处理

| 位置 | 方案 | 状态 |
|------|------|------|
| sync_to_db.py | 写入数据库前估算 | ✅ 已修复 |
| screen_from_db.py | 读库检测到Amount全0时估算 | ✅ 已修复 |
| single_stock.py | 读库检测到Amount全0时估算 | ✅ 已修复 |
| three_crows.py (核心算法) | 检测Amount列是否存在，不存在时用Volume估算 | ✅ 已实现 |

## 为什么不在数据库模块统一处理

astock_db.get_klines() 只返回原始数据，不修改。由各消费端根据自身需求处理。
这才是正确做法——数据库不该知道业务公式的细节。
