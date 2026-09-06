---
name: jingcai-zongjinqiu
description: 总进球玩法专属技能。大小球验证、档位集中度、攻防节奏分析。当用户需要总进球玩法分析、大小球判断、进球档位推荐时使用。EV门槛+7%，Kelly系数0.20，过关上限6关。
---

# 总进球玩法专属技能

## 1. 用途与触发场景

**用途**：对比赛的总进球数进行深度分析，识别大小球方向、档位集中度、攻防节奏机会。

**触发场景**：
- 用户要求分析某场比赛的总进球玩法
- 用户要求判断大小球方向
- 用户要求推荐进球档位
- 用户要求分析攻防节奏

## 2. 分析工作流（5步）

### 步骤1：数据采集
调用以下MCP工具获取数据：
- `data-collector.get_official_odds` - 获取官方总进球赔率（8个档位）
- `data-collector.get_support_rate` - 获取支持率
- `data-collector.get_third_party_odds` - 获取第三方大小球数据（可选）

### 步骤2：概率模型
调用以下MCP工具计算概率：
- `analyzer.poisson_predict` - 泊松分布预测（总进球最适合的模型）
- `analyzer.dixon_coles` - Dixon-Coles低比分修正
- `analyzer.ensemble_predict` - 4模型集成
- `analyzer.proxy_xg` - 预期进球分析（可选）

### 步骤3：价值分析
调用以下MCP工具评估价值：
- `analyzer.calculate_ev` - 计算期望值EV（8个档位逐一计算）
- `analyzer.calculate_kelly` - 计算Kelly仓位
- `analyzer.reverse_indicator` - 反向指标分析

### 步骤4：玩法适配度评估
调用以下MCP工具评估玩法适配度：
- `analyzer.play_specific_analysis` - 玩法定制化分析（总进球专属）
- `analyzer.multi_perspective_analysis` - 多视角分析

### 步骤5：输出结论
输出以下内容：
- 推荐档位（0/1/2/3/4/5/6/7+球）
- 大小球方向、模型概率、赔率、EV、Kelly仓位
- 档位集中度（Top2概率占比）
- 信心度（高/中/低）
- 推荐理由（结合大小球盘口、攻防节奏、档位集中度）
- 风险提示

## 3. 快速调用脚本

除了手动调用MCP工具，还可以使用自动化脚本一键完成完整分析：

```bash
python3 scripts/analyze_zongjinqiu.py --match-id <比赛ID> --home <主队> --away <客队>
```

脚本会自动执行上述5步工作流，返回完整的总进球分析结果。

## 4. 关键参数速查

| 参数 | 值 | 说明 |
|------|-----|------|
| EV门槛 | +7% | 正EV阈值（比胜平负高） |
| Kelly系数 | 0.20 | 仓位计算 |
| 过关上限 | 6关 | 最多串6场 |
| 选项数 | 8 | 0/1/2/3/4/5/6/7+球 |
| 0球校准系数 | ×0.65 | 泊松低估0球概率 |
| 1球校准系数 | ×0.85 | 泊松低估1球概率 |
| 档位集中度阈值 | >55% | Top2概率占比 |
| 大小球偏差阈值 | >15% | 模型vs盘口偏差 |

## 5. 参考资料

详细方法论和案例请查看：
- `references/methodology.md` - 总进球分析方法论（详细版，包含决策树、核心逻辑、专属策略、典型案例、注意事项）
- `references/SKILL.md.backup` - 原SKILL.md备份
