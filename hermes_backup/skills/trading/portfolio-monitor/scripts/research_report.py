#!/usr/bin/env python3
"""
DeepSeek 投研报告生成器 — 持仓股的完整投研分析

功能：
1. 从SQLite数据库读取持仓股的日线K线
2. 跑缠论4策略 + 游资3策略获取技术信号
3. 从腾讯API获取实时行情
4. 从东方财富获取基本面数据
5. 将所有数据组装成结构化提示词
6. 调用DeepSeek生成深度投研报告

依赖：
- chanlun_screener.py 中的 read_klines / check_beichi / check_guanjian_kline / check_san_mai_v2 / check_nichi
- youzi_screener.py 中的 check_qiangshi / check_dixi / check_fanbao
- DeepSeek API key 在 /etc/profile 中

用法：
  cd /home/harrydolly/code/TradingAgents-astock
  source .venv/bin/activate
  python3 ~/.hermes/skills/portfolio-monitor/scripts/research_report.py
"""

import sys, os, json, requests
import subprocess
import pandas as pd
import numpy as np
from datetime import datetime
from openai import OpenAI

# ===== 配置 =====
# 添加项目路径
PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, "/home/harrydolly/.hermes/skills/trading/three-crows-screening/scripts/")
sys.path.insert(0, "/home/harrydolly/.hermes/skills/youzi-screening/scripts/")

# 加载API Key
result = subprocess.run(['bash', '-c', 'source /etc/profile && echo $DEEPSEEK_API_KEY'], 
                       capture_output=True, text=True)
api_key = result.stdout.strip()
os.environ['DEEPSEEK_API_KEY'] = api_key

# ===== 持仓列表（在此修改）=====
PORTFOLIO = [
    ('301231', '荣信文化', 34.62),
    ('300550', '和仁科技', 14.63),
    ('600503', '华丽家族', 2.82),
    ('603586', '金麒麟', 17.63),
]

# ===== 工具函数 =====
def get_realtime(code):
    """腾讯实时行情"""
    prefix = 'sh' if code.startswith('6') else 'sz'
    try:
        r = requests.get(f'http://qt.gtimg.cn/q={prefix}{code}', timeout=5)
        p = r.text.split('~')
        if len(p) < 40: return None
        return {
            'price': float(p[3]), 'y_close': float(p[4]), 'open': float(p[5]),
            'high': float(p[33]), 'low': float(p[34]), 'chg': float(p[32]),
            'turn': float(p[38]), 'pe': float(p[39]) if p[39] else 0,
            'mcap': float(p[45]) if p[45] else 0,
        }
    except: return None

from chanlun_screener import read_klines, calc_macd, find_zones
from chanlun_screener import check_beichi, check_guanjian_kline, check_san_mai_v2, check_nichi
from youzi_screener import check_qiangshi, check_dixi, check_fanbao

# ===== 采集数据 =====
stock_reports = []
for code, name, cost in PORTFOLIO:
    df, end_date = read_klines(code, lookback_days=120)
    rt = get_realtime(code)
    if df is None or rt is None:
        print(f'{name}({code}) 数据不足，跳过')
        continue
    
    n = len(df)
    close = df['Close'].values.astype(float)
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    vol = df['Volume'].values.astype(float)
    cur = close[-1]
    today_chg = (cur / close[-2] - 1) * 100 if n > 1 else 0
    pnl = (cur - cost) / cost * 100
    
    # 技术指标
    ma5 = float(pd.Series(close).rolling(5).mean().values[-1])
    ma10 = float(pd.Series(close).rolling(10).mean().values[-1])
    ma20 = float(pd.Series(close).rolling(20).mean().values[-1])
    dif, dea, macd = calc_macd(df)
    vol_ma20 = float(pd.Series(vol).rolling(20).mean().values[-1])
    h60 = float(max(high[-60:])); l60 = float(min(low[-60:]))
    
    # 信号
    sigs = {}
    sigs['底背驰'], _ = check_beichi(df)
    sigs['关键K线'], _ = check_guanjian_kline(df)
    sigs['三买'], _ = check_san_mai_v2(df)
    nc_h, nc_r = check_nichi(df)
    sigs['逆驰'] = nc_h
    nc_score = 0
    if nc_h:
        sl = [r for r in nc_r if '逆驰评分' in r]
        if sl:
            try: nc_score = float(sl[0].split('/')[0].split(': ')[-1].strip())
            except: pass
    
    active = [k for k, v in sigs.items() if v]
    cz = find_zones(df)
    
    qs_h, _ = check_qiangshi(df)
    dx_h, _ = check_dixi(df)
    fb_h, _ = check_fanbao(df)
    yz = []
    if qs_h: yz.append('强势')
    if dx_h: yz.append('低吸')
    if fb_h: yz.append('反包')
    
    stock_reports.append({
        'code': code, 'name': name, 'cost': cost,
        'price': cur, 'real_price': rt['price'],
        'real_chg': rt['chg'], 'pnl': pnl,
        'turn': rt['turn'], 'pe': rt['pe'], 'mcap': rt['mcap'],
        'open': rt['open'], 'high': rt['high'], 'low': rt['low'],
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
        'dif': float(dif[-1]), 'dea': float(dea[-1]), 'macd_bar': float(macd[-1]),
        'h60': h60, 'l60': l60,
        'vol_ma20': vol_ma20, 'vol_latest': float(vol[-1]),
        'active_signals': active, 'nc_score': nc_score,
        'youzi_signals': yz,
        'zones': cz,
    })

if not stock_reports:
    print("没有可分析的持仓数据")
    sys.exit(1)

# ===== 构建提示词 =====
stock_sections = []
for s in stock_reports:
    sig_str = ', '.join(s['active_signals'])
    if s['nc_score'] > 0:
        sig_str = sig_str.replace('逆驰', f'逆驰{s["nc_score"]:.0f}/8')
    if s['youzi_signals']:
        sig_str += (' + ' if sig_str else '') + '游资:' + ','.join(s['youzi_signals'])
    
    z = s['zones']
    zone_str = f'中枢[{z[-1]["zd"]:.1f}, {z[-1]["zg"]:.1f}]' if z else '无明显中枢'
    
    macd_dir = '金叉向上' if s['dif'] > s['dea'] and s['macd_bar'] > 0 else \
                '死叉向下' if s['dif'] < s['dea'] else '零轴附近'
    
    spct = (s['price'] - s['l60']) / (s['h60'] - s['l60']) * 100 if s['h60'] > s['l60'] else 0
    
    stock_sections.append(f"""
### {s['name']}({s['code']})

**持仓数据**
- 成本: {s['cost']:.2f} | 价: {s['price']:.2f}(DB) / {s['real_price']:.2f}(实时)
- 盈亏: {s['pnl']:+.1f}% | 今日DB: {s['price']/s['cost']*100-100:+.1f}% | 实时涨跌: {s['real_chg']:+.2f}%
- 区间: O={s['open']:.2f} H={s['high']:.2f} L={s['low']:.2f}
- 换手{s['turn']}% | PE{s['pe']:.0f} | 市值{s['mcap']:.0f}亿

**技术面**
- MA5={s['ma5']:.1f} MA10={s['ma10']:.1f} MA20={s['ma20']:.1f}
- MACD: {s['dif']:.2f}/{s['dea']:.2f}/{s['macd_bar']:.2f} ({macd_dir})
- 60日区间[{s['l60']:.1f},{s['h60']:.1f}] 位于{spct:.0f}%分位
- 量: 20日均{s['vol_ma20']/1e4:.0f}万 最近{s['vol_latest']/1e4:.0f}万

**信号**: {sig_str if sig_str else '无'}
**中枢**: {zone_str}
**回撤**: 从高点{s['h60']:.1f}回撤{(s['price']-s['h60'])/s['h60']*100:.1f}%
""")

prompt = f"""你是一位顶级的A股投资分析师，精通缠论、游资心法、技术分析和基本面分析。

请对以下{len(stock_reports)}只持仓股票进行深度投研分析，每只股票给出：
1. **走势判断** — 当前处于什么阶段（起涨/主升/回调/见顶/筑底）
2. **核心逻辑** — 买入信号是否仍然有效
3. **风险点** — 最大风险是什么
4. **操作策略** — 具体到价位：止盈位、止损位、加仓位
5. **优先级** — 哪只最该动、哪只最安全

格式：每只独立分析约300-400字，给出具体价位，语言简洁直接可执行。最后给出综合排序。

分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}

{"".join(stock_sections)}

请开始分析。"""

# ===== 调用DeepSeek =====
client = OpenAI(api_key=api_key, base_url='https://api.deepseek.com')
r = client.chat.completions.create(
    model='deepseek-chat',
    messages=[
        {'role': 'system', 'content': '你是一位顶级的A股投资分析师，精通缠论和游资心法。回答简洁、专业、可执行。'},
        {'role': 'user', 'content': prompt}
    ],
    max_tokens=4000,
    temperature=0.1,
)
print(r.choices[0].message.content)
