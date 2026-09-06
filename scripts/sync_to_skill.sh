#!/bin/bash
# ============================================================
# 竞彩足球插件 → 反向封装Skill 自动同步脚本
# 
# 功能：
#   1. 检查插件版本和Skill版本
#   2. 自动反向封装，同步最新代码
#   3. 验证同步结果
#   4. 输出同步报告
#
# 用法：
#   bash sync_to_skill.sh              # 自动同步（版本不同才同步）
#   bash sync_to_skill.sh --force      # 强制同步
#   bash sync_to_skill.sh --check      # 仅检查版本，不同步
#   bash sync_to_skill.sh --verify     # 仅验证同步结果
# ============================================================

set -e

# 配置
PLUGIN_DIR="/home/user/.super_doubao/super-doubao-runtime/workspace/jingcai-football-plugin"
SKILL_DIR="/home/user/.super_doubao/super-doubao-runtime/workspace/.user_skills/jingcai-football-plugin-skill"
PLUGIN_CREATOR="/home/user/.super_doubao/super-doubao-runtime/workspace/.user_skills/agent-plugin-creator/scripts/plugin_to_skill.py"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 函数：打印带颜色的消息
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 函数：获取插件版本
get_plugin_version() {
    grep '"version"' "$PLUGIN_DIR/plugin.json" | head -1 | sed 's/.*"version": *"\([^"]*\)".*/\1/'
}

# 函数：获取Skill版本
get_skill_version() {
    grep 'plugin-version' "$SKILL_DIR/SKILL.md" | sed 's/.*plugin-version: *\([^ ]*\).*/\1/'
}

# 函数：检查版本
check_versions() {
    info "检查版本状态..."
    
    if [ ! -f "$PLUGIN_DIR/plugin.json" ]; then
        error "插件目录不存在: $PLUGIN_DIR"
        return 1
    fi
    
    PLUGIN_VERSION=$(get_plugin_version)
    info "插件版本: v$PLUGIN_VERSION"
    
    if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
        warning "Skill目录不存在，将创建新的"
        SKILL_VERSION="未安装"
    else
        SKILL_VERSION=$(get_skill_version)
    fi
    info "Skill版本: v$SKILL_VERSION"
    
    if [ "$PLUGIN_VERSION" = "$SKILL_VERSION" ]; then
        success "版本一致，无需同步"
        return 0
    else
        warning "版本不一致，需要同步"
        return 1
    fi
}

# 函数：执行同步
do_sync() {
    info "开始同步插件到Skill..."
    info "  插件目录: $PLUGIN_DIR"
    info "  Skill目录: $SKILL_DIR"
    echo ""
    
    # 执行反向封装
    python3 "$PLUGIN_CREATOR" "$PLUGIN_DIR" --output "$SKILL_DIR" --force
    
    echo ""
    success "反向封装完成"
}

# 函数：验证同步结果
verify_sync() {
    info "验证同步结果..."
    echo ""
    
    # 1. 版本验证
    PLUGIN_VERSION=$(get_plugin_version)
    SKILL_VERSION=$(get_skill_version)
    
    if [ "$PLUGIN_VERSION" = "$SKILL_VERSION" ]; then
        success "版本同步: v$PLUGIN_VERSION"
    else
        error "版本不同步: 插件v$PLUGIN_VERSION vs Skill v$SKILL_VERSION"
        return 1
    fi
    
    # 2. 文件数对比
    PLUGIN_FILES=$(find "$PLUGIN_DIR" -type f | wc -l)
    SKILL_FILES=$(find "$SKILL_DIR" -type f | wc -l)
    info "文件数: 插件$PLUGIN_FILES个 / Skill$SKILL_FILES个"
    
    # 3. 关键文件验证
    info "关键文件验证:"
    KEY_FILES=(
        "SKILL.md"
        "skills/jingcai-core/SKILL.md"
        "skills/jingcai-spf/SKILL.md"
        "skills/jingcai-rangqiu/SKILL.md"
        "skills/jingcai-zongjinqiu/SKILL.md"
        "skills/jingcai-bifen/SKILL.md"
        "skills/jingcai-banquanchang/SKILL.md"
        "servers/data-collector/server.py"
        "servers/analyzer/server.py"
        "servers/report-generator/server.py"
        "servers/quality-control/server.py"
        "servers/portfolio/server.py"
        "servers/self-evolution/server.py"
        "common/error_handler.py"
        "common/param_helpers.py"
        "data/update_history.py"
        "tests/mock_data_generator.py"
        "tests/e2e_test.py"
    )
    
    ALL_EXIST=true
    for file in "${KEY_FILES[@]}"; do
        if [ -f "$SKILL_DIR/$file" ]; then
            success "  ✅ $file"
        else
            error "  ❌ $file 缺失"
            ALL_EXIST=false
        fi
    done
    
    echo ""
    if [ "$ALL_EXIST" = true ]; then
        success "所有关键文件验证通过"
        return 0
    else
        error "部分关键文件缺失"
        return 1
    fi
}

# 函数：显示帮助
show_help() {
    echo "竞彩足球插件 → Skill 自动同步脚本"
    echo ""
    echo "用法:"
    echo "  bash sync_to_skill.sh [选项]"
    echo ""
    echo "选项:"
    echo "  (无参数)    自动同步（版本不同才同步）"
    echo "  --force     强制同步（不管版本是否一致）"
    echo "  --check     仅检查版本，不同步"
    echo "  --verify    仅验证同步结果"
    echo "  --help      显示帮助"
    echo ""
    echo "示例:"
    echo "  bash sync_to_skill.sh           # 自动同步"
    echo "  bash sync_to_skill.sh --force   # 强制同步"
    echo "  bash sync_to_skill.sh --check   # 检查版本"
}

# ============================================================
# 主流程
# ============================================================

echo ""
echo "============================================================"
echo "  竞彩足球插件 → Skill 自动同步工具"
echo "============================================================"
echo ""

# 解析参数
case "${1:-}" in
    --help|-h)
        show_help
        exit 0
        ;;
    --check)
        check_versions
        exit $?
        ;;
    --verify)
        verify_sync
        exit $?
        ;;
    --force)
        info "强制同步模式"
        do_sync
        echo ""
        verify_sync
        exit $?
        ;;
    *)
        # 自动同步模式
        if check_versions; then
            # 版本一致，无需同步
            echo ""
            success "同步完成（版本已一致，无需操作）"
            exit 0
        else
            # 版本不一致，执行同步
            echo ""
            do_sync
            echo ""
            verify_sync
            exit $?
        fi
        ;;
esac
