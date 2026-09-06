#!/usr/bin/env python3
"""
混合过关组合设计自动化脚本
自动执行5步工作流：收集候选选项→玩法搭配决策→串关结构设计→木桶原则校验→输出组合方案
用法：
  python3 design_mixed_portfolio.py --input candidates.json
  python3 design_mixed_portfolio.py --input candidates.json --json
"""
import argparse
import json
import os
import sys

# 脚本路径: jingcai-football-plugin/skills/jingcai-mixed/scripts/design_mixed_portfolio.py
# 4层dirname = jingcai-football-plugin/
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 过关上限规则
PLAY_LIMITS = {
    '胜平负': 8,
    '让球胜平负': 8,
    '总进球': 6,
    '比分': 4,
    '半全场': 4,
}

# 高赔玩法
HIGH_RISK_PLAYS = ['比分', '半全场']

def load_candidates(input_file):
    """加载候选选项列表"""
    if not os.path.exists(input_file):
        print(f"❌ 候选文件不存在: {input_file}")
        return []
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and 'candidates' in data:
        return data['candidates']
    return []

def play_mix_decision(candidates):
    """
    玩法搭配决策：混合过关 vs 单玩法串关
    返回: 'mixed' 或 'single'
    """
    # 统计各玩法的候选数量
    play_counts = {}
    for c in candidates:
        play = c.get('play', '')
        play_counts[play] = play_counts.get(play, 0) + 1
    
    num_plays = len(play_counts)
    total_candidates = len(candidates)
    
    # 玩法多样性
    diversity = num_plays / 5.0 if total_candidates > 0 else 0
    
    # 玩法集中度（最高占比）
    max_concentration = max(play_counts.values()) / total_candidates if total_candidates > 0 else 0
    
    # 混合过关得分
    mixed_score = diversity * 0.4 + (1 - max_concentration) * 0.3 + 0.3  # 确定性均衡默认0.3
    
    # 单玩法得分
    single_score = max_concentration * 0.5 + 0.3 + 0.2  # 命中率默认0.3，串关长度默认0.2
    
    return 'mixed' if mixed_score > single_score else 'single'

def check_barrel_principle(bet_slip):
    """
    木桶原则校验
    返回: (passed, checks)
    """
    checks = {
        'weakest_link': True,
        'play_ratio': True,
        'limit': True,
        'odds_range': True,
        'correlation': True,
    }
    
    options = bet_slip.get('options', [])
    if not options:
        return False, checks
    
    # 1. 最弱环节检查：每个选项EV>0，最低EV信心度>50%
    min_ev = min(o.get('ev', 0) for o in options)
    # 信心度字符串转数值：高=1.0, 中=0.7, 低=0.4
    confidence_map = {'高': 1.0, '中': 0.7, '低': 0.4}
    min_confidence = min(confidence_map.get(o.get('confidence', '低'), 0.4) for o in options)
    if min_ev <= 0 or min_confidence < 0.5:
        checks['weakest_link'] = False
    
    # 2. 玩法比例检查：高赔玩法≤总场数1/3
    high_risk_count = sum(1 for o in options if o.get('play') in HIGH_RISK_PLAYS)
    if high_risk_count > len(options) / 3:
        checks['play_ratio'] = False
    
    # 3. 上限检查：串关长度不超过最低上限玩法限制
    plays = [o.get('play', '') for o in options]
    min_limit = min(PLAY_LIMITS.get(p, 8) for p in plays) if plays else 8
    if len(options) > min_limit:
        checks['limit'] = False
    
    # 4. 赔率合理性：总赔率在3-50倍之间
    total_odds = 1.0
    for o in options:
        total_odds *= o.get('odds', 1.0)
    if total_odds < 3 or total_odds > 50:
        checks['odds_range'] = False
    
    # 5. 相关性检查：同一场比赛不同玩法选项不能同时串
    match_ids = [o.get('match_id', '') for o in options]
    if len(match_ids) != len(set(match_ids)):
        checks['correlation'] = False
    
    passed = all(checks.values())
    return passed, checks

def design_portfolio(candidates, mode='mixed'):
    """
    设计混合过关组合方案
    返回: 投注单列表
    """
    if not candidates:
        return []
    
    # 按EV排序
    sorted_candidates = sorted(candidates, key=lambda x: x.get('ev', 0), reverse=True)
    
    bet_slips = []
    
    if mode == 'mixed':
        # 混合过关：选择不同玩法的高EV选项
        selected_by_play = {}
        for c in sorted_candidates:
            play = c.get('play', '')
            if play not in selected_by_play:
                selected_by_play[play] = c
            if len(selected_by_play) >= 4:
                break
        
        # 构建投注单
        if len(selected_by_play) >= 2:
            options = list(selected_by_play.values())[:4]
            total_odds = 1.0
            for o in options:
                total_odds *= o.get('odds', 1.0)
            
            bet_slip = {
                'type': f"{len(options)}串1",
                'mode': '混合过关',
                'options': options,
                'total_odds': round(total_odds, 2),
                'stake': 2,
                'expected_payout': round(2 * total_odds, 2),
            }
            
            passed, checks = check_barrel_principle(bet_slip)
            bet_slip['barrel_check'] = {'passed': passed, 'checks': checks}
            
            bet_slips.append(bet_slip)
    else:
        # 单玩法串关：选择同一玩法的高EV选项
        play_counts = {}
        for c in sorted_candidates:
            play = c.get('play', '')
            if play not in play_counts:
                play_counts[play] = []
            play_counts[play].append(c)
        
        # 选择候选最多的玩法
        best_play = max(play_counts.keys(), key=lambda p: len(play_counts[p]))
        best_candidates = play_counts[best_play][:4]
        
        if len(best_candidates) >= 2:
            total_odds = 1.0
            for o in best_candidates:
                total_odds *= o.get('odds', 1.0)
            
            bet_slip = {
                'type': f"{len(best_candidates)}串1",
                'mode': f'{best_play}单玩法',
                'options': best_candidates,
                'total_odds': round(total_odds, 2),
                'stake': 2,
                'expected_payout': round(2 * total_odds, 2),
            }
            
            passed, checks = check_barrel_principle(bet_slip)
            bet_slip['barrel_check'] = {'passed': passed, 'checks': checks}
            
            bet_slips.append(bet_slip)
    
    return bet_slips

def print_result(result):
    """打印格式化结果"""
    print("\n" + "=" * 70)
    print("混合过关组合设计结果")
    print("=" * 70)
    print(f"候选选项数: {result.get('candidate_count', 0)}")
    print(f"搭配模式: {result.get('mode', '未知')}")
    print(f"投注单数: {len(result.get('bet_slips', []))}")
    print("-" * 70)
    
    for i, slip in enumerate(result.get('bet_slips', []), 1):
        print(f"\n投注单 {i}: {slip.get('type', '')} ({slip.get('mode', '')})")
        print(f"  总赔率: {slip.get('total_odds', 0)}")
        print(f"  投入: {slip.get('stake', 0)}元")
        print(f"  预期奖金: {slip.get('expected_payout', 0)}元")
        print(f"  选项:")
        for o in slip.get('options', []):
            print(f"    - {o.get('match_id', '')} {o.get('play', '')} {o.get('option', '')} (赔率{o.get('odds', 0)}, EV{o.get('ev', 0):.1%})")
        
        barrel = slip.get('barrel_check', {})
        print(f"  木桶原则校验: {'✅ 通过' if barrel.get('passed') else '❌ 未通过'}")
        if not barrel.get('passed'):
            for check, passed in barrel.get('checks', {}).items():
                if not passed:
                    print(f"    - {check}: ❌")
    
    print("\n" + "=" * 70)

def main():
    parser = argparse.ArgumentParser(description='混合过关组合设计')
    parser.add_argument('--input', required=True, help='候选选项JSON文件')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    args = parser.parse_args()
    
    # 加载候选选项
    candidates = load_candidates(args.input)
    
    # 玩法搭配决策
    mode = play_mix_decision(candidates)
    
    # 设计组合方案
    bet_slips = design_portfolio(candidates, mode)
    
    result = {
        'candidate_count': len(candidates),
        'mode': mode,
        'bet_slips': bet_slips,
    }
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_result(result)

if __name__ == '__main__':
    main()
