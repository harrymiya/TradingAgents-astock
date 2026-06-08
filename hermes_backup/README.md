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
