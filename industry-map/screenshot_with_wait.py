#!/usr/bin/env python3
"""使用 chromium headless 截图 React + D3 页面，等待力导向图稳定后截图"""
import subprocess
import time
import os
import sys

DIST_DIR = "/home/harrydolly/code/TradingAgents-astock/industry-map/dist"
OUTPUT = os.path.join(DIST_DIR, "screenshot.png")

# 启动本地 HTTP 服务
server = subprocess.Popen(
    [sys.executable, "-m", "http.server", "8898"],
    cwd=DIST_DIR,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

time.sleep(1)

# 先打开页面但不截图，等 D3 渲染
browser = subprocess.Popen(
    ["chromium", "--headless", "--no-sandbox", "--disable-gpu",
     "--disable-web-security",
     "http://localhost:8898/"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

time.sleep(5)
browser.kill()

# 第二次访问时截图，期待页面已被缓存
subprocess.run(
    ["chromium", "--headless", f"--screenshot={OUTPUT}",
     "--window-size=1920,1080",
     "--no-sandbox", "--disable-gpu", "--disable-web-security",
     "http://localhost:8898/"],
    capture_output=True, timeout=30
)

size = os.path.getsize(OUTPUT)
print(f"screenshot: {size} bytes")

server.terminate()
server.wait()
