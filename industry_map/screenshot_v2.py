#!/usr/bin/env python3
"""
industry_map/screenshot_v2.py — V2截图入口

用法:
  python3 -m industry_map.screenshot_v2 "英伟达(NVIDIA)" --mode graph
  python3 -m industry_map.screenshot_v2 "CPO共封装光学(全景)" --mode flow
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from industry_map.render_v2 import render_v2
from industry_map.db import ChainManager
from industry_map.screenshot import _fetch_prices, TMP_DIR, _find_free_port

def capture_v2(chain_name, metric='chg', mode='flow', output=None):
    import subprocess, time, threading, http.server, socketserver
    from pathlib import Path
    
    chain = ChainManager.get_chain(chain_name)
    if not chain:
        print("❌ 产业链 '%s' 不存在" % chain_name)
        return ''
    
    all_codes = list(set(s['code'] for l in chain['links'] for s in l['stocks']))
    print("📸 V2 %s (%s) · %d只 · %s模式" % (chain_name, metric, len(all_codes), mode))
    
    prices = _fetch_prices(all_codes)
    print("  → 行情 %d只" % len(prices))
    
    html = render_v2(chain_name, metric, prices, mode=mode)
    
    if output:
        out_path = Path(output)
    else:
        safe = chain_name.replace('/', '_').replace('(', '').replace(')', '')
        safe = ''.join(c if c.isalnum() or c in '_-' else '_' for c in safe)
        out_path = TMP_DIR / ('%s_%s_v2_%s.png' % (safe, metric, mode))
    
    tmp_html = out_path.with_suffix('.html')
    tmp_html.write_text(html, encoding='utf-8')
    
    old_cwd = os.getcwd()
    os.chdir(str(tmp_html.parent))
    
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
    
    # 动态分辨率
    sc = len(all_codes)
    if sc > 60: w, h = 3600, 2400
    elif sc > 30: w, h = 2800, 2000
    elif sc > 20: w, h = 2400, 1800
    else: w, h = 2000, 1400
    
    subprocess.run(['chromium', '--headless', '--screenshot='+str(out_path),
        '--window-size=%d,%d'%(w,h), '--no-sandbox', '--disable-gpu',
        'http://localhost:%d/'%port], capture_output=True, timeout=25)
    
    stop.set()
    os.chdir(old_cwd)
    
    sz = out_path.stat().st_size if out_path.exists() else 0
    print("  → %dKB | %s" % (sz//1024, out_path))
    return str(out_path)


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        print("用法: python3 -m industry_map.screenshot_v2 <链名> [--mode flow|graph] [--metric chg]")
        sys.exit(1)
    
    name = args[0]
    metric = 'chg'
    mode = 'flow'
    
    if '--metric' in args:
        mi = args.index('--metric')
        if mi+1 < len(args): metric = args[mi+1]
    if '--mode' in args:
        mi = args.index('--mode')
        if mi+1 < len(args): mode = args[mi+1]
    
    out = capture_v2(name, metric, mode)
    if out:
        print("\nMEDIA:%s" % out)
