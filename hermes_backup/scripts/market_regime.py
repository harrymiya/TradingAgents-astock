#!/usr/bin/env python3
"""
市场状态检测 — 判断当前行情类型，返回推荐策略

输出:
  {
    "regime": "强势/震荡/弱势/极弱",
    "score": 0-100,
    "advice": "策略建议",
    "recommended_strategy": "策略名"
  }
"""
import sqlite3, numpy as np, pandas as pd

DB = '/home/harrydolly/.hermes/astock_data.db'

def analyze():
    conn = sqlite3.connect(DB)
    end = conn.execute('SELECT MAX(date) FROM daily_klines').fetchone()[0]
    
    rows = conn.execute('''
        SELECT d.code, d.close, 
               (SELECT d2.close FROM daily_klines d2 WHERE d2.code=d.code AND d2.date=?),
               (SELECT d3.close FROM daily_klines d3 WHERE d3.code=d.code AND d3.date=?)
        FROM daily_klines d WHERE d.date=?
        AND d.code NOT LIKE "688%" AND d.code NOT LIKE "4%"
        AND d.code NOT LIKE "83%" AND d.code NOT LIKE "87%"
    ''', (f'{pd.Timestamp(end)-pd.Timedelta(days=5):%Y-%m-%d}',
          f'{pd.Timestamp(end)-pd.Timedelta(days=20):%Y-%m-%d}', end))
    data = rows.fetchall()
    conn.close()
    
    closes = np.array([r[1] for r in data])
    c5 = np.array([r[2] if r[2] else r[1] for r in data])
    c20 = np.array([r[3] if r[3] else r[1] for r in data])
    
    chg5 = (closes - c5) / c5 * 100
    chg20 = (closes - c20) / c20 * 100
    
    up5 = np.sum(chg5 > 0) / len(chg5) * 100
    up20 = np.sum(chg20 > 0) / len(chg20) * 100
    med5 = float(np.median(chg5))
    med20 = float(np.median(chg20))
    std5 = float(np.std(chg5))
    zt = int(np.sum(chg5 > 9.5))
    dt = int(np.sum(chg5 < -9.5))
    
    # 综合打分 0-100（越高越强）
    score = up5 * 0.4 + (up20 * 0.3) + (med5 + 10) * 2 + (med20 + 10) * 0.5
    score = max(0, min(100, score))
    
    if score >= 65:
        regime = "强势行情"
        advice = "赚钱效应强，做最强龙头"
        strategy = "qiangshi_sanmai"  # 强势股+三买
    elif score >= 45:
        regime = "震荡行情"
        advice = "多空平衡，低吸高抛"
        strategy = "sanmai_dixi"  # 三买+低吸
    elif score >= 25:
        regime = "弱势行情"
        advice = "亏钱效应明显，只做超跌反弹"
        strategy = "dixi_beichi"  # 低吸+底背驰
    else:
        regime = "极弱行情"
        advice = "系统性杀跌，建议空仓或极小仓位试错"
        strategy = "dixi_beichi_danger"  # 极严苛的低吸+底背驰
    
    return {
        "date": end,
        "regime": regime,
        "score": round(score, 1),
        "up5d_pct": round(up5, 1),
        "up20d_pct": round(up20, 1),
        "med5d": round(med5, 2),
        "med20d": round(med20, 2),
        "zt_dt_ratio": f"{zt}:{dt}",
        "volatility": round(std5, 1),
        "advice": advice,
        "strategy": strategy,
    }

if __name__ == "__main__":
    import json
    r = analyze()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print()
    print(f"📊 市场判断: {r['regime']} (评分{r['score']})")
    print(f"📌 建议: {r['advice']}")
    print(f"🎯 策略: {r['strategy']}")
