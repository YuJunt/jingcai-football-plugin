#!/usr/bin/env python3
"""
比分玩法自动化分析脚本
自动执行5步工作流：数据采集→概率模型→双锁定验证→收敛比分筛选→输出结论
用法：
  python3 analyze_bifen.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM
  python3 analyze_bifen.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM --json
"""
import argparse
import json
import math
import os
import sys

# 脚本路径: jingcai-football-plugin/skills/jingcai-bifen/scripts/analyze_bifen.py
# 4层dirname = jingcai-football-plugin/
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 导入MCP工具（使用importlib避免模块名冲突）
import importlib.util

def load_mcp_module(server_name, module_name):
    """动态加载MCP服务器模块"""
    server_path = os.path.join(PLUGIN_ROOT, 'servers', server_name, 'server.py')
    if not os.path.exists(server_path):
        return None
    spec = importlib.util.spec_from_file_location(module_name, server_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"⚠️  加载{server_name}失败: {e}")
        return None

# 加载data-collector
dc_module = load_mcp_module('data-collector', 'jingcai_dc_bf')
if dc_module:
    get_official_odds = dc_module.get_official_odds
    get_support_rate = dc_module.get_support_rate
else:
    get_official_odds = None
    get_support_rate = None

# 加载analyzer
az_module = load_mcp_module('analyzer', 'jingcai_az_bf')
if az_module:
    poisson_predict = az_module.poisson_predict
    dixon_coles = az_module.dixon_coles
    ensemble_predict = az_module.ensemble_predict
    calculate_ev = az_module.calculate_ev
    calculate_kelly = az_module.calculate_kelly
    reverse_indicator = az_module.reverse_indicator
    play_specific_analysis = az_module.play_specific_analysis
    multi_perspective_analysis = az_module.multi_perspective_analysis
else:
    poisson_predict = None
    dixon_coles = None
    ensemble_predict = None
    calculate_ev = None
    calculate_kelly = None
    reverse_indicator = None
    play_specific_analysis = None
    multi_perspective_analysis = None

# 导入历史数据校准模块
CALIBRATOR_DIR = os.path.join(PLUGIN_ROOT, 'skills', 'jingcai-core', 'scripts')
sys.path.insert(0, CALIBRATOR_DIR)
try:
    from historical_calibrator import calibrate_score_matrix
    HAS_CALIBRATOR = True
except ImportError:
    HAS_CALIBRATOR = False
    calibrate_score_matrix = None

def safe_call(func, **kwargs):
    """安全调用MCP工具，处理异常"""
    if func is None:
        return {'success': False, 'error': '工具不可用'}
    try:
        result = func.fn(**kwargs)
        if isinstance(result, dict):
            return result
        return {'success': True, 'data': result}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def calculate_score_matrix(lambda_home, lambda_away, max_goals=6):
    """
    计算比分概率矩阵（泊松分布）
    Returns:
        dict: {score: final_probability}，如 {"1:0": 0.15, "2:1": 0.12, ...}
    """
    matrix = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p_h = (lambda_home ** h) * math.exp(-lambda_home) / math.factorial(h)
            p_a = (lambda_away ** a) * math.exp(-lambda_away) / math.factorial(a)
            score = f"{h}:{a}"
            matrix[score] = p_h * p_a
    return matrix

def analyze_bifen(match_id, home_team, away_team, league='', verbose=True):
    """
    比分玩法完整分析
    """
    def log(msg):
        if verbose:
            print(msg)
    
    result = {
        'match_id': match_id,
        'match': f'{home_team} vs {away_team}',
        'league': league,
        'play': '比分',
        'steps': {},
        'recommendation': None,
    }
    
    # ============================================================
    # 步骤1：数据采集
    # ============================================================
    log(f"📊 步骤1：数据采集...")
    
    odds_result = safe_call(get_official_odds, match_id=match_id)
    result['steps']['data_collection'] = {'odds': odds_result}
    
    # 提取比分赔率（31个选项）
    bifen_odds = {}
    bifen_option_names = []
    spf_odds_for_lambda = []
    if odds_result.get('success'):
        data = odds_result.get('data', odds_result)
        odds_data = data.get('odds', data)
        if isinstance(odds_data, dict):
            bf = odds_data.get('比分', {})
            if isinstance(bf, dict):
                bifen_option_names = bf.get('option_names', [])
                odds_list = bf.get('odds', [])
                for name, odd in zip(bifen_option_names, odds_list):
                    bifen_odds[name] = odd
            spf = odds_data.get('胜平负', {})
            if isinstance(spf, dict):
                spf_odds_for_lambda = spf.get('odds', [])
    
    support_result = safe_call(get_support_rate, match_ids=match_id)
    result['steps']['data_collection']['support_rate'] = support_result
    
    log(f"   比分赔率: {len(bifen_odds)}个选项")
    
    # ============================================================
    # 步骤2：概率模型
    # ============================================================
    log(f"📈 步骤2：概率模型...")
    
    # 用胜平负赔率估算λ
    lambda_home = 1.3
    lambda_away = 1.0
    if len(spf_odds_for_lambda) >= 3 and all(o > 0 for o in spf_odds_for_lambda[:3]):
        total = sum(1.0/o for o in spf_odds_for_lambda[:3])
        p_home = (1.0/spf_odds_for_lambda[0]) / total
        p_away = (1.0/spf_odds_for_lambda[2]) / total
        lambda_home = max(0.5, p_home * 2.5)
        lambda_away = max(0.5, p_away * 2.5)
    
    # 泊松预测
    poisson_result = safe_call(poisson_predict, lambda_home=lambda_home, lambda_away=lambda_away)
    result['steps']['final_probability_model'] = {'poisson': poisson_result}
    
    # 用历史数据校准比分概率矩阵（替代简单泊松分布）
    if HAS_CALIBRATOR and calibrate_score_matrix:
        score_matrix = calibrate_score_matrix(lambda_home, lambda_away)
    else:
        # 降级：简单泊松分布
        score_matrix = calculate_score_matrix(lambda_home, lambda_away)
    result['steps']['final_probability_model']['score_matrix'] = score_matrix
    
    # Dixon-Coles修正
    if len(spf_odds_for_lambda) >= 3:
        dc_result = safe_call(dixon_coles, home_odds=spf_odds_for_lambda[0], draw_odds=spf_odds_for_lambda[1], away_odds=spf_odds_for_lambda[2])
    else:
        dc_result = {'success': False, 'error': '赔率数据不足'}
    result['steps']['final_probability_model']['dixon_coles'] = dc_result
    
    # 4模型集成（方向概率）
    match_data = {'odds': {'胜平负': {'odds': spf_odds_for_lambda if spf_odds_for_lambda else [1.5, 3.8, 6.0]}}}
    ensemble_result = safe_call(ensemble_predict, match_data=match_data)
    result['steps']['final_probability_model']['ensemble'] = ensemble_result
    
    # 提取方向概率
    direction_final_probs = [0.4, 0.3, 0.3]
    if ensemble_result.get('success'):
        data = ensemble_result.get('data', ensemble_result)
        ep = data.get('ensemble_final_probs', {})
        if isinstance(ep, dict):
            direction_final_probs = [ep.get('主胜', 0), ep.get('平局', 0), ep.get('客胜', 0)]
    
    # 总进球概率分布
    lambda_total = lambda_home + lambda_away
    total_goals_final_probs = []
    for k in range(8):
        p = (lambda_total ** k) * math.exp(-lambda_total) / math.factorial(k)
        total_goals_final_probs.append(p)
    total_goals_final_probs.append(max(0, 1 - sum(total_goals_final_probs)))
    
    # 总进球Top2集中度
    sorted_tg = sorted(total_goals_final_probs, reverse=True)
    tg_concentration = sum(sorted_tg[:2]) if len(sorted_tg) >= 2 else 0
    
    log(f"   方向概率: 主胜{direction_final_probs[0]:.1%} 平{direction_final_probs[1]:.1%} 客胜{direction_final_probs[2]:.1%}")
    log(f"   总预期进球: {lambda_total:.1f}球，Top2集中度: {tg_concentration:.1%}")
    
    # ============================================================
    # 步骤3：双锁定验证（硬条件）
    # ============================================================
    log(f"🔒 步骤3：双锁定验证...")
    
    direction_locked = max(direction_final_probs) > 0.50
    tg_locked = tg_concentration > 0.55
    double_locked = direction_locked and tg_locked
    
    result['steps']['double_lock'] = {
        'direction_locked': direction_locked,
        'tg_locked': tg_locked,
        'double_locked': double_locked,
        'direction_final_prob': max(direction_final_probs),
        'tg_concentration': tg_concentration,
    }
    
    log(f"   方向锁定: {'✅' if direction_locked else '❌'} (最高概率{max(direction_final_probs):.1%})")
    log(f"   总进球锁定: {'✅' if tg_locked else '❌'} (Top2集中度{tg_concentration:.1%})")
    log(f"   双锁定: {'✅ 通过' if double_locked else '❌ 不通过'}")
    
    # ============================================================
    # 步骤4：收敛比分筛选与价值分析
    # ============================================================
    log(f"💰 步骤4：收敛比分筛选与价值分析...")
    
    # 确定锁定方向
    direction_names = ['主胜', '平局', '客胜']
    locked_direction = direction_names[direction_final_probs.index(max(direction_final_probs))]
    
    # 确定总进球区间（Top2档位）
    tg_option_names = ['0球', '1球', '2球', '3球', '4球', '5球', '6球', '7+球']
    top2_tg_indices = sorted(range(len(total_goals_final_probs)), key=lambda i: total_goals_final_probs[i], reverse=True)[:2]
    tg_range = [tg_option_names[i] for i in sorted(top2_tg_indices)]
    
    # 筛选符合方向和总进球区间的比分
    candidate_scores = []
    for score, final_prob in score_matrix.items():
        h, a = map(int, score.split(':'))
        total = h + a
        
        # 方向筛选
        if locked_direction == '主胜' and h <= a:
            continue
        elif locked_direction == '平局' and h != a:
            continue
        elif locked_direction == '客胜' and h >= a:
            continue
        
        # 总进球筛选（只保留Top2档位附近的比分）
        if total not in [i for i in top2_tg_indices] and abs(total - (top2_tg_indices[0] + top2_tg_indices[1]) / 2) > 1:
            continue
        
        # 过滤极端比分
        if h > 5 or a > 5:
            continue
        
        if score in bifen_odds and bifen_odds[score] > 0:
            # 赔率隐含概率
            implied_final_prob = 1.0 / bifen_odds[score]
            # 核心优化：引入赔率隐含概率作为先验
            # 最终概率 = 赔率隐含概率 × 0.5 + 模型概率 × 0.5
            final_final_prob = implied_final_prob * 0.5 + final_prob * 0.5
            # 返奖率调整：比分玩法抽水最重（约60-65%）
            payout_rate = 0.55 if final_final_prob < 0.05 else 0.65
            adjusted_final_prob = final_final_prob * payout_rate
            ev = adjusted_final_prob * bifen_odds[score] - 1
            candidate_scores.append({
                'score': score,
                'final_prob': final_prob,
                'implied_final_prob': implied_final_prob,
                'final_final_prob': final_final_prob,
                'adjusted_final_prob': adjusted_final_prob,
                'odds': bifen_odds[score],
                'ev': ev,
            })
    
    # 按EV排序，取Top3
    candidate_scores.sort(key=lambda x: x['ev'], reverse=True)
    top_scores = candidate_scores[:3]
    
    result['steps']['value_analysis'] = {
        'locked_direction': locked_direction,
        'tg_range': tg_range,
        'candidate_count': len(candidate_scores),
        'top_scores': top_scores,
    }
    
    log(f"   锁定方向: {locked_direction}")
    log(f"   总进球区间: {tg_range}")
    log(f"   候选比分: {len(candidate_scores)}个")
    if top_scores:
        log(f"   Top3比分:")
        for s in top_scores:
            log(f"     {s['score']}: 概率{s['final_prob']:.1%}, 赔率{s['odds']}, EV={s['ev']:.1%}")
    
    # ============================================================
    # 步骤5：输出结论
    # ============================================================
    log(f"✅ 步骤5：输出结论...")
    
    if not double_locked:
        recommendation = '双锁定未通过，不推荐具体比分'
        confidence = '低'
        best_score = None
    elif not top_scores or top_scores[0]['ev'] < 0.15:
        recommendation = '无EV>15%的比分选项'
        confidence = '低'
        best_score = top_scores[0] if top_scores else None
    else:
        best_score = top_scores[0]
        recommendation = best_score['score']
        confidence = '高' if best_score['ev'] > 0.30 else ('中' if best_score['ev'] > 0.20 else '低')
    
    # 计算玩法适配度：比分玩法只适合双锁定通过的比赛
    if double_locked:
        play_fitness_score = 0.90  # 双锁定通过，适配度最高
    elif locked_direction and tg_concentration > 0.50:
        play_fitness_score = 0.65  # 方向锁定但总进球不够集中
    else:
        play_fitness_score = 0.40  # 双锁定未通过，适配度低
    
    # 计算模型置信度：根据最高比分概率
    best_prob = best_score['final_prob'] if best_score else 0
    if best_prob >= 0.12:
        model_confidence = 0.75
    elif best_prob >= 0.08:
        model_confidence = 0.60
    else:
        model_confidence = 0.45
    
    result['recommendation'] = {
        'option': recommendation,
        'score': best_score['score'] if best_score else None,
        'odds': best_score['odds'] if best_score else None,
        'final_probability': best_score['final_prob'] if best_score else 0,
        'ev': best_score['ev'] if best_score else 0,
        'confidence': confidence,
        'play_fitness_score': play_fitness_score,
        'model_confidence': model_confidence,
        'double_locked': double_locked,
        'locked_direction': locked_direction,
        'tg_range': tg_range,
        'top_scores': top_scores,
        'reason': f"方向{locked_direction}（概率{max(direction_final_probs):.1%}），总进球{tg_range}（集中度{tg_concentration:.1%}），双锁定{'通过' if double_locked else '未通过'}" + (f"，推荐{recommendation}（EV={best_score['ev']:.1%}）" if best_score else "") + f"，适配度{play_fitness_score:.0%}，模型置信度{model_confidence:.0%}",
    }
    
    log(f"   推荐: {recommendation} (信心度: {confidence})")
    
    return result

def print_result(result):
    """打印格式化结果"""
    print("\n" + "=" * 70)
    print("比分玩法分析结果")
    print("=" * 70)
    print(f"比赛: {result['match']}")
    print(f"联赛: {result.get('league', '未知')}")
    print(f"玩法: {result['play']}")
    print("-" * 70)
    
    rec = result.get('recommendation', {})
    print(f"推荐比分: {rec.get('option', '无')}")
    print(f"双锁定: {'✅ 通过' if rec.get('double_locked') else '❌ 未通过'}")
    print(f"锁定方向: {rec.get('locked_direction', '未知')}")
    print(f"总进球区间: {rec.get('tg_range', [])}")
    
    if rec.get('score'):
        print(f"赔率: {rec.get('odds', 'N/A')}")
        print(f"模型概率: {rec.get('final_probability', 0):.1%}")
        print(f"EV: {rec.get('ev', 0):.1%}")
    
    print(f"信心度: {rec.get('confidence', '低')}")
    
    if rec.get('top_scores'):
        print(f"\nTop3候选比分:")
        for s in rec['top_scores']:
            print(f"  {s['score']}: 概率{s['final_prob']:.1%}, 赔率{s['odds']}, EV={s['ev']:.1%}")
    
    print(f"\n推荐理由: {rec.get('reason', '')}")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description='比分玩法自动化分析')
    parser.add_argument('--match-id', required=True, help='比赛ID')
    parser.add_argument('--home', required=True, help='主队名称')
    parser.add_argument('--away', required=True, help='客队名称')
    parser.add_argument('--league', default='', help='联赛名称（可选）')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    args = parser.parse_args()
    
    verbose = not args.json
    result = analyze_bifen(args.match_id, args.home, args.away, args.league, verbose=verbose)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_result(result)

if __name__ == '__main__':
    main()
