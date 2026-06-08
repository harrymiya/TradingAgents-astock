# 盘中实时数据获取 & 数据完整性检查

## 盘中实时数据

使用 `tradingagents/dataflows/live_data.py`：

```python
from tradingagents.dataflows.live_data import get_data_for_analysis, format_analysis_text

# 统一接入：DB历史 + 腾讯当天实时行情（盘中推荐）
data = get_data_for_analysis("301231", "荣信文化")

# data['daily_klines'] — 合并后日线 [{date, open, high, low, close, volume, amount}]
# data['today_info'] — 盘中实时行情
#     {price, open, high, low, volume, pre_close, change, change_pct,
#      amount, turnover(%), pe, amplitude(%)}
# data['today_kline'] — 今天日K线（如果日线API有）
# data['minute_data'] — 分时明细（可能为None，接口不稳定）

# 合成分析示例
ti = data['today_info']
dk = data['daily_klines']
cur = ti['price']
closes = [k['close'] for k in dk]
ma5 = sum(closes[-5:]) / 5
ma20 = sum(closes[-20:]) / 20
print(f"当前{cur:.2f} vs MA5({ma5:.2f})偏离{abs(cur-ma5)/ma5*100:.1f}%")
print(f"换手率{ti.get('turnover',0):.2f}% 振幅{ti.get('amplitude',0):.2f}%")

# 格式化输出
print(format_analysis_text(data))
```

**原则：盘中分时数据不入库**。只临时获取。收盘后cronjob统一写入DB。

## 腾讯API实时行情字段（qt.gtimg.cn）

```
GET http://qt.gtimg.cn/q=sz301231  # 深圳用sz, 上海用sh
返回: v_sz301231="51~荣信文化~301231~35.06~33.81~32.66~122024~...~..."
                                                           ↑当前价 ↑昨收 ↑今开 ↑量(手)
split("~") 后索引:
  [1] 股票名  [3] 当前价  [4] 昨收  [5] 今开
  [6] 成交量(手)  [31] 涨跌额  [32] 涨跌幅%
  [33] 最高 [34] 最低 [37] 成交额 [38] 换手率% [39] PE [43] 振幅%
```

### ⚠️ 腾讯分钟/分时API已失效（2026.06.08确认）
- `web.ifzq.gtimg.cn/appstock/app/kline/mkline` → 302→web3解析不了
- `web.ifzq.gtimg.cn/appstock/app/minute/query` → `Can't load controller`
- 替代方案：使用 `qt.gtimg.cn` 实时行情接口获取盘中数据

## 腾讯API日K线接口

```
GET https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,800,qfq
返回嵌套结构:
  data.{prefix}{code}.qfqday = [[date, open, close, high, low, volume], ...]
  注意: close在第1列(索引1), high在第2列(索引2)!
  有时没有"data"外层或key为"day"而非"qfqday" — 需递归查找
```

## 数据完整性检查

任何全市场批量操作前执行：

```python
from tradingagents.dataflows.data_integrity import ensure_data
report = ensure_data()  # 自动检查+补全缺失股票
# report.is_complete: bool
# report.missing_stocks: [(code, name)]
```

脚本位置：`tradingagents/dataflows/data_integrity.py`

检查内容：
- DB最新交易日
- 各股票最新日是否为目标日
- 记录数是否>30条
- 自动从腾讯HTTP补缺失数据
