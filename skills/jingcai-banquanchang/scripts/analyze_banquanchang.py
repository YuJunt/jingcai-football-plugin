#!/usr/bin/env python3
"""
半全场玩法自动化分析脚本
自动执行5步工作流：数据采集→概率模型→价值分析→玩法适配度→输出结论
用法：
  python3 analyze_banquanchang.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM
  python3 analyze_banquanchang.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM --json
"""
import argparse
import json
import math
import os
import sys

# 脚本路径: jingcai-football-plugin/skills/jingcai-banquanchang/scripts/analyze_banquanchang.py
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
dc_module = load_mcp_module('data-collector', 'jingcai_dc_bqc')
if dc_module:
    get_official_odds = dc_module.get_official_odds
    get_support_rate = dc_module.get_support_rate
else:
    get_official_odds = None
    get_support_rate = None

# 加载analyzer
az_module = load_mcp_module('analyzer', 'jingcai_az_bqc')
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
    from historical_calibrator import calibrate_banquanchang
    HAS_CALIBRATOR = True
except ImportError:
    HAS_CALIBRATOR = False
    calibrate_banquanchang = None

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

def calculate_banquanchang_probs(lambda_home, lambda_away):
    """
    计算半全场9个选项的概率（简化版条件概率法）
    Step 1: 半场结果概率矩阵（λ_half = λ_full × 0.45）
    Step 2: 动态下半场λ（领先方λ下降，落后方λ上升）
    Step 3: 映射9种结果
    Step 4: 逆转选项×0.6修正
    """
    # 半场λ
    lambda_home_half = lambda_home * 0.45
    lambda_away_half = lambda_away * 0.45
    
    # 计算半场胜平负概率
    def calc_1x2_probs(lh, la, max_goals=5):
        p_home = 0
        p_draw = 0
        p_away = 0
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                p_h = (lh ** h) * math.exp(-lh) / math.factorial(h)
                p_a = (la ** a) * math.exp(-la) / math.factorial(a)
                p = p_h * p_a
                if h > a:
                    p_home += p
                elif h == a:
                    p_draw += p
                else:
                    p_away += p
        return [p_home, p_draw, p_away]
    
    half_probs = calc_1x2_probs(lambda_home_half, lambda_away_half)
    
    # 动态下半场λ
    # 半场主胜：主队λ×0.9（保守），客队λ×1.2（猛攻）
    # 半场平局：λ基本不变
    # 半场客胜：主队λ×1.2（猛攻），客队λ×0.9（保守）
    second_half_lambdas = {
        'home_win': (lambda_home * 0.55 * 0.9, lambda_away * 0.55 * 1.2),
        'draw': (lambda_home * 0.55, lambda_away * 0.55),
        'away_win': (lambda_home * 0.55 * 1.2, lambda_away * 0.55 * 0.9),
    }
    
    # 计算下半场胜平负概率
    second_half_probs = {}
    for key, (lh, la) in second_half_lambdas.items():
        second_half_probs[key] = calc_1x2_probs(lh, la)
    
    # 映射9种半全场结果
    # 半场主胜 + 下半场主胜/平局 = 全场主胜 → 胜胜
    # 半场主胜 + 下半场客胜，且逆转 = 胜负
    # 简化处理：直接用半场概率 × 全场概率的条件概率
    full_probs = calc_1x2_probs(lambda_home, lambda_away)
    
    # 9个选项的概率（简化版）
    option_names = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
    
    # 简化映射：
    # 胜胜 = 半场主胜 × 全场主胜 / (全场主胜+全场平局) （条件概率）
    # 胜平 = 半场主胜 × 全场平局 / (全场主胜+全场平局)
    # 胜负 = 半场主胜 × 全场客胜 × 0.6 （逆转修正）
    # 平胜 = 半场平局 × 全场主胜
    # 平平 = 半场平局 × 全场平局
    # 平负 = 半场平局 × 全场客胜
    # 负胜 = 半场客胜 × 全场主胜 × 0.6 （逆转修正）
    # 负平 = 半场客胜 × 全场平局 / (全场平局+全场客胜)
    # 负负 = 半场客胜 × 全场客胜 / (全场平局+全场客胜)
    
    p_hh, p_hd, p_ha = half_probs
    p_fh, p_fd, p_fa = full_probs
    
    probs = [0] * 9
    
    # 胜胜、胜平
    if p_fh + p_fd > 0:
        probs[0] = p_hh * p_fh / (p_fh + p_fd)  # 胜胜
        probs[1] = p_hh * p_fd / (p_fh + p_fd)  # 胜平
    probs[2] = p_hh * p_fa * 0.6  # 胜负（逆转修正）
    
    # 平胜、平平、平负
    probs[3] = p_hd * p_fh  # 平胜
    probs[4] = p_hd * p_fd  # 平平
    probs[5] = p_hd * p_fa  # 平负
    
    # 负胜（逆转修正）
    probs[6] = p_ha * p_fh * 0.6  # 负胜（逆转修正）
    # 负平、负负
    if p_fd + p_fa > 0:
        probs[7] = p_ha * p_fd / (p_fd + p_fa)  # 负平
        probs[8] = p_ha * p_fa / (p_fd + p_fa)  # 负负
    
    # 归一化
    total = sum(probs)
    if total > 0:
        probs = [p / total for p in probs]
    
    return option_names, probs, half_probs, full_probs

def analyze_banquanchang(match_id, home_team, away_team, league='', verbose=True):
    """
    半全场玩法完整分析
    """
    def log(msg):
        if verbose:
            print(msg)
    
    result = {
        'match_id': match_id,
        'match': f'{home_team} vs {away_team}',
        'league': league,
        'play': '半全场',
        'steps': {},
        'recommendation': None,
    }
    
    # ============================================================
    # 步骤1：数据采集
    # ============================================================
    log(f"📊 步骤1：数据采集...")
    
    odds_result = safe_call(get_official_odds, match_id=match_id)
    result['steps']['data_collection'] = {'odds': odds_result}
    
    # 提取半全场赔率（9个选项）
    bqc_odds = {}
    bqc_option_names = []
    spf_odds_for_lambda = []
    if odds_result.get('success'):
        data = odds_result.get('data', odds_result)
        odds_data = data.get('odds', data)
        if isinstance(odds_data, dict):
            bqc = odds_data.get('半全场', {})
            if isinstance(bqc, dict):
                bqc_option_names = bqc.get('option_names', [])
                odds_list = bqc.get('odds', [])
                for name, odd in zip(bqc_option_names, odds_list):
                    bqc_odds[name] = odd
            spf = odds_data.get('胜平负', {})
            if isinstance(spf, dict):
                spf_odds_for_lambda = spf.get('odds', [])
    
    support_result = safe_call(get_support_rate, match_ids=match_id)
    result['steps']['data_collection']['support_rate'] = support_result
    
    log(f"   半全场赔率: {len(bqc_odds)}个选项")
    
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
    result['steps']['probability_model'] = {'poisson': poisson_result}
    
    # 计算半场和全场概率（用于展示和校准）
    _, _, half_probs, full_probs = calculate_banquanchang_probs(lambda_home, lambda_away)
    
    # 用历史数据校准半全场概率（替代简化版条件概率法）
    if HAS_CALIBRATOR and calibrate_banquanchang:
        bqc_probs_dict = calibrate_banquanchang(lambda_home, lambda_away)
        option_names = list(bqc_probs_dict.keys())
        bqc_probs = [bqc_probs_dict.get(name, 0) for name in option_names]
    else:
        # 降级：简化版条件概率法
        option_names, bqc_probs, _, _ = calculate_banquanchang_probs(lambda_home, lambda_away)
    result['steps']['probability_model']['bqc_probs'] = dict(zip(option_names, bqc_probs))
    result['steps']['probability_model']['half_probs'] = half_probs
    result['steps']['probability_model']['full_probs'] = full_probs
    
    # Dixon-Coles修正
    if len(spf_odds_for_lambda) >= 3:
        dc_result = safe_call(dixon_coles, home_odds=spf_odds_for_lambda[0], draw_odds=spf_odds_for_lambda[1], away_odds=spf_odds_for_lambda[2])
    else:
        dc_result = {'success': False, 'error': '赔率数据不足'}
    result['steps']['probability_model']['dixon_coles'] = dc_result
    
    log(f"   半场概率: 主胜{half_probs[0]:.1%} 平{half_probs[1]:.1%} 客胜{half_probs[2]:.1%}")
    log(f"   全场概率: 主胜{full_probs[0]:.1%} 平{full_probs[1]:.1%} 客胜{full_probs[2]:.1%}")
    log(f"   概率最高: {option_names[bqc_probs.index(max(bqc_probs))]} ({max(bqc_probs):.1%})")
    
    # ============================================================
    # 步骤3：价值分析
    # ============================================================
    log(f"💰 步骤3：价值分析...")
    
    # 计算9个选项的EV
    ev_results = []
    for i, name in enumerate(option_names):
        odd = bqc_odds.get(name, 1.0)
        prob = bqc_probs[i] if i < len(bqc_probs) else 0
        if odd > 0 and prob > 0:
            # 赔率隐含概率
            implied_prob = 1.0 / odd
            # 核心优化：引入赔率隐含概率作为先验
            # 最终概率 = 赔率隐含概率 × 0.5 + 模型概率 × 0.5
            final_prob = implied_prob * 0.5 + prob * 0.5
            # 返奖率调整：半全场抽水重，逆转选项更低
            payout_rate = 0.50 if name in ['胜负', '负胜'] else 0.60
            adjusted_prob = final_prob * payout_rate
            ev_result = safe_call(calculate_ev, model_prob=adjusted_prob, odds=odd)
            ev_value = 0
            if ev_result.get('success'):
                data = ev_result.get('data', ev_result)
                ev_value = data.get('ev', 0)
            ev_results.append({
                'option': name, 
                'odds': odd, 
                'model_prob': prob,
                'implied_prob': implied_prob,
                'final_prob': final_prob,
                'adjusted_prob': adjusted_prob,
                'ev': ev_value
            })
    
    result['steps']['value_analysis'] = {'ev_results': ev_results}
    
    # 反向指标分析
    reverse_result = safe_call(reverse_indicator, odds=[bqc_odds.get(name, 1.0) for name in option_names[:3]], support=[0, 0, 0])
    result['steps']['value_analysis']['reverse_indicator'] = reverse_result
    
    # Kelly仓位（半全场Kelly系数0.05）
    # 过滤掉概率过低的选项（<3%），避免EV异常
    valid_ev_results = [r for r in ev_results if r['final_prob'] >= 0.03]
    if not valid_ev_results:
        valid_ev_results = ev_results
    best_ev = max(valid_ev_results, key=lambda x: x['ev']) if valid_ev_results else ev_results[0] if ev_results else {'option': '无', 'odds': 1.0, 'prob': 0, 'ev': 0}
    
    kelly_result = safe_call(calculate_kelly, model_prob=best_ev['final_prob'], odds=best_ev['odds'], fraction=0.05)
    result['steps']['value_analysis']['kelly'] = kelly_result
    
    log(f"   EV最高: {best_ev['option']} (EV={best_ev['ev']:.1%})")
    
    # ============================================================
    # 步骤4：玩法适配度评估
    # ============================================================
    log(f"🎯 步骤4：玩法适配度评估...")
    
    play_specific_result = safe_call(play_specific_analysis, match_data={'odds': {'半全场': {'odds': [bqc_odds.get(name, 1.0) for name in option_names]}}}, play_type='半全场')
    result['steps']['play_fitness'] = {'play_specific': play_specific_result}
    
    multi_result = safe_call(multi_perspective_analysis, match_data={'odds': {'半全场': {'odds': [bqc_odds.get(name, 1.0) for name in option_names]}}})
    result['steps']['play_fitness']['multi_perspective'] = multi_result
    
    # ============================================================
    # 步骤5：输出结论
    # ============================================================
    log(f"✅ 步骤5：输出结论...")
    
    # 半全场EV门槛+12%
    if best_ev['ev'] > 0.12:
        recommendation = best_ev['option']
        confidence = '高' if best_ev['ev'] > 0.25 else ('中' if best_ev['ev'] > 0.18 else '低')
    else:
        recommendation = '无明确价值选项'
        confidence = '低'
    
    # 计算玩法适配度：半全场适合半场和全场结果都明确的比赛
    half_certainty = max(half_probs) if half_probs else 0
    full_certainty = max(full_probs) if full_probs else 0
    if half_certainty >= 0.50 and full_certainty >= 0.55:
        play_fitness_score = 0.80  # 半场和全场都明确
    elif half_certainty >= 0.45 or full_certainty >= 0.50:
        play_fitness_score = 0.65  # 半场或全场明确
    else:
        play_fitness_score = 0.50  # 都不明确
    
    # 计算模型置信度：根据最高选项概率
    best_prob = best_ev['final_prob'] if best_ev else 0
    if best_prob >= 0.20:
        model_confidence = 0.75
    elif best_prob >= 0.12:
        model_confidence = 0.60
    else:
        model_confidence = 0.45
    
    result['recommendation'] = {
        'option': recommendation,
        'odds': best_ev['odds'],
        'probability': best_ev['final_prob'],
        'ev': best_ev['ev'],
        'confidence': confidence,
        'play_fitness_score': play_fitness_score,
        'model_confidence': model_confidence,
        'kelly_fraction': kelly_result.get('data', {}).get('kelly_fraction', 0) if kelly_result.get('success') else 0,
        'half_probs': half_probs,
        'full_probs': full_probs,
        'reason': f"半场主胜{half_probs[0]:.1%}/平{half_probs[1]:.1%}/客胜{half_probs[2]:.1%}，全场主胜{full_probs[0]:.1%}/平{full_probs[1]:.1%}/客胜{full_probs[2]:.1%}，{best_ev['option']}概率{best_ev['final_prob']:.1%}，赔率{best_ev['odds']}，EV={best_ev['ev']:.1%}，适配度{play_fitness_score:.0%}，模型置信度{model_confidence:.0%}",
    }
    
    log(f"   推荐: {recommendation} (信心度: {confidence})")
    
    return result

def print_result(result):
    """打印格式化结果"""
    print("\n" + "=" * 70)
    print("半全场玩法分析结果")
    print("=" * 70)
    print(f"比赛: {result['match']}")
    print(f"联赛: {result.get('league', '未知')}")
    print(f"玩法: {result['play']}")
    print("-" * 70)
    
    rec = result.get('recommendation', {})
    print(f"推荐选项: {rec.get('option', '无')}")
    print(f"赔率: {rec.get('odds', 'N/A')}")
    print(f"模型概率: {rec.get('probability', 0):.1%}")
    print(f"EV: {rec.get('ev', 0):.1%}")
    print(f"信心度: {rec.get('confidence', '低')}")
    print(f"Kelly仓位: {rec.get('kelly_fraction', 0):.1%}")
    
    half_probs = rec.get('half_probs', [0, 0, 0])
    full_probs = rec.get('full_probs', [0, 0, 0])
    print(f"\n半场概率: 主胜{half_probs[0]:.1%} 平{half_probs[1]:.1%} 客胜{half_probs[2]:.1%}")
    print(f"全场概率: 主胜{full_probs[0]:.1%} 平{full_probs[1]:.1%} 客胜{full_probs[2]:.1%}")
    
    print(f"\n推荐理由: {rec.get('reason', '')}")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description='半全场玩法自动化分析')
    parser.add_argument('--match-id', required=True, help='比赛ID')
    parser.add_argument('--home', required=True, help='主队名称')
    parser.add_argument('--away', required=True, help='客队名称')
    parser.add_argument('--league', default='', help='联赛名称（可选）')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    args = parser.parse_args()
    
    verbose = not args.json
    result = analyze_banquanchang(args.match_id, args.home, args.away, args.league, verbose=verbose)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_result(result)

if __name__ == '__main__':
    main()
