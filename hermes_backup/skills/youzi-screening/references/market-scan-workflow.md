# 全市场建仓信号筛选参考

## 跨skill联合扫描

`youzi-screening` 的3个策略 + `three-crows-screening` 的4个缠论策略可以联合使用进行全市场建仓信号筛选。

## 工作流

### 第1层：数据库扫描（30秒全市场）

```python
from chanlun_screener import check_beichi, check_guanjian_kline, check_san_mai_v2, check_nichi
from youzi_screener import check_qiangshi, check_dixi, check_fanbao

# 遍历数据库中所有有效股票（约4685只）
# 综合评分 = 缠论分 + 游资分
# 建仓条件：至少2个不同策略体系命中且综合分≥3
```

### 第2层：实时行情验证

对第1层筛出的顶级标的，用腾讯API查实时行情，筛选：
- 低开高走翻红（低开>2%且已站上昨收）
- 日内收阳（价>开盘）
- 量能健康（0.5%<换手<8%）
- 日内低位（价在区间40%分位以下）

### 第3层：DeepSeek深度研报（可选）

采集信号+数据，调用DeepSeek生成投研报告。

## 输出分类

| 梯队 | 条件 | 示例 |
|------|------|------|
| 🔴 第一梯队 | 缠论+游资双确认 | 三买+逆驰6/8+强+低吸+反包 |
| 🟡 第二梯队 | 单体系多策略 | 底背驰+三买+逆驰（缠论3重）|

## 注意事项

- 688科创板沪股在腾讯中前缀为 `sh`（不是 `sz`）
- 腾讯API单次最多查约30只股票，批量用 `|` 分隔
- 东财push2his API可能返回 `Connection aborted`，备用新浪
- 数据库数据截止到上一交易日，盘中需结合实时行情判断
