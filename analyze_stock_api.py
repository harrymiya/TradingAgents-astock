#!/usr/bin/env python3
"""
analyze_stock_api.py — TradingAgents框架个股分析API
启动: python3 analyze_stock_api.py
前端从 localhost:8787 访问
"""
import sys, os, json, time, sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PROJECT_DIR = "/home/harrydolly/code/TradingAgents-astock"
sys.path.insert(0, PROJECT_DIR)

# 缓存最近的分析结果
analysis_cache = {}
cache_timeout = 300  # 5分钟

DB_PATH = os.path.expanduser("~/.hermes/astock_data.db")

def get_stock_name(code):
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT name FROM stocks WHERE code=?", (code,)).fetchone()
        conn.close()
        return row[0] if row else code
    except:
        return code

class AnalysisHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        # CORS
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        
        path = parsed.path.rstrip('/')
        
        if path == '/analyze':
            codes = params.get('code', [])
            if not codes:
                self._respond({'error': 'Missing code parameter'})
                return
            code = codes[0]
            
            # 检查缓存
            now = time.time()
            if code in analysis_cache:
                cached = analysis_cache[code]
                if now - cached['time'] < cache_timeout:
                    self._respond(cached['result'])
                    return
            
            # 执行分析
            try:
                result = self._run_analysis(code)
                analysis_cache[code] = {'result': result, 'time': now}
                self._respond(result)
            except Exception as e:
                import traceback
                self._respond({'error': str(e), 'traceback': traceback.format_exc()})
        
        elif path == '/status':
            self._respond({'status': 'ok', 'cache_size': len(analysis_cache)})
        
        else:
            self._respond({'error': 'Not found'})
    
    def _respond(self, data):
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def _run_analysis(self, code):
        """运行TradingAgents框架分析单只股票"""
        code = code.strip()
        name = get_stock_name(code)
        target_date = time.strftime("%Y-%m-%d")
        
        # 移除截断的key，让框架从.env读取
        os.environ.pop('DEEPSEEK_API_KEY', None)
        
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        config = DEFAULT_CONFIG.copy()
        config["max_debate_rounds"] = 3
        config["max_risk_discuss_rounds"] = 3
        config["output_language"] = "Chinese"
        config["checkpoint_enabled"] = False
        
        selected_analysts = ["market", "news", "fundamentals", "hot_money"]
        
        t0 = time.time()
        
        graph = TradingAgentsGraph(
            selected_analysts=selected_analysts,
            config=config,
            debug=False,
        )
        final_state = graph.propagate(code, target_date)
        
        if isinstance(final_state, tuple):
            final_state = final_state[0]
        
        elapsed = time.time() - t0
        
        if not final_state:
            return {'code': code, 'name': name, 'status': 'empty', 'elapsed': elapsed}
        
        report = {
            'code': code, 'name': name,
            'status': 'ok', 'elapsed': round(elapsed),
            'market_report': (final_state.get('market_report', '') or '')[:3000],
            'news_report': (final_state.get('news_report', '') or '')[:3000],
            'fundamentals_report': (final_state.get('fundamentals_report', '') or '')[:3000],
            'hot_money_report': (final_state.get('hot_money_report', '') or '')[:3000],
        }
        
        debate = final_state.get('investment_debate_state', {})
        if debate:
            report['bull_history'] = (debate.get('bull_history', '') or '')[:3000]
            report['bear_history'] = (debate.get('bear_history', '') or '')[:3000]
            report['judge_decision'] = (debate.get('judge_decision', '') or '')[:3000]
        
        risk = final_state.get('risk_debate_state', {})
        if risk:
            report['risk_conservative'] = (risk.get('conservative_history', '') or '')[:2000]
            report['risk_aggressive'] = (risk.get('aggressive_history', '') or '')[:2000]
            report['risk_neutral'] = (risk.get('neutral_history', '') or '')[:2000]
            report['risk_judge'] = (risk.get('judge_decision', '') or '')[:3000]
        
        if final_state.get('trader_investment_plan'):
            report['trader_plan'] = (final_state['trader_investment_plan'] or '')[:3000]
        
        return report

if __name__ == '__main__':
    port = 8787
    server = HTTPServer(('0.0.0.0', port), AnalysisHandler)
    print(f"📊 TradingAgents 分析API已启动: http://localhost:{port}")
    print(f"   使用: curl http://localhost:{port}/analyze?code=000988")
    server.serve_forever()
