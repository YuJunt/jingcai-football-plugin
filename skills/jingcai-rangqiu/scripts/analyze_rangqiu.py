#!/usr/bin/env python3
"""
让球胜平负玩法自动化分析脚本
自动执行5步工作流：数据采集→概率模型→价值分析→玩法适配度→输出结论
用法：
  python3 analyze_rangqiu.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM
  python3 analyze_rangqiu.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM --json
"""
import argparse
import json
import os
import sys

# 脚本路径: jingcai-football-plugin/skills/jingcai-rangqiu/scripts/analyze_rangqiu.py
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
dc_module = load_mcp_module('data-collector', 'jingcai_dc_rq')
if dc_module:
    get_official_odds = dc_module.get_official_odds
    get_support_rate = dc_module.get_support_rate
else:
    get_official_odds = None
    get_support_rate = None

# 加载analyzer
az_module = load_mcp_module('analyzer', 'jingcai_az_rq')
if az_module:
    poisson_predict = az_module.poisson_predict
    dixon_coles = az_module.dixon_coles
    ensemble_predict = az_module.ensemble_predict
    calculate_ev = az_module.calculate_ev
    calculate_kelly = az_module.calculate_kelly
    reverse_indicator = az_module.reverse_indicator
    play_specific_analysis = az_module.play_specific_analysis
    multi_perspective_analysis = az_module.multi_perspective_analysis
    theoretical_vs_actual_handicap = getattr(az_module, 'theoretical_vs_actual_handicap', None)
    handicap_language_analyzer = getattr(az_module, 'handicap_language_analyzer', None)
else:
    poisson_predict = None
    dixon_coles = None
    ensemble_predict = None
    calculate_ev = None
    calculate_kelly = None
    reverse_indicator = None
    play_specific_analysis = None
    multi_perspective_analysis = None
    theoretical_vs_actual_handicap = None
    handicap_language_analyzer = None

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

def analyze_rangqiu(match_id, home_team, away_team, league='', verbose=True):
    """
    让球胜平负玩法完整分析
    """
    def log(msg):
        if verbose:
            print(msg)
    
    result = {
        'match_id': match_id,
        'match': f'{home_team} vs {away_team}',
        'league': league,
        'play': '让球胜平负',
        'handicap': None,
        'steps': {},
        'recommendation': None,
    }
    
    # ============================================================
    # 步骤1：数据采集
    # ============================================================
    log(f"📊 步骤1：数据采集...")
    
    odds_result = safe_call(get_official_odds, match_id=match_id)
    result['steps']['data_collection'] = {'odds': odds_result}
    
    # 提取让球胜平负赔率和让球数
    rq_odds = []
    handicap = None
    spf_odds_for_lambda = []
    if odds_result.get('success'):
        data = odds_result.get('data', odds_result)
        odds_data = data.get('odds', data)
        if isinstance(odds_data, dict):
            rq = odds_data.get('让球胜平负', {})
            if isinstance(rq, dict):
                rq_odds = rq.get('odds', [])
                handicap = rq.get('handicap', None)
            spf = odds_data.get('胜平负', {})
            if isinstance(spf, dict):
                spf_odds_for_lambda = spf.get('odds', [])
    
    result['handicap'] = handicap
    
    support_result = safe_call(get_support_rate, match_ids=match_id)
    result['steps']['data_collection']['support_rate'] = support_result
    
    log(f"   让球胜平负赔率: {rq_odds if rq_odds else '未获取'}")
    log(f"   让球数: {handicap if handicap else '未知'}")
    
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
    
    poisson_probs = []
    if poisson_result.get('success'):
        data = poisson_result.get('data', poisson_result)
        result_probs = data.get('result_probs', {})
        if isinstance(result_probs, dict):
            poisson_probs = [result_probs.get('主胜', 0), result_probs.get('平局', 0), result_probs.get('客胜', 0)]
    
    # Dixon-Coles修正（用胜平负赔率）
    if len(spf_odds_for_lambda) >= 3:
        dc_result = safe_call(dixon_coles, home_odds=spf_odds_for_lambda[0], draw_odds=spf_odds_for_lambda[1], away_odds=spf_odds_for_lambda[2])
    else:
        dc_result = {'success': False, 'error': '赔率数据不足'}
    result['steps']['probability_model']['dixon_coles'] = dc_result
    
    # 4模型集成（用胜平负赔率，因为ensemble_predict需要胜平负数据）
    match_data = {'odds': {'胜平负': {'odds': spf_odds_for_lambda if spf_odds_for_lambda else [1.5, 3.8, 6.0]}}}
    ensemble_result = safe_call(ensemble_predict, match_data=match_data)
    result['steps']['probability_model']['ensemble'] = ensemble_result
    
    # 提取集成概率（胜平负概率）
    ensemble_probs_spf = []
    if ensemble_result.get('success'):
        data = ensemble_result.get('data', ensemble_result)
        ep = data.get('ensemble_probs', {})
        if isinstance(ep, dict):
            ensemble_probs_spf = [ep.get('主胜', 0), ep.get('平局', 0), ep.get('客胜', 0)]
    
    # 将胜平负概率转换为让球胜平负概率（简化版，基于让球数调整）
    # 实际应该用泊松净胜球分布计算，这里用简化方法
    ensemble_probs = [0.4, 0.3, 0.3]  # 默认值
    if ensemble_probs_spf and handicap:
        try:
            hc = int(handicap)  # 让球数，负数表示主队让球
            if hc < 0:  # 主队让球
                # 主队让1球：让胜=主胜2球以上，让平=主胜1球，让负=平/客胜
                # 简化转换：让胜概率降低，让平/让负概率增加
                p_home, p_draw, p_away = ensemble_probs_spf
                # 假设主胜中，赢1球占40%，赢2球以上占60%
                ensemble_probs = [
                    p_home * 0.6,  # 让胜
                    p_home * 0.4,  # 让平
                    p_draw + p_away  # 让负
                ]
            elif hc > 0:  # 客队让球
                p_home, p_draw, p_away = ensemble_probs_spf
                ensemble_probs = [
                    p_home + p_draw,  # 让胜
                    p_away * 0.4,  # 让平
                    p_away * 0.6  # 让负
                ]
        except (ValueError, TypeError):
            ensemble_probs = ensemble_probs_spf if ensemble_probs_spf else [0.4, 0.3, 0.3]
    elif ensemble_probs_spf:
        ensemble_probs = ensemble_probs_spf
    
    # 理论vs实际盘口偏离分析（让球专属）
    if theoretical_vs_actual_handicap:
        handicap_result = safe_call(theoretical_vs_actual_handicap, lambda_home=lambda_home, lambda_away=lambda_away, actual_handicap=handicap)
        result['steps']['probability_model']['handicap_analysis'] = handicap_result
    
    # 盘口语言识别（让球专属）
    if handicap_language_analyzer:
        language_result = safe_call(handicap_language_analyzer, opening_handicap=handicap, closing_handicap=handicap, opening_water=0.9, closing_water=0.95)
        result['steps']['probability_model']['handicap_language'] = language_result
    
    final_probs = ensemble_probs if ensemble_probs else (poisson_probs if poisson_probs else [0.4, 0.3, 0.3])
    
    log(f"   集成概率: 让胜{final_probs[0]:.1%} 让平{final_probs[1]:.1%} 让负{final_probs[2]:.1%}")
    
    # ============================================================
    # 步骤3：价值分析
    # ============================================================
    log(f"💰 步骤3：价值分析...")
    
    ev_results = []
    for i, (odd, prob) in enumerate(zip(rq_odds if rq_odds else [1.5, 3.8, 6.0], final_probs)):
        ev_result = safe_call(calculate_ev, model_prob=prob, odds=odd)
        ev_value = 0
        if ev_result.get('success'):
            data = ev_result.get('data', ev_result)
            ev_value = data.get('ev', 0)
        ev_results.append({'option': ['让胜', '让平', '让负'][i], 'odds': odd, 'prob': prob, 'ev': ev_value})
    
    result['steps']['value_analysis'] = {'ev_results': ev_results}
    
    # 反向指标分析
    reverse_result = safe_call(reverse_indicator, odds=rq_odds, support=[0, 0, 0])
    result['steps']['value_analysis']['reverse_indicator'] = reverse_result
    
    # Kelly仓位（让球胜平负Kelly系数0.20）
    best_ev = max(ev_results, key=lambda x: x['ev'])
    kelly_result = safe_call(calculate_kelly, model_prob=best_ev['prob'], odds=best_ev['odds'], fraction=0.20)
    result['steps']['value_analysis']['kelly'] = kelly_result
    
    log(f"   EV最高: {best_ev['option']} (EV={best_ev['ev']:.1%})")
    
    # ============================================================
    # 步骤4：玩法适配度评估
    # ============================================================
    log(f"🎯 步骤4：玩法适配度评估...")
    
    play_specific_result = safe_call(play_specific_analysis, match_data={'odds': {'让球胜平负': {'odds': rq_odds}}}, play_type='让球胜平负')
    result['steps']['play_fitness'] = {'play_specific': play_specific_result}
    
    multi_result = safe_call(multi_perspective_analysis, match_data={'odds': {'让球胜平负': {'odds': rq_odds}}})
    result['steps']['play_fitness']['multi_perspective'] = multi_result
    
    # ============================================================
    # 步骤5：输出结论
    # ============================================================
    log(f"✅ 步骤5：输出结论...")
    
    if best_ev['ev'] > 0.05:
        recommendation = best_ev['option']
        confidence = '高' if best_ev['ev'] > 0.15 else ('中' if best_ev['ev'] > 0.1 else '低')
    else:
        recommendation = '无明确价值选项'
        confidence = '低'
    
    # 计算玩法适配度：让球胜平负适合让球盘口0.5-1.5、让平有价值的比赛
    best_odd = best_ev['odds'] if best_ev else 0
    best_option = best_ev['option'] if best_ev else ''
    if best_option == '让平' and best_odd > 3.5:
        play_fitness_score = 0.90  # 让平专项，适配度最高
    elif 1.5 <= best_odd <= 2.5:
        play_fitness_score = 0.75  # 让胜/让负稳胆区间
    else:
        play_fitness_score = 0.60
    
    # 计算模型置信度：根据最高概率的集中度
    best_prob = best_ev['prob'] if best_ev else 0
    if best_prob >= 0.55:
        model_confidence = 0.80
    elif best_prob >= 0.40:
        model_confidence = 0.65
    else:
        model_confidence = 0.50
    
    result['recommendation'] = {
        'option': recommendation,
        'odds': best_ev['odds'],
        'probability': best_ev['prob'],
        'ev': best_ev['ev'],
        'confidence': confidence,
        'play_fitness_score': play_fitness_score,
        'model_confidence': model_confidence,
        'kelly_fraction': kelly_result.get('data', {}).get('kelly_fraction', 0) if kelly_result.get('success') else 0,
        'reason': f"模型概率{best_ev['prob']:.1%}，赔率{best_ev['odds']}，EV={best_ev['ev']:.1%}，适配度{play_fitness_score:.0%}，模型置信度{model_confidence:.0%}",
    }
    
    log(f"   推荐: {recommendation} (信心度: {confidence})")
    
    return result

def print_result(result):
    """打印格式化结果"""
    print("\n" + "=" * 70)
    print("让球胜平负玩法分析结果")
    print("=" * 70)
    print(f"比赛: {result['match']}")
    print(f"联赛: {result.get('league', '未知')}")
    print(f"让球数: {result.get('handicap', '未知')}")
    print(f"玩法: {result['play']}")
    print("-" * 70)
    
    rec = result.get('recommendation', {})
    print(f"推荐选项: {rec.get('option', '无')}")
    print(f"赔率: {rec.get('odds', 'N/A')}")
    print(f"模型概率: {rec.get('probability', 0):.1%}")
    print(f"EV: {rec.get('ev', 0):.1%}")
    print(f"信心度: {rec.get('confidence', '低')}")
    print(f"Kelly仓位: {rec.get('kelly_fraction', 0):.1%}")
    print(f"推荐理由: {rec.get('reason', '')}")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description='让球胜平负玩法自动化分析')
    parser.add_argument('--match-id', required=True, help='比赛ID')
    parser.add_argument('--home', required=True, help='主队名称')
    parser.add_argument('--away', required=True, help='客队名称')
    parser.add_argument('--league', default='', help='联赛名称（可选）')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    args = parser.parse_args()
    
    verbose = not args.json
    result = analyze_rangqiu(args.match_id, args.home, args.away, args.league, verbose=verbose)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_result(result)

if __name__ == '__main__':
    main()
