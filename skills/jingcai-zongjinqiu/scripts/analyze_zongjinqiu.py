#!/usr/bin/env python3
"""
总进球玩法自动化分析脚本
自动执行5步工作流：数据采集→概率模型→价值分析→玩法适配度→输出结论
用法：
  python3 analyze_zongjinqiu.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM
  python3 analyze_zongjinqiu.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM --json
"""
import argparse
import json
import math
import os
import sys

# 脚本路径: jingcai-football-plugin/skills/jingcai-zongjinqiu/scripts/analyze_zongjinqiu.py
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
dc_module = load_mcp_module('data-collector', 'jingcai_dc_zjq')
if dc_module:
    get_official_odds = dc_module.get_official_odds
    get_support_rate = dc_module.get_support_rate
else:
    get_official_odds = None
    get_support_rate = None

# 加载analyzer
az_module = load_mcp_module('analyzer', 'jingcai_az_zjq')
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
    from historical_calibrator import calibrate_total_goals
    HAS_CALIBRATOR = True
except ImportError:
    HAS_CALIBRATOR = False
    calibrate_total_goals = None

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

def poisson_total_goals_probs(lambda_total, max_goals=7):
    """
    计算总进球数的泊松概率分布
    Args:
        lambda_total: 总预期进球数
        max_goals: 最大进球数（7表示7+球）
    Returns:
        list: 0到7+球的概率列表
    """
    probs = []
    for k in range(max_goals):
        p = (lambda_total ** k) * math.exp(-lambda_total) / math.factorial(k)
        probs.append(p)
    # 7+球 = 1 - 0到6球的概率
    prob_7_plus = 1 - sum(probs)
    probs.append(max(0, prob_7_plus))
    return probs

def analyze_zongjinqiu(match_id, home_team, away_team, league='', verbose=True):
    """
    总进球玩法完整分析
    """
    def log(msg):
        if verbose:
            print(msg)
    
    result = {
        'match_id': match_id,
        'match': f'{home_team} vs {away_team}',
        'league': league,
        'play': '总进球',
        'steps': {},
        'recommendation': None,
    }
    
    # ============================================================
    # 步骤1：数据采集
    # ============================================================
    log(f"📊 步骤1：数据采集...")
    
    odds_result = safe_call(get_official_odds, match_id=match_id)
    result['steps']['data_collection'] = {'odds': odds_result}
    
    # 提取总进球赔率（8个档位）
    zjq_odds = []
    spf_odds_for_lambda = []
    if odds_result.get('success'):
        data = odds_result.get('data', odds_result)
        odds_data = data.get('odds', data)
        if isinstance(odds_data, dict):
            zjq = odds_data.get('总进球', {})
            if isinstance(zjq, dict):
                zjq_odds = zjq.get('odds', [])
            spf = odds_data.get('胜平负', {})
            if isinstance(spf, dict):
                spf_odds_for_lambda = spf.get('odds', [])
    
    support_result = safe_call(get_support_rate, match_ids=match_id)
    result['steps']['data_collection']['support_rate'] = support_result
    
    log(f"   总进球赔率: {zjq_odds if zjq_odds else '未获取'}")
    
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
    
    lambda_total = lambda_home + lambda_away
    
    # 泊松预测
    poisson_result = safe_call(poisson_predict, lambda_home=lambda_home, lambda_away=lambda_away)
    result['steps']['probability_model'] = {'poisson': poisson_result}
    
    # 用泊松分布计算总进球概率（8个档位）
    # 用历史数据校准总进球概率（替代纯泊松分布+简单校准）
    if HAS_CALIBRATOR and calibrate_total_goals:
        total_goals_probs = calibrate_total_goals(lambda_total)
    else:
        # 降级：纯泊松分布+低比分校准
        total_goals_probs = poisson_total_goals_probs(lambda_total)
        if len(total_goals_probs) >= 2:
            total_goals_probs[0] *= 0.65
            total_goals_probs[1] *= 0.85
            total_prob = sum(total_goals_probs)
            if total_prob > 0:
                total_goals_probs = [p / total_prob for p in total_goals_probs]
    
    result['steps']['probability_model']['total_goals_probs'] = total_goals_probs
    result['steps']['probability_model']['lambda_total'] = lambda_total
    
    # Dixon-Coles修正
    if len(spf_odds_for_lambda) >= 3:
        dc_result = safe_call(dixon_coles, home_odds=spf_odds_for_lambda[0], draw_odds=spf_odds_for_lambda[1], away_odds=spf_odds_for_lambda[2])
    else:
        dc_result = {'success': False, 'error': '赔率数据不足'}
    result['steps']['probability_model']['dixon_coles'] = dc_result
    
    # 档位集中度（Top2概率占比）
    sorted_probs = sorted(total_goals_probs, reverse=True)
    concentration = sum(sorted_probs[:2]) if len(sorted_probs) >= 2 else 0
    result['steps']['probability_model']['concentration'] = concentration
    
    option_names = ['0球', '1球', '2球', '3球', '4球', '5球', '6球', '7+球']
    log(f"   总预期进球: {lambda_total:.1f}球")
    log(f"   档位集中度: {concentration:.1%} (Top2)")
    log(f"   概率最高: {option_names[total_goals_probs.index(max(total_goals_probs))]} ({max(total_goals_probs):.1%})")
    
    # ============================================================
    # 步骤3：价值分析
    # ============================================================
    log(f"💰 步骤3：价值分析...")
    
    # 计算8个档位的EV
    ev_results = []
    for i in range(8):
        odd = zjq_odds[i] if i < len(zjq_odds) and zjq_odds[i] > 0 else 1.0
        prob = total_goals_probs[i] if i < len(total_goals_probs) else 0
        # 赔率隐含概率（去水前）
        implied_prob = 1.0 / odd if odd > 0 else 0
        # 核心优化：引入赔率隐含概率作为先验
        # 最终概率 = 赔率隐含概率 × 0.5 + 模型概率 × 0.5
        # 这样可以避免模型高估低概率事件，让概率更接近庄家判断
        final_prob = implied_prob * 0.5 + prob * 0.5
        # 返奖率调整（低概率选项抽水更重）
        payout_rate = 0.65 if final_prob < 0.10 else 0.73
        adjusted_prob = final_prob * payout_rate
        ev_result = safe_call(calculate_ev, model_prob=adjusted_prob, odds=odd)
        ev_value = 0
        if ev_result.get('success'):
            data = ev_result.get('data', ev_result)
            ev_value = data.get('ev', 0)
        ev_results.append({
            'option': option_names[i], 
            'odds': odd, 
            'model_prob': prob,
            'implied_prob': implied_prob,
            'final_prob': final_prob,
            'adjusted_prob': adjusted_prob,
            'ev': ev_value
        })
    
    result['steps']['value_analysis'] = {'ev_results': ev_results}
    
    # 反向指标分析（总进球不适用，跳过）
    # reverse_result = safe_call(reverse_indicator, home_odds=zjq_odds[0] if len(zjq_odds)>0 else 1, draw_odds=zjq_odds[1] if len(zjq_odds)>1 else 1, away_odds=zjq_odds[2] if len(zjq_odds)>2 else 1)
    result['steps']['value_analysis']['reverse_indicator'] = {'note': '总进球不适用反向指标'}
    
    # Kelly仓位（总进球Kelly系数0.20）
    best_ev = max(ev_results, key=lambda x: x['ev'])
    kelly_result = safe_call(calculate_kelly, model_prob=best_ev['final_prob'], odds=best_ev['odds'], fraction=0.20)
    result['steps']['value_analysis']['kelly'] = kelly_result
    
    log(f"   EV最高: {best_ev['option']} (EV={best_ev['ev']:.1%})")
    
    # ============================================================
    # 步骤4：玩法适配度评估
    # ============================================================
    log(f"🎯 步骤4：玩法适配度评估...")
    
    play_specific_result = safe_call(play_specific_analysis, match_data={'odds': {'总进球': {'odds': zjq_odds}}}, play_type='总进球')
    result['steps']['play_fitness'] = {'play_specific': play_specific_result}
    
    multi_result = safe_call(multi_perspective_analysis, match_data={'odds': {'总进球': {'odds': zjq_odds}}})
    result['steps']['play_fitness']['multi_perspective'] = multi_result
    
    # ============================================================
    # 步骤5：输出结论
    # ============================================================
    log(f"✅ 步骤5：输出结论...")
    
    # 过滤掉概率过低的选项（<10%），避免EV异常偏高
    # 0球、7+球等极端选项概率低，EV计算容易失真
    # 同时明确过滤0球和7+球这两个最极端的选项
    valid_ev_results = [r for r in ev_results 
                       if r['final_prob'] >= 0.10 
                       and r['option'] not in ['0球', '7+球']]
    if not valid_ev_results:
        valid_ev_results = ev_results  # 如果所有选项都被过滤，则不过滤
    
    # 总进球EV门槛+7%
    best_ev = max(valid_ev_results, key=lambda x: x['ev'])
    
    if best_ev['ev'] > 0.07:
        recommendation = best_ev['option']
        confidence = '高' if best_ev['ev'] > 0.20 else ('中' if best_ev['ev'] > 0.12 else '低')
    else:
        recommendation = '无明确价值选项'
        confidence = '低'
    
    # 大小球方向判断
    over_25_prob = sum(total_goals_probs[3:])  # 3球及以上 = 大2.5
    under_25_prob = sum(total_goals_probs[:3])  # 0-2球 = 小2.5
    direction = '大球' if over_25_prob > under_25_prob else '小球'
    
    # 计算玩法适配度：总进球适合档位集中度高、大小球方向明确的比赛
    if concentration >= 0.55:
        play_fitness_score = 0.85  # 档位高度集中
    elif concentration >= 0.45:
        play_fitness_score = 0.70  # 档位中等集中
    else:
        play_fitness_score = 0.55  # 档位分散
    
    # 计算模型置信度：根据最高档位概率
    best_prob = best_ev['final_prob'] if best_ev else 0
    if best_prob >= 0.25:
        model_confidence = 0.80
    elif best_prob >= 0.18:
        model_confidence = 0.65
    else:
        model_confidence = 0.50
    
    result['recommendation'] = {
        'option': recommendation,
        'odds': best_ev['odds'],
        'probability': best_ev['final_prob'],
        'ev': best_ev['ev'],
        'confidence': confidence,
        'play_fitness_score': play_fitness_score,
        'model_confidence': model_confidence,
        'kelly_fraction': kelly_result.get('data', {}).get('kelly_fraction', 0) if kelly_result.get('success') else 0,
        'direction': direction,
        'over_25_prob': over_25_prob,
        'under_25_prob': under_25_prob,
        'concentration': concentration,
        'reason': f"总预期进球{lambda_total:.1f}球，{direction}概率{max(over_25_prob, under_25_prob):.1%}，档位集中度{concentration:.1%}，{best_ev['option']}EV={best_ev['ev']:.1%}，适配度{play_fitness_score:.0%}，模型置信度{model_confidence:.0%}",
    }
    
    log(f"   推荐: {recommendation} (信心度: {confidence})")
    log(f"   大小球方向: {direction} (大球{over_25_prob:.1%} / 小球{under_25_prob:.1%})")
    
    return result

def print_result(result):
    """打印格式化结果"""
    print("\n" + "=" * 70)
    print("总进球玩法分析结果")
    print("=" * 70)
    print(f"比赛: {result['match']}")
    print(f"联赛: {result.get('league', '未知')}")
    print(f"玩法: {result['play']}")
    print("-" * 70)
    
    rec = result.get('recommendation', {})
    print(f"推荐档位: {rec.get('option', '无')}")
    print(f"大小球方向: {rec.get('direction', '未知')}")
    print(f"赔率: {rec.get('odds', 'N/A')}")
    print(f"模型概率: {rec.get('probability', 0):.1%}")
    print(f"EV: {rec.get('ev', 0):.1%}")
    print(f"档位集中度: {rec.get('concentration', 0):.1%} (Top2)")
    print(f"信心度: {rec.get('confidence', '低')}")
    print(f"Kelly仓位: {rec.get('kelly_fraction', 0):.1%}")
    print(f"推荐理由: {rec.get('reason', '')}")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description='总进球玩法自动化分析')
    parser.add_argument('--match-id', required=True, help='比赛ID')
    parser.add_argument('--home', required=True, help='主队名称')
    parser.add_argument('--away', required=True, help='客队名称')
    parser.add_argument('--league', default='', help='联赛名称（可选）')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    args = parser.parse_args()
    
    verbose = not args.json
    result = analyze_zongjinqiu(args.match_id, args.home, args.away, args.league, verbose=verbose)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_result(result)

if __name__ == '__main__':
    main()
