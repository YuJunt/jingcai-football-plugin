---
name: jingcai-rangqiu
description: 让球胜平负玩法专属技能。让平专项、赢球输盘风险、亚盘水位辅助。当用户需要让球胜平负玩法分析、让平价值识别、赢球输盘风险判断时使用。EV门槛+5%，Kelly系数0.20，过关上限8关。
---

# 让球胜平负玩法专属技能

## 1. 用途与触发场景

**用途**：对比赛的让球胜平负结果进行深度分析，识别让平专项、赢球输盘风险、让胜稳胆机会。

**触发场景**：
- 用户要求分析某场比赛的让球胜平负玩法
- 用户要求识别让平价值
- 用户要求判断赢球输盘风险
- 用户要求推荐让球胜稳胆

## 2. 分析工作流（5步）

### 步骤1：数据采集
调用以下MCP工具获取数据：
- `data-collector.get_official_odds` - 获取官方让球胜平负赔率（含让球数）
- `data-collector.get_support_rate` - 获取支持率（投注比例）
- `data-collector.get_third_party_odds` - 获取第三方亚盘数据（可选）

### 步骤2：概率模型
调用以下MCP工具计算概率：
- `analyzer.poisson_predict` - 泊松分布预测
- `analyzer.dixon_coles` - Dixon-Coles低比分修正
- `analyzer.ensemble_predict` - 4模型集成
- `analyzer.theoretical_vs_actual_handicap` - 理论vs实际盘口偏离分析

### 步骤3：价值分析
调用以下MCP工具评估价值：
- `analyzer.calculate_ev` - 计算期望值EV
- `analyzer.calculate_kelly` - 计算Kelly仓位
- `analyzer.handicap_language_analyzer` - 盘口语言识别（8种模式）
- `analyzer.reverse_indicator` - 反向指标分析

### 步骤4：玩法适配度评估
调用以下MCP工具评估玩法适配度：
- `analyzer.play_specific_analysis` - 玩法定制化分析（让球胜平负专属）
- `analyzer.multi_perspective_analysis` - 多视角分析

### 步骤5：输出结论
输出以下内容：
- 推荐选项（让胜/让平/让负）
- 让球数、模型概率、赔率、EV、Kelly仓位
- 信心度（高/中/低）
- 推荐理由（结合让球数合理性、亚盘水位、赢球输盘风险）
- 风险提示

## 3. 快速调用脚本

除了手动调用MCP工具，还可以使用自动化脚本一键完成完整分析：

```bash
python3 scripts/analyze_rangqiu.py --match-id <比赛ID> --home <主队> --away <客队>
```

脚本会自动执行上述5步工作流，返回完整的让球胜平负分析结果。

## 4. 关键参数速查

| 参数 | 值 | 说明 |
|------|-----|------|
| EV门槛 | +5% | 正EV阈值 |
| Kelly系数 | 0.20 | 仓位计算（比胜平负低） |
| 过关上限 | 8关 | 最多串8场 |
| 选项数 | 3 | 让胜/让平/让负 |
| 让平价值概率 | >25% | 配合赔率>3.5 |
| 让平价值赔率 | >3.5 | 配合概率>25% |

## 5. 参考资料

详细方法论和案例请查看：
- `references/methodology.md` - 让球胜平负分析方法论（详细版，包含决策树、核心逻辑、专属策略、典型案例、注意事项）
- `references/SKILL.md.backup` - 原SKILL.md备份
