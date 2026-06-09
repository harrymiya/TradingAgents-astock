"""
industry_map/portal_v2.py — V2产业地图门户页面
"""
import sys, os, sqlite3, json, time, urllib.request, re

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')

def query_db(sql, params=()):
    for attempt in range(5):
        try:
            db = sqlite3.connect(DB_PATH, timeout=5)
            db.row_factory = sqlite3.Row
            cur = db.execute(sql, params)
            rows = cur.fetchall()
            db.close()
            return rows
        except sqlite3.OperationalError as e:
            if 'locked' in str(e) and attempt < 4:
                time.sleep(2)
                continue
            raise

def get_stock_prices(codes):
    prices = {}
    for i in range(0, len(codes), 30):
        batch = codes[i:i+30]
        q = [('sh' if c.startswith('6') else 'sz') + c for c in batch]
        try:
            resp = urllib.request.urlopen(
                'https://qt.gtimg.cn/q=' + ','.join(q), timeout=8)
            for line in resp.read().decode('gbk').split(';'):
                if not line.strip() or '~' not in line: continue
                parts = line.split('~')
                raw = re.sub(r'v_(?:sh|sz)?(\d{6}).*', r'\1', parts[0])
                chg = float(parts[32]) if len(parts)>32 and parts[32] else 0
                hi = float(parts[33]) if len(parts)>33 and parts[33] else 0
                lo = float(parts[34]) if len(parts)>34 and parts[34] else 0
                prices[raw] = {
                    'name': parts[1], 'price': float(parts[3]) if parts[3] else 0,
                    'chg': chg, 'volume': int(parts[6]) if parts[6] else 0,
                    'amplitude': round((hi-lo)/lo*100,2) if lo>0 else 0,
                }
        except: pass
        time.sleep(0.15)
    return prices


CSS = '''*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0a0e17;color:#e0e0e0;min-height:100vh}
.header{background:linear-gradient(135deg,#0f1923 0%,#1a2a3f 100%);padding:24px 32px;border-bottom:1px solid #1e3a5f}
.header h1{font-size:28px;color:#fff;margin-bottom:8px}
.header h1 span{background:linear-gradient(90deg,#00d4ff,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header .stats{display:flex;gap:24px;color:#8899aa;font-size:14px}
.content{max-width:1400px;margin:0 auto;padding:24px}
.chain-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
.chain-card{background:#111b2e;border:1px solid #1a2f4a;border-radius:12px;overflow:hidden;cursor:pointer;transition:all 0.2s}
.chain-card:hover{border-color:#00d4ff;transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,212,255,0.1)}
.chain-card .card-header{padding:16px 20px 12px;background:linear-gradient(135deg,#151f33,#0e1a2a);border-bottom:1px solid #1a2f4a;display:flex;justify-content:space-between;align-items:center}
.chain-card .card-header h3{font-size:16px;color:#d0d8e8}
.chain-card .card-header .badge{background:#1e3a5f;color:#66b8ff;padding:2px 10px;border-radius:20px;font-size:12px}
.chain-card .card-desc{padding:8px 20px;color:#667788;font-size:12px;line-height:1.5;min-height:36px}
.chain-card .card-stocks{padding:8px 20px 14px;display:flex;flex-wrap:wrap;gap:4px}
.stock-tag{padding:2px 8px;border-radius:4px;font-size:11px;background:#0f1a2b;color:#8899aa}
.stock-tag.up{color:#ff4444}
.stock-tag.down{color:#00b300}
.stock-tag.limit-up{color:#ff2222;background:rgba(255,34,34,0.15);font-weight:bold}
.actions{display:flex;gap:6px;margin-top:8px;padding:0 20px 12px}
.actions a{text-decoration:none;font-size:11px;padding:4px 12px;border-radius:6px;color:#8899aa;background:#0f1a2b;border:1px solid #1a2f4a;transition:all 0.15s}
.actions a:hover{background:#1a2f4a;color:#d0d8e8}
.actions a.flow{border-color:#00d4ff33;color:#66d0ff}
.actions a.graph{border-color:#7c3aed33;color:#a78bfa}
.footer{text-align:center;padding:32px;color:#445566;font-size:12px}'''


def build_card(name, desc, count, tags_html, enc_name):
    return '''<div class="chain-card" onclick="window.open('/api/chain/''' + enc_name + '''/html','_blank')">
<div class="card-header"><h3>''' + name + '''</h3><span class="badge">''' + str(count) + '''只</span></div>
<div class="card-desc">''' + desc + '''</div>
<div class="card-stocks">''' + tags_html + '''</div>
<div class="actions">
<a class="flow" href="/api/chain/''' + enc_name + '''/html?view=flow" target="_blank" onclick="event.stopPropagation()">▶ 流程图</a>
<a class="graph" href="/api/chain/''' + enc_name + '''/html?view=graph" target="_blank" onclick="event.stopPropagation()">◈ 星图</a>
</div>
</div>'''


def build_portal_html():
    chains = query_db('SELECT id, name, description FROM industry_chains ORDER BY id')
    
    all_codes = set()
    chain_data = []
    for ch in chains:
        links = query_db(
            'SELECT cl.id, cl.name FROM chain_links cl WHERE cl.chain_id=? ORDER BY cl.sort_order',
            (ch['id'],))
        link_stocks = {}
        link_codes = set()
        for lk in links:
            stocks = query_db('SELECT cs.code FROM chain_stocks cs WHERE cs.link_id=?', (lk['id'],))
            link_stocks[lk['id']] = [dict(s) for s in stocks]
            for s in stocks:
                link_codes.add(s['code'])
                all_codes.add(s['code'])
        chain_data.append({
            'id': ch['id'], 'name': ch['name'], 'desc': ch['description'] or '',
            'links': [dict(l) for l in links], 'link_stocks': link_stocks,
            'stock_count': len(link_codes),
        })
    
    prices = get_stock_prices(list(all_codes))
    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
    
    cards = []
    for ch in chain_data:
        preview_codes = list(set(
            s['code'] for lk in ch['link_stocks'] for s in ch['link_stocks'][lk]
        ))
        tags = []
        for code in preview_codes[:8]:
            p = prices.get(code, {})
            chg = p.get('chg', 0)
            if chg > 9.5:
                cls = 'limit-up'
            elif chg > 0:
                cls = 'up'
            elif chg < 0:
                cls = 'down'
            else:
                cls = ''
            display = (p.get('name') or code)[:6]
            if chg != 0:
                display += ' {0:+.1f}%'.format(chg)
            tags.append('<span class="stock-tag {0}">{1}</span>'.format(cls, display))
        if len(preview_codes) > 8:
            tags.append('<span class="stock-tag" style="color:#445566">+{0}</span>'.format(len(preview_codes)-8))
        
        enc_name = urllib.request.quote(ch['name'])
        cards.append(build_card(ch['name'], ch['desc'][:60], ch['stock_count'], ''.join(tags), enc_name))
    
    cards_html = '\n'.join(cards)
    
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>A股产业链全景图 V2</title>
<style>''' + CSS + '''</style></head>
<body>
<div class="header">
<h1>A股产业链全景图 <span>V2</span></h1>
<div class="stats">
<span>''' + str(len(chains)) + ''' 条产业链</span>
<span>''' + str(len(all_codes)) + ''' 只成分股</span>
<span>''' + now_str + '''</span>
</div>
</div>
<div class="content"><div class="chain-grid">
''' + cards_html + '''
</div></div>
<div class="footer">A股产业链地图 V2 · ''' + now_str + '''</div>
</body>
</html>'''


if __name__ == '__main__':
    import http.server
    
    html_content = build_portal_html()
    print('HTML generated: ' + str(len(html_content)) + ' bytes')
    
    class PortalHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.rstrip('/')
            if path == '' or path == '/' or path == '/index.html':
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(html_content.encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'404')
        def log_message(self, *a): pass
    
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    server = http.server.HTTPServer(('0.0.0.0', port), PortalHandler)
    print('Portal: http://localhost:' + str(port))
    server.serve_forever()
