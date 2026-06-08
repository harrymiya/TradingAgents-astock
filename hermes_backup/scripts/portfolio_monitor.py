#!/usr/bin/env python3
"""
持仓监控 — 荣信文化/和仁科技/华丽家族/金麒麟 每日出局/加仓信号
依赖: astock-daily-sync 先跑（数据同步到DB）
"""
import sys, os, json
sys.path.insert(0, '/home/harrydolly/code/TradingAgents-astock')
sys.path.insert(0, '/home/harrydolly/.hermes/skills/trading/three-crows-screening/scripts/')
sys.path.insert(0, '/home/harrydolly/.hermes/skills/youzi-screening/scripts/')

import requests
import pandas as pd
import numpy as np
from datetime import datetime
import sqlite3
import io

DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")

# ===== 持仓列表 =====
PORTFOLIO = [
    ('301231', '荣信文化', 34.62),
    ('300550', '和仁科技', 14.63),
    ('600503', '华丽家族', 2.82),
    ('603586', '金麒麟', 17.63),
]

# ===== 信号规则 =====
def check_exit(code, df, reasons_chanlun, reasons_youzi):
    """出局信号判断"""
    n = len(df)
    close = df['Close'].values
    high = df['High'].values
    low = df['Low'].values
    vol = df['Volume'].values
    cur = close[-1]
    
    ma20 = pd.Series(close).rolling(20).mean().values[-1]
    ma60 = pd.Series(close).rolling(60).mean().values[-1]
    ma5 = pd.Series(close).rolling(5).mean().values[-1]
    
    signals = []
    
    # 1. MACD死叉恶化
    ema_f = pd.Series(close).ewm(span=12).mean().values
    ema_s = pd.Series(close).ewm(span=26).mean().values
    dif = ema_f - ema_s
    dea = pd.Series(dif).ewm(span=9).mean().values
    macd = 2 * (dif - dea)
    
    if macd[-1] < 0 and macd[-1] < macd[-2] and macd[-2] < macd[-3]:
        signals.append('⚠️ MACD绿柱持续放大，空头加速')
    
    # 2. 跌破MA60
    if cur < ma60 * 0.98:
        signals.append(f'🔴 跌破MA60({ma60:.1f})，趋势破位')
    
    # 3. 放量大跌
    c2 = (cur / close[-2] - 1) * 100 if n > 1 else 0
    vol_ma20 = pd.Series(vol).rolling(20).mean().values[-1]
    if c2 < -5 and vol[-1] > vol_ma20 * 1.5:
        signals.append('🔴 放量大跌超5%')
    
    # 4. 连续3日收阴
    if n >= 4:
        if (close[-1] < close[-2] and close[-2] < close[-3] and close[-3] < close[-4]):
            signals.append('⚠️ 连续3日收阴')
    
    # 5. 缠论信号全部消失
    if not any(['底背驰' in str(r) or '三买' in str(r) or '逆驰' in str(r) for r in reasons_chanlun]):
        signals.append('⚠️ 缠论信号全部消失')
    
    return signals

def check_add(code, df, reasons_chanlun, reasons_youzi):
    """加仓信号判断"""
    n = len(df)
    close = df['Close'].values
    high = df['High'].values
    low = df['Low'].values
    vol = df['Volume'].values
    cur = close[-1]
    
    ma5 = pd.Series(close).rolling(5).mean().values[-1]
    ma20 = pd.Series(close).rolling(20).mean().values[-1]
    ma60 = pd.Series(close).rolling(60).mean().values[-1]
    
    signals = []
    
    # 1. 放量突破MA5
    c2 = (cur / close[-2] - 1) * 100 if n > 1 else 0
    vol_ma20 = pd.Series(vol).rolling(20).mean().values[-1]
    if cur > ma5 and vol[-1] > vol_ma20 * 1.3 and c2 > 2:
        signals.append('🟢 放量站上MA5')
    
    # 2. MACD金叉
    ema_f = pd.Series(close).ewm(span=12).mean().values
    ema_s = pd.Series(close).ewm(span=26).mean().values
    dif = ema_f - ema_s
    dea = pd.Series(dif).ewm(span=9).mean().values
    macd = 2 * (dif - dea)
    
    if macd[-1] > 0 and dif[-1] > dea[-1]:
        signals.append('🟢 MACD金叉')
    elif macd[-1] > macd[-2] and macd[-2] < macd[-3]:
        signals.append('🟢 MACD绿柱缩短，底背离中')
    
    # 3. 缩量回踩MA60企稳
    vol_ratio = vol[-1] / vol_ma20
    if cur > ma60 * 0.99 and vol_ratio < 0.6:
        signals.append('🟢 缩量回踩MA60企稳')
    
    return signals

# ===== 主逻辑 =====
def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f'📋 持仓监控报告 — {now}')
    print(f'{"="*70}')
    
    from chanlun_screener import check_beichi, check_guanjian_kline, check_san_mai_v2, check_nichi
    from youzi_screener import check_qiangshi, check_dixi, check_fanbao
    from chanlun_screener import read_klines, find_zones
    
    for code, name, buy_price in PORTFOLIO:
        print(f'\n--- {name}({code}) 买入价{buy_price:.2f} ---')
        
        # 从DB读K线
        df, end_date = read_klines(code, lookback_days=90)
        if df is None:
            print('  数据不足，跳过')
            continue
        
        n = len(df)
        cur = float(df['Close'].values[-1])
        c2 = (cur / float(df['Close'].values[-2]) - 1) * 100 if n > 1 else 0
        
        pnl = (cur - buy_price) / buy_price * 100
        icon_pnl = '🟢' if pnl > 0 else '🔴' if pnl < -2 else '⚪'
        
        print(f'  {icon_pnl} 最新: {end_date} 收{cur:.2f} 当日{c2:+.2f}% | 成本{buy_price:.2f} | 盈亏{pnl:+.1f}%')
        
        ma5 = pd.Series(df['Close']).rolling(5).mean().values[-1]
        ma10 = pd.Series(df['Close']).rolling(10).mean().values[-1]
        ma20 = pd.Series(df['Close']).rolling(20).mean().values[-1]
        ma60 = pd.Series(df['Close']).rolling(60).mean().values[-1]
        print(f'  均线: MA5={ma5:.1f} MA10={ma10:.1f} MA20={ma20:.1f} MA60={ma60:.1f}')
        
        # 重新跑策略
        bc_h, bc_r = check_beichi(df)
        kk_h, kk_r = check_guanjian_kline(df)
        sm_h, sm_r = check_san_mai_v2(df)
        nc_h, nc_r = check_nichi(df)
        
        alerts_exit = []
        alerts_add = []
        
        # 收集当前信号
        cl_reasons = []
        if bc_h: cl_reasons.append('底背驰')
        if kk_h: cl_reasons.append('关键K线')
        if sm_h: cl_reasons.append('三买')
        if nc_h: 
            sr = [r for r in nc_r if '逆驰评分' in r]
            ns = 0
            if sr:
                try: ns = float(sr[0].split('/')[0].split(': ')[-1])
                except: pass
            cl_reasons.append(f'逆驰{ns:.0f}/8')
        
        yz_reasons = []
        qs_h, qs_r = check_qiangshi(df)
        dx_h, dx_r = check_dixi(df)
        fb_h, fb_r = check_fanbao(df)
        if qs_h: yz_reasons.append('强势股')
        if dx_h: yz_reasons.append('游资低吸')
        if fb_h: yz_reasons.append('反包')
        
        print(f'  缠论信号: {" ".join(cl_reasons) if cl_reasons else "无"}')
        print(f'  游资信号: {" ".join(yz_reasons) if yz_reasons else "无"}')
        
        exit_sigs = check_exit(code, df, cl_reasons + yz_reasons, yz_reasons)
        add_sigs = check_add(code, df, cl_reasons + yz_reasons, yz_reasons)
        
        if exit_sigs:
            print(f'\n  ❗ 出局信号:')
            for s in exit_sigs:
                print(f'    {s}')
        
        if add_sigs:
            print(f'\n  💡 加仓信号:')
            for s in add_sigs:
                print(f'    {s}')
        
        if not exit_sigs and not add_sigs:
            print(f'  ✅ 无异常，继续持有')
        
        print()

    print('=' * 70)
    print('  提示: 此报告基于DB数据(最近交易日)，盘中实时可额外查询')
    print(f'  cronjob: 交易日16:30自动跑（同步数据后）')

if __name__ == '__main__':
    main()
