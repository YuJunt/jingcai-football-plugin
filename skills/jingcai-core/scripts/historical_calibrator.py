#!/usr/bin/env python3
"""
历史数据校准模块
用85454场历史数据校准各玩法的实际概率分布，替代模型概率
解决低概率选项EV异常偏高的问题

用法：
  python3 historical_calibrator.py --calibrate
  python3 historical_calibrator.py --play 比分 --lambda-home 1.5 --lambda-away 1.0
"""
import argparse
import json
import math
import os
import glob
from collections import defaultdict

# 历史数据目录
# 脚本路径: jingcai-football-plugin/skills/jingcai-core/scripts/historical_calibrator.py
# 4层dirname = jingcai-football-plugin/
HISTORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'data', 'history')

# 校准结果缓存
_calibration_cache = {}

def load_all_history():
    """加载所有历史数据"""
    if 'all_data' in _calibration_cache:
        return _calibration_cache['all_data']
    
    all_data = []
    for f in glob.glob(os.path.join(HISTORY_DIR, '*.json')):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
                all_data.extend(data)
        except:
            pass
    
    _calibration_cache['all_data'] = all_data
    return all_data

def calibrate_total_goals(lambda_total):
    """
    校准总进球概率分布
    用历史数据的实际进球分布校准泊松模型
    Returns: list - 0到7+球的校准后概率
    """
    cache_key = f'tg_{lambda_total:.2f}'
    if cache_key in _calibration_cache:
        return _calibration_cache[cache_key]
    
    all_data = load_all_history()
    
    # 计算历史实际进球分布
    actual_dist = [0] * 8  # 0-7+球
    total_matches = 0
    for match in all_data:
        hg = match.get('home_goals', -1)
        ag = match.get('away_goals', -1)
        if hg >= 0 and ag >= 0:
            total = hg + ag
            idx = min(total, 7)
            actual_dist[idx] += 1
            total_matches += 1
    
    if total_matches == 0:
        return [0.125] * 8
    
    # 归一化
    actual_dist = [p / total_matches for p in actual_dist]
    
    # 泊松模型概率
    poisson_dist = []
    for k in range(7):
        p = (lambda_total ** k) * math.exp(-lambda_total) / math.factorial(k)
        poisson_dist.append(p)
    poisson_dist.append(max(0, 1 - sum(poisson_dist)))
    
    # 校准：泊松概率 × (实际概率/泊松概率) 的加权平均
    # 权重：增加收缩力度到50%，因为竞彩赔率抽水重，模型概率容易高估
    calibrated = []
    for i in range(8):
        if poisson_dist[i] > 0.001:
            # 贝叶斯收缩：向实际分布收缩50%
            shrinkage = 0.5
            cal_p = poisson_dist[i] * (1 - shrinkage) + actual_dist[i] * shrinkage
        else:
            cal_p = actual_dist[i] * 0.5
        # 对低概率选项（<10%）额外惩罚，因为模型容易高估低概率事件
        if cal_p < 0.10:
            cal_p *= 0.7
        calibrated.append(cal_p)
    
    # 重新归一化
    total = sum(calibrated)
    if total > 0:
        calibrated = [p / total for p in calibrated]
    
    _calibration_cache[cache_key] = calibrated
    return calibrated

def calibrate_score_matrix(lambda_home, lambda_away):
    """
    校准比分概率矩阵
    用历史数据的实际比分分布校准泊松模型，加入Dixon-Coles修正
    Returns: dict - {score: probability}
    """
    cache_key = f'score_{lambda_home:.2f}_{lambda_away:.2f}'
    if cache_key in _calibration_cache:
        return _calibration_cache[cache_key]
    
    all_data = load_all_history()
    
    # 计算历史实际比分分布
    actual_scores = defaultdict(int)
    total_matches = 0
    for match in all_data:
        hg = match.get('home_goals', -1)
        ag = match.get('away_goals', -1)
        if hg >= 0 and ag >= 0 and hg <= 6 and ag <= 6:
            score = f'{hg}:{ag}'
            actual_scores[score] += 1
            total_matches += 1
    
    # 泊松模型比分矩阵
    poisson_scores = {}
    for h in range(7):
        for a in range(7):
            p_h = (lambda_home ** h) * math.exp(-lambda_home) / math.factorial(h)
            p_a = (lambda_away ** a) * math.exp(-lambda_away) / math.factorial(a)
            score = f'{h}:{a}'
            poisson_scores[score] = p_h * p_a
    
    # Dixon-Coles修正（rho=-0.13）
    # 对低比分（0:0, 1:0, 0:1, 1:1）进行修正
    rho = -0.13
    dc_correction = {
        '0:0': 1 - rho * lambda_home * lambda_away,
        '1:0': 1 + rho * lambda_away,
        '0:1': 1 + rho * lambda_home,
        '1:1': 1 - rho,
    }
    
    dc_scores = {}
    for score, p in poisson_scores.items():
        if score in dc_correction:
            dc_scores[score] = p * dc_correction[score]
        else:
            dc_scores[score] = p
    
    # 归一化Dixon-Coles
    total_dc = sum(dc_scores.values())
    if total_dc > 0:
        dc_scores = {k: v / total_dc for k, v in dc_scores.items()}
    
    # 校准：Dixon-Coles概率50% + 实际概率50%（比分模型不确定性高）
    calibrated = {}
    for score in dc_scores.keys():
        actual_p = actual_scores.get(score, 0) / total_matches if total_matches > 0 else 0
        dc_p = dc_scores.get(score, 0)
        # 贝叶斯收缩，50%收缩到实际分布
        shrinkage = 0.5
        cal_p = dc_p * (1 - shrinkage) + actual_p * shrinkage
        # 对低概率选项（<3%）额外惩罚
        if cal_p < 0.03:
            cal_p *= 0.6
        calibrated[score] = cal_p
    
    # 重新归一化
    total = sum(calibrated.values())
    if total > 0:
        calibrated = {k: v / total for k, v in calibrated.items()}
    
    _calibration_cache[cache_key] = calibrated
    return calibrated

def calibrate_banquanchang(lambda_home, lambda_away):
    """
    校准半全场概率分布
    用历史数据的实际半场/全场结果分布校准模型
    Returns: dict - {option: probability}，9个选项
    """
    cache_key = f'bqc_{lambda_home:.2f}_{lambda_away:.2f}'
    if cache_key in _calibration_cache:
        return _calibration_cache[cache_key]
    
    all_data = load_all_history()
    
    # 计算历史实际半全场分布
    actual_bqc = defaultdict(int)
    total_matches = 0
    for match in all_data:
        hthg = match.get('hthg', -1)  # 半场主队进球
        htag = match.get('htag', -1)  # 半场客队进球
        hg = match.get('home_goals', -1)
        ag = match.get('away_goals', -1)
        
        if hthg >= 0 and htag >= 0 and hg >= 0 and ag >= 0:
            # 半场结果
            if hthg > htag:
                ht = '胜'
            elif hthg == htag:
                ht = '平'
            else:
                ht = '负'
            
            # 全场结果
            if hg > ag:
                ft = '胜'
            elif hg == ag:
                ft = '平'
            else:
                ft = '负'
            
            option = ht + ft
            actual_bqc[option] += 1
            total_matches += 1
    
    if total_matches == 0:
        return {'胜胜': 0.25, '胜平': 0.05, '胜负': 0.02, '平胜': 0.15, '平平': 0.20, '平负': 0.08, '负胜': 0.02, '负平': 0.05, '负负': 0.18}
    
    # 归一化实际分布
    actual_dist = {k: v / total_matches for k, v in actual_bqc.items()}
    
    # 模型概率（简化版条件概率法）
    lambda_home_half = lambda_home * 0.45
    lambda_away_half = lambda_away * 0.45
    
    def calc_1x2(lh, la, max_goals=5):
        p_h = p_d = p_a = 0
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                p = ((lh ** h) * math.exp(-lh) / math.factorial(h)) * \
                    ((la ** a) * math.exp(-la) / math.factorial(a))
                if h > a: p_h += p
                elif h == a: p_d += p
                else: p_a += p
        return [p_h, p_d, p_a]
    
    half_probs = calc_1x2(lambda_home_half, lambda_away_half)
    full_probs = calc_1x2(lambda_home, lambda_away)
    
    # 简化映射
    model_dist = {
        '胜胜': half_probs[0] * full_probs[0] / (full_probs[0] + full_probs[1]) if (full_probs[0] + full_probs[1]) > 0 else 0,
        '胜平': half_probs[0] * full_probs[1] / (full_probs[0] + full_probs[1]) if (full_probs[0] + full_probs[1]) > 0 else 0,
        '胜负': half_probs[0] * full_probs[2] * 0.6,  # 逆转修正
        '平胜': half_probs[1] * full_probs[0],
        '平平': half_probs[1] * full_probs[1],
        '平负': half_probs[1] * full_probs[2],
        '负胜': half_probs[2] * full_probs[0] * 0.6,  # 逆转修正
        '负平': half_probs[2] * full_probs[1] / (full_probs[1] + full_probs[2]) if (full_probs[1] + full_probs[2]) > 0 else 0,
        '负负': half_probs[2] * full_probs[2] / (full_probs[1] + full_probs[2]) if (full_probs[1] + full_probs[2]) > 0 else 0,
    }
    
    # 归一化模型分布
    total_model = sum(model_dist.values())
    if total_model > 0:
        model_dist = {k: v / total_model for k, v in model_dist.items()}
    
    # 校准：模型概率40% + 实际概率60%（半全场模型不确定性最高，实际权重更大）
    calibrated = {}
    all_options = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
    for option in all_options:
        model_p = model_dist.get(option, 0)
        actual_p = actual_dist.get(option, 0)
        shrinkage = 0.6  # 60%收缩到实际分布
        cal_p = model_p * (1 - shrinkage) + actual_p * shrinkage
        # 对逆转选项（胜负/负胜）额外惩罚，因为模型高估逆转概率
        if option in ['胜负', '负胜']:
            cal_p *= 0.5
        # 对低概率选项（<3%）额外惩罚
        if cal_p < 0.03:
            cal_p *= 0.7
        calibrated[option] = cal_p
    
    # 重新归一化
    total = sum(calibrated.values())
    if total > 0:
        calibrated = {k: v / total for k, v in calibrated.items()}
    
    _calibration_cache[cache_key] = calibrated
    return calibrated

def get_calibration_stats():
    """获取校准统计信息"""
    all_data = load_all_history()
    
    # 总进球分布
    tg_dist = [0] * 8
    # 比分分布（Top10）
    score_dist = defaultdict(int)
    # 半全场分布
    bqc_dist = defaultdict(int)
    
    total = 0
    for match in all_data:
        hg = match.get('home_goals', -1)
        ag = match.get('away_goals', -1)
        if hg < 0 or ag < 0:
            continue
        
        total += 1
        tg = min(hg + ag, 7)
        tg_dist[tg] += 1
        
        if hg <= 5 and ag <= 5:
            score_dist[f'{hg}:{ag}'] += 1
        
        hthg = match.get('hthg', -1)
        htag = match.get('htag', -1)
        if hthg >= 0 and htag >= 0:
            ht = '胜' if hthg > htag else ('平' if hthg == htag else '负')
            ft = '胜' if hg > ag else ('平' if hg == ag else '负')
            bqc_dist[ht + ft] += 1
    
    return {
        'total_matches': total,
        'total_goals_dist': {f'{i}球': round(tg_dist[i] / total * 100, 1) for i in range(8)},
        'top_scores': sorted(score_dist.items(), key=lambda x: x[1], reverse=True)[:10],
        'banquanchang_dist': {k: round(v / total * 100, 1) for k, v in sorted(bqc_dist.items())},
    }

def main():
    parser = argparse.ArgumentParser(description='历史数据校准模块')
    parser.add_argument('--calibrate', action='store_true', help='执行校准并输出统计')
    parser.add_argument('--play', choices=['总进球', '比分', '半全场'], help='指定玩法校准')
    parser.add_argument('--lambda-home', type=float, default=1.5, help='主队预期进球')
    parser.add_argument('--lambda-away', type=float, default=1.0, help='客队预期进球')
    args = parser.parse_args()
    
    if args.calibrate:
        print("=" * 60)
        print("历史数据校准统计")
        print("=" * 60)
        stats = get_calibration_stats()
        print(f"\n总比赛场数: {stats['total_matches']}")
        
        print(f"\n总进球实际分布:")
        for goals, pct in stats['total_goals_dist'].items():
            print(f"  {goals}: {pct}%")
        
        print(f"\n最常见比分Top10:")
        for score, count in stats['top_scores']:
            print(f"  {score}: {count}场 ({count/stats['total_matches']*100:.1f}%)")
        
        print(f"\n半全场实际分布:")
        for option, pct in stats['banquanchang_dist'].items():
            print(f"  {option}: {pct}%")
        
        print("\n" + "=" * 60)
    
    elif args.play:
        lambda_total = args.lambda_home + args.lambda_away
        
        if args.play == '总进球':
            probs = calibrate_total_goals(lambda_total)
            print(f"总进球校准概率 (λ_total={lambda_total:.2f}):")
            for i, p in enumerate(probs):
                label = f'{i}球' if i < 7 else '7+球'
                print(f"  {label}: {p*100:.1f}%")
        
        elif args.play == '比分':
            scores = calibrate_score_matrix(args.lambda_home, args.lambda_away)
            print(f"比分校准概率 (λ_home={args.lambda_home:.2f}, λ_away={args.lambda_away:.2f}):")
            top_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
            for score, p in top_scores:
                print(f"  {score}: {p*100:.1f}%")
        
        elif args.play == '半全场':
            bqc = calibrate_banquanchang(args.lambda_home, args.lambda_away)
            print(f"半全场校准概率 (λ_home={args.lambda_home:.2f}, λ_away={args.lambda_away:.2f}):")
            for option, p in sorted(bqc.items(), key=lambda x: x[1], reverse=True):
                print(f"  {option}: {p*100:.1f}%")

if __name__ == '__main__':
    main()
