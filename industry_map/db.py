"""
industry_map/db.py — 产业链数据库操作层

全部数据读写在 astock_data.db 上，提供四个核心接口：
  ChainDB          — 数据库连接管理器
  ChainManager     — 产业链CRUD
  StockManager     — 股票关联CRUD
  IndustryManager  — 行业分类管理
"""

import sqlite3
from pathlib import Path
from collections import defaultdict
from typing import Optional, List, Dict, Any

DB_PATH = Path('/home/harrydolly/.hermes/astock_data.db')

# ============================================================
# 表结构定义（建表DDL）
# ============================================================

SCHEMA_SQL = """
-- 行业分类表
CREATE TABLE IF NOT EXISTS industries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 产业链主表
CREATE TABLE IF NOT EXISTS industry_chains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 产业链-行业关联
CREATE TABLE IF NOT EXISTS chain_industry_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id INTEGER NOT NULL REFERENCES industry_chains(id) ON DELETE CASCADE,
    industry_id INTEGER NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
    UNIQUE(chain_id, industry_id)
);

-- 产业链环节
CREATE TABLE IF NOT EXISTS chain_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id INTEGER NOT NULL REFERENCES industry_chains(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    barrier INTEGER DEFAULT 3,
    localization_rate INTEGER DEFAULT 50,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 环节上游依赖
CREATE TABLE IF NOT EXISTS chain_link_deps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL REFERENCES chain_links(id) ON DELETE CASCADE,
    depends_on_link_id INTEGER NOT NULL REFERENCES chain_links(id) ON DELETE CASCADE,
    UNIQUE(link_id, depends_on_link_id)
);

-- 环节-股票关联
CREATE TABLE IF NOT EXISTS chain_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL REFERENCES chain_links(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    UNIQUE(link_id, code)
);

-- 股票行业归属（从行情API自动更新）
CREATE TABLE IF NOT EXISTS stock_industries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    industry_name TEXT NOT NULL,
    source TEXT DEFAULT 'eastmoney',
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(code, industry_name)
);

-- 东财概念板块（辅助数据）
CREATE TABLE IF NOT EXISTS eastmoney_concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    concept TEXT NOT NULL,
    source TEXT DEFAULT 'eastmoney',
    UNIQUE(code, concept)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_chain_links_chain ON chain_links(chain_id);
CREATE INDEX IF NOT EXISTS idx_chain_stocks_link ON chain_stocks(link_id);
CREATE INDEX IF NOT EXISTS idx_chain_stocks_code ON chain_stocks(code);
CREATE INDEX IF NOT EXISTS idx_stock_industries_code ON stock_industries(code);
CREATE INDEX IF NOT EXISTS idx_em_concepts_code ON eastmoney_concepts(code);
CREATE INDEX IF NOT EXISTS idx_em_concepts_name ON eastmoney_concepts(concept);
"""

# ============================================================
# 数据库连接
# ============================================================

class ChainDB:
    """数据库连接管理器"""
    
    @staticmethod
    def connect():
        db = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db
    
    @staticmethod
    def init_db():
        """初始化建表（安全幂等）"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.executescript(SCHEMA_SQL)
        db.commit()
        db.close()
    
    @staticmethod
    def load_stock_names() -> Dict[str, str]:
        """从stocks表加载名称映射"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("SELECT code, name FROM stocks")
        names = {r['code']: r['name'] for r in cur.fetchall()}
        db.close()
        return names

# ============================================================
# 产业链管理器
# ============================================================

class ChainManager:
    """产业链CRUD"""
    
    @staticmethod
    def list_chains() -> List[Dict]:
        """列出所有产业链及统计信息"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("""
            SELECT c.*, 
                   (SELECT COUNT(*) FROM chain_links WHERE chain_id = c.id) as link_count,
                   (SELECT COUNT(DISTINCT cs.code) FROM chain_stocks cs 
                    JOIN chain_links cl ON cs.link_id = cl.id WHERE cl.chain_id = c.id) as stock_count
            FROM industry_chains c
            ORDER BY stock_count DESC
        """)
        chains = [dict(r) for r in cur.fetchall()]
        db.close()
        return chains
    
    @staticmethod
    def get_chain(chain_name: str) -> Optional[Dict]:
        """获取产业链完整结构"""
        db = ChainDB.connect()
        cur = db.cursor()
        
        cur.execute("SELECT * FROM industry_chains WHERE name = ?", (chain_name,))
        chain = cur.fetchone()
        if not chain:
            db.close()
            return None
        
        chain = dict(chain)
        
        # 环节
        cur.execute("SELECT * FROM chain_links WHERE chain_id = ? ORDER BY sort_order", (chain['id'],))
        links = []
        for r in cur.fetchall():
            r = dict(r)
            # 股票
            cur.execute("""
                SELECT cs.code, COALESCE(s.name, cs.code) as stock_name
                FROM chain_stocks cs
                LEFT JOIN stocks s ON cs.code = s.code
                WHERE cs.link_id = ?
                ORDER BY cs.code
            """, (r['id'],))
            r['stocks'] = [dict(s) for s in cur.fetchall()]
            links.append(r)
        chain['links'] = links
        
        # 依赖（环节名→上游环节名列表）
        cur.execute("""
            SELECT l1.name as link_name, l2.name as dep_name
            FROM chain_link_deps d
            JOIN chain_links l1 ON d.link_id = l1.id
            JOIN chain_links l2 ON d.depends_on_link_id = l2.id
            WHERE l1.chain_id = ?
        """, (chain['id'],))
        
        deps = defaultdict(list)
        for r in cur.fetchall():
            deps[r['link_name']].append(r['dep_name'])
        chain['deps'] = dict(deps)
        
        # 下游（环节名→下游环节名列表）
        cur.execute("""
            SELECT l1.name as link_name, l2.name as dep_name
            FROM chain_link_deps d
            JOIN chain_links l1 ON d.link_id = l1.id
            JOIN chain_links l2 ON d.depends_on_link_id = l2.id
            WHERE l2.chain_id = ?
        """, (chain['id'],))
        
        downstream = defaultdict(list)
        for r in cur.fetchall():
            downstream[r['dep_name']].append(r['link_name'])
        chain['downstream'] = dict(downstream)
        
        db.close()
        return chain
    
    @staticmethod
    def create_chain(name: str, description: str = "") -> int:
        """新增产业链"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("INSERT OR IGNORE INTO industry_chains (name, description) VALUES (?, ?)", 
                    (name, description))
        db.commit()
        chain_id = cur.lastrowid
        db.close()
        return chain_id
    
    @staticmethod
    def delete_chain(name: str) -> bool:
        """删除产业链（级联删除环节、股票关联、依赖）"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("DELETE FROM industry_chains WHERE name = ?", (name,))
        deleted = cur.rowcount > 0
        db.commit()
        db.close()
        return deleted

# ============================================================
# 环节管理器
# ============================================================

class LinkManager:
    """环节CRUD"""
    
    @staticmethod
    def add_link(chain_name: str, link_name: str, level: int = 1, 
                 barrier: int = 3, rate: int = 50, description: str = "",
                 sort_order: int = 0) -> Optional[int]:
        """新增环节"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("SELECT id FROM industry_chains WHERE name = ?", (chain_name,))
        c = cur.fetchone()
        if not c: db.close(); return None
        
        cur.execute("""INSERT INTO chain_links 
            (chain_id, name, level, barrier, localization_rate, description, sort_order) 
            VALUES (?,?,?,?,?,?,?)""",
            (c['id'], link_name, level, barrier, rate, description, sort_order))
        db.commit()
        link_id = cur.lastrowid
        db.close()
        return link_id
    
    @staticmethod
    def add_dep(chain_name: str, link_name: str, dep_name: str) -> bool:
        """设置环节的上游依赖"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("SELECT id FROM industry_chains WHERE name = ?", (chain_name,))
        c = cur.fetchone()
        if not c: db.close(); return False
        
        cur.execute("SELECT id FROM chain_links WHERE chain_id = ? AND name = ?", (c['id'], link_name))
        l = cur.fetchone()
        cur.execute("SELECT id FROM chain_links WHERE chain_id = ? AND name = ?", (c['id'], dep_name))
        d = cur.fetchone()
        if not l or not d: db.close(); return False
        
        cur.execute("INSERT OR IGNORE INTO chain_link_deps (link_id, depends_on_link_id) VALUES (?,?)",
                    (l['id'], d['id']))
        db.commit()
        db.close()
        return True

# ============================================================
# 股票关联管理器
# ============================================================

class StockManager:
    """股票关联管理"""
    
    @staticmethod
    def add_stocks(chain_name: str, link_name: str, codes: List[str]) -> int:
        """批量添加股票到环节"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("SELECT id FROM industry_chains WHERE name = ?", (chain_name,))
        c = cur.fetchone()
        if not c: db.close(); return 0
        
        cur.execute("SELECT id FROM chain_links WHERE chain_id = ? AND name = ?", (c['id'], link_name))
        l = cur.fetchone()
        if not l: db.close(); return 0
        
        added = 0
        for code in codes:
            code = code.strip()
            if not code: continue
            # 也确保stocks表有记录
            cur.execute("INSERT OR IGNORE INTO stocks (code, name) VALUES (?, ?)", (code, code))
            cur.execute("INSERT OR IGNORE INTO chain_stocks (link_id, code) VALUES (?,?)", (l['id'], code))
            if cur.rowcount: added += 1
        
        db.commit()
        db.close()
        return added
    
    @staticmethod
    def remove_stock(chain_name: str, link_name: str, code: str) -> bool:
        """移除股票"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("""
            DELETE FROM chain_stocks 
            WHERE link_id = (SELECT cl.id FROM chain_links cl 
                             JOIN industry_chains ic ON cl.chain_id = ic.id
                             WHERE ic.name = ? AND cl.name = ?)
            AND code = ?
        """, (chain_name, link_name, code))
        removed = cur.rowcount > 0
        db.commit()
        db.close()
        return removed

# ============================================================
# 行业管理器
# ============================================================

class IndustryManager:
    """行业分类管理"""
    
    @staticmethod
    def list_industries() -> List[Dict]:
        """列出所有行业及关联产业链数"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("""
            SELECT i.*, COUNT(cit.chain_id) as chain_count
            FROM industries i
            LEFT JOIN chain_industry_tags cit ON i.id = cit.industry_id
            GROUP BY i.id
            ORDER BY chain_count DESC, i.sort_order
        """)
        inds = [dict(r) for r in cur.fetchall()]
        db.close()
        return inds
    
    @staticmethod
    def get_stock_industry(code: str) -> Optional[str]:
        """获取股票的行业归属"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("SELECT industry_name FROM stock_industries WHERE code = ? LIMIT 1", (code,))
        r = cur.fetchone()
        db.close()
        return r['industry_name'] if r else None
    
    @staticmethod
    def get_stocks_by_industry(industry_name: str) -> List[str]:
        """获取某行业的所有股票代码"""
        db = ChainDB.connect()
        cur = db.cursor()
        cur.execute("SELECT code FROM stock_industries WHERE industry_name = ?", (industry_name,))
        codes = [r['code'] for r in cur.fetchall()]
        db.close()
        return codes

# ============================================================
# 初始化
# ============================================================

# 首次导入时自动建表
ChainDB.init_db()
