"""
industry_map/server.py — API Server for Web版产业链地图

提供JSON API给React前端查询DB数据，支持实时行情。

启动：
  python3 -m industry_map.server [--port 8896]

API：
  GET /api/chains              — 所有产业链列表
  GET /api/chain/{name}        — 产业链完整数据
  GET /api/chain/{name}/html   — HTML流程图（直接嵌入）
"""

import json, urllib.request, time, sys, os
from http.server import HTTPServer, BaseHTTPRequestHandler
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from industry_map.db import ChainManager, ChainDB

def fetch_prices(codes):
    prices = {}
    for i in range(0, len(codes), 30):
        batch = codes[i:i+30]
        q = [('sh' if c.startswith('6') else 'sz') + c for c in batch]
        try:
            resp = urllib.request.urlopen(
                'https://qt.gtimg.cn/q=' + ','.join(q) + '&_=' + str(int(time.time()*1000)),
                timeout=10
            )
            for line in resp.read().decode('gbk').split(';'):
                if not line.strip() or '~' not in line: continue
                p = line.split('~')
                raw = p[0].replace('sh','').replace('sz','')
                chg = float(p[32]) if len(p)>32 and p[32] else 0
                hi = float(p[33]) if len(p)>33 and p[33] else 0
                lo = float(p[34]) if len(p)>34 and p[34] else 0
                prices[raw] = {
                    'price': float(p[3]) if p[3] else 0,
                    'chg': chg,
                    'yearChg': float(p[69]) if len(p)>69 and p[69] else 0,
                    'volume': int(p[6]) if p[6] else 0,
                    'amplitude': round((hi-lo)/lo*100,2) if lo>0 else 0,
                }
        except: pass
        time.sleep(0.15)
    return prices

class APIHandler(BaseHTTPRequestHandler):
    def _json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def _html(self, html):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def _error(self, msg, code=404):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({'error': msg}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
    
    def do_GET(self):
        path = self.path.rstrip('/')
        
        # /api/chains — 所有产业链列表
        if path == '/api/chains':
            chains = ChainManager.list_chains()
            stock_names = ChainDB.load_stock_names()
            self._json({'chains': chains, 'total': len(chains)})
        
        # /api/chain/{name} — 产业链完整数据+实时行情
        elif path.startswith('/api/chain/') and path.endswith('/data'):
            name = path[11:-5]
            chain = ChainManager.get_chain(name)
            if not chain:
                self._error(f"产业链 '{name}' 不存在")
                return
            # 收集股票代码
            codes = list(set(s['code'] for l in chain['links'] for s in l['stocks']))
            metric = self.path.split('?')[1].split('=')[1] if '?metric=' in self.path else 'chg'
            prices = fetch_prices(codes)
            self._json({'chain': chain, 'prices': prices, 'metric': metric})
        
        # /api/chain/{name} 或 /api/chain/{name}/ — 产业链信息
        elif path.startswith('/api/chain/'):
            name = path[11:]
            chain = ChainManager.get_chain(name)
            if not chain:
                self._error(f"产业链 '{name}' 不存在")
                return
            self._json({'chain': chain})
        
        # /api/stock-names — 股票名称映射
        elif path == '/api/stock-names':
            self._json(ChainDB.load_stock_names())
        
        # /api/industries — 行业分类
        elif path == '/api/industries':
            from industry_map.db import IndustryManager
            self._json({'industries': IndustryManager.list_industries()})
        
        else:
            self._error("Not found")
    
    def log_message(self, *a): pass

def main():
    port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == '--port' else 8896
    server = HTTPServer(('0.0.0.0', port), APIHandler)
    print(f"🌐 Industry Map API Server: http://localhost:{port}")
    print(f"   GET /api/chains       — 所有产业链")
    print(f"   GET /api/chain/半导体  — 半导体详情")
    print(f"   GET /api/chain/半导体/data — 半导体+实时行情")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == '__main__':
    main()
