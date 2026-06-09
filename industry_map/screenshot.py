"""
industry_map/screenshot.py — 产业链HTML截图工具

用法:
  from industry_map import screenshot
  path = screenshot.capture("半导体", metric="chg")
  # 然后直接用 MEDIA:path 发到飞书
"""

import os, subprocess, time, threading, socket
import http.server
import socketserver
from pathlib import Path
from . import render
from .db import ChainManager

# 临时目录
TMP_DIR = Path('/home/harrydolly/industry_map_cache')
TMP_DIR.mkdir(parents=True, exist_ok=True)

def capture(chain_name: str, metric: str = 'chg', output: str = None) -> str:
    """
    截图产业链地图
    返回PNG文件路径，可直接用于 MEDIA:/path
    
    示例:
      截图后通过飞书MEDIA发送:
        path = capture("半导体")
        print(f"MEDIA:{path}")
    """
    chain = ChainManager.get_chain(chain_name)
    if not chain:
        print(f"❌ 产业链 '{chain_name}' 不存在")
        return ""
    
    # 收集所有股票代码
    all_codes = list(set(
        s['code'] for l in chain['links'] for s in l['stocks']
    ))
    
    print(f"📸 {chain_name} ({metric}) · {len(all_codes)}只股票")
    
    # 获取实时行情
    prices = _fetch_prices(all_codes)
    print(f"  → 实时行情 {len(prices)}只")
    
    # 渲染HTML
    html = render.render_chain(chain_name, metric, prices)
    
    if output:
        out_path = Path(output)
    else:
        safe_name = chain_name.replace('/', '_').replace('(', '').replace(')', '')
        safe_name = ''.join(c if c.isalnum() or c in '_-' else '_' for c in safe_name)
        out_path = TMP_DIR / f"{safe_name}_{metric}.png"
    
    tmp_html = out_path.with_suffix('.html')
    tmp_html.write_text(html, encoding='utf-8')
    tmp_dir = tmp_html.parent
    
    # HTTP服务（需要切换到HTML所在目录）
    old_cwd = os.getcwd()
    os.chdir(str(tmp_dir))
    
    port = _find_free_port()
    stop = threading.Event()
    
    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            p = self.path.split('#')[0]
            if p == '/': self.path = '/' + tmp_html.name
            return super().do_GET()
    
    def serve():
        try:
            with socketserver.TCPServer(('', port), H) as hd:
                hd.timeout = 1
                while not stop.is_set(): hd.handle_request()
        except: pass
    
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.3)
    
    # 动态分辨率：保证每只股票都能清晰显示（按去重股票数）
    stock_count = len(all_codes)
    if stock_count > 60:
        width, height = 3600, 2400
    elif stock_count > 30:
        width, height = 2800, 2000
    elif stock_count > 20:
        width, height = 2400, 1800
    else:
        width, height = 2000, 1400
    
    subprocess.run([
        'chromium', '--headless',
        f'--screenshot={out_path}',
        f'--window-size={width},{height}',
        '--no-sandbox', '--disable-gpu',
        f'http://localhost:{port}/'
    ], capture_output=True, timeout=25)
    
    stop.set()
    os.chdir(old_cwd)
    
    sz = out_path.stat().st_size if out_path.exists() else 0
    print(f"  → {sz//1024}KB | {out_path}")
    return str(out_path)


def _find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _fetch_prices(codes):
    """获取行情数据：盘后从feat表取 → 盘中腾讯API实时覆盖"""
    import urllib.request, json, time as _time, re, sqlite3
    from pathlib import Path
    
    prices = {}
    db_path = Path('/home/harrydolly/.hermes/astock_data.db')
    
    # 1. 先从数据库取最新数据（盘后或昨日收盘）
    if db_path.exists():
        try:
            db = sqlite3.connect(str(db_path))
            cur = db.cursor()
            cur.execute("SELECT MAX(date) FROM feat")
            latest = cur.fetchone()[0]
            if latest:
                # 查所有股票的最新一条数据（用ROWID优化）
                latest_date = latest
                for i in range(0, len(codes), 200):
                    batch = codes[i:i+200]
                    placeholders = ','.join(['?'] * len(batch))
                    cur.execute(f"""
                        SELECT code, close, chg, volume, amp
                        FROM feat 
                        WHERE code IN ({placeholders})
                        AND date = ?
                    """, batch + [latest_date])
                    for r in cur.fetchall():
                        prices[r[0]] = {
                            'price': float(r[1]) if r[1] else 0,
                            'chg': float(r[2]) if r[2] else 0,
                            'volume': float(r[3]) if r[3] else 0,
                            'amplitude': float(r[4]) if r[4] else 0,
                            'yearChg': 0,
                            'source': 'db',
                        }
            db.close()
        except:
            pass
    
    print(f"  → DB历史: {len(prices)}只")
    
    # 2. 腾讯API实时数据覆盖
    now = _time.localtime()
    is_trading = (now.tm_hour >= 9 and now.tm_hour < 15) or (now.tm_hour == 9 and now.tm_min >= 30)
    
    for i in range(0, len(codes), 30):
        batch = codes[i:i+30]
        q = [('sh' if c.startswith('6') else 'sz') + c for c in batch]
        try:
            resp = urllib.request.urlopen(
                'https://qt.gtimg.cn/q=' + ','.join(q) + '&_=' + str(int(_time.time()*1000)),
                timeout=10
            )
            for line in resp.read().decode('gbk').split(';'):
                if not line.strip() or '~' not in line: continue
                p = line.split('~')
                m = re.search(r'(\d{6})', p[0])
                if not m: continue
                raw = m.group(1)
                chg = float(p[32]) if len(p)>32 and p[32] else 0
                hi = float(p[33]) if len(p)>33 and p[33] else 0
                lo = float(p[34]) if len(p)>34 and p[34] else 0
                prices[raw] = {
                    'price': float(p[3]) if p[3] else prices.get(raw, {}).get('price', 0),
                    'chg': chg,
                    'yearChg': float(p[69]) if len(p)>69 and p[69] else 0,
                    'volume': int(p[6]) if p[6] else prices.get(raw, {}).get('volume', 0),
                    'amplitude': round((hi-lo)/lo*100,2) if lo>0 else prices.get(raw, {}).get('amplitude', 0),
                    'source': 'realtime' if is_trading else 'db',
                }
        except:
            pass
        _time.sleep(0.15)
    
    source_counts = {}
    for v in prices.values():
        s = v.get('source', 'unknown')
        source_counts[s] = source_counts.get(s, 0) + 1
    print(f"  → 腾讯实时覆盖完成: {source_counts}")
    
    return prices
