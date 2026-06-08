# 新浪财经 HTTP API 已知问题

## 1. Amount（成交额）列缺失

`get_stock_data()` （来自 `tradingagents.dataflows.a_stock`）底层走新浪 HTTP 接口。新浪返回的 CSV **只有6列**：

```
Date, Open, High, Low, Close, Volume
```

**没有 Amount 列。**

### 影响

- SQLite `daily_klines.amount` 字段会存为 0
- 所有需要成交额（AMO）的分析（如三阴选股的放量/缩量比较）会得出错误结论
- 下游分析脚本如果检测到 `Amount` 列全为 0 可以回退估算，但最佳方案是在同步时直接估算

### 修复方案

在 `sync_to_db.py` 中，写入数据库之前估算成交额：

```python
# Volume 是手数（1手=100股），(Open+Close)/2 估算成交均价
amount = volume * 100 * (open_price + close_price) / 2
```

已经在 `sync_to_db.py` 中实现。如果将来切换到其他数据源（如腾讯、东财 push2），需要确认它们是否返回 Amount 列。

## 2. mootdx TCP 连接不可用

mootdx 的行情服务器（223.80.188.186:7709）在公司网络下无法连接：

```
OSError: [Errno 113] No route to host
```

所有数据回退到 HTTP 接口。

## 3. 股票列表去重

新浪全市场股票列表接口返回约 5500+ 只股票，代码格式为 6 位数字。但存在少量重复（不同的市场标记对应同一代码）。`save_stock_list` 使用 `INSERT OR IGNORE` 自动去重。

## 4. 接口限速

新浪 HTTP 接口没有明确的限速文档，但实测连续大量请求（每只 ~0.5-2秒）不会触发封禁。全量 4685 只的同步需约 1-2 小时。
