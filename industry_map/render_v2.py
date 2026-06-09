#!/usr/bin/env python3
"""
industry_map/render_v2.py — 新一代产业链渲染器 V2
"""
import time, json
from .db import ChainManager, ChainDB

COLOR_CYCLE = ['#7c3aed','#2563eb','#0891b2','#059669','#d97706',
               '#dc2626','#db2777','#4f46e5','#0d9488','#ca8a04',
               '#e11d48','#65a30d','#f97316','#6366f1']

LEVEL_NAMES = {0: '\u2b06 \u4e0a\u6e38', 1: '\u2194 \u4e2d\u6e38', 2: '\u2b07 \u4e0b\u6e38'}
METRIC_NAMES = {'chg':'\u4eca\u65e5\u6da8\u5e45','yearChg':'\u5e74\u5ea6\u6da8\u5e45','volume':'\u6210\u4ea4\u91cf','amplitude':'\u632f\u5e45'}

def _chg_border(v):
    if v > 5: return '#00c853'
    if v > 3: return '#2ea043'
    if v > 1: return '#58a6ff'
    if v >= -1: return '#8b949e'
    if v > -3: return '#f85149'
    if v > -5: return '#d73a49'
    return '#7d1a2c'

def render_v2(chain_name, metric='chg', prices=None, mode='flow'):
    chain = ChainManager.get_chain(chain_name)
    if not chain:
        return "<html><body><h1>\u4ea7\u4e1a\u94fe '" + chain_name + "' \u4e0d\u5b58\u5728</h1></body></html>"
    if prices is None: prices = {}
    
    links = chain['links']
    deps = chain.get('deps', {})
    all_chains = ChainManager.list_chains()
    stock_names = ChainDB.load_stock_names()
    all_codes = list(set(s['code'] for l in links for s in l['stocks']))
    now_str = time.strftime("%m/%d %H:%M")
    metric_name = METRIC_NAMES.get(metric, metric)
    
    chain_heat = {c['name']: c['stock_count'] for c in all_chains}
    client_chains = [c for c in all_chains if c['name'].startswith('\u3010\u5ba2\u6237\u3011')]
    normal_chains = [c for c in all_chains if not c['name'].startswith('\u3010\u5ba2\u6237\u3011')]
    client_chains.sort(key=lambda x: chain_heat.get(x['name'], 0), reverse=True)
    normal_chains.sort(key=lambda x: chain_heat.get(x['name'], 0), reverse=True)
    
    link_color = {}
    for i, l in enumerate(sorted(links, key=lambda x: x['sort_order'])):
        link_color[l['name']] = COLOR_CYCLE[i % len(COLOR_CYCLE)]
    
    # 构建数据
    links_json = []
    for l in links:
        stocks = []
        for s in l['stocks']:
            code = s['code']
            name = stock_names.get(code, s['stock_name'] or code)
            p = prices.get(code, {})
            chg_val = p.get(metric, 0) or 0
            price_val = p.get('price', 0) or 0
            chg_str = ("+" if chg_val>0 else "") + "{:.2f}%".format(chg_val)
            cls = 'up' if chg_val>0 else ('down' if chg_val<0 else 'na')
            bc = _chg_border(chg_val)
            stocks.append({"code":code,"name":name,"price":round(price_val,2),"chg":round(chg_val,2),"chgStr":chg_str,"cls":cls,"borderColor":bc})
        up = deps.get(l['name'], [])
        links_json.append({"id": l['id'], "name": l['name'], "level": l['level'], "barrier": l['barrier'], "rate": l['localization_rate'], "color": link_color[l['name']], "stocks": stocks, "deps": up})
    
    graph_nodes = []
    graph_links = []
    seen_stocks = set()
    for l in links:
        graph_nodes.append({"id":"link_%d"%l['id'],"name":l['name'],"type":"link","color":link_color[l['name']],"barrier":l['barrier'],"rate":l['localization_rate'],"stock_count":len(l['stocks'])})
        for s in l['stocks']:
            code = s['code']
            if code not in seen_stocks:
                seen_stocks.add(code)
                name = stock_names.get(code, s['stock_name'] or code)
                p = prices.get(code, {}); chg_val = p.get(metric, 0) or 0
                graph_nodes.append({"id":"stock_%s"%code,"name":name,"code":code,"type":"stock","chg":round(chg_val,2)})
            graph_links.append({"source":"link_%d"%l['id'],"target":"stock_%s"%code,"type":"has"})
        for u in deps.get(l['name'], []):
            for l2 in links:
                if l2['name'] == u:
                    graph_links.append({"source":"link_%d"%l2['id'],"target":"link_%d"%l['id'],"type":"dep"})
                    break
    
    def _sidebar_items(chains, tag):
        h = ''
        mh = max([chain_heat.get(c['name'], 1) for c in chains]) if chains else 1
        for c in chains:
            ht = chain_heat.get(c['name'], 1)
            bw = max(2, int(16 * ht / mh))
            cl = 'active' if c['name'] == chain_name else ''
            label = '\u5ba2' if tag=='client' else '\u94fe'
            h += '<a class="sb %s" href="#%s"><span class="hbar" style="width:%dpx"></span><span class="tag tag-%s">%s</span><span class="nm">%s</span><span class="ct">%d</span><span class="hot">%d</span></a>\n' % (cl, c['name'], bw, tag, label, c['name'], c['stock_count'], ht)
        return h
    
    sidebar_client = _sidebar_items(client_chains, 'client')
    sidebar_chain = _sidebar_items(normal_chains, 'chain')
    
    # 生成 selected 标记
    sel_chg = ' selected' if metric=='chg' else ''
    sel_yc = ' selected' if metric=='yearChg' else ''
    sel_vol = ' selected' if metric=='volume' else ''
    sel_amp = ' selected' if metric=='amplitude' else ''
    sel_flow = ' selected' if mode=='flow' else ''
    sel_graph = ' selected' if mode=='graph' else ''
    
    data_json = json.dumps({"links":links_json,"graphNodes":graph_nodes,"graphLinks":graph_links,"levels":LEVEL_NAMES}, ensure_ascii=False)
    
    # 用字典 format（避免 % 冲突）
    ctx = dict(
        title = chain['name'],
        sidebar_client = sidebar_client,
        sidebar_chain = sidebar_chain,
        chain_count = len(all_chains),
        chain_name = chain['name'],
        metric_name = metric_name,
        stock_count = len(all_codes),
        sel_chg = sel_chg,
        sel_yc = sel_yc,
        sel_vol = sel_vol,
        sel_amp = sel_amp,
        sel_flow = sel_flow,
        sel_graph = sel_graph,
        now_str = now_str,
        data_json = data_json,
        mode = mode,
        metric = metric,
    )
    
    return HTML_TPL.format(**ctx)


HTML_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} | 产业图谱V2</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#0d1117;color:#c9d1d9;height:100vh;overflow:hidden}}
.app{{display:flex;height:100vh}}
.side{{width:240px;min-width:240px;background:#161b22;border-right:1px solid #30363d;display:flex;flex-direction:column}}
.side-h{{padding:10px 12px;border-bottom:1px solid #30363d;font-size:13px;font-weight:600;color:#58a6ff;display:flex;align-items:center;gap:6px;flex-shrink:0}}
.side-tab{{display:flex;border-bottom:1px solid #30363d;flex-shrink:0}}
.stb{{flex:1;padding:6px;font-size:10px;text-align:center;cursor:pointer;color:#8b949e;border-bottom:2px solid transparent;user-select:none}}
.stb.active{{color:#58a6ff;border-bottom-color:#58a6ff;background:#1f3a5f20}}
.sl{{flex:1;overflow-y:auto;padding:4px 0}}
.sb{{display:flex;align-items:center;padding:5px 8px;margin:1px 4px;background:#21262d;border:1px solid #30363d;border-radius:5px;color:#c9d1d9;cursor:pointer;text-decoration:none;font-size:10px;gap:3px;transition:border-color .15s}}
.sb:hover{{border-color:#58a6ff}}
.sb.active{{background:#1f3a5f;border-color:#58a6ff;color:#58a6ff;font-weight:600}}
.sb .nm{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.sb .ct{{font-size:9px;color:#8b949e}}
.sb .hbar{{min-width:2px;height:12px;border-radius:2px;background:#58a6ff;opacity:0.5}}
.sb .hot{{font-size:8px;color:#f0883e;padding:0 3px}}
.sb .tag{{font-size:8px;padding:1px 4px;border-radius:3px;margin-right:3px}}
.tag-client{{background:#7c3aed40;color:#a78bfa}}
.tag-chain{{background:#2563eb40;color:#60a5fa}}
.main{{flex:1;display:flex;flex-direction:column;min-width:0}}
.hdr{{padding:8px 16px;background:#0d1117;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:10px;flex-shrink:0;flex-wrap:wrap}}
.hdr h1{{font-size:15px;color:#58a6ff;flex-shrink:0}}
.hdr .sub{{font-size:10px;color:#8b949e}}
.ctl{{display:flex;align-items:center;gap:6px;padding:4px 16px;background:#161b22;border-bottom:1px solid #30363d;font-size:10px;flex-shrink:0;flex-wrap:wrap}}
.ctl label{{color:#8b949e;font-size:10px}}
.ctl select{{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:3px;padding:1px 4px;font-size:10px}}
.ctl-btn{{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:3px;padding:1px 6px;font-size:10px;cursor:pointer}}
.ctl-btn:hover{{border-color:#58a6ff;color:#58a6ff}}
.leg{{display:flex;align-items:center;gap:2px;margin-left:auto}}
.leg-i{{display:flex;align-items:center;gap:2px;font-size:8px;color:#8b949e}}
.leg-c{{width:6px;height:6px;border-radius:50%}}
.ut{{font-size:8px;color:#6e7681;white-space:nowrap}}
.fc{{flex:1;overflow:auto;padding:12px 16px;position:relative}}
.frw{{display:flex;gap:16px;align-items:stretch;min-height:100%}}
.fcc{{flex:1;min-width:200px}}
.lvl{{font-size:10px;font-weight:600;color:#6e7681;margin-bottom:6px;padding:3px 6px;background:#0d1117;border-radius:4px;text-align:center}}
.lg{{background:#161b22;border:1px solid #30363d;border-radius:8px;margin-bottom:10px;overflow:hidden}}
.lgh{{padding:6px 10px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none}}
.lgh:hover{{background:#1c2333}}
.lgn{{font-size:11px;font-weight:600;gap:4px;display:flex;align-items:center}}
.lgn .fold-icon{{font-size:8px;color:#6e7681;width:12px;text-align:center}}
.lgb{{font-size:8px;padding:1px 4px;border-radius:4px}}
.lg-body{{overflow:hidden;transition:max-height 0.25s ease;max-height:2000px}}
.lg-body.collapsed{{max-height:0}}
.st{{display:flex;justify-content:space-between;align-items:center;padding:3px 8px;font-size:10px;border-left:3px solid;margin:1px 6px;border-radius:3px;background:#0d1117}}
.st-l{{display:flex;align-items:center;gap:4px;min-width:0}}
.st-nm{{color:#e6edf3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:90px;font-size:10px}}
.st-cd{{color:#6e7681;font-size:8px;flex-shrink:0}}
.st-r{{display:flex;gap:4px;align-items:center;flex-shrink:0}}
.st-pr{{font-size:9px;color:#8b949e}}
.st-cg{{font-size:9px;font-weight:600}}
.up{{color:#3fb950}} .down{{color:#f85149}} .na{{color:#8b949e}}
.fh{{font-size:8px;color:#6e7681;padding:2px 10px 4px;display:flex;gap:6px}}
.ac{{display:flex;align-items:center;justify-content:center;width:24px;min-width:24px;color:#30363d;font-size:16px}}
#graph-svg{{width:100%;height:100%}}
.node-link{{cursor:pointer}}
.node-link circle{{stroke-width:2px;transition:r 0.2s}}
.node-link:hover circle{{stroke:#58a6ff;stroke-width:3px}}
.node-link text{{font-size:10px;fill:#c9d1d9;pointer-events:none;text-anchor:middle;dominant-baseline:central}}
.node-link.stock-node text{{font-size:8px;fill:#8b949e}}
.link-line{{stroke:#30363d;stroke-width:1;stroke-opacity:0.6}}
.link-line.dep{{stroke-dasharray:3,3;stroke:#58a6ff;stroke-opacity:0.4}}
.legend-box{{position:absolute;bottom:12px;right:16px;background:#161b22e0;border:1px solid #30363d;border-radius:6px;padding:6px 10px;font-size:9px;color:#8b949e;z-index:10;line-height:1.6}}
.fold-bar{{display:flex;gap:4px;padding:2px 0}}
</style>
</head>
<body>
<div class="app">
<div class="side">
<div class="side-h">🏭 产业图谱 · 热力排序</div>
<div class="side-tab">
<div class="stb active" onclick="switchTab('client')">目标客户</div>
<div class="stb" onclick="switchTab('chain')">行业链</div>
</div>
<div class="sl" id="sidebar-client">{sidebar_client}</div>
<div class="sl" id="sidebar-chain" style="display:none">{sidebar_chain}</div>
<div class="side-h" style="border-top:1px solid #30363d;border-bottom:none;font-size:10px;color:#6e7681;padding:6px 12px">{chain_count}个图谱 · 热度=股票数</div>
</div>
<div class="main">
<div class="hdr">
<h1>{chain_name}</h1>
<span class="sub">{metric_name} · {stock_count}只</span>
</div>
<div class="ctl">
<label>着色:</label>
<select id="ms" onchange="changeMetric(this.value)">
<option value="chg"{sel_chg}>今日涨幅</option>
<option value="yearChg"{sel_yc}>年度涨幅</option>
<option value="volume"{sel_vol}>成交量</option>
<option value="amplitude"{sel_amp}>振幅</option>
</select>
<label>视图:</label>
<select id="vw" onchange="changeView(this.value)">
<option value="flow"{sel_flow}>链式图</option>
<option value="graph"{sel_graph}>节点图</option>
</select>
<div class="fold-bar">
<button class="ctl-btn" onclick="toggleAll(true)">全展开</button>
<button class="ctl-btn" onclick="toggleAll(false)">全收起</button>
</div>
<div class="leg">
<span class="leg-i"><span class="leg-c" style="background:#00c853"></span>&gt;5</span>
<span class="leg-i"><span class="leg-c" style="background:#2ea043"></span>3</span>
<span class="leg-i"><span class="leg-c" style="background:#8b949e"></span>±1</span>
<span class="leg-i"><span class="leg-c" style="background:#f85149"></span>-3</span>
<span class="leg-i"><span class="leg-c" style="background:#7d1a2c"></span>&lt;-5</span>
</div>
<span class="ut">{now_str}</span>
</div>
<div class="fc" id="main-content"></div>
</div>
</div>
<script id="app-data" type="application/json">{data_json}</script>
<script>
var _DATA = JSON.parse(document.getElementById('app-data').textContent);
var currentMode = '{mode}';
var currentMetric = '{metric}';
var simulation = null;

function switchTab(tab) {{
  document.querySelectorAll('.stb')[0].classList.toggle('active',tab==='client');
  document.querySelectorAll('.stb')[1].classList.toggle('active',tab==='chain');
  document.getElementById('sidebar-client').style.display = tab==='client'?'':'none';
  document.getElementById('sidebar-chain').style.display = tab==='chain'?'':'none';
}}

function changeMetric(v){{window.location.href=window.location.pathname+'?mode='+currentMode+'&metric='+v;}}
function changeView(v){{currentMode=v;renderMain();}}
function toggleAll(e){{document.querySelectorAll('.lg-body').forEach(function(el){{el.classList.toggle('collapsed',!e);}});document.querySelectorAll('.fold-icon').forEach(function(el){{el.textContent=e?'\\u25BC':'\\u25B6';}});}}
function toggleLink(el){{var b=el.nextElementSibling;b.classList.toggle('collapsed');el.querySelector('.fold-icon').textContent=b.classList.contains('collapsed')?'\\u25B6':'\\u25BC';}}

function renderMain(){{
  var c=document.getElementById('main-content');c.innerHTML='';
  if(currentMode==='flow')renderFlow(c);else renderGraph(c);
}}

function renderFlow(container){{
  var d=_DATA,lvls={{0:[],1:[],2:[]}};
  d.links.forEach(function(l){{if(l.level in lvls)lvls[l.level].push(l);}});
  var h='<div class="frw">';
  Object.keys(lvls).forEach(function(lev,idx){{
    h+='<div class="fcc"><div class="lvl">'+(d.levels[lev]||'')+'</div>';
    lvls[lev].forEach(function(l){{
      var s='';for(var i=0;i<Math.min(l.barrier,5);i++)s+='🛡';
      h+='<div class="lg"><div class="lgh" onclick="toggleLink(this)"><span class="lgn"><span class="fold-icon">\\u25BC</span>'+l.name+'</span><span class="lgb" style="background:'+l.color+'20;color:'+l.color+'">'+s+' '+l.rate+'%</span></div><div class="lg-body">';
      l.stocks.forEach(function(s){{h+='<div class="st" style="border-left-color:'+s.borderColor+'"><div class="st-l"><span class="st-nm">'+s.name+'</span><span class="st-cd">'+s.code+'</span></div><div class="st-r"><span class="st-pr">'+((s.price&&s.price!=='--')?s.price:'--')+'</span><span class="st-cg '+s.cls+'">'+s.chgStr+'</span></div></div>';}});
      if(l.deps&&l.deps.length)h+='<div class="fh">\\u2190 '+l.deps.slice(0,4).join(' \\u2194 ')+'</div>';
      h+='</div></div>';
    }});
    h+='</div>';
    if(idx<2){{h+='<div class="ac"><div style="display:flex;flex-direction:column;align-items:center;gap:15px;opacity:0.3">';for(var i=0;i<5;i++)h+='<span style="font-size:16px;color:#8b949e">\\u2192</span>';h+='</div></div>';}}
  }});
  h+='</div>';container.innerHTML=h;
}}

function renderGraph(container){{
  container.innerHTML='<svg id="graph-svg"></svg><div class="legend-box"><div class="item"><span style="color:#58a6ff">\\u25CF</span> \\u73AF\\u8282</div><div class="item"><span style="color:#8b949e">\\u25CF</span> \\u80A1\\u7968</div><div class="item"><span style="border-bottom:2px dashed #58a6ff">---</span> \\u4F9D\\u8D56</div></div>';
  var svgEl=document.getElementById('graph-svg'),w=container.clientWidth||800,h=container.clientHeight||500;
  svgEl.setAttribute('width',w);svgEl.setAttribute('height',h);
  var svg=d3.select('#graph-svg'),g=svg.append('g');
  svg.call(d3.zoom().scaleExtent([0.2,4]).on('zoom',function(e){{g.attr('transform',e.transform);}}));
  var dd=JSON.parse(JSON.stringify(_DATA)),nodes=dd.graphNodes,links=dd.graphLinks;
  links.forEach(function(l){{l.source=l.source;l.target=l.target;}});
  var sim=d3.forceSimulation(nodes)
    .force('link',d3.forceLink(links).id(function(d){{return d.id;}}).distance(function(d){{return d.type==='dep'?150:90;}}))
    .force('charge',d3.forceManyBody().strength(function(d){{return d.type==='link'?-400:-100;}}))
    .force('center',d3.forceCenter(w/2,h/2))
    .force('collision',d3.forceCollide(function(d){{return d.type==='link'?90:25;}}));
  var linkEl=g.append('g').selectAll('line').data(links).join('line').attr('class',function(d){{return 'link-line '+d.type;}});
  var nodeEl=g.append('g').selectAll('g').data(nodes).join('g')
    .attr('class',function(d){{return 'node-link '+(d.type==='stock'?'stock-node':'link-node');}})
    .call(d3.drag().on('start',function(e,d){{if(!e.active)sim.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;}}).on('drag',function(e,d){{d.fx=e.x;d.fy=e.y;}}).on('end',function(e,d){{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}}));
  nodeEl.filter(function(d){{return d.type==='link';}}).each(function(d){{
    var g2=d3.select(this);g2.append('circle').attr('r',Math.min(35+d.stock_count*2,65)).attr('fill',d.color+'30').attr('stroke',d.color).attr('stroke-width',2);
    g2.append('text').attr('dy',-4).attr('font-size','11px').attr('fill','#e6edf3').text(d.name.length>7?d.name.slice(0,6)+'...':d.name);
    g2.append('text').attr('dy',12).attr('font-size','9px').attr('fill','#8b949e').text(d.stock_count+'\u53EA');
  }});
  nodeEl.filter(function(d){{return d.type==='stock';}}).each(function(d){{
    var g2=d3.select(this),c='#8b949e';
    if(d.chg>5)c='#00c853';else if(d.chg>3)c='#2ea043';else if(d.chg>1)c='#58a6ff';else if(d.chg>=-1)c='#8b949e';else if(d.chg>-3)c='#f85149';else if(d.chg>-5)c='#d73a49';else c='#7d1a2c';
    g2.append('circle').attr('r',5).attr('fill',c).attr('stroke','#30363d');g2.append('text').attr('dy',-7).attr('font-size','8px').text(d.name.length>5?d.name.slice(0,4)+'...':d.name);
  }});
  sim.on('tick',function(){{linkEl.attr('x1',function(d){{return d.source.x;}}).attr('y1',function(d){{return d.source.y;}}).attr('x2',function(d){{return d.target.x;}}).attr('y2',function(d){{return d.target.y;}});nodeEl.attr('transform',function(d){{return 'translate('+d.x+','+d.y+')';}});}});
  simulation=sim;
}}
window.addEventListener('resize',function(){{if(currentMode==='graph')renderGraph();}});
renderMain();
</script>
</body>
</html>"""
