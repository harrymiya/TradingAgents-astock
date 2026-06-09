"""
industry_map/render.py — 从数据库读取产业链数据，渲染为流程图HTML

使用方式：
  from industry_map.render import render_chain
  html = render_chain("半导体", metric="chg", prices=实时行情字典)
"""

import time
from .db import ChainManager, ChainDB

COLOR_CYCLE = ['#7c3aed','#2563eb','#0891b2','#059669','#d97706',
               '#dc2626','#db2777','#4f46e5','#0d9488','#ca8a04',
               '#e11d48','#65a30d','#f97316','#6366f1']

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
        c = chg_color(v)
        s = f"{'+' if v>0 else ''}{v:.2f}%"
        return s, c, 'up' if v>0 else ('down' if v<0 else 'na')
    elif metric == 'volume':
        v2 = v/10000
        return f"{v2:.0f}万手", '#58a6ff' if v2>10 else '#8b949e', 'na'
    return f"{v:.2f}%", chg_color(v), 'na'

def render_chain(chain_name, metric='chg', prices=None):
    """生成产业链流程图HTML"""
    chain = ChainManager.get_chain(chain_name)
    if not chain:
        return f"<html><body><h1>产业链 '{chain_name}' 不存在</h1></body></html>"
    
    if prices is None: prices = {}
    links = chain['links']
    deps = chain.get('deps', {})
    
    # 环节颜色
    link_color = {}
    for i, l in enumerate(sorted(links, key=lambda x: x['sort_order'])):
        link_color[l['name']] = COLOR_CYCLE[i % len(COLOR_CYCLE)]
    
    # 按level分组
    level_groups = {0:[], 1:[], 2:[]}
    for l in links:
        level_groups[l['level']].append(l)
    
    # 侧边栏
    all_chains = ChainManager.list_chains()
    stock_names = ChainDB.load_stock_names()
    
    all_codes = [s['code'] for l in links for s in l['stocks']]
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
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
.sb.active {{background:#1f3a5f;border-color:#58a6ff;color:#58a6ff;font-weight:600}}
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
<body><div class="app">
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
<div class="hdr"><h1>{chain["name"]}</h1><span class="sub">{METRIC_NAMES.get(metric,metric)} · {len(set(all_codes))}只</span></div>
<div class="ctl"><label>着色:</label>
<select id="ms"><option value="chg"{" selected" if metric=='chg' else ""}>今日涨幅</option><option value="yearChg"{" selected" if metric=='yearChg' else ""}>年度涨幅</option><option value="volume"{" selected" if metric=='volume' else ""}>成交量</option><option value="amplitude"{" selected" if metric=='amplitude' else ""}>振幅</option></select>
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
<div class="lgh"><span class="lgn" style="color:{color}">{l['name']}</span>
<span class="lgb" style="background:{color}20;color:{color}">{"🛡"*l['barrier']} {l['localization_rate']}%</span></div>
'''
            for s in l['stocks']:
                p = prices.get(s['code'], {})
                name = stock_names.get(s['code'], s['stock_name'] or s['code'])
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
                html += f'<div class="fh"><span>← {" ↔ ".join(upstream[:4])}</span></div>\n'
            html += '</div>\n'
        html += '</div>\n'
        if col_idx < 2:
            html += '<div class="ac"><div style="display:flex;flex-direction:column;align-items:center;gap:20px;opacity:0.4">'
            html += ''.join(['<span style="font-size:18px;color:#8b949e">→</span>' for _ in range(5)])
            html += '</div></div>\n'
    html += '</div></div></div></div></body></html>'
    return html
