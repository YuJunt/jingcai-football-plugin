# 工具强制调用检查清单

# 工具强制调用检查清单（利用率必须100%）

**每次实战必须调用以下工具，禁止跳过：**

### 阶段1：数据采集（必须调用data-collector的8个工具）
| 工具 | 用途 | 必须调用 |
|------|------|---------|
| `get_match_list` | 获取赛程列表 | ✅ |
| `get_official_odds` | 获取5玩法赔率 | ✅ |
| `parse_odds_response` | 解析赔率响应 | ✅ |
| `get_official_info` | 获取8大资讯（返回search_fallback后用general_search） | ✅ |
| `get_third_party_odds` | 获取第三方赔率（返回fetch_url后用general_search） | ✅ |
| `get_support_rate` | 获取支持率 | ✅ |
| `validate_data_completeness` | 验证数据完整性 | ✅ |
| `batch_record_odds_snapshot` | 记录赔率快照 | ✅ |

### 阶段2：深度分析（必须调用analyzer的8个工具）
| 工具 | 用途 | 必须调用 |
|------|------|---------|
| `full_match_analysis` | 一键全玩法分析（每场比赛） | ✅ |
| `dixon_coles` | Dixon-Coles比分修正 | ✅ |
| `multi_perspective_analysis` | 5模块多视角分析 | ✅ |
| `reverse_indicator` | 反向指标分析 | ✅ |
| `ml_predict` | ML双模型预测 | ✅ |
| `history_analytics` | 历史数据分析 | ✅ |
| `confidence_filter_score` | 置信度过滤 | ✅ |
| `play_specific_analysis` | 5玩法定制化分析 | ✅ |

### 阶段3：投注组合（必须调用portfolio+quality-control的7个工具）
| 工具 | 用途 | 必须调用 |
|------|------|---------|
| `build_full_portfolio` | 一键组单 | ✅ |
| `calc_parlay_payout` | 串关奖金计算 | ✅ |
| `auto_select_mn` | M串N自动选择 | ✅ |
| `build_hedge_structure` | 保本对冲结构 | ✅ |
| `generate_bet_slip` | 标准投注单 | ✅ |
| `check_official_rules` | 官方规则校验 | ✅ |
| `reflection_check` | 反思检查 | ✅ |

### 阶段4：自进化（必须调用self-evolution的5个工具）
| 工具 | 用途 | 必须调用 |
|------|------|---------|
| `preload_memory` | 赛前记忆预加载 | ✅ |
| `add_decision` | 决策入库 | ✅ |
| `get_stats` | 历史统计 | ✅ |
| `add_lesson` | 经验教训 | ✅ |
| `review_engine_full` | 复盘引擎 | ✅ |

### 报告生成（必须调用report-generator的3个工具）
| 工具 | 用途 | 必须调用 |
|------|------|---------|
| `generate_data_report_pure` | 纯数据报告 | ✅ |
| `generate_full_play_analysis_report` | 全玩法分析报告 | ✅ |
| `standardize_output` | 标准化输出 | ✅ |

**工具利用率目标：125个工具中至少调用31个核心工具（25%），禁止只调用3个一键工具。**

---
