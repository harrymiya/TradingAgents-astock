#!/usr/bin/env python3
"""
A股数据DB备份脚本。
每天收盘后备份 astock_data.db 到 ~/.hermes/backups/ 目录。
保留最近7天的备份，自动清理过期版本。

用法:
  python3 backup_astock_db.py              # 执行备份
  python3 backup_astock_db.py --force      # 强制备份（覆盖当日已有备份）
  python3 backup_astock_db.py --list       # 查看现有备份
  python3 backup_astock_db.py --clean      # 只清理过期备份
"""

import sqlite3
import os
import sys
import shutil
import time
import glob
import argparse
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser('~/.hermes/astock_data.db')
BACKUP_DIR = os.path.expanduser('~/.hermes/backups/')
MAX_DAYS = 60  # 每7天一备，保留60天（~9个备份）

def ensure_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)

def get_db_stats(path):
    """获取DB文件统计信息"""
    if not os.path.exists(path):
        return None, None, None
    size_mb = os.path.getsize(path) / 1024 / 1024
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM daily_klines WHERE date > '2000-01-01'")
        row = cur.fetchone()
        conn.close()
        return size_mb, row[0], row[1], row[2]
    except:
        return size_mb, None, None, None

def backup(force=False):
    ensure_dir()
    
    today = datetime.now().strftime('%Y-%m-%d')
    backup_file = os.path.join(BACKUP_DIR, f'astock_data_{today}.db')
    
    # 检查是否已有当日备份
    if os.path.exists(backup_file) and not force:
        size_mb = os.path.getsize(backup_file) / 1024 / 1024
        print(f"⚠️  当日备份已存在: {backup_file} ({size_mb:.0f}MB)")
        print(f"   使用 --force 覆盖")
        return
    
    # 检查源DB
    if not os.path.exists(DB_PATH):
        print(f"❌ 源DB不存在: {DB_PATH}")
        return
    
    src_size, src_min, src_max, src_rows = get_db_stats(DB_PATH)
    
    print(f"📦 备份 A股数据库")
    print(f"  源: {DB_PATH} ({src_size:.0f}MB, {src_rows:,}行, {src_min}~{src_max})")
    
    t0 = time.time()
    shutil.copy2(DB_PATH, backup_file)
    elapsed = time.time() - t0
    
    dst_size = os.path.getsize(backup_file) / 1024 / 1024
    print(f"  目标: {backup_file}")
    print(f"  大小: {dst_size:.0f}MB")
    print(f"  耗时: {elapsed:.1f}秒")
    print(f"  ✅ 备份完成")
    
    # 清理过期
    clean(quiet=True)

def list_backups():
    ensure_dir()
    
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, 'astock_data_*.db')), reverse=True)
    
    if not files:
        print("📂 暂无备份")
        return
    
    print(f"📂 A股数据库备份列表 ({BACKUP_DIR})")
    print(f"{'='*60}")
    print(f"{'文件名':<35} {'大小':>8} {'状态'}")
    print(f"{'-'*60}")
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    for f in files:
        fname = os.path.basename(f)
        date_str = fname.replace('astock_data_', '').replace('.db', '')
        size_mb = os.path.getsize(f) / 1024 / 1024
        
        # 判断状态
        age_days = (datetime.now() - datetime.strptime(date_str, '%Y-%m-%d')).days
        if age_days == 0:
            status = '今日'
        elif age_days <= MAX_DAYS:
            status = f'{age_days}d前'
        else:
            status = '🕐 过期'
        
        print(f"{fname:<35} {size_mb:>6.0f}MB  {status}")
    print(f"{'='*60}")
    print(f"共 {len(files)} 个备份，保留最近 {MAX_DAYS} 天")

def clean(quiet=False):
    ensure_dir()
    
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, 'astock_data_*.db')))
    cutoff = datetime.now() - timedelta(days=MAX_DAYS)
    deleted = 0
    
    for f in files:
        fname = os.path.basename(f)
        date_str = fname.replace('astock_data_', '').replace('.db', '')
        try:
            file_date = datetime.strptime(date_str, '%Y-%m-%d')
            if file_date < cutoff:
                os.remove(f)
                deleted += 1
                if not quiet:
                    print(f"  🗑  删除过期: {fname}")
        except ValueError:
            continue
    
    if not quiet:
        if deleted:
            print(f"✅ 已清理 {deleted} 个过期备份")
        else:
            print(f"✅ 无过期备份需要清理")
    return deleted

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='A股数据DB备份')
    parser.add_argument('--force', action='store_true', help='强制覆盖当日备份')
    parser.add_argument('--list', action='store_true', help='查看备份列表')
    parser.add_argument('--clean', action='store_true', help='只清理过期备份')
    args = parser.parse_args()
    
    if args.list:
        list_backups()
    elif args.clean:
        clean(quiet=False)
    else:
        backup(force=args.force)
