#!/usr/bin/env python3
"""
screening_server.py — 轻量选股HTTP服务
"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import screening_api

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/screening':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode() if length > 0 else '{}'
            status, headers, data = screening_api.json_handler(body)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, fmt, *args):
        pass  # 安静运行

if __name__ == '__main__':
    port = 8788
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"Screening API on :{port}")
    server.serve_forever()
