# 竞彩足球全量深度分析插件

> **版本**: v1.8.1 | **规范**: Agent Plugins 1.0.0 | **工具**: 123个MCP工具 | **技能**: 6个

## 概述

专业级竞彩足球分析预测Agent Plugin，覆盖数据采集、深度分析、报告生成、质量控制、投注组合、自进化闭环全流程。支持胜平负/让球胜平负/总进球/比分/半全场5种玩法+混合过关。

## 核心特性

- **超级一键工具** `run_full_workflow`：一次调用自动触发完整工作流，调用109个MCP工具，成功率100%
- **5玩法专属分析**：每种玩法独立的分析方法论、EV门槛、Kelly系数、过关上限
- **4阶段工作流**：数据采集→深度分析→投注组合→自进化闭环
- **自进化机制**：投注入库→赛后结算→复盘反思→经验回流到下一次分析
- **多模型矩阵**：泊松+Dixon-Coles+4模型集成+ML双模型+Elo/Glicko-2评分
- **31联赛10万场历史数据**：模型校准、回测、相同对阵分析

## 快速开始

### 方式1：超级一键工具（推荐）

只需调用一个工具，自动完成全部工作流：

```python
run_full_workflow(
    date='2026-09-06',        # 比赛日期
    total_budget=500,          # 总预算（元）
    risk_preference='balanced' # 风险偏好: conservative/balanced/aggressive
)
```

内部自动执行：
1. **阶段1**：采集当期所有比赛的5玩法赔率+8大资讯+第三方赔率+支持率
2. **阶段2**：48个分析工具逐场深度分析（5玩法全覆盖）
3. **阶段3**：动态生成投注组合方案（非硬解码，根据当期价值机会）
4. **阶段4**：自进化闭环（决策记录+经验沉淀+模型校准）

### 方式2：分步调用

根据需要调用各服务器的独立工具，详见下方MCP工具列表。

## 技能列表

| 技能 | 用途 | EV门槛 | Kelly系数 | 过关上限 |
|------|------|--------|----------|---------|
| `jingcai-core` | 核心协调层，工作流编排 | - | - | - |
| `jingcai-spf` | 胜平负玩法专属 | +5% | 0.25 | 8关 |
| `jingcai-rangqiu` | 让球胜平负玩法专属 | +5% | 0.20 | 8关 |
| `jingcai-zongjinqiu` | 总进球玩法专属 | +7% | 0.20 | 6关 |
| `jingcai-bifen` | 比分玩法专属 | +15% | 0.03 | 4关 |
| `jingcai-banquanchang` | 半全场玩法专属 | +12% | 0.05 | 4关 |

## MCP服务器与工具

| 服务器 | 工具数 | 核心能力 |
|--------|--------|---------|
| `data-collector` | 29 | 官方5玩法赔率/8大资讯/第三方赔率/支持率/多源交叉验证 |
| `analyzer` | 48 | 泊松/Dixon-Coles/4模型集成/ML预测/半全场条件概率/反向指标/多视角分析 |
| `portfolio` | 19 | 动态投注组合/M串N/复式/保本结构/资金管理/标准投注单 |
| `quality-control` | 4 | 官方规则校验/预检/反思检查/混合过关木桶原则 |
| `self-evolution` | 17 | 决策日志/赛后复盘/模型校准/策略回测/记忆管理/案例库 |
| `report-generator` | 5 | 数据报告/全玩法分析报告/标准化输出 |
| `workflow` | 1 | 超级一键工具`run_full_workflow` |

## 目录结构

```
jingcai-football-plugin/
├── plugin.json              # 插件清单
├── mcp.json                 # MCP配置（7个服务器）
├── README.md                # 本文件
├── skills/                  # 6个技能（1核心+5玩法专属）
│   ├── jingcai-core/
│   ├── jingcai-spf/
│   ├── jingcai-rangqiu/
│   ├── jingcai-zongjinqiu/
│   ├── jingcai-bifen/
│   └── jingcai-banquanchang/
├── servers/                 # 7个MCP服务器
│   ├── data-collector/
│   ├── analyzer/
│   ├── portfolio/
│   ├── quality-control/
│   ├── self-evolution/
│   ├── report-generator/
│   └── workflow/
├── data/                    # 数据资产
│   ├── history/             # 31联赛10万场历史数据
│   ├── ml_model.pkl         # ML模型（83328样本训练）
│   ├── lambda_calibration.json  # 分联赛λ校准参数
│   └── decision_log.json    # 决策日志
├── scripts/                 # 辅助脚本
│   ├── sync_to_wrapper_skill.sh  # 同步到反向封装Skill
│   ├── batch_third_party_collector.py
│   └── batch_news_collector.py
└── output/                  # 输出目录（报告/投注单）
```

## 数据采集说明

### 官方数据（竞彩网API）
- ✅ 5玩法赔率：胜平负/让球胜平负/总进球8档/比分28个/半全场9个
- ✅ 赛程列表/支持率
- ⚠️ 8大资讯API：云IP被封禁，用general_search替代

### 第三方数据
- ✅ 欧指/亚盘/大小球：general_search搜索获取
- ✅ 伤停/预测/新闻：general_search搜索获取
- 脚本提供解析框架，LLM主动调用general_search补充

## 自进化闭环

```
赛前分析 ← 经验回流 ← 自进化反思 ← 赛后复盘 ← 赛后结算
    ↓
投注入库（decision_log.json）
```

每次分析前自动预加载：
- 各玩法历史命中率/ROI
- 分联赛校准参数
- 典型案例库
- 策略参数（动态调整的EV门槛/Kelly系数）

## 开发说明

### 添加新工具
1. 在对应服务器的`server.py`中添加`@mcp.tool()`装饰的函数
2. 如在`workflow`中需要自动调用，在`run_full_workflow`中添加`call_tool()`
3. 运行语法验证：`python3 -c "import py_compile; py_compile.compile('servers/xxx/server.py', doraise=True)"`

### 同步到反向封装Skill
```bash
bash scripts/sync_to_wrapper_skill.sh
```

### 规范验证
```bash
# 插件验证
python3 ../.user_skills/agent-plugin-creator/scripts/validate_plugin.py .

# 安全审计
python3 ../.user_skills/agent-plugin-creator/scripts/audit_plugin.py .

# MCP握手测试
python3 ../.user_skills/agent-plugin-creator/scripts/test_mcp_handshake.py --command "python3 servers/workflow/server.py"
```

## 更新日志

### v1.8.1 (2026-09-06)
- 新增workflow服务器，超级一键工具`run_full_workflow`（调用109个工具，成功率100%）
- 工具总数123个，7个MCP服务器
- 移除3个重复工具（collect_all_matches/get_odds_history/record_odds_snapshot）
- 修复get_multi_source_odds内部FunctionTool调用bug
- 修复让球概率计算（泊松比分矩阵精确计算）
- 新增批量第三方数据采集和8大资讯搜索脚本

### v1.1.0 (2026-09-06)
- 能力移植审计：补充32项遗漏能力
- MCP服务器从4个扩展到6个
- MCP工具从50个扩展到82个
- 新增报告生成和质量控制能力

### v1.0.0 (2026-09-06)
- 初始版本
- 6个技能（1核心+5玩法专属）
- 4个MCP服务器（50个工具）
- 4阶段工作流

## 注意事项

1. **理性购彩**：所有输出为模拟盘分析，不构成投注建议
2. **数据时效性**：赔率和资讯需实时获取，禁止使用过时数据
3. **禁止硬解码**：投注单数量/类型/玩法组合必须动态决定
4. **全量分析**：5种玩法必须全覆盖，禁止因"复杂"跳过比分/半全场
5. **决策必须有理由**：无理由的决策不被接受

## 许可证

本插件仅供学习研究使用。
