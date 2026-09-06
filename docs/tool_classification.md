# Analyzer工具分类治理文档

> 版本：v1.9.0 | 最后更新：2026-09-06
> 目的：明确52个MCP工具的分层和调用时机，避免LLM混淆

## 工具分层架构

```
analyzer服务器（52个MCP工具）
├── L1 基础分析层（18个）- 必调，确定性计算
├── L2 高级分析层（16个）- 必调，增强分析深度
├── L3 玩法定制层（10个）- 必调，5玩法专属校准
└── L4 历史数据层（8个）- 必调，历史规律挖掘
```

## L1 基础分析层（18个）

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| poisson_predict | 泊松比分预测 | 每场比赛必调 |
| dixon_coles | Dixon-Coles比分修正 | 每场比赛必调 |
| calculate_ev | EV计算 | 每个选项必调 |
| calculate_kelly | Kelly仓位计算 | 投注组合前 |
| ensemble_predict | 4模型集成概率 | 每场比赛必调 |
| implied_probs | 隐含概率计算 | 赔率解析时 |
| remove_vig | 去水计算 | 赔率解析时 |
| odds_converter | 欧指→亚盘/大小球转换 | 第三方数据交叉验证 |
| full_match_analysis | 单场全玩法分析 | 每场比赛必调 |
| play_specific_analysis | 5玩法定制化分析 | 每场比赛必调 |
| confidence_filter | 信心度过滤 | 价值筛选时 |
| value_option_filter | 价值选项筛选 | 价值筛选时 |
| adjust_lambda | λ动态调整 | 有资讯时调整 |
| match_pace_analysis | 比赛节奏分析 | 半全场分析时 |
| conditional_prob_half_full | 半全场条件概率 | 半全场分析时 |
| brier_score | 概率准确度评估 | 赛后复盘时 |
| parlay_ev | 串关EV计算 | 投注组合时 |
| generate_pre_match_checklist | 赛前检查清单 | 分析前 |

## L2 高级分析层（16个）

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| ml_predict | ML模型预测（GB+RF） | 每场比赛必调 |
| monte_carlo_simulate | 蒙特卡洛模拟 | 串关风险评估时 |
| simulate_parlay | 串关模拟 | 投注组合时 |
| bayesian_shrinkage | 贝叶斯收缩 | 概率校准时 |
| glicko2_rating | Glicko-2球队评分 | 球队强度评估时 |
| multi_perspective_analysis | 5模块多视角分析 | 重点比赛必调 |
| reverse_indicator | 反向指标分析 | 有支持率数据时 |
| odds_divergence | 多博彩公司赔率分歧 | 有第三方数据时 |
| referee_analysis | 裁判因素分析 | 有裁判数据时 |
| odds_movement_pattern | 赔率走势模式 | 有初终盘数据时 |
| track_odds_clv | CLV追踪 | 有初终盘数据时 |
| multi_agent_debate | 多Agent辩论 | 疑难比赛分析时 |
| strategy_ab_test | 策略A/B测试 | 策略优化时 |
| simulate_strategy | 策略模拟 | 策略优化时 |
| time_weighted_poisson | 时间加权泊松 | 近期状态权重调整 |
| attack_defense_matchup | 攻防对位分析 | 每场比赛必调 |

## L3 玩法定制层（10个）

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| htft_frequency_calibration | 半全场频率校准 | 半全场分析时 |
| second_half_goal_diff | 下半场进球差分析 | 半全场分析时 |
| team_half_time_profile | 球队半场画像 | 半全场分析时 |
| score_frequency_calibration | 比分频率校准 | 比分分析时 |
| jingcai_payout_calibrator | 竞彩返奖率校准（73%） | 所有玩法EV计算时 |
| handicap_language_analyzer | 盘口语言识别（8种模式） | 让球分析时 |
| theoretical_vs_actual_handicap | 理论vs实际盘口偏离 | 让球分析时 |
| total_goals_league_calibration | 总进球联赛档位校准 | 总进球分析时 |
| style_matchup | 风格对位分析 | 每场比赛必调 |
| expected_goal_difference | 预期进球差 | 每场比赛必调 |

## L4 历史数据层（8个）

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| historical_stats_deep | 历史数据深度统计 | 每场比赛必调 |
| history_analytics | 历史数据分析（9维度） | 重点比赛必调 |
| league_focus_analysis | 联赛专攻分析 | 联赛特征匹配时 |
| find_similar_matches | 相同对阵历史查询 | 每场比赛必调 |
| league_pattern_match | 联赛特征自动匹配 | 每场比赛必调 |
| strategy_backtest | 策略回测 | 策略优化时 |
| update_team_strength | 球队强度动态更新 | 赛后复盘时 |
| weighted_scorecard | 加权评分卡 | 综合评分时 |

## 调用规则

### workflow自动调用（100%覆盖）
- run_full_workflow工具自动按阶段调用全部52个工具
- L1基础分析 → L2高级分析 → L3玩法定制 → L4历史数据
- LLM不需要手动选择，workflow保证全覆盖

### LLM手动调用场景
- 单场比赛深度分析时，可手动调用L2/L3的特定工具
- 策略优化时，可手动调用L4的strategy_backtest
- 赛后复盘时，可手动调用update_team_strength

## 工具依赖关系

```
L1基础分析（无依赖）
    ↓ 输出：概率/EV/价值选项
L2高级分析（依赖L1的概率）
    ↓ 输出：增强概率/风险评估
L3玩法定制（依赖L1+L2）
    ↓ 输出：分玩法推荐
L4历史数据（独立，可并行）
    ↓ 输出：历史规律/校准参数
综合决策（依赖全部）
```

## 性能优化建议

1. **L1工具**：计算快（<0.1s），可全量并行
2. **L2工具**：计算中等（0.1-1s），ML预测较慢
3. **L3工具**：计算快（<0.1s），依赖校准数据
4. **L4工具**：IO密集（读取历史数据），可缓存

## 后续优化方向

- [ ] L2工具中ML预测可异步执行
- [ ] L4历史数据可预加载索引
- [ ] 工具间依赖关系可DAG调度
- [ ] 工具输出可缓存，避免重复计算
