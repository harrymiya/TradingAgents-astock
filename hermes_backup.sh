#!/usr/bin/env bash
# hermes_backup_to_project.sh
# 打包Hermes skills + configs → TradingAgents-astock project
# 每周执行一次

set -e

DATE_TAG=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="/home/harrydolly/code/TradingAgents-astock"
BACKUP_DIR="${PROJECT_DIR}/hermes_backup"
SKILL_DIR="${BACKUP_DIR}/skills"
CONFIG_DIR="${BACKUP_DIR}/config"
CRON_DIR="${BACKUP_DIR}/cron"
MEMORY_DIR="${BACKUP_DIR}/memory"

echo "=== Hermes Backup to Project ==="
echo "Date: $(date)"
echo ""

# 清理旧备份
rm -rf "$BACKUP_DIR"
mkdir -p "$SKILL_DIR" "$CONFIG_DIR" "$CRON_DIR" "$MEMORY_DIR"

# 1. Skills — 所有自定义skill
echo "1/4 Skills..."
cp -r ~/.hermes/skills/* "$SKILL_DIR/" 2>/dev/null || echo "  (no skills)"
# 扁平化找所有SKILL.md
find "$SKILL_DIR" -name "SKILL.md" | while read f; do
    name=$(basename "$(dirname "$f")")
    echo "  ✓ $name"
done

# 2. Configs
echo "2/4 Configs..."
cp ~/.hermes/config.yaml "$CONFIG_DIR/" 2>/dev/null || echo "  (no config)"
cp ~/.hermes/.env "$CONFIG_DIR/" 2>/dev/null || echo "  (no .env)"
cp ~/.hermes/profiles.yaml "$CONFIG_DIR/" 2>/dev/null || echo "  (no profiles)"

# 3. Cron jobs — 导出当前cron定义
echo "3/4 Cron..."
hermes cron list > "$CRON_DIR/cron_list.txt" 2>/dev/null || echo "  (no cron list)"
# crontab -l 作为补充
crontab -l > "$CRON_DIR/crontab.txt" 2>/dev/null || echo "  (no crontab)"

# 4. Memory — 当前记忆（不包含数据库）
echo "4/4 Memory..."
cp ~/.hermes/memory.md "$MEMORY_DIR/" 2>/dev/null || echo "  (no memory)"
cp ~/.hermes/user.md "$MEMORY_DIR/" 2>/dev/null || echo "  (no user profile)"
# session DB太大，只保存结构
ls -lh ~/.hermes/*.db 2>/dev/null | head -5 > "$MEMORY_DIR/db_info.txt"

# 5. 自定义脚本
if [ -d ~/.hermes/scripts ]; then
    mkdir -p "$BACKUP_DIR/scripts"
    cp -r ~/.hermes/scripts/* "$BACKUP_DIR/scripts/" 2>/dev/null
fi

# 6. 生成README
cat > "$BACKUP_DIR/README.md" << 'REOF'
# Hermes Agent Backup

> 自动备份于 $(date +%Y-%m-%d_%H:%M:%S)

## 目录结构

- `skills/` — Hermes 所有技能（SKILL.md）
- `config/` — 配置文件 (config.yaml, .env)
- `cron/` — 定时任务定义
- `memory/` — 记忆文件
- `scripts/` — 自定义脚本

## 恢复方法

```bash
# Skills
cp -r skills/* ~/.hermes/skills/

# Config
cp config/config.yaml ~/.hermes/
cp config/.env ~/.hermes/

# 注意: session DB (~/.hermes/*.db) 未备份，已包含在 astock_data.db 中
```
REOF

# 7. 创建说明文件，告诉Git这个目录是外来的
echo "This directory contains Hermes Agent backup data (skills, configs, memories)." > "$BACKUP_DIR/.gitignore"
echo "It is NOT part of the TradingAgents-astock source code." >> "$BACKUP_DIR/.gitignore"
echo "" >> "$BACKUP_DIR/.gitignore"
echo "# Don't gitignore the files themselves - we want them tracked" > "$BACKUP_DIR/.gitkeep"

# 统计
echo ""
echo "=== 备份统计 ==="
echo "Skills: $(find $SKILL_DIR -name 'SKILL.md' | wc -l) 个技能"
echo "Config: $(ls $CONFIG_DIR 2>/dev/null | wc -l) 个文件"
echo "Scripts: $(find $BACKUP_DIR/scripts -type f 2>/dev/null | wc -l) 个"
echo "总大小: $(du -sh $BACKUP_DIR | cut -f1)"
echo ""
echo "✅ 备份完成: $BACKUP_DIR"
