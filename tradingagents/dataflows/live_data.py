"""
盘中实时数据 + DB历史数据 统一获取模块

数据策略:
  - 盘中分析/扫描: DB历史日线(≤昨日) + 腾讯当天日线(盘中实时) + 腾讯分时(盘中明细)
  - 收盘后同步: sync_fast.py 增量写入当天日线到DB(不入分时)
  - 分时数据: 盘中临时拉取，不入库
"""

import requests
import json
import time
import traceback
from typing import Optional, Dict, List, Any, Tuple

# ---- 腾讯API ----

def fetch_tencent_kline(code: str, count: int = 800) -> Optional[List[Dict]]:
    """从腾讯财经拉取日K线 (含当天盘中的日K)
    返回 [{date, open, high, low, close, volume, amount}, ...]
    """
    # sz=深交所 sh=上交所
    prefix = "sz" if code.startswith(("0", "3")) else "sh"
    full_code = f"{prefix}{code}"
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full_code},day,,,{count},qfq"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        # 腾讯返回结构：{code:0, msg:"", data: {"sz301231": {"qfqday": [[...], ...], "qt": {...}}}}
        # 路径: data → data["data"] → data["data"][full_code] → ["qfqday"]
        inner = data.get("data") or data
        stock_data = inner.get(full_code) if isinstance(inner, dict) else inner
        # 校验 stock_data 是字典且包含日线数组
        if not isinstance(stock_data, dict):
            stock_data = data
        # 找日线数组
        days = None
        for k in ("qfqday", "day", "klines"):
            if k in stock_data:
                days = stock_data[k]
                break
        if not days or not isinstance(days, list):
            return None
        klines = []
        for d in days:
            if len(d) >= 6:
                klines.append({
                    "date": str(d[0]),
                    "open": float(d[1]),
                    "close": float(d[2]),
                    "high": float(d[3]),
                    "low": float(d[4]),
                    "volume": float(d[5]) if len(d) > 5 else 0,
                    "amount": float(d[6]) if len(d) > 6 and d[6] else 0,
                })
        return klines
    except Exception as e:
        return None


def fetch_tencent_realtime(code: str) -> Optional[Dict]:
    """从腾讯拉取实时行情
    返回 {price, open, high, low, volume, pre_close, change, change_pct, ...}
    """
    prefix = "sz" if code.startswith(("0", "3")) else "sh"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    try:
        r = requests.get(url, timeout=10)
        text = r.text
        # 格式: v_{prefix}{code}="1~name~code~price~...~..."
        parts = text.split("~")
        if len(parts) < 33:
            return None
        
        price = float(parts[3]) if parts[3] else 0
        pre_close = float(parts[4]) if parts[4] else 0
        open_p = float(parts[5]) if parts[5] else 0
        volume = int(parts[6]) if parts[6] else 0  # 手
        high = float(parts[33]) if len(parts) > 33 and parts[33] else 0
        low = float(parts[34]) if len(parts) > 34 and parts[34] else 0
        change = float(parts[31]) if len(parts) > 31 and parts[31] else (price - pre_close)
        change_pct = float(parts[32]) if len(parts) > 32 and parts[32] else 0
        
        return {
            "price": price,
            "open": open_p,
            "high": high,
            "low": low,
            "pre_close": pre_close,
            "volume": volume,
            "change": change,
            "change_pct": change_pct,
            "amount": float(parts[37]) if len(parts) > 37 and parts[37] else 0,
            "turnover": float(parts[38]) if len(parts) > 38 and parts[38] else 0,  # 换手率%
            "pe": float(parts[39]) if len(parts) > 39 and parts[39] else 0,
            "amplitude": float(parts[43]) if len(parts) > 43 and parts[43] else 0,  # 振幅%
        }
    except Exception as e:
        return None


def fetch_tencent_minute(code: str) -> Optional[List[Dict]]:
    """从腾讯拉取当天分时数据 (5分钟粒度)
    返回 [{time, price, avg_price, volume, amount}, ...]
    """
    prefix = "sz" if code.startswith(("0", "3")) else "sh"
    url = f"http://web.ifzq.gtimg.cn/appstock/app/kline/mkline?param={prefix}{code},m,,60"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        # 结构: {data: {code: {m: {klines: [...], ...}}}}
        for key in ("data", code):
            if isinstance(data, dict) and key in data:
                data = data[key]
        
        # 找分钟数据
        minutes = None
        if isinstance(data, dict):
            for k in ("m", "mins", "minute"):
                if k in data:
                    minutes = data[k]
                    break
        
        if not minutes:
            # 尝试另一个接口格式
            url2 = f"http://web.ifzq.gtimg.cn/appstock/app/kline/mkline?param={prefix}{code},m,,15"
            try:
                r2 = requests.get(url2, timeout=10)
                data2 = r2.json()
                for key in ("data", code):
                    if isinstance(data2, dict) and key in data2:
                        data2 = data2[key]
                if isinstance(data2, dict):
                    for k in ("m", "mins", "minute"):
                        if k in data2:
                            minutes = data2[k]
                            break
            except Exception:
                pass
        
        if not minutes or not isinstance(minutes, dict):
            return None
        
        # 尝试找 klines 数组
        klines_raw = minutes.get("klines") or minutes.get("data") or minutes.get("list")
        if not klines_raw or not isinstance(klines_raw, list):
            return None
        
        result = []
        for row in klines_raw:
            if isinstance(row, str):
                # 格式: "09:35 32.50 32.48 12345 67890"
                parts = row.split()
                if len(parts) >= 3:
                    result.append({
                        "time": parts[0],
                        "price": float(parts[1]),
                        "avg_price": float(parts[2]) if len(parts) > 2 else 0,
                        "volume": int(parts[3]) if len(parts) > 3 else 0,
                        "amount": float(parts[4]) if len(parts) > 4 else 0,
                    })
            elif isinstance(row, (list, tuple)):
                if len(row) >= 3:
                    result.append({
                        "time": str(row[0]),
                        "price": float(row[1]),
                        "avg_price": float(row[2]) if len(row) > 2 else 0,
                        "volume": float(row[3]) if len(row) > 3 else 0,
                        "amount": float(row[4]) if len(row) > 4 else 0,
                    })
        return result if result else None
    except Exception as e:
        return None


def fetch_tencent_minute_v2(code: str) -> Optional[List[Dict]]:
    """备用分时接口: 腾讯 data 分钟K线
    """
    prefix = "sz" if code.startswith(("0", "3")) else "sh"
    url = f"http://web.ifzq.gtimg.cn/appstock/app/kline/mkline?param={prefix}{code},m,,0,,30"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        for key in ("data", code):
            if isinstance(data, dict) and key in data:
                data = data[key]
        if not isinstance(data, dict):
            return None
        for k in ("m", "mins"):
            if k in data:
                minutes = data[k]
                if isinstance(minutes, dict):
                    klines_raw = minutes.get("klines")
                    if klines_raw and isinstance(klines_raw, list):
                        result = []
                        for row in klines_raw:
                            if isinstance(row, str):
                                parts = row.split()
                                if len(parts) >= 3:
                                    result.append({
                                        "time": parts[0],
                                        "price": float(parts[1]),
                                        "volume": int(parts[3]) if len(parts) > 3 else 0,
                                    })
                        return result
        return None
    except Exception:
        return None


# ---- DB 操作 ----

def get_db_klines(code: str, start_date: str = "2026-01-01", end_date: str = "") -> List[Dict]:
    """从DB读取历史日线"""
    import sqlite3
    db_path = "/home/harrydolly/.hermes/astock_data.db"
    if not end_date:
        from datetime import datetime
        end_date = datetime.now().strftime("%Y-%m-%d")
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(
            """SELECT date, open, high, low, close, volume, amount 
               FROM daily_klines
               WHERE code = ? AND date >= ? AND date <= ?
               ORDER BY date""",
            (code, start_date, end_date)
        )
        rows = c.fetchall()
        conn.close()
        return [
            {"date": r[0], "open": r[1], "high": r[2],
             "low": r[3], "close": r[4], "volume": r[5], "amount": r[6]}
            for r in rows
        ]
    except Exception as e:
        return []


def save_klines_to_db(code: str, klines: List[Dict]):
    """保存日线到DB（增量，INSERT OR REPLACE）"""
    import sqlite3
    db_path = "/home/harrydolly/.hermes/astock_data.db"
    try:
        conn = sqlite3.connect(db_path)
        rows = []
        for k in klines:
            rows.append((
                code,
                k.get("date", ""),
                float(k.get("open", 0)),
                float(k.get("high", 0)),
                float(k.get("low", 0)),
                float(k.get("close", 0)),
                float(k.get("volume", 0)),
                float(k.get("amount", 0)),
            ))
        c = conn.cursor()
        c.executemany(
            """INSERT OR REPLACE INTO daily_klines 
               (code, date, open, high, low, close, volume, amount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows
        )
        conn.commit()
        conn.close()
        return len(rows)
    except Exception as e:
        return 0


# ---- 统一数据获取 ----

def get_data_for_analysis(code: str, name: str = "", lookback_days: int = 120) -> Dict:
    """统一盘中数据获取
    - DB历史日线
    - 腾讯当天日线（盘中实时）
    - 腾讯分时（盘中明细）
    
    Returns:
    {
        "code": "301231",
        "name": "荣信文化",
        "today_info": {price, open, high, low, volume, pre_close, change_pct, ...},  # 或None(停牌)
        "daily_klines": [{date, open, high, low, close, volume, amount}, ...],  # 合并的历史+今天
        "minute_data": [{time, price, volume}, ...],  # 分时明细, 或None
        "today_kline": {date, open, high, low, close, volume, amount}  # 当天日K, 或None
    }
    """
    from datetime import datetime, timedelta
    
    today = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    
    result = {
        "code": code,
        "name": name,
        "today_info": None,
        "daily_klines": [],
        "minute_data": None,
        "today_kline": None,
    }
    
    # 1. DB历史日线
    db_klines = get_db_klines(code, start_date=start_date)
    result["daily_klines"] = db_klines
    
    # 2. 腾讯日线（含当天）
    today_kline = None
    try:
        tencent_klines = fetch_tencent_kline(code, count=lookback_days)
        if tencent_klines:
            # 取当天日K
            today_klines = [k for k in tencent_klines if k["date"] == today]
            if today_klines:
                today_kline = today_klines[-1]
                result["today_kline"] = today_kline
            # 合并到日线（去重）
            existing_dates = {k["date"] for k in result["daily_klines"]}
            for k in tencent_klines:
                if k["date"] not in existing_dates:
                    result["daily_klines"].append(k)
            # 如果有腾讯当天数据但没有DB当天数据，也更新DB已有时
            if today_kline:
                for i, k in enumerate(result["daily_klines"]):
                    if k["date"] == today:
                        result["daily_klines"][i] = today_kline
    except Exception:
        pass
    
    # 排序
    result["daily_klines"].sort(key=lambda x: x["date"])
    
    # 3. 腾讯实时行情（当天开盘价/当前价/涨跌幅）
    try:
        realtime = fetch_tencent_realtime(code)
        if realtime:
            result["today_info"] = realtime
    except Exception:
        pass
    
    # 4. 当天分时数据
    try:
        minute_data = fetch_tencent_minute(code)
        if not minute_data:
            minute_data = fetch_tencent_minute_v2(code)
        result["minute_data"] = minute_data
    except Exception:
        pass
    
    return result


def combine_db_history(code: str, lookback_days: int = 120) -> Tuple[List[Dict], str]:
    """仅从DB获取历史日线 + 说明最新日期
    用于非盘中场景（如收盘后分析）
    返回 (klines, latest_date_str)
    """
    from datetime import datetime, timedelta
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    klines = get_db_klines(code, start_date=start_date)
    latest = klines[-1]["date"] if klines else "无数据"
    return klines, latest


def format_analysis_text(data: Dict) -> str:
    """格式化分析数据为可读文本"""
    lines = []
    code = data["code"]
    name = data["name"] or code
    
    lines.append(f"▶ {name}({code})")
    lines.append("")
    
    # 今日行情
    ti = data.get("today_info")
    if ti:
        chg_s = f"{ti['change']:.2f}({ti['change_pct']:.2f}%)" if ti.get("change_pct") else f"{ti['change']:.2f}"
        lines.append(f"【盘中实时】")
        lines.append(f"  当前价: {ti['price']:.2f} | 涨跌: {chg_s}")
        lines.append(f"  今开: {ti['open']:.2f} | 昨收: {ti['pre_close']:.2f}")
        lines.append(f"  最高: {ti['high']:.2f} | 最低: {ti['low']:.2f}")
        if ti.get("volume"):
            lines.append(f"  成交量: {ti['volume']/10000:.1f}万手 | 换手率: {ti.get('turnover', 0):.2f}%")
        if ti.get("pe"):
            lines.append(f"  PE(TTM): {ti.get('pe', 0):.1f}")
    
    tk = data.get("today_kline")
    if tk:
        lines.append(f"  当天日K: O={tk['open']:.2f} H={tk['high']:.2f} L={tk['low']:.2f} C={tk['close']:.2f} V={tk['volume']:.0f}")
    
    # 分时
    md = data.get("minute_data")
    if md:
        prices = [m["price"] for m in md if m.get("price")]
        if prices:
            max_p = max(prices)
            min_p = min(prices)
            cur_p = prices[-1] if prices else 0
            vol_total = sum(m.get("volume", 0) for m in md if m.get("volume"))
            lines.append(f"  分时: {len(prices)}段 | 范围 {min_p:.2f}~{max_p:.2f} | 当前 {cur_p:.2f} | 量 {vol_total/10000:.0f}万手")
    
    # 日线统计
    dk = data.get("daily_klines", [])
    if dk:
        closes = [k["close"] for k in dk if k.get("close")]
        if closes:
            lines.append("")
            lines.append(f"【日线历史({len(dk)}条)】")
            lines.append(f"  范围: {dk[0]['date']} ~ {dk[-1]['date']}")
            lines.append(f"  最高: {max(closes):.2f} | 最低: {min(closes):.2f}")
            lines.append(f"  最新: {closes[-1]:.2f}")
            # 简单均线
            if len(closes) >= 5:
                ma5 = sum(closes[-5:]) / 5
                lines.append(f"  MA5: {ma5:.2f}")
            if len(closes) >= 20:
                ma20 = sum(closes[-20:]) / 20
                lines.append(f"  MA20: {ma20:.2f}")
    
    if not ti and not dk and not md:
        lines.append("  无数据")
    
    return "\n".join(lines)


# ---- 快捷函数 ----

def get_stock_with_live(code: str, name: str = "", lookback_days: int = 120) -> Dict:
    """一站式获取：盘中=实时+DB历史，收盘后=DB历史"""
    return get_data_for_analysis(code, name, lookback_days)


def print_stock_live(code: str, name: str = ""):
    """直接打印盘中数据"""
    data = get_data_for_analysis(code, name)
    print(format_analysis_text(data))
    return data


if __name__ == "__main__":
    # 测试4只持仓
    stocks = [
        ("301231", "荣信文化"),
        ("300550", "和仁科技"),
        ("600503", "华丽家族"),
        ("603586", "金麒麟"),
    ]
    for code, name in stocks:
        data = get_data_for_analysis(code, name)
        print("=" * 50)
        print(format_analysis_text(data))
        print()
