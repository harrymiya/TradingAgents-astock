#!/usr/bin/env python3
"""
V3 产业链地图生成器 — 完整的单页面HTML应用
集成：所有产业链 + 实时行情 + 买卖持有评分 + 颜色标记
"""
import json, sqlite3, os, re, time, urllib.request, sys

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')
OUT_DIR = os.path.expanduser('~/industry_map_cache')
os.makedirs(OUT_DIR, exist_ok=True)

print("=== V3 产业链地图生成 ===")

# ========== 1. 读取DB数据 ==========
db = sqlite3.connect(DB_PATH)

chains_data = db.execute('SELECT id, name, description FROM industry_chains ORDER BY id').fetchall()

chain_links_map = {}
for ch_id, _, _ in chains_data:
    links = db.execute(
        'SELECT id, name, level, sort_order FROM chain_links WHERE chain_id=? ORDER BY sort_order',
        (ch_id,)).fetchall()
    chain_links_map[ch_id] = links

chain_stocks_map = {}
for ch_id, _, _ in chains_data:
    stocks = db.execute('''
        SELECT cs.code, cs.link_id, cl.name as link_name
        FROM chain_stocks cs
        JOIN chain_links cl ON cs.link_id = cl.id
        WHERE cl.chain_id=?
    ''', (ch_id,)).fetchall()
    chain_stocks_map[ch_id] = stocks

# 收集所有代码后，查feat表
all_codes = list(set(s[0] for m in chain_stocks_map.values() for s in m))
print(f"  总代码数: {len(all_codes)}")

feat_data = {}
try:
    feat_rows = db.execute('''
        SELECT code, pos_20d, ma20_pct, vr_5, ret5, ret3
        FROM feat WHERE code IN ({})
    '''.format(','.join('?' for _ in all_codes)), all_codes).fetchall()
    for r in feat_rows:
        feat_data[r[0]] = {
            'pos_20d': r[1] or 0,
            'ma20_pct': r[2] or 0,
            'vr_5': r[3] or 0,
            'ret5': r[4] or 0,
            'ret3': r[5] or 0,
        }
    print(f"  获取了 {len(feat_data)} 只feat历史数据")
except Exception as e:
    print(f"  feat获取失败: {e}")

db.close()

# ========== 2. 获取实时行情（含技术面）==========
print("获取实时行情...")

def fetch_prices(codes):
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
                price = float(parts[3]) if parts[3] else 0
                chg = float(parts[32]) if len(parts)>32 and parts[32] else 0
                hi = float(parts[33]) if len(parts)>33 and parts[33] else 0
                lo = float(parts[34]) if len(parts)>34 and parts[34] else 0
                pe = float(parts[39]) if len(parts)>39 and parts[39] else 0
                amplitude = float(parts[43]) if len(parts)>43 and parts[43] else 0
                pb = float(parts[48]) if len(parts)>48 and parts[48] else 0
                year_chg = float(parts[69]) if len(parts)>69 and parts[69] else 0
                prices[raw] = {
                    'name': parts[1], 'price': price, 'chg': chg,
                    'hi': hi, 'lo': lo, 'pe': pe, 'pb': pb,
                    'amplitude': amplitude, 'yearChg': year_chg,
                    'volume': int(parts[6]) if parts[6] else 0,
                }
        except: pass
        time.sleep(0.15)
    return prices

prices = fetch_prices(all_codes)
print(f"  获取了 {len(prices)} 只行情")

# ========== 3. 评分逻辑 ==========
def score_stock(code, p):
    """综合评分: 0-100, >70=买入, 40-70=持有, <40=卖出
    评分维度: 技术面(今日涨跌幅) + 趋势面(年度涨跌) + 估值面(PE) + 
              策略面(S3超跌信号: pos_20d, ma20_pct) + 活跃度(振幅/量比)
    """
    if not p or not isinstance(p, dict) or p.get('price', 0) == 0:
        # 无实时数据时，用feat历史数据评分
        fd = feat_data.get(code, {})
        if not fd:
            return 40, ['无数据']
        score = 45  # 偏低基准
        reasons = []
        ma20_pct = fd.get('ma20_pct', 0) or 0
        pos_20d = fd.get('pos_20d', 50) or 50
        ret5 = fd.get('ret5', 0) or 0
        ret3 = fd.get('ret3', 0) or 0
        
        # S3信号：超跌但企稳（越接近S3条件越好）
        if pos_20d < 20:
            score += 15
            reasons.append('超跌反弹S3')
        elif pos_20d > 80:
            score -= 10
            reasons.append('高位风险')
        
        # MA20偏离
        if -15 < ma20_pct < -8:
            score += 10
            reasons.append('超跌区域')
        elif ma20_pct > 0:
            score -= 5
            reasons.append('均线上方')
        elif ma20_pct < -20:
            score -= 10
            reasons.append('深度破位')
        
        # 5日收益率
        if ret5 > 8:
            score += 10
            reasons.append('近期强势')
        elif ret5 < -8:
            score -= 10
            reasons.append('近期弱势')
        
        score = max(10, min(90, score))
        return score, reasons[:3]
    
    score = 50  # 基准分
    reasons = []
    
    chg = p.get('chg', 0)
    year_chg = p.get('yearChg', 0)
    pe = p.get('pe', 0)
    amplitude = p.get('amplitude', 0)
    volume = p.get('volume', 0)
    
    # 技术面评分 (今日涨跌幅)
    if chg > 9.5:
        score += 25  # 涨停=强
        reasons.append("涨停")
    elif chg > 5:
        score += 15
        reasons.append("大涨+5%")
    elif chg > 2:
        score += 8
        reasons.append("上涨+2%")
    elif chg > 0:
        score += 3
        reasons.append("微涨")
    elif chg > -3:
        score -= 3
        reasons.append("微跌")
    elif chg > -5:
        score -= 8
        reasons.append("下跌-3%")
    elif chg > -9.5:
        score -= 15
        reasons.append("大跌-5%")
    else:
        score -= 25  # 跌停
        reasons.append("跌停")
    
    # 年度涨跌幅 (趋势判断)
    if year_chg > 50:
        score += 5
        reasons.append("年度强势(+50%)")
    elif year_chg > 20:
        score += 3
        reasons.append("年度上涨(+20%)")
    elif year_chg < -30:
        score -= 10
        reasons.append("年度颓势(-30%)")
    elif year_chg < -15:
        score -= 5
        reasons.append("年度下跌(-15%)")
    
    # 估值评分 (PE)
    if 0 < pe < 20:
        score += 5
        reasons.append(f"低PE({pe:.0f})")
    elif 20 <= pe < 40:
        score += 2
    elif pe >= 100:
        score -= 3
        reasons.append(f"高PE({pe:.0f})")
    elif pe <= 0:
        score -= 3  # 亏损
        reasons.append("亏损")
    
    # 振幅评分 (活跃度)
    if amplitude > 8:
        score += 5
        reasons.append("高活跃")
    elif amplitude < 1:
        score -= 3
        reasons.append("低活跃")
    
    # 封顶
    score = max(0, min(100, score))
    
    return score, reasons[:3]


# ========== 4. 评分 ==========
print("计算评分...")
stock_scores = {}
for code in all_codes:
    p = prices.get(code, {})
    score, reasons = score_stock(code, p)
    
    if score >= 70:
        signal = 'buy'
        signal_cn = '买入'
        color = '#00cc00'
    elif score >= 40:
        signal = 'hold'
        signal_cn = '持有'
        color = '#ffaa00'
    else:
        signal = 'sell'
        signal_cn = '卖出'
        color = '#ff3333'
    
    stock_scores[code] = {
        'name': p.get('name', ''),
        'price': p.get('price', 0),
        'chg': p.get('chg', 0),
        'score': score,
        'signal': signal,
        'signal_cn': signal_cn,
        'color': color,
        'reasons': reasons,
    }


# ========== 5. 生成HTML ==========
print("生成HTML...")

# 统计各链信号分布
chain_stats = []
for ch_id, ch_name, ch_desc in chains_data:
    stocks = chain_stocks_map.get(ch_id, [])
    if not stocks:
        continue
    
    # 获取本链的有效股票
    valid_codes = set(s[0] for s in stocks)
    valid_prices = {c: stock_scores[c] for c in valid_codes if c in stock_scores}
    
    if not valid_prices:
        continue
    
    buy_cnt = sum(1 for s in valid_prices.values() if s['signal'] == 'buy')
    hold_cnt = sum(1 for s in valid_prices.values() if s['signal'] == 'hold')
    sell_cnt = sum(1 for s in valid_prices.values() if s['signal'] == 'sell')
    avg_score = sum(s['score'] for s in valid_prices.values()) / len(valid_prices)
    
    # 决定产业链信号（多数决）
    if buy_cnt > hold_cnt and buy_cnt > sell_cnt:
        chain_signal = 'buy'
        chain_signal_cn = '买入'
        chain_color = '#00cc00'
    elif sell_cnt > buy_cnt and sell_cnt > hold_cnt:
        chain_signal = 'sell'
        chain_signal_cn = '卖出'
        chain_color = '#ff3333'
    else:
        chain_signal = 'hold'
        chain_signal_cn = '持有'
        chain_color = '#ffaa00'
    
    # 决定链趋势箭头
    avg_chg = sum(s['chg'] for s in valid_prices.values()) / len(valid_prices)
    if avg_chg > 2:
        trend_arrow = '↑'
        trend_note = '强势'
    elif avg_chg < -2:
        trend_arrow = '↓'
        trend_note = '弱势'
    else:
        trend_arrow = '→'
        trend_note = '震荡'
    
    chain_stats.append({
        'id': ch_id, 'name': ch_name, 'desc': ch_desc or '',
        'stock_count': len(valid_prices),
        'buy': buy_cnt, 'hold': hold_cnt, 'sell': sell_cnt,
        'avg_score': avg_score, 'avg_chg': avg_chg,
        'signal': chain_signal, 'signal_cn': chain_signal_cn,
        'color': chain_color, 'trend_arrow': trend_arrow, 'trend_note': trend_note,
        'companies': sorted(valid_prices.items(), key=lambda x: -x[1]['score'])[:20]
    })


# 排序：买入链优先，按平均分降序
chain_stats.sort(key=lambda c: (-c['avg_score']))

# 总体统计
total_buy = sum(c['buy'] for c in chain_stats)
total_hold = sum(c['hold'] for c in chain_stats)
total_sell = sum(c['sell'] for c in chain_stats)
total_stocks = total_buy + total_hold + total_sell

# 生成HTML
def generate_html():
    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 头部统计卡片
    header_cards = f'''
    <div class="stat-cards">
        <div class="stat-card" style="border-left: 4px solid #00d4ff;">
            <div class="stat-value">{len(chain_stats)}</div>
            <div class="stat-label">产业链</div>
        </div>
        <div class="stat-card" style="border-left: 4px solid #7c3aed;">
            <div class="stat-value">{total_stocks}</div>
            <div class="stat-label">成分股</div>
        </div>
        <div class="stat-card buy-bg">
            <div class="stat-value">{total_buy}</div>
            <div class="stat-label">买入信号</div>
        </div>
        <div class="stat-card hold-bg">
            <div class="stat-value">{total_hold}</div>
            <div class="stat-label">持有信号</div>
        </div>
        <div class="stat-card sell-bg">
            <div class="stat-value">{total_sell}</div>
            <div class="stat-label">卖出信号</div>
        </div>
    </div>'''
    
    # 各链卡片
    chain_cards = []
    for c in chain_stats:
        # 前5只股票的标签
        tags = []
        for code, s in c['companies'][:8]:
            signal_icon = {'buy':'🟢','hold':'🟡','sell':'🔴'}.get(s['signal'],'⚪')
            chg_str = f'{s["chg"]:+.1f}%' if s['chg'] != 0 else ''
            tags.append(f'<span class="stock-tag {s["signal"]}" title="{s["reasons"]}">{signal_icon}{s["name"]} {chg_str}</span>')
        if c['stock_count'] > 8:
            tags.append(f'<span class="stock-tag" style="color:#445566">+{c["stock_count"]-8}</span>')
        
        # 信号条
        total_s = c['buy'] + c['hold'] + c['sell']
        buy_pct = c['buy'] / total_s * 100 if total_s else 0
        hold_pct = c['hold'] / total_s * 100 if total_s else 0
        sell_pct = c['sell'] / total_s * 100 if total_s else 0
        
        card = f'''
<div class="chain-card" style="border-left: 4px solid {c['color']};" onclick="toggleChain('{c['id']}')">
    <div class="card-header">
        <div>
            <h3>{c['trend_arrow']} {c['name']}</h3>
            <div class="card-desc">{c['desc'][:80]}</div>
        </div>
        <div class="card-right">
            <span class="signal-badge" style="background:{c['color']}22;color:{c['color']};border:1px solid {c['color']}44;">
                {c['signal_cn']} {c['trend_arrow']}
            </span>
            <span class="card-score">{c['avg_score']:.0f}分</span>
        </div>
    </div>
    <div class="signal-bar">
        <div class="bar-buy" style="width:{buy_pct:.1f}%"></div>
        <div class="bar-hold" style="width:{hold_pct:.1f}%"></div>
        <div class="bar-sell" style="width:{sell_pct:.1f}%"></div>
    </div>
    <div class="signal-labels">
        <span class="buy">买入 {c['buy']}</span>
        <span class="hold">持有 {c['hold']}</span>
        <span class="sell">卖出 {c['sell']}</span>
        <span class="avg-chg">{c['avg_chg']:+.2f}%</span>
        <span class="stock-count">{c['stock_count']}只</span>
    </div>
    <div class="card-stocks">{''.join(tags)}</div>
    <div id="detail-{c['id']}" class="detail-table" style="display:none;">
        <table>
            <tr><th>代码</th><th>名称</th><th>现价</th><th>涨幅</th><th>评分</th><th>信号</th><th>原因</th></tr>'''
        
        for code, s in c['companies'][:20]:
            signal_icon = {'buy':'🟢','hold':'🟡','sell':'🔴'}.get(s['signal'],'⚪')
            card += f'''
            <tr style="color:{s['color']}">
                <td>{code}</td><td>{s['name']}</td>
                <td>{s['price']:.2f}</td><td class="{'up' if s['chg']>0 else 'down'}">{s['chg']:+.2f}%</td>
                <td>{s['score']}</td>
                <td>{signal_icon} {s['signal_cn']}</td>
                <td style="font-size:11px;">{','.join(s['reasons'])}</td>
            </tr>'''
        
        card += '</table></div></div>'
        chain_cards.append(card)
    
    chains_html = '\n'.join(chain_cards)
    
    # 图例
    legend = '''
    <div class="legend">
        <span><span class="dot" style="background:#00cc00"></span>买入(≥70分)</span>
        <span><span class="dot" style="background:#ffaa00"></span>持有(40-69分)</span>
        <span><span class="dot" style="background:#ff3333"></span>卖出(<40分)</span>
        <span>↑强势 ↑买入 →震荡 ↓弱势 ↓卖出</span>
    </div>'''
    
    # 信号分布总体图
    total_pct_buy = total_buy / total_stocks * 100 if total_stocks else 0
    total_pct_hold = total_hold / total_stocks * 100 if total_stocks else 0
    total_pct_sell = total_sell / total_stocks * 100 if total_stocks else 0
    
    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>A股产业链全景图 V3 — 买卖持有评分</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e17;color:#e0e0e0;min-height:100vh}
.header{background:linear-gradient(135deg,#0f1923 0%,#1a2a3f 100%);padding:20px 32px;border-bottom:1px solid #1e3a5f}
.header h1{font-size:26px;color:#fff;margin-bottom:8px}
.header h1 span{background:linear-gradient(90deg,#00d4ff,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{color:#8899aa;font-size:13px;display:flex;gap:16px;flex-wrap:wrap}
.stat-cards{display:flex;gap:12px;margin:16px 0;flex-wrap:wrap}
.stat-card{background:#111b2e;border:1px solid #1a2f4a;border-radius:8px;padding:12px 20px;min-width:100px}
.stat-card .stat-value{font-size:24px;font-weight:bold;color:#fff}
.stat-card .stat-label{font-size:12px;color:#8899aa;margin-top:2px}
.buy-bg{border-left:4px solid #00cc00!important}
.hold-bg{border-left:4px solid #ffaa00!important}
.sell-bg{border-left:4px solid #ff3333!important}
.content{max-width:1400px;margin:0 auto;padding:16px 24px}
.legend{display:flex;gap:16px;font-size:12px;color:#8899aa;padding:8px 0;flex-wrap:wrap}
.legend .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:middle}
.overall-bar{height:8px;border-radius:4px;overflow:hidden;display:flex;margin:8px 0 16px;background:#111b2e;border:1px solid #1a2f4a}
.overall-bar .seg-buy{background:#00cc00;transition:width 0.5s}
.overall-bar .seg-hold{background:#ffaa00;transition:width 0.5s}
.overall-bar .seg-sell{background:#ff3333;transition:width 0.5s}

.chain-card{background:#111b2e;border:1px solid #1a2f4a;border-radius:10px;margin-bottom:12px;overflow:hidden;cursor:pointer;transition:all 0.2s}
.chain-card:hover{transform:translateY(-1px);box-shadow:0 4px 16px rgba(0,0,0,0.3)}
.card-header{display:flex;justify-content:space-between;align-items:flex-start;padding:14px 18px}
.card-header h3{font-size:15px;color:#d0d8e8}
.card-desc{color:#667788;font-size:11px;margin-top:3px}
.card-right{text-align:right}
.signal-badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:bold}
.card-score{display:block;font-size:20px;font-weight:bold;color:#d0d8e8;margin-top:4px}
.signal-bar{height:4px;display:flex;margin:0 18px;border-radius:2px;overflow:hidden}
.bar-buy{background:#00cc00;height:100%}
.bar-hold{background:#ffaa00;height:100%}
.bar-sell{background:#ff3333;height:100%}
.signal-labels{display:flex;gap:12px;font-size:11px;padding:4px 18px;color:#667788;flex-wrap:wrap}
.signal-labels .buy{color:#00cc00}
.signal-labels .hold{color:#ffaa00}
.signal-labels .sell{color:#ff3333}
.signal-labels .avg-chg{margin-left:auto}
.signal-labels .stock-count{color:#446688}
.card-stocks{padding:6px 18px 10px;display:flex;flex-wrap:wrap;gap:4px}
.stock-tag{padding:2px 8px;border-radius:4px;font-size:11px;background:#0f1a2b;color:#8899aa}
.stock-tag.buy{color:#00cc00;background:#001a00}
.stock-tag.hold{color:#ffaa00;background:#1a1000}
.stock-tag.sell{color:#ff5555;background:#1a0000}
.detail-table{background:#0a0e17;border-top:1px solid #1a2f4a}
.detail-table table{width:100%;border-collapse:collapse;font-size:12px}
.detail-table th{text-align:left;padding:6px 12px;color:#667788;border-bottom:1px solid #1a2f4a;font-weight:normal}
.detail-table td{padding:4px 12px;border-bottom:1px solid #0f1520}
.detail-table tr:hover{background:#111b2e}
.up{color:#ff4444}
.down{color:#00b300}
.filter-bar{display:flex;gap:8px;margin:12px 0;flex-wrap:wrap}
.filter-btn{padding:6px 14px;border-radius:16px;font-size:12px;border:1px solid #1a2f4a;background:#111b2e;color:#8899aa;cursor:pointer;transition:all 0.2s}
.filter-btn:hover{background:#1a2f4a;color:#d0d8e8}
.filter-btn.active{background:#1e3a5f;color:#66b8ff;border-color:#1e3a5f}
.search-input{background:#111b2e;border:1px solid #1a2f4a;border-radius:16px;padding:6px 14px;color:#e0e0e0;font-size:13px;width:200px;outline:none}
.search-input:focus{border-color:#00d4ff}
.footer{text-align:center;padding:24px;color:#445566;font-size:11px}
</style>
</head>
<body>
<div class="header">
<h1>A股产业链全景图 <span>V3</span></h1>
<div class="subtitle">
<span>''' + now_str + '''</span>
<span>''' + str(len(chain_stats)) + '''条产业链</span>
<span>''' + str(total_stocks) + '''只成分股</span>
<span>数据源: 通达信F10 + 企查查 + 腾讯行情</span>
</div>
</div>
<div class="content">
''' + header_cards + '''

<div class="overall-bar">
<div class="seg-buy" style="width:''' + f'{total_pct_buy:.1f}%' + '''"></div>
<div class="seg-hold" style="width:''' + f'{total_pct_hold:.1f}%' + '''"></div>
<div class="seg-sell" style="width:''' + f'{total_pct_sell:.1f}%' + '''"></div>
</div>

''' + legend + '''

<div class="filter-bar">
<button class="filter-btn active" onclick="filterChain('all',this)">🏠 全部</button>
<button class="filter-btn" onclick="filterChain('buy',this)">🟢 买入链</button>
<button class="filter-btn" onclick="filterChain('hold',this)">🟡 持有链</button>
<button class="filter-btn" onclick="filterChain('sell',this)">🔴 卖出链</button>
<input class="search-input" placeholder="搜索产业链..." oninput="searchChain(this.value)">
</div>

<div id="chain-list">
''' + chains_html + '''
</div>
</div>
<div class="footer">A股产业链全景图 V3 · 评分逻辑: 技术面(涨跌幅/振幅/趋势)+估值(PE)+活跃度 · ''' + now_str + '''</div>

<script>
function toggleChain(id){
    var el = document.getElementById('detail-'+id);
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
}
function filterChain(type, btn){
    document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    var cards = document.querySelectorAll('.chain-card');
    cards.forEach(function(c){
        if(type === 'all'){c.style.display = ''; return;}
        var badge = c.querySelector('.signal-badge');
        if(!badge) return;
        var text = badge.textContent.trim();
        if(type === 'buy' && text.includes('买入')){c.style.display = '';}
        else if(type === 'hold' && text.includes('持有')){c.style.display = '';}
        else if(type === 'sell' && text.includes('卖出')){c.style.display = '';}
        else {c.style.display = 'none';}
    });
}
function searchChain(val){
    var q = val.toLowerCase();
    var cards = document.querySelectorAll('.chain-card');
    cards.forEach(function(c){
        var title = c.querySelector('h3').textContent.toLowerCase();
        c.style.display = title.includes(q) ? '' : 'none';
    });
}
</script>
</body>
</html>'''
    return html


html_content = generate_html()
out_path = os.path.join(OUT_DIR, 'industry_map_v3.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html_content)
print(f"✅ V3 HTML 已生成: {out_path}")
print(f"   大小: {len(html_content)} 字节")
print(f"   产业链: {len(chain_stats)} 条")
print(f"   股票: {total_stocks} 只 (买入{total_buy}/持有{total_hold}/卖出{total_sell})")

# 输出前10链
print("\n=== Top 10 产业链评分排行 ===")
for c in chain_stats[:10]:
    print(f"  {c['signal_icon_placeholder'] if False else ('🟢' if c['signal']=='buy' else '🟡' if c['signal']=='hold' else '🔴')} {c['name']:20s} 评分{c['avg_score']:.0f} 买入{c['buy']}/持有{c['hold']}/卖出{c['sell']}  {c['trend_note']}")
