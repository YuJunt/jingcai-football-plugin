---
name: jingcai-spf
description: 胜平负玩法专属技能。稳胆首选、平局价值、冷门博冷策略。当用户需要胜平负玩法分析、稳胆推荐、平局价值识别、冷门博冷时使用。EV门槛+5%，Kelly系数0.25，过关上限8关。
---

# 胜平负玩法专属技能

## 1. 用途与触发场景

**用途**：对比赛的胜平负结果进行深度分析，识别稳胆、平局价值、冷门博冷机会。

**触发场景**：
- 用户要求分析某场比赛的胜平负玩法
- 用户要求推荐稳胆比赛
- 用户要求识别平局价值
- 用户要求博冷门比赛

## 2. 分析工作流（5步）

### 步骤1：数据采集
调用以下MCP工具获取数据：
- `data-collector.get_official_odds` - 获取官方胜平负赔率
- `data-collector.get_support_rate` - 获取支持率（投注比例）
- `data-collector.get_third_party_odds` - 获取第三方欧指数据（可选）

### 步骤2：概率模型
调用以下MCP工具计算概率：
- `analyzer.poisson_predict` - 泊松分布预测
- `analyzer.dixon_coles` - Dixon-Coles低比分修正
- `analyzer.ensemble_predict` - 4模型集成（市场隐含+泊松+DC+贝叶斯）

### 步骤3：价值分析
调用以下MCP工具评估价值：
- `analyzer.calculate_ev` - 计算期望值EV
- `analyzer.calculate_kelly` - 计算Kelly仓位
- `analyzer.reverse_indicator` - 反向指标分析（热门陷阱/冷门价值）

### 步骤4：玩法适配度评估
调用以下MCP工具评估玩法适配度：
- `analyzer.play_specific_analysis` - 玩法定制化分析（胜平负专属）
- `analyzer.multi_perspective_analysis` - 多视角分析（数据/模型/盘口/基本面/逆向）

### 步骤5：输出结论
输出以下内容：
- 推荐选项（主胜/平局/客胜）
- 模型概率、赔率、EV、Kelly仓位
- 信心度（高/中/低）
- 推荐理由（结合数据、模型、盘口、基本面）
- 风险提示

## 3. 快速调用脚本

除了手动调用MCP工具，还可以使用自动化脚本一键完成完整分析：

```bash
python3 scripts/analyze_spf.py --match-id <比赛ID> --home <主队> --away <客队>
```

脚本会自动执行上述5步工作流，返回完整的胜平负分析结果。

## 4. 关键参数速查

| 参数 | 值 | 说明 |
|------|-----|------|
| EV门槛 | +5% | 正EV阈值 |
| Kelly系数 | 0.25 | 仓位计算 |
| 过关上限 | 8关 | 最多串8场 |
| 选项数 | 3 | 胜/平/负 |
| 稳胆赔率区间 | 1.40-1.70 | 适合做稳胆 |

## 5. 参考资料

详细方法论和案例请查看：
- `references/methodology.md` - 胜平负分析方法论（详细版，包含决策树、核心逻辑、专属策略、典型案例、注意事项）
- `references/SKILL.md.backup` - 原SKILL.md备份
