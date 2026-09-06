## v1.2.0 P0新增能力（9个工具+4个数据资产）

### 半全场专属强化（3工具+1数据资产）
- `htft_frequency_calibration`：半全场9组合历史频率校准（核心区间82.7%/平开头52.8%/逆转8%）
- `second_half_goal_diff`：下半场进球差(SHGD)指标，预测"平→胜/平→负"的最佳指标
- `team_half_time_profile`：球队半场习惯画像（善抢开局/慢热型/后发制人）
- 数据资产：`data/htft_frequency.json`（36联赛半全场频率基准库）

### 比分玩法强化（1工具+1数据资产）
- `score_frequency_calibration`：比分历史频率校准（泊松60%+历史40%），Top8收敛度分析
- 数据资产：`data/score_frequency.json`（36联赛比分频率基准库）

### 总进球玩法强化（1工具+1数据资产）
- `total_goals_league_calibration`：总进球联赛档位校准，解决联赛风格差异（德甲大球/意甲小球）
- 数据资产：`data/league_goal_distribution.json`（36联赛总进球档位分布）

### 竞彩适配度强化（1工具）
- `jingcai_payout_calibrator`：竞彩返奖率校准器（69%去水，非国际95%），EV门槛修正

### 盘口分析强化（2工具+1数据资产）
- `handicap_language_analyzer`：盘口语言识别（8种变动模式，大热退盘一票否决）
- `theoretical_vs_actual_handicap`：理论盘口vs实际盘口偏离分析（Elo差计算理论让球）
- 数据资产：`data/eu_ah_conversion.json`（欧亚转换对照表+盘口语言规则）

### 混合过关强化（1工具）
- `mixed_parlay_wooden_bucket_check`：混合过关木桶原则严格校验（关数上限=最低玩法上限）

---

## v1.3.0 P1新增能力（8个工具，纯数学）

### analyzer新增6工具（更精准的概率建模）
- `time_weighted_poisson`：时间加权泊松（半衰期30天，近期比赛权重更高，捕捉球队状态变化）
- `attack_defense_match`：攻防匹配显式公式（λ主=主队场均进×客队场均失×主场系数）
- `expected_goal_diff_vs_handicap`：预期净胜值与让球盘口±0.3量化比较（让球胜平负核心）
- `weighted_15dim_scorecard`：15维度加权评分表+一票否决（综合判断，避免单一指标误导）
- `attack_defense_style_match`：攻防风格匹配（强攻vs弱守/慢热vs抢开局的风格克制）
- `bayesian_shrinkage`：贝叶斯小样本自适应收缩（3场4球等极端样本向联赛均值收缩）

### portfolio新增2工具（更科学的资金与对冲）
- `layered_bankroll_pool`：分层资金池（60%稳健/30%容错/10%搏冷）+2%固定单位法
- `cross_play_hedge`：3种跨玩法对冲结构识别（同场不同玩法互相对冲降低风险）

---

## v1.4.0 P2新增能力（4个工具，全部免费数据）

### ML集成模型（1工具+训练脚本+8.8MB模型）
- `ml_predict`：GradientBoosting+RandomForest双模型集成预测1X2
  - 83328场历史数据训练（31联赛），5折交叉验证准确率53.1%（随机基线33.3%，+20个百分点）
  - 15维特征：近期进失球/射门射正/状态差/赔率隐含概率/攻防匹配
  - 重新训练：`python3 data/train_ml_model.py --evaluate`
- 适用：胜平负/让球胜平负的1X2概率交叉验证，与4模型集成结果互相对照

### Glicko-2评分系统（1工具）
- `glicko2_rating`：Elo升级版，增加RD评分偏差（置信度）和波动率σ
- 新球队/比赛少的球队RD高（预测更谨慎），比赛越多RD越低（评分越可靠）
- 适用：球队实力评估，比经典Elo更能反映评分不确定性

### 代理xG模型（1工具，免费替代付费xG）
- `proxy_xg`：用射门/射正/角球/点球估算预期进球
- 公式：proxy_xG = 射正×0.30 + 射门×0.05 + 角球×0.02 + 点球×0.79
- 23个欧洲联赛有射门数据，其余13联赛用进球λ近似
- 适用：总进球/比分玩法，判断"实际进球vs创造机会"是否背离（状态真假）

### 净胜球分布统计（1工具，让球核心）
- `goal_difference_distribution`：统计球队净胜球分布（净胜2+/净胜1/平/净负1/净负2+）
- 直接输出让1球场景下让胜/让平/让负概率
- 适用：让球胜平负玩法的核心量化依据

---

