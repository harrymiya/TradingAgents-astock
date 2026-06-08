# mootdx 通达信TCP连接配置（从connect.cfg）

## 来源文件

```
~/文档/游资/connect.cfg
```
通达信客户端配置文件，GBK编码，用 `configparser` 解析。

## 可用服务器（实测）

从40个服务器中筛选出可达的（2026-06-08测试）：

| IP | 端口 | 延迟 | 权重 |
|:---|:---:|:----:|:---:|
| 202.108.253.139 | 80 | 22ms ⭐ | 60 |
| 202.108.253.158 | 80 | 23ms | 60 |
| 180.153.18.170 | 7709 | 42ms | 50 |
| 180.153.18.172 | 80 | 44ms | 50 |
| 115.238.56.198 | 7709 | 42ms | 50 |
| 60.191.117.167 | 7709 | 54ms | 50 |
| 218.75.126.9 | 7709 | 56ms | 50 |
| 115.238.90.165 | 7709 | 52ms | 50 |
| 60.12.136.250 | 7709 | 51ms | 50 |

默认使用 `202.108.253.139:80`（最快，22ms）。

## mootdx 初始化

```python
from mootdx.quotes import Quotes

# 使用指定服务器（不再依赖mootdx自带的auto-detect）
client = Quotes.factory(market='std', tcp=('202.108.253.139', 80, True))

# 获取日K线（frequency=9=日线, count=120=120条）
df = client.bars(symbol='301231', frequency=9, start=0, count=120)
# 返回DataFrame，字段: open, close, high, low, volume, amount, datetime

# 获取实时行情
quote = client.quotes(symbols=['301231', '000001'])
```

## 速度对比

| 指标 | 腾讯API | mootdx TCP |
|:----|:------:|:---------:|
| 单只耗时 | ~300ms | ~115ms |
| 全市场4685只 | ~30m | ~9m |
| 含当天数据 | 需解析嵌套JSON | 直接返回 |
| 实时行情 | 解析GBK文本 | 直接返回 |

## 降级策略

mootdx失败时自动降级到：
1. 腾讯日线API：`web.ifzq.gtimg.cn/appstock/app/fqkline/get`
2. 腾讯实时行情：`qt.gtimg.cn`
