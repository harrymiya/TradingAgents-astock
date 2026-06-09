#!/usr/bin/env python3
"""
产业链地图 v3 - 从 astock_data.db 数据库读取产业结构数据
用法:
  python3 industry_map.py --industry 半导体 --metric chg --output out.png
  python3 industry_map.py --list                           # 列出所有产业链
  python3 industry_map.py --add-chain "新产业链" --desc "..." # 新增产业链
  python3 industry_map.py --add-link "产业链" --name "环节名" --level 0 --barrier 4 --rate 30
  python3 industry_map.py --add-stock "产业链:环节名" 000001,600519  # 添加股票
"""
import json, sqlite3, time, urllib.request, subprocess, argparse, sys
import http.server, socketserver, threading, socket
from pathlib import Path
from collections import defaultdict

DB_PATH = Path('/home/harrydolly/.hermes/astock_data.db')
BASE_DIR = Path(__file__).parent

# ==================== 数据库操作 ====================

def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db

def load_stock_names():
    """从 stocks 表加载所有股票名称映射"""
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT code, name FROM stocks")
    names = {r['code']: r['name'] for r in cur.fetchall()}
    db.close()
    return names

stock_names = load_stock_names()

def list_chains():
    """列出所有产业链及其统计"""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT c.*, 
               (SELECT COUNT(*) FROM chain_links WHERE chain_id = c.id) as link_count,
               (SELECT COUNT(DISTINCT cs.code) FROM chain_stocks cs JOIN chain_links cl ON cs.link_id = cl.id WHERE cl.chain_id = c.id) as stock_count
        FROM industry_chains c
        ORDER BY stock_count DESC
    """)
    chains = cur.fetchall()
    db.close()
    return chains

def get_chain(chain_name):
    """获取产业链完整数据"""
    db = get_db()
    cur = db.cursor()
    
    cur.execute("SELECT * FROM industry_chains WHERE name = ?", (chain_name,))
    chain = cur.fetchone()
    if not chain:
        db.close()
        return None
    
    # 获取环节
    cur.execute("SELECT * FROM chain_links WHERE chain_id = ? ORDER BY sort_order", (chain['id'],))
    links = cur.fetchall()
    
    # 获取每个环节的股票
    links_with_stocks = []
    for link in links:
        cur.execute("""
            SELECT cs.code, s.name as stock_name
            FROM chain_stocks cs
            LEFT JOIN stocks s ON cs.code = s.code
            WHERE cs.link_id = ?
            ORDER BY cs.code
        """, (link['id'],))
        stocks = cur.fetchall()
        links_with_stocks.append({
            'id': link['id'],
            'name': link['name'],
            'level': link['level'],
            'barrier': link['barrier'],
            'localization_rate': link['localization_rate'],
            'description': link['description'],
            'sort_order': link['sort_order'],
            'stocks': [{'code': s['code'], 'name': s['stock_name'] or s['code']} for s in stocks]
        })
    
    # 获取依赖关系
    cur.execute("""
        SELECT link_id, depends_on_link_id FROM chain_link_deps
        WHERE link_id IN (SELECT id FROM chain_links WHERE chain_id = ?)
    """, (chain['id'],))
    
    deps = defaultdict(list)
    for d in cur.fetchall():
        deps[d['link_id']].append(d['depends_on_link_id'])
    
    # 反查下游
    cur.execute("""
        SELECT link_id, depends_on_link_id FROM chain_link_deps
        WHERE depends_on_link_id IN (SELECT id FROM chain_links WHERE chain_id = ?)
    """, (chain['id'],))
    
    downstream = defaultdict(list)
    for d in cur.fetchall():
        downstream[d['depends_on_link_id']].append(d['link_id'])
    
    db.close()
    
    # 构建link_name->names映射(上下游名称)
    link_id_to_name = {l['id']: l['name'] for l in links_with_stocks}
    
    return {
        'id': chain['id'],
        'name': chain['name'],
        'description': chain['description'],
        'links': links_with_stocks,
        'deps': {link_id_to_name[k]: [link_id_to_name[v] for v in vals] for k, vals in deps.items()},
        'downstream': {link_id_to_name[k]: [link_id_to_name[v] for v in vals] for k, vals in downstream.items()},
    }

# ==================== 行情 ====================

def fetch_prices(codes):
    """从腾讯API获取实时行情"""
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

# ==================== 图表生成 ====================

COLOR_CYCLE = ['#7c3aed','#2563eb','#0891b2','#059669','#d97706','#dc2626','#db2777','#4f46e5','#0d9488','#ca8a04','#e11d48','#65a30d']
LEVEL_NAMES = {0: '⬆ 上游·材料/设备/芯片', 1: '↔ 中游·制造/平台', 2: '⬇ 下游·应用/终端'}
METRIC_NAMES = {'chg':'今日涨幅','yearChg':'年度涨幅','volume':'成交量','amplitude':'振幅'}

def chg_color(v):
    if v > 5: return '#00c853'
    if v > 3: return '#2ea043'
    if v > 1: return '#58a6ff'
    if v >= -1: return '#8b949e'
    if v > -3: return '#f85149'
    if v > -5: return '#d73a49'
    return '#7d1a2c'

def fmt_val(v, metric):
    if metric in ('chg','yearChg'):
        c = chg_color(v); s = f"{'+' if v>0 else ''}{v:.2f}%"
        return s, c, 'up' if v>0 else ('down' if v<0 else 'na')
    elif metric == 'volume':
        v2 = v/10000; return f"{v2:.0f}万手", '#58a6ff' if v2>10 else '#8b949e', 'na'
    return f"{v:.2f}%", chg_color(v), 'na'

def generate_html(chain, metric='chg', prices=None):
    """从数据库数据生成流程图HTML"""
    if prices is None: prices = {}
    links = chain['links']
    deps = chain.get('deps', {})
    
    # 环节颜色分配
    link_color = {}
    for i, l in enumerate(sorted(links, key=lambda x: x['sort_order'])):
        link_color[l['name']] = COLOR_CYCLE[i % len(COLOR_CYCLE)]
    
    # 按level分组
    level_groups = {0:[], 1:[], 2:[]}
    for l in links:
        level_groups[l['level']].append(l)
    
    # 侧边栏排序
    all_chains = list_chains()
    
    # 收集所有股票代码
    all_codes = []
    for l in links:
        all_codes.extend(s['code'] for s in l['stocks'])
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{chain['name']}产业链地图</title>
<style>
* {{margin:0;padding:0;box-sizing:border-box}}
body {{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#0d1117;color:#c9d1d9;height:100vh;overflow:hidden}}
.app {{display:flex;height:100vh}}
.side {{width:210px;min-width:210px;background:#161b22;border-right:1px solid #30363d;padding:12px;display:flex;flex-direction:column}}
.side h2 {{font-size:14px;color:#58a6ff;margin-bottom:10px;flex-shrink:0}}
.sl {{flex:1;overflow-y:auto}}
.sb {{display:flex;align-items:center;padding:6px 8px;margin-bottom:2px;background:#21262d;border:1px solid #30363d;border-radius:5px;color:#c9d1d9;cursor:pointer;text-decoration:none;font-size:11px;gap:4px}}
.sb:hover {{border-color:#58a6ff}}
.sb.active {{background:#1f3a5f;border-color:#58a6ff;color:#58a6ff}}
.sb .nm {{flex:1}}
.sb .ct {{font-size:10px;color:#8b949e}}
.sb .hbar {{min-width:2px;height:14px;border-radius:2px;opacity:0.5}}
.sd {{font-size:10px;color:#8b949e;padding:8px;background:#0d1117;border-radius:4px;margin-top:8px;line-height:1.5;flex-shrink:0}}
.main {{flex:1;display:flex;flex-direction:column;min-width:0}}
.hdr {{padding:10px 16px;background:#0d1117;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:10px;flex-shrink:0}}
.hdr h1 {{font-size:16px;color:#58a6ff}}
.hdr .sub {{font-size:11px;color:#8b949e}}
.ctl {{display:flex;align-items:center;gap:8px;padding:6px 16px;background:#161b22;border-bottom:1px solid #30363d;font-size:11px;flex-shrink:0}}
.ctl label {{color:#8b949e}}
.ctl select {{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:3px;padding:2px 6px;font-size:11px}}
.leg {{display:flex;align-items:center;gap:4px;margin-left:auto}}
.leg-i {{display:flex;align-items:center;gap:2px;font-size:9px;color:#8b949e}}
.leg-c {{width:7px;height:7px;border-radius:50%}}
.ut {{font-size:9px;color:#6e7681;white-space:nowrap}}
.fc {{flex:1;overflow-y:auto;padding:16px 24px}}
.frr {{display:flex;gap:20px;align-items:stretch}}
.fcc {{flex:1;min-width:0}}
.lvl {{font-size:11px;font-weight:600;color:#6e7681;margin-bottom:10px;padding:4px 8px;background:#0d1117;border-radius:4px}}
.lg {{background:#161b22;border:1px solid #30363d;border-radius:8px;margin-bottom:12px;overflow:hidden}}
.lgh {{padding:8px 10px;display:flex;justify-content:space-between;align-items:center}}
.lgn {{font-size:12px;font-weight:600}}
.lgb {{font-size:9px;padding:1px 5px;border-radius:4px}}
.st {{display:flex;justify-content:space-between;align-items:center;padding:4px 10px;font-size:11px;border-left:3px solid;margin:1px 6px;border-radius:3px;background:#0d1117}}
.st-l {{display:flex;align-items:center;gap:4px;min-width:0}}
.st-nm {{color:#e6edf3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100px}}
.st-cd {{color:#6e7681;font-size:9px;flex-shrink:0}}
.st-r {{display:flex;gap:6px;align-items:center;flex-shrink:0}}
.st-pr {{font-size:10px;color:#8b949e}}
.st-cg {{font-size:10px;font-weight:600}}
.up {{color:#3fb950}} .down {{color:#f85149}} .na {{color:#8b949e}}
.fh {{font-size:9px;color:#6e7681;padding:4px 10px 6px;display:flex;gap:10px}}
.ac {{display:flex;align-items:center;justify-content:center;width:30px;min-width:30px;color:#30363d;font-size:20px}}
</style></head>
<body>
<div class="app">
<div class="side">
<h2>🏭 产业地图</h2>
<div class="sl">
'''
    max_s = max((c['stock_count'] for c in all_chains), default=100)
    for c in all_chains:
        cls = 'active' if c['name'] == chain['name'] else ''
        bw = max(3, int(20 * c['stock_count'] / max_s))
        html += f'<a class="sb {cls}" href="#{c["name"]}"><div class="hbar" style="width:{bw}px;background:#58a6ff"></div><span class="nm">{c["name"]}</span><span class="ct">{c["stock_count"]}</span></a>\n'
    
    html += f'</div>\n<div class="sd">{chain["description"]}</div>\n</div>\n'
    html += f'''<div class="main">
<div class="hdr"><h1>{chain["name"]}</h1><span class="sub">{METRIC_NAMES.get(metric,metric)} · {len(all_codes)}只</span></div>
<div class="ctl">
<label>着色:</label>
<select id="ms">
<option value="chg"{" selected" if metric=='chg' else ""}>今日涨幅</option>
<option value="yearChg"{" selected" if metric=='yearChg' else ""}>年度涨幅</option>
<option value="volume"{" selected" if metric=='volume' else ""}>成交量</option>
<option value="amplitude"{" selected" if metric=='amplitude' else ""}>振幅</option>
</select>
<div class="leg">
<span class="leg-i"><span class="leg-c" style="background:#00c853"></span>>5%</span>
<span class="leg-i"><span class="leg-c" style="background:#2ea043"></span>3%</span>
<span class="leg-i"><span class="leg-c" style="background:#8b949e"></span>±1%</span>
<span class="leg-i"><span class="leg-c" style="background:#f85149"></span>-3%</span>
<span class="leg-i"><span class="leg-c" style="background:#7d1a2c"></span><-5%</span>
</div>
<span class="ut">🕐 {time.strftime("%m/%d %H:%M")}</span>
</div>
<div class="fc"><div class="frr">
'''
    
    for col_idx in [0, 1, 2]:
        items = level_groups[col_idx]
        html += f'<div class="fcc"><div class="lvl">{LEVEL_NAMES[col_idx]}</div>\n'
        
        for l in items:
            color = link_color[l['name']]
            upstream = deps.get(l['name'], [])
            
            html += f'''<div class="lg">
<div class="lgh">
<span class="lgn" style="color:{color}">{l['name']}</span>
<span class="lgb" style="background:{color}20;color:{color}">{"🛡"*l['barrier']} {l['localization_rate']}%</span>
</div>
'''
            for s in l['stocks']:
                p = prices.get(s['code'], {})
                name = s['name'] or stock_names.get(s['code'], s['code'])
                pr = p.get('price', 0) or 0
                v = p.get(metric, 0)
                vs, c, cls = fmt_val(v, metric)
                ps = f"{pr:.2f}" if pr else '--'
                
                html += f'''<div class="st" style="border-left-color:{c}">
<div class="st-l"><span class="st-nm">{name}</span><span class="st-cd">{s['code']}</span></div>
<div class="st-r"><span class="st-pr">{ps}</span><span class="st-cg {cls}">{vs}</span></div>
</div>
'''
            
            if upstream:
                html += f'<div class="fh"><span>← {"↔".join(upstream[:4])}</span></div>\n'
            
            html += '</div>\n'
        
        html += '</div>\n'
        
        if col_idx < 2:
            html += '<div class="ac"><div style="display:flex;flex-direction:column;align-items:center;gap:20px;opacity:0.4">'
            html += ''.join(['<span style="font-size:18px;color:#8b949e">→</span>' for _ in range(5)])
            html += '</div></div>\n'
    
    html += '</div></div></div></div></body></html>'
    return html

# ==================== 截图 ====================

def make_screenshot(chain_name, metric, output):
    print(f"📸 {chain_name} ({metric})")
    
    chain = get_chain(chain_name)
    if not chain:
        print(f"❌ 产业链 '{chain_name}' 不存在")
        return None
    
    # 收集所有股票代码
    codes = []
    for l in chain['links']:
        codes.extend(s['code'] for s in l['stocks'])
    codes = list(set(codes))
    
    print(f"  → {len(codes)} stocks")
    prices = fetch_prices(codes)
    print(f"  → {len(prices)} realtime")
    
    html = generate_html(chain, metric, prices)
    out = Path(output)
    tmp = out.with_suffix('.html')
    tmp.write_text(html, encoding='utf-8')
    
    # 随机端口启动HTTP
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    
    stop = threading.Event()
    
    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            p = self.path.split('#')[0]
            if p == '/': self.path = '/' + tmp.name
            return super().do_GET()
    
    def serve():
        try:
            with socketserver.TCPServer(('', port), H) as hd:
                hd.timeout = 1
                while not stop.is_set(): hd.handle_request()
        except: pass
    
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.3)
    
    r = subprocess.run([
        'chromium','--headless',
        f'--screenshot={out}',
        '--window-size=1600,900',
        '--no-sandbox','--disable-gpu',
        f'http://localhost:{port}/'
    ], capture_output=True, text=True, timeout=25)
    
    stop.set()
    for l in r.stderr.split('\n'):
        if 'written' in l.lower():
            print(f"  → {l.strip()}")
    
    sz = out.stat().st_size if out.exists() else 0
    print(f"  → {sz//1024}KB")
    return str(out)

# ==================== 命令行管理 ====================

def cmd_list():
    chains = list_chains()
    print(f"\n{'='*60}")
    print(f"{'产业链':<16} {'环节':>4} {'股票':>5}")
    print(f"{'-'*60}")
    for c in chains:
        print(f"  {c['name']:<14} {c['link_count']:>4} {c['stock_count']:>5}")
    print(f"{'='*60}")

def cmd_add_chain(name, desc):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO industry_chains (name, description) VALUES (?, ?)", (name, desc))
        db.commit()
        print(f"✅ 新增产业链: {name}")
    except Exception as e:
        print(f"❌ {e}")
    db.close()

def cmd_add_link(chain_name, link_name, level, barrier, rate, desc=""):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM industry_chains WHERE name = ?", (chain_name,))
    row = cur.fetchone()
    if not row:
        print(f"❌ 产业链 '{chain_name}' 不存在")
        db.close()
        return
    chain_id = row['id']
    try:
        cur.execute("INSERT INTO chain_links (chain_id, name, level, barrier, localization_rate, description) VALUES (?,?,?,?,?,?)",
                    (chain_id, link_name, level, barrier, rate, desc))
        db.commit()
        print(f"✅ 新增环节: {chain_name} → {link_name} (level={level})")
    except Exception as e:
        print(f"❌ {e}")
    db.close()

def cmd_add_dep(chain_name, link_name, dep_name):
    """设置环节的上游依赖"""
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM industry_chains WHERE name = ?", (chain_name,))
    c = cur.fetchone()
    if not c: print(f"❌ 产业链不存在"); db.close(); return
    chain_id = c['id']
    cur.execute("SELECT id FROM chain_links WHERE chain_id = ? AND name = ?", (chain_id, link_name))
    l = cur.fetchone()
    cur.execute("SELECT id FROM chain_links WHERE chain_id = ? AND name = ?", (chain_id, dep_name))
    d = cur.fetchone()
    if not l or not d: print(f"❌ 环节不存在"); db.close(); return
    try:
        cur.execute("INSERT OR IGNORE INTO chain_link_deps (link_id, depends_on_link_id) VALUES (?,?)", (l['id'], d['id']))
        db.commit()
        print(f"✅ 依赖: {link_name} → 上游 {dep_name}")
    except Exception as e:
        print(f"❌ {e}")
    db.close()

def cmd_add_stock(chain_name, link_name, codes_str):
    codes = [c.strip() for c in codes_str.split(',') if c.strip()]
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM industry_chains WHERE name = ?", (chain_name,))
    c = cur.fetchone()
    if not c: print(f"❌ 产业链不存在"); db.close(); return
    chain_id = c['id']
    cur.execute("SELECT id FROM chain_links WHERE chain_id = ? AND name = ?", (chain_id, link_name))
    l = cur.fetchone()
    if not l: print(f"❌ 环节不存在"); db.close(); return
    
    added = 0
    for code in codes:
        try:
            cur.execute("INSERT OR IGNORE INTO chain_stocks (link_id, code) VALUES (?,?)", (l['id'], code))
            if cur.rowcount: added += 1
        except: pass
    
    # 也存到stocks表（如果没有）
    for code in codes:
        cur.execute("INSERT OR IGNORE INTO stocks (code, name) VALUES (?,?)", (code, code))
    
    db.commit()
    print(f"✅ 添加 {added}/{len(codes)} 只股票到 {chain_name}/{link_name}")
    db.close()

# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(description='产业链地图')
    parser.add_argument('--industry', help='产业链名（截图用）')
    parser.add_argument('--metric', default='chg', choices=['chg','yearChg','volume','amplitude'])
    parser.add_argument('--output', default='screenshot.png')
    
    # 管理命令
    parser.add_argument('--list', action='store_true', help='列出所有产业链')
    parser.add_argument('--add-chain', help='新增产业链')
    parser.add_argument('--add-desc', help='产业链描述')
    parser.add_argument('--add-link', help='新增环节到产业链')
    parser.add_argument('--link-name', help='环节名')
    parser.add_argument('--level', type=int, default=1, help='环节层级 0=上游 1=中游 2=下游')
    parser.add_argument('--barrier', type=int, default=3, help='壁垒 1-5')
    parser.add_argument('--rate', type=int, default=50, help='国产化率 %%')
    parser.add_argument('--add-stock', help='添加股票: "产业链:环节名"')
    parser.add_argument('--codes', help='股票代码，逗号分隔')
    parser.add_argument('--add-dep', help='设置上游依赖: "产业链:环节名=上游环节"')
    
    args = parser.parse_args()
    
    if args.list:
        cmd_list()
        return
    
    if args.add_chain:
        cmd_add_chain(args.add_chain, args.add_desc or '')
        return
    
    if args.add_link:
        cmd_add_link(args.add_chain or args.industry, args.link_name, args.level, args.barrier, args.rate)
        return
    
    if args.add_stock:
        if ':' in args.add_stock:
            parts = args.add_stock.split(':')
            cmd_add_stock(parts[0], parts[1], args.codes or '')
        return
    
    if args.add_dep:
        if '=' in args.add_dep:
            parts = args.add_dep.split('=')
            link_parts = parts[0].split(':')
            if len(link_parts) == 2:
                cmd_add_dep(link_parts[0], link_parts[1], parts[1])
        return
    
    # 默认：截图
    if args.industry:
        out = make_screenshot(args.industry, args.metric, args.output)
        if out:
            print(f"\n✅ {out}")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
