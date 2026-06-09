#!/usr/bin/env python3
"""
Phase 1: 预计算特征表 (feat table)
每日每只股票的特征 + 未来N日收益
用SQL窗口函数一次算完，不再逐只遍历
"""

import sqlite3
import os
import time

DB = os.path.expanduser("~/.hermes/astock_data.db")

def build_feat_table():
    """创建 feat 表，一次性预计算所有特征"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    print("=== Phase 1: 构建特征表 ===")
    t0 = time.time()
    
    # 1. 确保索引
    print("1/3 确保索引...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_daily_code_date ON daily_klines(code, date)")
    
    # 2. 创建特征表
    print("2/3 创建 feat 表...")
    cur.execute("DROP TABLE IF EXISTS feat")
    
    cur.execute("""
        CREATE TABLE feat AS
        WITH prices AS (
            SELECT 
                code, date, close, open, high, low, volume,
                LAG(close, 1) OVER w AS prev_close_1,
                LAG(close, 2) OVER w AS prev_close_2,
                LAG(close, 3) OVER w AS prev_close_3,
                LEAD(close, 1) OVER w AS lead_close_1,
                LEAD(close, 2) OVER w AS lead_close_2,
                LEAD(close, 3) OVER w AS lead_close_3,
                LEAD(close, 5) OVER w AS lead_close_5,
                LEAD(close, 10) OVER w AS lead_close_10
            FROM daily_klines
            WINDOW w AS (PARTITION BY code ORDER BY date)
        ),
        base AS (
            SELECT 
                d.code, d.date, d.close, d.open, d.high, d.low, d.volume,
                p.prev_close_1, p.prev_close_2, p.prev_close_3,
                p.lead_close_1, p.lead_close_2, p.lead_close_3, p.lead_close_5, p.lead_close_10,
                -- 较昨收涨跌 (%)
                ROUND(CASE WHEN p.prev_close_1 IS NOT NULL AND p.prev_close_1 > 0 
                    THEN (d.close - p.prev_close_1) / p.prev_close_1 * 100 
                    ELSE NULL END, 2) AS chg,
                -- 振幅
                ROUND((d.high - d.low) / d.low * 100, 2) AS amp,
                -- 量比 (vs 5日)
                ROUND(d.volume / AVG(d.volume) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING), 2) AS vr_5,
                -- 量比 (vs 20日)
                ROUND(d.volume / AVG(d.volume) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING), 2) AS vr_20,
                -- MA均线
                ROUND(AVG(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW), 2) AS ma5,
                ROUND(AVG(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW), 2) AS ma10,
                ROUND(AVG(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 2) AS ma20,
                ROUND(AVG(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW), 2) AS ma60,
                -- 均线偏离度 (%)
                ROUND((d.close - AVG(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)) 
                    / AVG(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) * 100, 2) AS ma20_pct,
                ROUND((d.close - AVG(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)) 
                    / AVG(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) * 100, 2) AS ma60_pct,
                -- 20/60日位置
                MIN(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
                MAX(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d,
                MIN(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS low_60d,
                MAX(d.close) OVER (PARTITION BY d.code ORDER BY d.date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS high_60d,
                -- 前N日涨跌幅
                ROUND(CASE WHEN p.prev_close_2 IS NOT NULL AND p.prev_close_2 > 0 
                    THEN (p.prev_close_1 - p.prev_close_2) / p.prev_close_2 * 100 ELSE NULL END, 2) AS chg_1,
                ROUND(CASE WHEN p.prev_close_3 IS NOT NULL AND p.prev_close_3 > 0 
                    THEN (p.prev_close_2 - p.prev_close_3) / p.prev_close_3 * 100 ELSE NULL END, 2) AS chg_2
            FROM daily_klines d
            JOIN prices p ON d.code = p.code AND d.date = p.date
        )
        SELECT 
            code, date, close, open, high, low, volume,
            chg, amp, vr_5, vr_20,
            ma5, ma10, ma20, ma60,
            ma20_pct, ma60_pct,
            -- 20日位置: 0~100 (100=最高点)
            ROUND(CASE WHEN high_20d != low_20d 
                THEN (close - low_20d) * 100.0 / (high_20d - low_20d) 
                ELSE 50 END, 1) AS pos_20d,
            -- 60日位置
            ROUND(CASE WHEN high_60d != low_60d 
                THEN (close - low_60d) * 100.0 / (high_60d - low_60d) 
                ELSE 50 END, 1) AS pos_60d,
            -- 连跌天数 (当日+前N日连续收跌)
            CASE WHEN chg < 0 AND chg_1 < 0 AND chg_2 < 0 THEN 4
                 WHEN chg < 0 AND chg_1 < 0 THEN 3
                 WHEN chg < 0 THEN 2
                 ELSE 1
            END AS down_days,
            -- 连涨天数
            CASE WHEN chg > 0 AND chg_1 > 0 AND chg_2 > 0 THEN 4
                 WHEN chg > 0 AND chg_1 > 0 THEN 3
                 WHEN chg > 0 THEN 2
                 ELSE 1
            END AS up_days,
            -- 未来收益率
            ROUND((lead_close_1 - close) / close * 100, 2) AS ret1,
            ROUND((lead_close_2 - close) / close * 100, 2) AS ret2,
            ROUND((lead_close_3 - close) / close * 100, 2) AS ret3,
            ROUND((lead_close_5 - close) / close * 100, 2) AS ret5,
            ROUND((lead_close_10 - close) / close * 100, 2) AS ret10
        FROM base
    """)
    
    t1 = time.time()
    cur.execute("SELECT COUNT(*) FROM feat")
    rows = cur.fetchone()[0]
    print(f"    ✓ feat 表创建完成: {rows:,} 行, 耗时 {t1-t0:.1f}s")
    
    # 3. 建索引
    print("3/3 建索引...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_feat_date ON feat(date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_feat_code ON feat(code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_feat_chg ON feat(chg)")
    t2 = time.time()
    print(f"    ✓ 索引完成, {t2-t1:.1f}s")
    
    # 验证
    samples = cur.execute("""
        SELECT code, date, chg, pos_20d, vr_20, ret1, ret3 
        FROM feat LIMIT 10
    """).fetchmany(5)
    print("\n=== 样例数据 ===")
    for row in samples:
        print(f"    {row}")
    
    # 统计
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            ROUND(AVG(chg), 2) as avg_chg,
            ROUND(AVG(ret1), 2) as avg_ret1,
            ROUND(AVG(ret3), 2) as avg_ret3
        FROM feat WHERE chg IS NOT NULL
    """)
    stats = cur.fetchone()
    print(f"\n    总记录: {stats[0]:,} | 均涨跌: {stats[1]}% | 次日收益: {stats[2]}% | 3日收益: {stats[3]}%")
    
    cur.execute("""
        SELECT SUBSTR(date, 1, 4) as yr, COUNT(*) as r, 
               ROUND(AVG(chg), 2) as ac, ROUND(AVG(ret1), 2) as ar1
        FROM feat WHERE chg IS NOT NULL
        GROUP BY yr ORDER BY yr
    """)
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]:,}行, 日均涨跌 {row[2]}%, 次日收益 {row[3]}%")
    
    conn.commit()
    conn.close()
    print(f"\n✅ Phase 1 完成! 总耗时 {time.time()-t0:.1f}s")
    print(f"   特征列: chg, amp, vr_5, vr_20, ma5/10/20/60, ma20_pct, ma60_pct")
    print(f"           pos_20d, pos_60d, down_days, up_days")


if __name__ == "__main__":
    build_feat_table()
