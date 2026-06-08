#!/bin/bash
# Hermes 完整迁移打包脚本
# 用法: ./package_hermes.sh                    # 全量包
#       ./package_hermes.sh --light            # 轻量包（不含A股DB和项目代码）
#       ./package_hermes.sh --restore TARGET   # 解压恢复到指定目录

set -e

HERMES_HOME="$HOME/.hermes"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MODE="${1:-full}"

if [ "$MODE" = "--restore" ]; then
    TARGET="$2"
    if [ -z "$TARGET" ]; then
        echo "用法: $0 --restore <目标目录>"
        exit 1
    fi
    echo "📦 恢复 Hermes 到 $TARGET"
    TAR=$(ls -t $HOME/hermes_backup_*.tar.gz 2>/dev/null | head -1)
    if [ -z "$TAR" ]; then
        echo "❌ 未找到备份包"
        exit 1
    fi
    tar xzf "$TAR" -C "$TARGET"
    echo "✅ 恢复完成: $TAR → $TARGET"
    echo "⚠️  请检查 config.yaml 中的 API Key 和平台配置"
    exit 0
fi

echo "📦 Hermes 环境打包 (模式: $MODE)"
echo "================================================"

# 临时目录
TMPDIR=$(mktemp -d)
PACKAGE="$HOME/hermes_backup_${TIMESTAMP}.tar.gz"
LIGHT_PACKAGE="$HOME/hermes_backup_${TIMESTAMP}_light.tar.gz"

# 1. 核心配置 (所有情况都包)
echo "  [1/5] 打包核心配置..."
mkdir -p "$TMPDIR/hermes/config"
cp "$HERMES_HOME/config.yaml" "$TMPDIR/hermes/config/"
cp "$HERMES_HOME/.env" "$TMPDIR/hermes/config/" 2>/dev/null || true
cp "$HERMES_HOME/auth.json" "$TMPDIR/hermes/config/" 2>/dev/null || true
cp "$HERMES_HOME/SOUL.md" "$TMPDIR/hermes/" 2>/dev/null || true

# 2. 记忆
echo "  [2/5] 打包记忆..."
mkdir -p "$TMPDIR/hermes/memories"
cp -r "$HERMES_HOME/memories/"* "$TMPDIR/hermes/memories/" 2>/dev/null || true

# 3. Skills
echo "  [3/5] 打包Skills..."
mkdir -p "$TMPDIR/hermes/skills"
for skill_dir in "$HERMES_HOME/skills/"*/; do
    skill_name=$(basename "$skill_dir")
    if [ "$skill_name" != "apple" ] && [ "$skill_name" != "dogfood" ]; then
        mkdir -p "$TMPDIR/hermes/skills/$skill_name"
        cp -r "$skill_dir"* "$TMPDIR/hermes/skills/$skill_name/" 2>/dev/null || true
    fi
done

# 4. 脚本
echo "  [4/5] 打包脚本..."
mkdir -p "$TMPDIR/hermes/scripts"
cp "$HERMES_HOME/scripts/"*.py "$TMPDIR/hermes/scripts/" 2>/dev/null || true
cp "$HERMES_HOME/scripts/"*.sh "$TMPDIR/hermes/scripts/" 2>/dev/null || true

# 5. A股数据和会话DB (light模式跳过)
if [ "$MODE" = "--light" ]; then
    echo "  [5/5] ⚡ 轻量模式: 跳过A股DB(766MB)和state.db"
    echo ""
    echo "   ⚠️  轻量包不含:"
    echo "     - astock_data.db (可到新机器用mootdx重新拉取)"
    echo "     - state.db (会话索引丢失，但不影响功能)"
else
    echo "  [5/5] 打包A股DB和会话索引..."
    cp "$HERMES_HOME/astock_data.db" "$TMPDIR/hermes/" 2>/dev/null || true
    cp "$HERMES_HOME/state.db" "$TMPDIR/hermes/" 2>/dev/null || true
fi

# 打包
cd "$TMPDIR"
if [ "$MODE" = "--light" ]; then
    tar czf "$LIGHT_PACKAGE" hermes/
    FINAL_PACKAGE="$LIGHT_PACKAGE"
else
    tar czf "$PACKAGE" hermes/
    FINAL_PACKAGE="$PACKAGE"
fi

# 清理
cd "$HOME"
rm -rf "$TMPDIR"

# 报告
SIZE=$(du -h "$FINAL_PACKAGE" | cut -f1)
echo ""
echo "✅ 打包完成!"
echo "  包: $FINAL_PACKAGE"
echo "  大小: $SIZE"
echo ""
echo "📋 在新机器上恢复:"
echo "  tar xzf $FINAL_PACKAGE -C \$HOME"
echo "  然后 ln -sf \$HOME/hermes \$HOME/.hermes  (或直接放在正确位置)"
echo "  或使用: $0 --restore \$HOME"
echo ""
echo "⚠️  迁移后需要在新机器上做:"
echo "  1. 检查 config.yaml 中的 API Key 是否有效"
echo "  2. 重新安装 Hermes Agent（apt/pip）"
echo "  3. git clone TradingAgents-astock + pip install -e ."
echo "  4. 重新配置平台通道（Feishu/Telegram的Token可能过期）"
