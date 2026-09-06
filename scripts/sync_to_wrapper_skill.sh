#!/bin/bash
# 竞彩插件 → 反向封装Skill 自动同步脚本（自动发现版）
# 用法: bash scripts/sync_to_wrapper_skill.sh
# 作用: 自动发现所有服务器和技能，同步到封装Skill，并自动更新SKILL.md

set -e

PLUGIN_ROOT="/home/user/.super_doubao/super-doubao-runtime/workspace/jingcai-football-plugin"
SKILL_ROOT="/home/user/.super_doubao/super-doubao-runtime/workspace/.user_skills/jingcai-football-plugin-skill"

echo "=== 竞彩插件 → 封装Skill 同步（自动发现版）==="
echo "插件根: $PLUGIN_ROOT"
echo "封装根: $SKILL_ROOT"
echo ""

# 1. 自动发现并同步MCP服务器
echo "【1/7】同步MCP服务器（自动发现）..."
SERVER_COUNT=0
for server_dir in "$PLUGIN_ROOT"/servers/*/; do
    server=$(basename "$server_dir")
    # 跳过空目录
    if [ ! -f "$server_dir/server.py" ]; then
        echo "  ⏭️  $server (无server.py，跳过)"
        continue
    fi
    mkdir -p "$SKILL_ROOT/servers/$server"
    cp -r "$server_dir"*.py "$SKILL_ROOT/servers/$server/" 2>/dev/null || true
    # 统计工具数
    TOOL_COUNT=$(grep -c "@mcp.tool" "$server_dir/server.py" 2>/dev/null || echo 0)
    echo "  ✅ $server ($TOOL_COUNT工具)"
    SERVER_COUNT=$((SERVER_COUNT + 1))
done
echo "  共 $SERVER_COUNT 个服务器"

# 2. 自动发现并同步技能
echo ""
echo "【2/7】同步技能（自动发现）..."
SKILL_COUNT=0
for skill_dir in "$PLUGIN_ROOT"/skills/*/; do
    skill=$(basename "$skill_dir")
    if [ ! -f "$skill_dir/SKILL.md" ]; then
        echo "  ⏭️  $skill (无SKILL.md，跳过)"
        continue
    fi
    mkdir -p "$SKILL_ROOT/skills/$skill"
    cp "$skill_dir/SKILL.md" "$SKILL_ROOT/skills/$skill/" 2>/dev/null || true
    # 同步references
    if [ -d "$skill_dir/references" ]; then
        mkdir -p "$SKILL_ROOT/skills/$skill/references"
        cp -r "$skill_dir/references/"* "$SKILL_ROOT/skills/$skill/references/" 2>/dev/null || true
    fi
    # 同步scripts
    if [ -d "$skill_dir/scripts" ]; then
        mkdir -p "$SKILL_ROOT/skills/$skill/scripts"
        cp -r "$skill_dir/scripts/"* "$SKILL_ROOT/skills/$skill/scripts/" 2>/dev/null || true
    fi
    LINES=$(wc -l < "$skill_dir/SKILL.md" 2>/dev/null || echo 0)
    echo "  ✅ $skill (${LINES}行)"
    SKILL_COUNT=$((SKILL_COUNT + 1))
done
echo "  共 $SKILL_COUNT 个技能"

# 3. 同步公共模块
echo ""
echo "【3/7】同步公共模块..."
mkdir -p "$SKILL_ROOT/common"
cp "$PLUGIN_ROOT/common/"*.py "$SKILL_ROOT/common/" 2>/dev/null || true
echo "  ✅ common"

# 4. 同步数据资产
echo ""
echo "【4/7】同步数据资产..."
mkdir -p "$SKILL_ROOT/data/history"
cp "$PLUGIN_ROOT/data/"*.json "$SKILL_ROOT/data/" 2>/dev/null || true
cp "$PLUGIN_ROOT/data/"*.pkl "$SKILL_ROOT/data/" 2>/dev/null || true
cp "$PLUGIN_ROOT/data/"*.md "$SKILL_ROOT/data/" 2>/dev/null || true
cp "$PLUGIN_ROOT/data/history/"*.json "$SKILL_ROOT/data/history/" 2>/dev/null || true
echo "  ✅ data (历史数据+ML模型+配置)"

# 5. 同步插件配置
echo ""
echo "【5/7】同步插件配置..."
mkdir -p "$SKILL_ROOT/references"
cp "$PLUGIN_ROOT/plugin.json" "$SKILL_ROOT/references/" 2>/dev/null || true
cp "$PLUGIN_ROOT/mcp.json" "$SKILL_ROOT/references/" 2>/dev/null || true
cp "$PLUGIN_ROOT/README.md" "$SKILL_ROOT/" 2>/dev/null || true
echo "  ✅ plugin.json + mcp.json + README"

# 6. 同步启动脚本
echo ""
echo "【6/7】同步启动脚本..."
mkdir -p "$SKILL_ROOT/scripts"
cp "$PLUGIN_ROOT/scripts/start_mcp.py" "$SKILL_ROOT/scripts/" 2>/dev/null || true
echo "  ✅ start_mcp.py"

# 7. 自动更新封装Skill的SKILL.md（调用Python脚本）
echo ""
echo "【7/7】自动更新封装Skill的SKILL.md..."
python3 "$PLUGIN_ROOT/scripts/update_wrapper_skill.py"

echo ""
echo "=== MD5校验（关键文件）==="
for f in servers/data-collector/server.py servers/analyzer/server.py skills/jingcai-core/SKILL.md data/ml_model.pkl; do
    if [ -f "$PLUGIN_ROOT/$f" ] && [ -f "$SKILL_ROOT/$f" ]; then
        h1=$(md5sum "$PLUGIN_ROOT/$f" | awk '{print $1}')
        h2=$(md5sum "$SKILL_ROOT/$f" | awk '{print $1}')
        if [ "$h1" = "$h2" ]; then
            echo "  ✅ $f (MD5一致)"
        else
            echo "  ❌ $f (MD5不一致!)"
        fi
    fi
done

echo ""
echo "=== 同步完成 ==="
echo "封装Skill路径: $SKILL_ROOT"
echo "版本: v$PLUGIN_VERSION | 技能: $SKILL_COUNT | 服务器: $SERVER_COUNT | 工具: $TOTAL_TOOLS"
echo "下次修改插件后，运行: bash scripts/sync_to_wrapper_skill.sh"
