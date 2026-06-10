#!/usr/bin/env python3
"""screening_server.py — 轻量选股HTTP服务 + 异步个股分析"""
import json, os, sys, time, threading, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import screening_api

# 异步分析任务存储
_analysis_tasks = {}
_ANALYSIS_CACHE = {}

def _run_analysis_bg(task_id, code, date_str):
    """后台线程：跑TradingAgents全量分析"""
    try:
        # 确保venv依赖可用
        venv_path = "/home/harrydolly/code/TradingAgents-astock/.venv/lib/python3.11/site-packages"
        if venv_path not in sys.path:
            sys.path.insert(0, venv_path)
        
        import site
        site.addsitedir(venv_path)
        
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        _analysis_tasks[task_id] = {'status': 'running', 'progress': '初始化分析...'}
        
        config = DEFAULT_CONFIG.copy()
        config["max_debate_rounds"] = 3
        config["max_risk_discuss_rounds"] = 3
        config["output_language"] = "Chinese"
        config["checkpoint_enabled"] = False

        # API Key
        import subprocess
        result = subprocess.run(['bash', '-c', 'source /etc/profile >/dev/null 2>&1; echo $DEEPSEEK_API_KEY'],
                              capture_output=True, text=True)
        real_key = result.stdout.strip()
        if real_key and len(real_key) > 20:
            os.environ['DEEPSEEK_API_KEY'] = real_key

        selected_analysts = ["market", "social", "news", "fundamentals",
                             "policy", "hot_money", "lockup", "chanlun"]

        _analysis_tasks[task_id] = {'status': 'running', 'progress': '正在调用分析师团队（8位分析师）...'}
        
        t0 = time.time()
        graph = TradingAgentsGraph(
            selected_analysts=selected_analysts,
            config=config,
            debug=False,
        )
        final_state = graph.propagate(code, date_str)
        
        if isinstance(final_state, tuple):
            final_state = final_state[0]
        
        elapsed = time.time() - t0
        
        if not final_state:
            _analysis_tasks[task_id] = {
                'status': 'ok', 'progress': '完成',
                'result': {'code': code, 'status': 'empty', 'elapsed': round(elapsed)}
            }
            return
        
        report = {
            'code': code, 'status': 'ok', 'elapsed': round(elapsed),
            'market_report': (final_state.get('market_report', '') or '')[:3000],
            'sentiment_report': (final_state.get('sentiment_report', '') or '')[:3000],
            'news_report': (final_state.get('news_report', '') or '')[:3000],
            'fundamentals_report': (final_state.get('fundamentals_report', '') or '')[:3000],
            'policy_report': (final_state.get('policy_report', '') or '')[:3000],
            'hot_money_report': (final_state.get('hot_money_report', '') or '')[:3000],
            'lockup_report': (final_state.get('lockup_report', '') or '')[:3000],
            'chanlun_report': (final_state.get('chanlun_report', '') or '')[:3000],
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
        
        _analysis_tasks[task_id] = {
            'status': 'ok', 'progress': '完成',
            'result': report
        }
        _ANALYSIS_CACHE[code] = report
        
    except Exception as e:
        import traceback
        _analysis_tasks[task_id] = {
            'status': 'error', 'progress': '分析失败',
            'error': str(e), 'traceback': traceback.format_exc()
        }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path.rstrip('/')
        
        if path == '/api/analyze_status':
            task_id = (params.get('task_id') or [None])[0]
            code = (params.get('code') or [None])[0]
            
            self._send_cors()
            
            # 优先检查缓存
            if code and code in _ANALYSIS_CACHE:
                self._respond({
                    'status': 'ok', 'progress': '完成（缓存）',
                    'result': _ANALYSIS_CACHE[code]
                })
                return
            
            if task_id and task_id in _analysis_tasks:
                self._respond(_analysis_tasks[task_id])
                return
            
            self._respond({'status': 'unknown', 'progress': '未找到分析任务'})
        
        elif path == '/api/analyze_cache':
            self._send_cors()
            self._respond({
                'cache_size': len(_ANALYSIS_CACHE),
                'cached_codes': list(_ANALYSIS_CACHE.keys())
            })
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        path = self.path.rstrip('/')
        
        if path == '/api/screening':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode() if length > 0 else '{}'
            status, headers, data = screening_api.json_handler(body)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        
        elif path == '/api/analyze_stock':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode()) if length > 0 else {}
            code = body.get('code', '')
            date_str = body.get('date', time.strftime("%Y-%m-%d"))
            
            self._send_cors()
            
            if not code:
                self._respond({'error': 'Missing code'})
                return
            
            # 检查缓存
            if code in _ANALYSIS_CACHE:
                self._respond({
                    'task_id': None, 'cached': True,
                    'result': _ANALYSIS_CACHE[code]
                })
                return
            
            task_id = uuid.uuid4().hex[:12]
            _analysis_tasks[task_id] = {'status': 'queued', 'progress': '排队中...'}
            
            # 启动后台线程
            thread = threading.Thread(target=_run_analysis_bg, args=(task_id, code, date_str), daemon=True)
            thread.start()
            
            self._respond({'task_id': task_id, 'cached': False, 'status': 'queued'})
        
        else:
            self.send_response(404)
            self._send_cors()
            self._respond({'error': 'Not found'})
    
    def do_OPTIONS(self):
        self._send_cors()
    
    def _send_cors(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def _respond(self, data):
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def log_message(self, fmt, *args):
        pass  # 安静运行


if __name__ == '__main__':
    port = 8788
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"Screening API on :{port}")
    server.serve_forever()
