#!/bin/bash
# 竞彩插件 → 反向封装Skill 自动同步脚本
# 用法: bash scripts/sync_to_wrapper_skill.sh
# 作用: 将插件根目录的所有变更自动同步到 .user_skills/jingcai-football-plugin-skill/

set -e

PLUGIN_ROOT="/home/user/.super_doubao/super-doubao-runtime/workspace/jingcai-football-plugin"
SKILL_ROOT="/home/user/.super_doubao/super-doubao-runtime/workspace/.user_skills/jingcai-football-plugin-skill"

echo "=== 竞彩插件 → 封装Skill 同步 ==="
echo "插件根: $PLUGIN_ROOT"
echo "封装根: $SKILL_ROOT"
echo ""

# 1. 同步6个MCP服务器
echo "【1/6】同步MCP服务器..."
for server in data-collector analyzer report-generator quality-control portfolio self-evolution workflow; do
    mkdir -p "$SKILL_ROOT/servers/$server"
    cp -r "$PLUGIN_ROOT/servers/$server/"*.py "$SKILL_ROOT/servers/$server/" 2>/dev/null || true
    echo "  ✅ $server"
done

# 2. 同步6个技能（含references）
echo "【2/6】同步技能..."
for skill in jingcai-core jingcai-spf jingcai-rangqiu jingcai-zongjinqiu jingcai-bifen jingcai-banquanchang; do
    mkdir -p "$SKILL_ROOT/skills/$skill"
    cp "$PLUGIN_ROOT/skills/$skill/SKILL.md" "$SKILL_ROOT/skills/$skill/" 2>/dev/null || true
    if [ -d "$PLUGIN_ROOT/skills/$skill/references" ]; then
        mkdir -p "$SKILL_ROOT/skills/$skill/references"
        cp -r "$PLUGIN_ROOT/skills/$skill/references/"* "$SKILL_ROOT/skills/$skill/references/" 2>/dev/null || true
    fi
    echo "  ✅ $skill"
done

# 3. 同步公共模块
echo "【3/6】同步公共模块..."
mkdir -p "$SKILL_ROOT/common"
cp "$PLUGIN_ROOT/common/"*.py "$SKILL_ROOT/common/" 2>/dev/null || true
echo "  ✅ common"

# 4. 同步数据资产（历史数据+ML模型+配置）
echo "【4/6】同步数据资产..."
mkdir -p "$SKILL_ROOT/data/history"
cp "$PLUGIN_ROOT/data/"*.json "$SKILL_ROOT/data/" 2>/dev/null || true
cp "$PLUGIN_ROOT/data/"*.pkl "$SKILL_ROOT/data/" 2>/dev/null || true
cp "$PLUGIN_ROOT/data/"*.md "$SKILL_ROOT/data/" 2>/dev/null || true
cp "$PLUGIN_ROOT/data/history/"*.json "$SKILL_ROOT/data/history/" 2>/dev/null || true
echo "  ✅ data (31联赛历史+ML模型+配置)"

# 5. 同步插件配置
echo "【5/6】同步插件配置..."
mkdir -p "$SKILL_ROOT/references"
cp "$PLUGIN_ROOT/plugin.json" "$SKILL_ROOT/references/" 2>/dev/null || true
cp "$PLUGIN_ROOT/mcp.json" "$SKILL_ROOT/references/" 2>/dev/null || true
cp "$PLUGIN_ROOT/README.md" "$SKILL_ROOT/" 2>/dev/null || true
echo "  ✅ plugin.json + mcp.json + README"

# 6. 同步start_mcp.py
echo "【6/6】同步启动脚本..."
cp "$PLUGIN_ROOT/scripts/start_mcp.py" "$SKILL_ROOT/scripts/" 2>/dev/null || true
echo "  ✅ start_mcp.py"

echo ""
echo "=== MD5校验（关键文件）==="
for f in servers/data-collector/server.py servers/analyzer/server.py skills/jingcai-core/SKILL.md data/ml_model.pkl data/league_source_map.json; do
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
echo "下次修改插件后，运行: bash scripts/sync_to_wrapper_skill.sh"
