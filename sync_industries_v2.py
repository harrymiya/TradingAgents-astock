#!/usr/bin/env python3
"""
5线程并行同步行业分类数据 - 文件日志版
"""
import sqlite3, os, re, time, threading, sys, logging

DB = os.path.expanduser('~/.hermes/astock_data.db')
LOG = '/tmp/sync_v2.log'

logging.basicConfig(
    filename=LOG,
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    force=True
)

SERVERS = [
    ('202.108.253.139', 80),
    ('202.108.253.140', 80),
    ('202.108.253.141', 80),
    ('202.120.7.113', 7709),
    ('59.36.22.219', 7709),
]

def get_stock_codes():
    db = sqlite3.connect(DB)
    codes = [r[0] for r in db.execute("""
        SELECT DISTINCT code FROM feat 
        WHERE code NOT LIKE '688%%' AND code NOT LIKE '4%%'
        AND code NOT LIKE '83%%' AND code NOT LIKE '87%%'
        ORDER BY code
    """).fetchall()]
    db.close()
    return codes

def parse_industry(f10_text):
    if not f10_text or not isinstance(f10_text, str):
        return None, None, None
    lines = f10_text.split('\n')
    l1 = l2 = l3 = None
    for line in lines:
        line = line.strip()
        m = re.search(r'所属研究行业[：:]\s*([^\r\n(]+)', line)
        if m:
            parts = re.split(r'[／/]', m.group(1).strip())
            parts = [p.strip().lstrip(':') for p in parts if p.strip()]
            if len(parts) >= 1: l1 = parts[0]
            if len(parts) >= 2: l2 = parts[1]
            if len(parts) >= 3: l3 = parts[2]
            return l1, l2, l3
        m2 = re.search(r'所属行业[：:]\s*([^\r\n(]+)', line)
        if m2:
            parts = re.split(r'[／/]', m2.group(1).strip())
            parts = [p.strip().lstrip(':') for p in parts if p.strip()]
            if len(parts) >= 1: l1 = parts[0]
            if len(parts) >= 2: l2 = parts[1]
            if len(parts) >= 3: l3 = parts[2]
            return l1, l2, l3
    return l1, l2, l3

class IndustryWorker(threading.Thread):
    def __init__(self, wid, server, codes, stats):
        super().__init__()
        self.wid = wid
        self.server = server
        self.codes = codes
        self.stats = stats
        self.success = 0
        self.fail = 0
    
    def run(self):
        from mootdx.quotes import Quotes
        
        try:
            client = Quotes.factory(market='std', tcp=(self.server[0], self.server[1], True))
        except Exception as e:
            logging.error(f"W{self.wid} 连接失败 {self.server[0]}:{self.server[1]}: {e}")
            # 尝试备用
            try:
                client = Quotes.factory(market='std')
            except:
                logging.error(f"W{self.wid} 也无法建立默认连接")
                return
        
        db = sqlite3.connect(DB)
        
        for code in self.codes:
            try:
                f10 = client.F10(code, 'industry_analysis')
                hys = f10.get('行业分析', '') if isinstance(f10, dict) else str(f10)
                l1, l2, l3 = parse_industry(hys)
                if l1 or l2 or l3:
                    db.execute(
                        "INSERT OR REPLACE INTO stock_industries (code, industry_l1, industry_l2, industry_l3, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                        (code, l1, l2, l3)
                    )
                    db.commit()
                    self.success += 1
                else:
                    self.fail += 1
            except Exception as e:
                self.fail += 1
                if self.fail % 20 == 0:
                    logging.warning(f"W{self.wid} 已失败{self.fail}只，最新: {code} {str(e)[:80]}")
            
            with self.stats['lock']:
                self.stats['done'] += 1
                done = self.stats['done']
                total = self.stats['total']
                if done % 100 == 0 or done == total:
                    elapsed = time.time() - self.stats['t0']
                    rate = done / max(elapsed, 1)
                    remain = (total - done) / max(rate, 1)
                    log_msg = f"[{done:>6}/{total}] {100*done//total:>2}%  成功{self.stats['success_total']+self.success}只  耗时{elapsed:.0f}s  ETA{remain/60:.0f}min"
                    logging.info(log_msg)
                    print(log_msg, flush=True)
        
        db.close()

def main():
    logging.info("=== 行业分类同步开始 (5线程并行) ===")
    
    all_codes = get_stock_codes()
    logging.info(f"股票总数: {len(all_codes)}")
    
    db = sqlite3.connect(DB)
    existing = {r[0] for r in db.execute("SELECT code FROM stock_industries WHERE industry_l1 IS NOT NULL AND industry_l1 != ''").fetchall()}
    db.close()
    
    need_codes = [c for c in all_codes if c not in existing]
    logging.info(f"已有{len(existing)}只, 需拉{len(need_codes)}只")
    
    if not need_codes:
        logging.info("全部已同步")
        print("✅ 全部已同步", flush=True)
        return
    
    chunk_size = max(1, len(need_codes) // 5)
    chunks = [need_codes[i:i+chunk_size] for i in range(0, len(need_codes), chunk_size)]
    
    stats = {
        'done': 0,
        'total': len(need_codes),
        't0': time.time(),
        'success_total': 0,
        'lock': threading.Lock(),
    }
    
    workers = []
    for i, chunk in enumerate(chunks[:5]):
        if not chunk:
            continue
        w = IndustryWorker(i+1, SERVERS[i], chunk, stats)
        workers.append(w)
        w.start()
        logging.info(f"W{i+1}: {SERVERS[i][0]}:{SERVERS[i][1]} → {len(chunk)}只")
        print(f"  W{i+1}: {SERVERS[i][0]}:{SERVERS[i][1]} → {len(chunk)}只", flush=True)
        time.sleep(0.3)
    
    for w in workers:
        w.join()
    
    elapsed = time.time() - stats['t0']
    total_success = sum(w.success for w in workers)
    total_fail = sum(w.fail for w in workers)
    msg = f"✅ 完成! 成功{total_success}只, 失败{total_fail}只, 总耗时{elapsed:.0f}s"
    logging.info(msg)
    print(msg, flush=True)

if __name__ == '__main__':
    main()
