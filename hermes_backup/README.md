# Hermes Agent Backup

> 自动备份于 2026-06-09
> 95个skill + config + cron，17MB

## 目录结构

```
hermes_backup/
├── skills/        # 95个 Hermes skill（完整备份）
├── config/        # config.yaml
├── cron/          # cronjob 列表
├── memory/        # 记忆文件（不含session DB）
├── scripts/       # 自定义脚本（9个）
├── RESTORE.md     # ⭐ 恢复手册 — 给人看的人
├── AGENTS.md      # ⭐ 初始化上下文 — 给下一个Hermes AI看
└── README.md      # 本文件
```

## 快速恢复命令

```bash
# Skills
cp -r skills/* ~/.hermes/skills/

# Config
cp config/config.yaml ~/.hermes/
cp config/.env ~/.hermes/
```

**需要额外恢复：**
- `~/.hermes/astock_data.db` — A股日线数据库（766MB，从源机器拷贝或重建）
- `~/.hermes/state.db` — Hermes session 数据库（自动重建）
