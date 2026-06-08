#!/usr/bin/env python3
"""
持仓监控 — 每日出局/加仓信号
用法: cd /home/harrydolly/code/TradingAgents-astock && source .venv/bin/activate && python3 ~/.hermes/scripts/portfolio_monitor.py

PORTFOLIO 列表编辑此文件底部，添加新持仓时需要:
  ('301231', '荣信文化', 34.62)  # (6位代码, 名称, 买入成本)
"""
import sys, os
sys.path.insert(0, '/home/harrydolly/code/TradingAgents-astock')
sys.path.insert(0, '/home/harrydolly/.hermes/skills/trading/three-crows-screening/scripts/')
sys.path.insert(0, '/home/harrydolly/.hermes/skills/youzi-screening/scripts/')

import requests
import pandas as pd
import numpy as np
from datetime import datetime
from chanlun_screener import check_beichi, check_guanjian_kline, check_san_mai_v2, check_nichi
from chanlun_screener import read_klines, find_zones
from youzi_screener import check_qiangshi, check_dixi, check_fanbao

# ===== 持仓列表（编辑这里添加新股票） =====
PORTFOLIO = [
    ('301231', '荣信文化', 34.62),
    ('300550', '和仁科技', 14.63),
    ('600503', '华丽家族', 2.82),
    ('603586', '金麒麟', 17.63),
]


def get_rt(code):
    """腾讯实时行情"""
    prefix = 'sh' if code.startswith('6') else 'sz'
    try:
        r = requests.get(f'http://qt.gtimg.cn/q={prefix}{code}', timeout=5)
        parts = r.text.split('~')
        if len(parts) < 40: return None
        return {
            'price': float(parts[3]), 'y_close': float(parts[4]),
            'open': float(parts[5]), 'high': float(parts[33]),
            'low': float(parts[34]), 'chg': float(parts[32]),
            'turn': float(parts[38]), 'pe': float(parts[39]) if parts[39] else 0,
            'mcap': float(parts[45]) if parts[45] else 0,
        }
    except: return None


def check_exit(df, cl_reasons, yz_reasons):
    """出局信号判断"""
    n = len(df); close = df['Close'].values; high = df['High'].values
    low = df['Low'].values; vol = df['Volume'].values.astype(float); cur = close[-1]
    ma20 = pd.Series(close).rolling(20).mean().values[-1]
    ma60 = pd.Series(close).rolling(60).mean().values[-1]
    
    signals = []
    
    # MACD绿柱持续放大
    ema_f = pd.Series(close).ewm(span=12).mean().values
    ema_s = pd.Series(close).ewm(span=26).mean().values
    dif = ema_f - ema_s; dea = pd.Series(dif).ewm(span=9).mean().values
    macd = 2 * (dif - dea)
    if macd[-1] < 0 and macd[-1] < macd[-2] and macd[-2] < macd[-3]:
        signals.append('⚠️ MACD绿柱持续放大，空头加速')
    
    # 跌破MA60
    if cur < ma60 * 0.98:
        signals.append(f'🔴 跌破MA60({ma60:.1f})，趋势破位')
    
    # 放量大跌
    c2 = (cur / close[-2] - 1) * 100 if n > 1 else 0
    vol_ma20 = pd.Series(vol).rolling(20).mean().values[-1]
    if c2 < -5 and vol[-1] > vol_ma20 * 1.5:
        signals.append('🔴 放量大跌超5%')
    
    # 连阴
    if n >= 4 and all(close[-i-1] > close[-i] for i in range(3)):
        signals.append('⚠️ 连续3日收阴')
    
    # 缠论信号全消失
    if not any(k in str(cl_reasons) for k in ['底背驰', '三买', '逆驰']):
        signals.append('⚠️ 缠论信号全部消失')
    
    return signals


def check_add(df):
    """加仓信号判断"""
    close = df['Close'].values.astype(float); vol = df['Volume'].values.astype(float)
    cur = close[-1]
    ma5 = pd.Series(close).rolling(5).mean().values[-1]
    ma20 = pd.Series(close).rolling(20).mean().values[-1]
    ma60 = pd.Series(close).rolling(60).mean().values[-1]
    vol_ma20 = pd.Series(vol).rolling(20).mean().values[-1]
    c2 = (cur / close[-2] - 1) * 100 if len(close) > 1 else 0
    
    sigs = []
    
    # 放量站上MA5
    if cur > ma5 and vol[-1] > vol_ma20 * 1.3 and c2 > 2:
        sigs.append('🟢 放量站上MA5')
    
    # MACD金叉
    ema_f = pd.Series(close).ewm(span=12).mean().values
    ema_s = pd.Series(close).ewm(span=26).mean().values
    dif = ema_f - ema_s; dea = pd.Series(dif).ewm(span=9).mean().values; macd = 2 * (dif - dea)
    if macd[-1] > 0 and dif[-1] > dea[-1]:
        sigs.append('🟢 MACD金叉')
    elif macd[-1] > macd[-2] and macd[-2] < macd[-3]:
        sigs.append('🟢 MACD绿柱缩短')
    
    # 缩量回踩MA60企稳
    if cur > ma60 * 0.99 and vol[-1] / vol_ma20 < 0.6:
        sigs.append('🟢 缩量回踩MA60企稳')
    
    return sigs


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f'📋 持仓监控报告 — {now}')
    print(f'{"="*70}')
    
    for code, name, buy_price in PORTFOLIO:
        print(f'\n--- {name}({code}) 买入价{buy_price:.2f} ---')
        
        df, end_date = read_klines(code, lookback_days=90)
        if df is None:
            print('  数据不足')
            continue
        
        n = len(df); cur = float(df['Close'].values[-1])
        c2 = (cur / float(df['Close'].values[-2]) - 1) * 100 if n > 1 else 0
        pnl = (cur - buy_price) / buy_price * 100
        icon_pnl = '🟢' if pnl > 0 else '🔴' if pnl < -2 else '⚪'
        
        print(f'  {icon_pnl} 最新: {end_date} 收{cur:.2f} 当日{c2:+.2f}% | 盈亏{pnl:+.1f}%')
        
        ma5 = pd.Series(df['Close']).rolling(5).mean().values[-1]
        ma10 = pd.Series(df['Close']).rolling(10).mean().values[-1]
        ma20 = pd.Series(df['Close']).rolling(20).mean().values[-1]
        ma60 = pd.Series(df['Close']).rolling(60).mean().values[-1]
        print(f'  均线: MA5={ma5:.1f} MA10={ma10:.1f} MA20={ma20:.1f} MA60={ma60:.1f}')
        
        # 跑策略
        bc_h, _ = check_beichi(df); kk_h, _ = check_guanjian_kline(df)
        sm_h, _ = check_san_mai_v2(df); nc_h, nc_r = check_nichi(df)
        
        cl = []
        if bc_h: cl.append('底背驰')
        if kk_h: cl.append('关键K线')
        if sm_h: cl.append('三买')
        if nc_h:
            sr = [r for r in nc_r if '逆驰评分' in r]
            ns = 0
            if sr:
                try: ns = float(sr[0].split('/')[0].split(': ')[-1])
                except: pass
            cl.append(f'逆驰{ns:.0f}/8')
        
        qs_h, _ = check_qiangshi(df); dx_h, _ = check_dixi(df); fb_h, _ = check_fanbao(df)
        yz = []
        if qs_h: yz.append('强势股')
        if dx_h: yz.append('游资低吸')
        if fb_h: yz.append('反包')
        
        print(f'  缠论信号: {" ".join(cl) if cl else "无"}')
        print(f'  游资信号: {" ".join(yz) if yz else "无"}')
        
        exit_sigs = check_exit(df, cl, yz)
        add_sigs = check_add(df)
        
        if exit_sigs:
            print(f'\n  ❗ 出局信号:')
            for s in exit_sigs: print(f'    {s}')
        
        if add_sigs:
            print(f'\n  💡 加仓信号:')
            for s in add_sigs: print(f'    {s}')
        
        if not exit_sigs and not add_sigs:
            print('  ✅ 无异常，继续持有')
        
        print()
    
    print(f'{"="*70}')
    print('  提示: 此报告基于DB数据(最近交易日)。cronjob: 交易日8:30/16:30自动推送')


if __name__ == '__main__':
    main()
