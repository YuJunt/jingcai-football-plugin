# jingcai-football-plugin

> 竞彩足球全量深度分析与投注方案插件v1.13.0。包含8个技能（1核心+1方法论+5玩法专属+1混合过关）和9个MCP服务器（178个工具），覆盖数据采集、深度分析、报告生成、质量控制、投注组合、自进化闭环全流程。核心能力：官方5玩法赔率+8大资讯API直采、支持率/资金流/置信度过滤、ML集成模型（85454场训练）、Dixon-Coles/泊松/半全场条件概率、混合过关木桶校验、保本组合+M串N+复式容错、赛后结算+自进化回流、模拟账户管理、参数自校准、自动化测试。全部使用免费数据，无需付费数据源。

![Version](https://img.shields.io/badge/version-1.13.0-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Skills](https://img.shields.io/badge/skills-8-purple) ![MCP Servers](https://img.shields.io/badge/MCP-9-orange) ![Tools](https://img.shields.io/badge/tools-178-red) ![Tests](https://img.shields.io/badge/tests-21-brightgreen)

## 功能特性

- 包含 8 个 Agent Skill
  - **jingcai-core**: 竞彩足球核心技能（协调层）。工作流编排、通用方法论、质量控制、自进化闭环、报告生成。当用户需要竞彩足球全流程分析、投注方案设计、赛后复盘、策略优化时使用。核心模式：4阶段工作流（数据采集→深度分析→投注组合→自进化）。
  - **jingcai-methodology**: 竞彩足球通用方法论知识层。包含EV计算/Kelly公式/概率模型/资金管理/保本策略/高级分析维度/被忽略维度/典型错误自检/官方规则。由jingcai-core在分析阶段按需调用。
  - **jingcai-spf**: 胜平负玩法专属技能。稳胆首选、平局价值、冷门博冷策略。EV门槛+5%，Kelly系数0.25，过关上限8关。
  - **jingcai-rangqiu**: 让球胜平负玩法专属技能。让平专项、赢球输盘风险、亚盘水位辅助。EV门槛+5%，Kelly系数0.20，过关上限8关。
  - **jingcai-zongjinqiu**: 总进球玩法专属技能。大小球验证、档位集中度、攻防节奏分析。EV门槛+7%，Kelly系数0.20，过关上限6关。
  - **jingcai-bifen**: 比分玩法专属技能。方向+总进球双锁定、比分收敛度五步法、Dixon-Coles修正。EV门槛+15%，Kelly系数0.03，过关上限4关。
  - **jingcai-banquanchang**: 半全场玩法专属技能。半场矩阵→动态下半场λ→映射9结果、逆转选项分析、比赛节奏。EV门槛+12%，Kelly系数0.05，过关上限4关。
  - **jingcai-mixed**: 混合过关专属技能。木桶原则校验、玩法搭配策略、过关上限规则、混合vs单玩法选择决策。混合过关是竞彩特色，允许不同玩法的选项串在同一张投注单上。
- 包含 9 个 MCP 服务器
  - **analyzer**: 52个工具（深度分析、概率模型、价值分析）
  - **data-collector**: 36个工具（数据采集、赔率获取、资讯获取、数据持久化）
  - **news-intelligence**: 7个工具（资讯智能分析）
  - **portfolio**: 20个工具（投注组合、保本策略、M串N、复式容错）
  - **quality-control**: 4个工具（质量控制、预检、反思检查）
  - **report-generator**: 5个工具（报告生成、标准化输出）
  - **self-evolution**: 28个工具（自进化、模拟账户、赛后结算、经验提取）
  - **visualization**: 6个工具（可视化、图表生成）
  - **workflow**: 3个工具（工作流编排、参数管理、参数自校准）
- 关键词: 竞彩足球, 体育彩票, 足球分析, 投注策略, 价值投注, 蒙特卡洛模拟, 多智能体, 半全场条件概率, CLV追踪, 历史数据分析, 自进化闭环, 模拟账户, 参数自校准, Agent Plugin

## 安装

### 前置要求

- 支持 Agent Plugins 1.0 标准的客户端（Claude Code、Cursor、VS Code Copilot、Codex 等）
- Node.js 18+ 或 Python 3.10+（取决于 MCP 服务器实现语言）

### 安装步骤

1. 将此插件目录复制到客户端的插件目录，或通过插件市场安装
2. 在客户端配置中启用此插件
3. 如果包含 MCP 服务器，确保已安装相应依赖：
   - `data-collector`: `cd servers/data-collector && pip install -e .`
   - `analyzer`: `cd servers/analyzer && pip install -e .`
   - `report-generator`: `cd servers/report-generator && pip install -e .`
   - `quality-control`: `cd servers/quality-control && pip install -e .`
   - `portfolio`: `cd servers/portfolio && pip install -e .`
   - `self-evolution`: `cd servers/self-evolution && pip install -e .`
   - `workflow`: `cd servers/workflow && pip install -e .`
   - `news-intelligence`: `cd servers/news-intelligence && pip install -e .`
   - `visualization`: `cd servers/visualization && pip install -e .`

## 使用方法

### Skills

插件包含以下技能，在对话中提及相关场景时会自动触发：

#### jingcai-banquanchang

半全场玩法专属技能。半场矩阵→动态下半场λ→映射9结果、逆转选项分析、比赛节奏。当用户需要半全场玩法分析、半场/全场结果推荐、逆转博冷时使用。EV门槛+12%，Kelly系数0.05，过关上限4关。

**主要功能:**

- 玩法特点
- 9种选项
- 玩法选择决策树（LLM必须按此判断）
- 核心分析逻辑
- P0新增专属工具（3个，必须使用）

#### jingcai-bifen

比分玩法专属技能。方向+总进球双锁定、比分收敛度五步法、Dixon-Coles修正。当用户需要比分玩法分析、具体比分推荐、高赔博冷时使用。EV门槛+15%，Kelly系数0.03，过关上限4关。

**主要功能:**

- 玩法特点
- 31种选项
- 玩法选择决策树（LLM必须按此判断）
- 核心分析逻辑
- 专属策略

#### jingcai-core

竞彩足球核心技能（协调层）。工作流编排、通用方法论、质量控制、自进化闭环、报告生成。当用户需要竞彩足球全流程分析、投注方案设计、赛后复盘、策略优化时使用。核心模式：4阶段工作流（数据采集→深度分析→投注组合→自进化），先输出全量专业分析报告，再基于报告与用户协作输出投注方案。

**主要功能:**

- ⚡ 快速开始（LLM必读）
- 核心理念
- LLM参与点规范（核心，必须遵守）
- 版本更新记录
- 🔧 工具强制调用检查清单（利用率必须100%）

#### jingcai-mixed

混合过关专属技能。木桶原则校验、玩法搭配策略、过关上限规则、混合vs单玩法选择决策。当用户需要混合过关投注、多玩法串关、过关组合优化时使用。混合过关是竞彩特色，允许不同玩法的选项串在同一张投注单上。

**主要功能:**

- 什么是混合过关
- 核心原则：木桶理论
- 玩法搭配策略
- 过关上限规则（硬约束）
- 混合过关vs单玩法串关选择决策树

#### jingcai-rangqiu

让球胜平负玩法专属技能。让平专项、赢球输盘风险、亚盘水位辅助。当用户需要让球胜平负玩法分析、让平价值识别、赢球输盘风险判断时使用。EV门槛+5%，Kelly系数0.20，过关上限8关。

**主要功能:**

- 玩法特点
- 与亚盘的核心差异
- 玩法选择决策树（LLM必须按此判断）
- 核心分析逻辑
- 专属策略

#### jingcai-spf

胜平负玩法专属技能。稳胆首选、平局价值、冷门博冷策略。当用户需要胜平负玩法分析、稳胆推荐、平局价值识别、冷门博冷时使用。EV门槛+5%，Kelly系数0.25，过关上限8关。

**主要功能:**

- 玩法特点
- 玩法选择决策树（LLM必须按此判断）
- 核心分析逻辑
- 专属策略
- 关键参数速查表

#### jingcai-zongjinqiu

总进球玩法专属技能。大小球验证、档位集中度、攻防节奏分析。当用户需要总进球玩法分析、大小球判断、进球档位推荐时使用。EV门槛+7%，Kelly系数0.20，过关上限6关。

**主要功能:**

- 玩法特点
- 玩法选择决策树（LLM必须按此判断）
- 核心分析逻辑
- 专属策略
- 关键参数速查表

### MCP 工具

#### data-collector

- **传输方式**: stdio
- **启动命令**: `python3`

*工具列表请参考服务器源代码*

#### analyzer

- **传输方式**: stdio
- **启动命令**: `python3`

**工具列表:**

| 工具名 | 描述 |
|--------|------|
| `find_similar_matches` | - |
| `league_pattern_match` | - |
| `strategy_backtest` | - |
| `update_team_strength` | - |

#### report-generator

- **传输方式**: stdio
- **启动命令**: `python3`

*工具列表请参考服务器源代码*

#### quality-control

- **传输方式**: stdio
- **启动命令**: `python3`

*工具列表请参考服务器源代码*

#### portfolio

- **传输方式**: stdio
- **启动命令**: `python3`

*工具列表请参考服务器源代码*

#### self-evolution

- **传输方式**: stdio
- **启动命令**: `python3`

**工具列表:**

| 工具名 | 描述 |
|--------|------|
| `get_user_preferences` | - |
| `update_user_preferences` | - |

#### workflow

- **传输方式**: stdio
- **启动命令**: `python3`

**工具列表:**

| 工具名 | 描述 |
|--------|------|
| `run_full_workflow` | - |

#### news-intelligence

- **传输方式**: stdio
- **启动命令**: `python3`

**工具列表:**

| 工具名 | 描述 |
|--------|------|
| `generate_news_search_keywords` | - |
| `parse_news_text` | - |
| `quantify_injury_impact` | - |
| `analyze_motivation` | - |
| `analyze_fixture_congestion` | - |
| `news_to_lambda_mapping` | - |
| `aggregate_news_intelligence` | - |

#### visualization

- **传输方式**: stdio
- **启动命令**: `python3`

**工具列表:**

| 工具名 | 描述 |
|--------|------|
| `generate_odds_trend_chart` | - |
| `generate_probability_radar` | - |
| `generate_payout_matrix` | - |
| `generate_hit_rate_trend` | - |
| `generate_interactive_report` | - |
| `generate_ev_distribution_chart` | - |

## 配置

### plugin.json

插件的核心配置文件，包含插件元数据。

```json
{
  "name": "jingcai-football-plugin",
  "version": "1.11.0",
  "description": "竞彩足球全量深度分析与投注方案插件v1.5.0。包含6个技能（1核心+5玩法专属）和6个MCP服务器（123个工具），覆盖数据采集、深度分析、报告生成、质量控制、投注组合、自进化闭环全流程。核心能力：官方5玩法赔率+8大资讯API直采、支持率/资金流/置信度过滤、ML集成模型（83328场训练）、Dixon-Coles/泊松/半全场条件概率、混合过关木桶校验、保本组合+M串N+复式容错、赛后结算+自进化回流。全部使用免费数据，无需付费数据源。"
}
```

### mcp.json

MCP 服务器配置文件，定义插件包含的 MCP 服务器。

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "data-collector": {
      "type": "stdio",
      "command": "python3",
      "args": [
        "./servers/data-collector/server.py"
      ],
      "cwd": "${PLUGIN_ROOT}",
      "description": "数据采集MCP服务器。31个工具：官方赛程/5玩法赔率/8大资讯/支持率/赛果/赔率走势/第三方数据/批量采集/500.com解析。"
    },
    "analyzer": {
      "type": "stdio",
      "command": "python3",
      "args": [
        "./servers/analyzer/server.py"
      ],
  
```

## 兼容性

此插件符合 [Agent Plugins 1.0](https://github.com/agentplugins/agent-plugins-spec) 开放规范，支持以下客户端：

- ✅ Claude Code
- ✅ Cursor
- ✅ VS Code (GitHub Copilot)
- ✅ OpenAI Codex
- ✅ Google Gemini (部分支持)

## 开发

### 目录结构

```
jingcai-football-plugin/
├── plugin.json          # 插件清单（必需）
├── skills/              # Agent Skills
│   └── jingcai-banquanchang/
│       └── SKILL.md
│   └── jingcai-bifen/
│       └── SKILL.md
│   └── jingcai-core/
│       └── SKILL.md
│   └── jingcai-mixed/
│       └── SKILL.md
│   └── jingcai-rangqiu/
│       └── SKILL.md
│   └── jingcai-spf/
│       └── SKILL.md
│   └── jingcai-zongjinqiu/
│       └── SKILL.md
├── mcp.json             # MCP 服务器配置
├── servers/             # MCP 服务器代码
│   └── data-collector/
│   └── analyzer/
│   └── report-generator/
│   └── quality-control/
│   └── portfolio/
│   └── self-evolution/
│   └── workflow/
│   └── news-intelligence/
│   └── visualization/
└── com.<client>/        # 客户端专属扩展（可选）
```

### 验证

使用 agent-plugin-creator 技能的验证工具：

```bash
# 验证插件结构
python3 scripts/validate_plugin.py .

# 安全审计
python3 scripts/audit_plugin.py .
```

## 许可证

MIT © jingcai-football-team
