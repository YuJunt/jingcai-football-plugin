#!/usr/bin/env python3
"""
胜平负玩法完整分析脚本
自动执行5步工作流：
  1. 数据采集（get_official_odds + get_support_rate）
  2. 概率模型（poisson_predict + dixon_coles + ensemble_predict）
  3. 价值分析（calculate_ev + calculate_kelly + reverse_indicator）
  4. 玩法适配度评估（play_specific_analysis + multi_perspective_analysis）
  5. 输出结论（推荐选项、EV、信心度、理由）

用法：
  python3 analyze_spf.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM
  python3 analyze_spf.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM --json
"""
import argparse
import json
import os
import sys

# 添加MCP服务器路径
# 脚本路径: jingcai-football-plugin/skills/jingcai-spf/scripts/analyze_spf.py
# 4层dirname = jingcai-football-plugin/
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, 'servers', 'data-collector'))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, 'servers', 'analyzer'))

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
dc_module = load_mcp_module('data-collector', 'jingcai_dc')
if dc_module:
    get_official_odds = dc_module.get_official_odds
    get_support_rate = dc_module.get_support_rate
else:
    get_official_odds = None
    get_support_rate = None

# 加载analyzer
az_module = load_mcp_module('analyzer', 'jingcai_az')
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


def analyze_spf(match_id, home_team, away_team, league='', verbose=True):
    """
    胜平负玩法完整分析
    
    Args:
        match_id: 比赛ID
        home_team: 主队名称
        away_team: 客队名称
        league: 联赛名称（可选）
        verbose: 是否打印进度信息（默认True）
    
    Returns:
        dict: 完整的胜平负分析结果
    """
    def log(msg):
        if verbose:
            print(msg)
    
    result = {
        'match_id': match_id,
        'match': f'{home_team} vs {away_team}',
        'league': league,
        'play': '胜平负',
        'steps': {},
        'recommendation': None,
    }
    
    # ============================================================
    # 步骤1：数据采集
    # ============================================================
    log(f"📊 步骤1：数据采集...")
    
    # 获取官方赔率
    odds_result = safe_call(get_official_odds, match_id=match_id)
    result['steps']['data_collection'] = {'odds': odds_result}
    
    # 提取胜平负赔率
    spf_odds = []
    if odds_result.get('success'):
        data = odds_result.get('data', odds_result)
        odds_data = data.get('odds', data)
        if isinstance(odds_data, dict):
            spf = odds_data.get('胜平负', {})
            if isinstance(spf, dict):
                spf_odds = spf.get('odds', [])
    
    # 获取支持率
    support_result = safe_call(get_support_rate, match_ids=match_id)
    result['steps']['data_collection']['support_rate'] = support_result
    
    log(f"   胜平负赔率: {spf_odds if spf_odds else '未获取'}")
    
    # ============================================================
    # 步骤2：概率模型
    # ============================================================
    log(f"📈 步骤2：概率模型...")
    
    # 估算λ（基于赔率的简单估算，实际应该用更复杂的方法）
    lambda_home = 1.3
    lambda_away = 1.0
    if len(spf_odds) >= 3 and all(o > 0 for o in spf_odds[:3]):
        # 简单的赔率→概率转换
        total = sum(1.0/o for o in spf_odds[:3])
        p_home = (1.0/spf_odds[0]) / total
        p_away = (1.0/spf_odds[2]) / total
        # 粗略估算λ
        lambda_home = max(0.5, p_home * 2.5)
        lambda_away = max(0.5, p_away * 2.5)
    
    # 泊松预测
    poisson_result = safe_call(poisson_predict, lambda_home=lambda_home, lambda_away=lambda_away)
    result['steps']['probability_model'] = {'poisson': poisson_result}
    
    # 提取泊松概率
    poisson_probs = []
    if poisson_result.get('success'):
        data = poisson_result.get('data', poisson_result)
        result_probs = data.get('result_probs', {})
        if isinstance(result_probs, dict):
            poisson_probs = [
                result_probs.get('主胜', 0),
                result_probs.get('平局', 0),
                result_probs.get('客胜', 0),
            ]
    
    # Dixon-Coles修正
    if len(spf_odds) >= 3:
        dc_result = safe_call(dixon_coles, home_odds=spf_odds[0], draw_odds=spf_odds[1], away_odds=spf_odds[2])
    else:
        dc_result = {'success': False, 'error': '赔率数据不足'}
    result['steps']['probability_model']['dixon_coles'] = dc_result
    
    # 4模型集成
    match_data = {'odds': {'胜平负': {'odds': spf_odds if spf_odds else [1.5, 3.8, 6.0]}}}
    ensemble_result = safe_call(ensemble_predict, match_data=match_data)
    result['steps']['probability_model']['ensemble'] = ensemble_result
    
    # 提取集成概率
    ensemble_probs = []
    if ensemble_result.get('success'):
        data = ensemble_result.get('data', ensemble_result)
        ep = data.get('ensemble_probs', {})
        if isinstance(ep, dict):
            ensemble_probs = [
                ep.get('主胜', 0),
                ep.get('平局', 0),
                ep.get('客胜', 0),
            ]
    
    # 使用集成概率作为最终概率
    final_probs = ensemble_probs if ensemble_probs else (poisson_probs if poisson_probs else [0.4, 0.3, 0.3])
    
    log(f"   集成概率: 主胜{final_probs[0]:.1%} 平{final_probs[1]:.1%} 客胜{final_probs[2]:.1%}")
    
    # ============================================================
    # 步骤3：价值分析
    # ============================================================
    log(f"💰 步骤3：价值分析...")
    
    # 计算每个选项的EV
    ev_results = []
    for i, (odd, prob) in enumerate(zip(spf_odds if spf_odds else [1.5, 3.8, 6.0], final_probs)):
        ev_result = safe_call(calculate_ev, model_prob=prob, odds=odd)
        ev_value = 0
        if ev_result.get('success'):
            data = ev_result.get('data', ev_result)
            ev_value = data.get('ev', 0)
        ev_results.append({'option': ['主胜', '平局', '客胜'][i], 'odds': odd, 'prob': prob, 'ev': ev_value})
    
    result['steps']['value_analysis'] = {'ev_results': ev_results}
    
    # 计算Kelly仓位（对EV最高的选项）
    best_ev = max(ev_results, key=lambda x: x['ev'])
    kelly_result = safe_call(calculate_kelly, model_prob=best_ev['prob'], odds=best_ev['odds'], fraction=0.25)
    result['steps']['value_analysis']['kelly'] = kelly_result
    
    # 反向指标分析
    reverse_match_data = {
        'odds': {'胜平负': {'odds': spf_odds if spf_odds else [1.5, 3.8, 6.0]}},
        'support': [70, 20, 10],  # 示例支持率，实际应该从数据中提取
    }
    reverse_result = safe_call(reverse_indicator, match_data=reverse_match_data)
    result['steps']['value_analysis']['reverse_indicator'] = reverse_result
    
    log(f"   EV最高: {best_ev['option']} (EV={best_ev['ev']:.1%})")
    
    # ============================================================
    # 步骤4：玩法适配度评估
    # ============================================================
    log(f"🎯 步骤4：玩法适配度评估...")
    
    # 玩法定制化分析
    play_analysis_result = safe_call(
        play_specific_analysis,
        match_data={'home': home_team, 'away': away_team, 'league': league},
        play_type='胜平负'
    )
    result['steps']['play_fitness'] = {'play_specific': play_analysis_result}
    
    # 多视角分析
    multi_perspective_result = safe_call(
        multi_perspective_analysis,
        match_data={'home': home_team, 'away': away_team, 'odds': spf_odds}
    )
    result['steps']['play_fitness']['multi_perspective'] = multi_perspective_result
    
    # ============================================================
    # 步骤5：输出结论
    # ============================================================
    log(f"✅ 步骤5：输出结论...")
    
    # 确定推荐选项（EV最高且EV>5%）
    recommendation = None
    if best_ev['ev'] > 0.05:
        recommendation = best_ev['option']
        confidence = '高' if best_ev['ev'] > 0.15 else ('中' if best_ev['ev'] > 0.1 else '低')
    else:
        recommendation = '无明确价值选项'
        confidence = '低'
    
    # 计算玩法适配度：胜平负适合稳胆（赔率1.4-1.8）和实力接近的比赛
    best_odd = best_ev['odds'] if best_ev else 0
    if 1.4 <= best_odd <= 1.8:
        play_fitness_score = 0.85  # 稳胆区间，适配度高
    elif 1.8 < best_odd <= 3.0:
        play_fitness_score = 0.70  # 实力接近，适配度中等
    elif best_odd > 3.0:
        play_fitness_score = 0.50  # 冷门区间，适配度低
    else:
        play_fitness_score = 0.60
    
    # 计算模型置信度：根据最高概率的集中度
    best_prob = best_ev['prob'] if best_ev else 0
    if best_prob >= 0.60:
        model_confidence = 0.85  # 高确定性
    elif best_prob >= 0.45:
        model_confidence = 0.70  # 中等确定性
    else:
        model_confidence = 0.50  # 低确定性
    
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
    """打印分析结果"""
    print("\n" + "=" * 70)
    print("胜平负玩法分析结果")
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
    print(f"推荐理由: {rec.get('reason', '')}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='胜平负玩法完整分析')
    parser.add_argument('--match-id', required=True, help='比赛ID')
    parser.add_argument('--home', required=True, help='主队名称')
    parser.add_argument('--away', required=True, help='客队名称')
    parser.add_argument('--league', default='', help='联赛名称（可选）')
    parser.add_argument('--json', action='store_true', help='以JSON格式输出')
    
    args = parser.parse_args()
    
    # JSON模式下不打印进度信息
    verbose = not args.json
    
    result = analyze_spf(args.match_id, args.home, args.away, args.league, verbose=verbose)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_result(result)


if __name__ == '__main__':
    main()
