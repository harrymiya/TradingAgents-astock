"""
TradingAgents-Astock 分析入口
用法：
    source .venv/bin/activate
    export DEEPSEEK_API_KEY="你的key"
    python3 run.py <股票代码或名称> [日期]
"""
import sys
import os

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    stock = args[0]
    date = args[1] if len(args) > 1 else "2026-06-07"

    # 检查key
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        print("❌ DEEPSEEK_API_KEY 未设置")
        print("   请先运行: export DEEPSEEK_API_KEY=\"你的key\"")
        sys.exit(1)

    print(f"🚀 分析 {stock} 日期 {date}")
    print(f"   环境变量 DEEPSEEK_API_KEY: 已设置 (len={len(key)})")

    # 1. 缠论算法分析
    print("\n1️⃣ 缠论算法分析...")
    from tradingagents.dataflows.a_stock import get_stock_data
    from tradingagents.dataflows.chanlun import analyze_chanlun, klines_from_dataframe
    from io import StringIO
    import pandas as pd

    csv_str = get_stock_data(stock, "2026-01-01", date)
    df = pd.read_csv(StringIO(csv_str), comment='#')
    klines = klines_from_dataframe(df, date_col="Date",
        ohlc=("Open", "High", "Low", "Close", "Volume"))
    result = analyze_chanlun(klines, ticker=stock, trade_date=date)
    print(result.to_markdown_report())

    # 2. 基本面
    print("\n2️⃣ 基本面...")
    from tradingagents.dataflows.a_stock import get_fundamentals
    rv = get_fundamentals(stock, date)
    if isinstance(rv, str):
        for line in rv.split('\n')[:15]:
            if line and not line.startswith('#'):
                print(f"   {line}")

    # 3. 完整流水线（可选，想加速可以去掉）
    print("\n3️⃣ 多Agent分析 (market + chanlun)...")
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    g = TradingAgentsGraph(selected_analysts=['market', 'chanlun'])
    result = g.propagate(stock, date)

    for key in ['chanlun_report', 'market_report', 'final_trade_decision']:
        val = result.get(key, '')
        if val:
            print(f"\n--- {key} ---")
            print(str(val)[:600])

    print(f"\n✅ 分析完成")

if __name__ == "__main__":
    main()
