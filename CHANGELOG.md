# 竞彩足球插件 更新日志

## [1.12.0] - 2026-09-06

### 新增
- P3-1: 新增visualization服务器（6个工具：赔率走势图/概率雷达图/收益矩阵/命中率趋势/HTML交互报告/EV分布图）
- P3-2: 新增自动化测试套件tests/test_all.py（38个测试用例，覆盖9个服务器+端到端workflow+插件结构）
- 补充: 新增jingcai-mixed混合过关专属技能（木桶原则/玩法搭配策略/过关上限/决策树）
- 补充: 数据文件治理（创建models/calibration/decisions/third_party子目录）

### 优化
- 修复analyzer服务器外部模块导入问题（fund_flow/error_handler/confidence_filter改为try-except）
- 修复self-evolution服务器缺少PLUGIN_ROOT定义
- 修复workflow服务器缺少ni/viz变量定义
- 自动化测试38/38全部通过

## [1.11.0] - 2026-09-06

### 新增
- P2-1: 新增news-intelligence服务器（7个工具：搜索关键词/资讯解析/伤停量化/战意分析/赛程疲劳/λ映射/智能聚合）
- P2-3: 用户偏好记忆功能（user_preferences.json + get_user_preferences/update_user_preferences）
- P2-2: 并行执行基础设施（parallel_call函数，ThreadPoolExecutor）

### 优化
- P2-3: jingcai-core技能新增"LLM参与点规范"（3个参与点+人机协作模式+能力检查清单）
- P2-2: 阶段2历史数据工具组并行执行，耗时从15分钟降至5.8秒
- MCP服务器从7个→8个，工具总数从127→136个

## [1.10.0] - 2026-09-06

### 新增
- P1-2: 5个玩法技能各增加决策树（什么时候选/不选这个玩法+适配度评分）
- P1-3: 新增4个历史数据工具（find_similar_matches/league_pattern_match/strategy_backtest/update_team_strength）

### 优化
- P1-1: analyzer工具分类治理（L1基础18/L2高级16/L3玩法定制10/L4历史数据8）
- 创建docs/tool_classification.md工具分类文档
- 工具总数从123→127个

## [1.9.0] - 2026-09-06

### 新增
- P0-1: 新增common/tool_response.py统一返回格式（ok/fail/parse_response/safe_tool）
- P0-2: 工作流可观测性（数据完整性/分析覆盖率/工具性能/错误记录）

### 优化
- workflow服务器使用标准返回格式（tool/success/data/meta/error）
- safe_call兼容新旧格式（parse_response适配层）
- 工具调用成功率99%（108/109）

## [1.8.1] - 2026-09-06

### 新增
- 新增workflow服务器（run_full_workflow超级一键工具，4阶段调用109个工具）
- 工具总数达到123个，调用成功率100%（109/109）

### 优化
- 移除3个重复工具（collect_all_matches/get_odds_history/record_odds_snapshot）
- 修复多个服务器内部FunctionTool调用bug
- 添加README.md完整使用说明
- 初始化git仓库，pre-commit hook自动同步封装Skill
