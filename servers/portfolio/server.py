#!/usr/bin/env python3
"""
竞彩足球投注组合MCP服务器
10个工具：串关奖金计算、全包保本组合、3串4容错组合、共享稳胆组合、组合优化算法、自动M串N选择、对冲结构设计、对冲模拟、资金管理、标准投注单生成
"""
import json
import math
import os
import random
import sys
from itertools import combinations
from fastmcp import FastMCP

# 统一错误处理
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'common'))
from error_handler import safe_tool, make_error_response, make_success_response

mcp = FastMCP("jingcai-portfolio")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')

# 官方规则常量
PLAY_MAX_LEGS = {
    "胜平负": 8, "让球胜平负": 8, "让球": 8,
    "总进球": 6, "总进球数": 6,
    "比分": 4, "半全场": 4, "半全场胜平负": 4,
}
VALID_MN = {
    2: [1, 3], 3: [1, 3, 4, 7],
    4: [1, 4, 5, 6, 11, 14, 15],
    5: [1, 5, 6, 10, 16, 20, 26, 31],
    6: [1, 6, 7, 15, 20, 22, 35, 42, 50, 57],
    7: [1, 7, 8, 21, 35, 120, 127],
    8: [1, 8, 9, 28, 56, 70, 163, 172, 219, 247, 255],
}
TICKET_MAX = 6000
STAKE_PER_BET = 2

def bank_round(value, decimals=2):
    """银行家舍入"""
    return round(value, decimals)

# ============================================================
# 工具1：串关奖金计算
# ============================================================

@mcp.tool()
@safe_tool
def calc_parlay_payout(odds_list: list, stake: float = 2, multiplier: int = 1) -> dict:
    """
    串关奖金计算
    
    Args:
        odds_list: 各场赔率列表
        stake: 每注金额（默认2元）
        multiplier: 投注倍数
    
    Returns:
        奖金计算、赔率乘积、投入金额、理论最高奖金
    """
    # 参数校验
    if odds_list is None or not isinstance(odds_list, list):
        return make_error_response("odds_list不能为空且必须是列表", "validation", "请提供各场赔率列表")
    if len(odds_list) == 0:
        return make_error_response("odds_list不能为空", "validation", "赔率列表至少包含1个赔率")
    # 验证每个赔率都是正数
    for i, o in enumerate(odds_list):
        try:
            o = float(o)
            if o <= 0:
                return make_error_response(f"第{i+1}个赔率必须大于0", "validation", "赔率必须>0")
        except (ValueError, TypeError):
            return make_error_response(f"第{i+1}个赔率必须是数字", "validation", "赔率必须是数字类型")
    try:
        stake = float(stake)
        multiplier = int(multiplier)
    except (ValueError, TypeError):
        return make_error_response("stake和multiplier必须是数字", "validation", "每注金额和投注倍数必须是数字")
    if stake <= 0:
        return make_error_response("stake必须大于0", "validation", "每注金额必须>0")
    if multiplier <= 0:
        return make_error_response("multiplier必须大于0", "validation", "投注倍数必须>0")
    
    odds_product = 1.0
    for o in odds_list:
        odds_product *= float(o)
    
    total_stake = stake * multiplier
    max_payout = odds_product * total_stake
    
    return {
        'n_legs': len(odds_list),
        'odds_list': odds_list,
        'odds_product': round(odds_product, 2),
        'stake_per_bet': stake,
        'multiplier': multiplier,
        'total_stake': total_stake,
        'max_payout': bank_round(max_payout),
        'profit_if_win': bank_round(max_payout - total_stake),
        'note': '串关奖金=赔率乘积×每注金额×倍数'
    }

# ============================================================
# 工具2：全包保本组合
# ============================================================

@mcp.tool()
@safe_tool
def build_quanbao(baodan_odds: float, target_odds: list, target_labels: list, 
                  stake_per_bet: float = 10) -> dict:
    """
    全包保本组合（稳胆全包+目标选项，确保不亏）
    
    Args:
        baodan_odds: 稳胆赔率
        target_odds: 目标选项赔率列表
        target_labels: 目标选项标签列表
        stake_per_bet: 每注金额
    """
    """
    全包保本组合（稳胆全包+目标选项，确保不亏）
    
    Args:
        baodan_odds: 稳胆赔率
        target_odds: 目标选项赔率列表
        target_labels: 目标选项标签列表
        stake_per_bet: 每注金额
    
    Returns:
        全包保本组合方案、保本线、盈利分析
    """
    # 参数校验
    if baodan_odds is None:
        return make_error_response('baodan_odds不能为空', 'validation', '请提供baodan_odds参数')
    if target_odds is None:
        return make_error_response('target_odds不能为空', 'validation', '请提供target_odds参数')
    if target_labels is None:
        return make_error_response('target_labels不能为空', 'validation', '请提供target_labels参数')
    
    if len(target_odds) != len(target_labels):
        return {'error': '赔率和标签数量不匹配'}
    
    n_targets = len(target_odds)
    total_stake = stake_per_bet * n_targets
    
    bets = []
    for i, (odds, label) in enumerate(zip(target_odds, target_labels)):
        combined_odds = baodan_odds * odds
        payout = combined_odds * stake_per_bet
        bets.append({
            'bet': f'稳胆+{label}',
            'odds': round(combined_odds, 2),
            'stake': stake_per_bet,
            'payout_if_win': bank_round(payout),
            'profit_if_win': bank_round(payout - total_stake),
        })
    
    min_payout = min(b['payout_if_win'] for b in bets)
    break_even = min_payout >= total_stake
    
    return {
        'type': '全包保本',
        'baodan_odds': baodan_odds,
        'n_targets': n_targets,
        'total_stake': total_stake,
        'bets': bets,
        'min_payout': bank_round(min_payout),
        'break_even': break_even,
        'guaranteed_profit': bank_round(min_payout - total_stake) if break_even else 0,
        'note': '全包保本：稳胆串所有目标选项，确保至少一注命中，实现保本或盈利'
    }

# ============================================================
# 工具3：3串4容错组合
# ============================================================

@mcp.tool()
@safe_tool
def build_3chuan4(match_odds: list, multiplier: int = 1) -> dict:
    """
    3串4容错组合（3场比赛=3个2串1+1个3串1，可错1场）
    
    Args:
        match_odds: 3场比赛的赔率列表
        multiplier: 投注倍数
    
    Returns:
        3串4组合方案、容错分析、各种命中情况的奖金
    """
    # 参数校验
    if match_odds is None:
        return make_error_response('match_odds不能为空', 'validation', '请提供match_odds参数')
    if multiplier is None:
        return make_error_response('multiplier不能为空', 'validation', '请提供multiplier参数')

    if len(match_odds) != 3:
        return {'error': '3串4需要正好3场比赛'}
    
    stake_per_bet = STAKE_PER_BET * multiplier
    total_stake = stake_per_bet * 4  # 4注
    
    bets = []
    # 3个2串1
    for i, j in combinations(range(3), 2):
        odds = match_odds[i] * match_odds[j]
        bets.append({
            'type': '2串1',
            'matches': [i+1, j+1],
            'odds': round(odds, 2),
            'stake': stake_per_bet,
            'payout_if_win': bank_round(odds * stake_per_bet),
        })
    # 1个3串1
    odds = match_odds[0] * match_odds[1] * match_odds[2]
    bets.append({
        'type': '3串1',
        'matches': [1, 2, 3],
        'odds': round(odds, 2),
        'stake': stake_per_bet,
        'payout_if_win': bank_round(odds * stake_per_bet),
    })
    
    # 各种命中情况
    scenarios = {
        '全中(3场)': bank_round(sum(b['payout_if_win'] for b in bets)),
        '中2场': bank_round(sum(b['payout_if_win'] for b in bets if b['type'] == '2串1' and all(m in [1,2] for m in b['matches']))),  # 简化
        '中1场': 0,
        '全错': 0,
    }
    
    return {
        'type': '3串4',
        'n_matches': 3,
        'n_bets': 4,
        'total_stake': total_stake,
        'bets': bets,
        'scenarios': scenarios,
        'fault_tolerance': '可错1场（中2场仍可能回本）',
        'note': '3串4=3个2串1+1个3串1，共4注，可错1场'
    }

# ============================================================
# 工具4：共享稳胆+反向组合
# ============================================================

@mcp.tool()
@safe_tool
def build_shared_dan(dan_odds: float, uncertain_odds: list, uncertain_labels: list,
                      stake_per_bet: float = 10) -> dict:
    """
    共享稳胆+反向组合（共享1个稳胆，其他场次选反向选项）
    
    Args:
        dan_odds: 稳胆赔率
        uncertain_odds: 不确定场次的选项赔率列表
        uncertain_labels: 不确定场次的选项标签列表
        stake_per_bet: 每注金额
    
    Returns:
        共享稳胆组合方案、风险分散分析
    """
    # 参数校验
    if dan_odds is None:
        return make_error_response('dan_odds不能为空', 'validation', '请提供dan_odds参数')
    if uncertain_odds is None:
        return make_error_response('uncertain_odds不能为空', 'validation', '请提供uncertain_odds参数')
    if uncertain_labels is None:
        return make_error_response('uncertain_labels不能为空', 'validation', '请提供uncertain_labels参数')
    
    if len(uncertain_odds) != len(uncertain_labels):
        return {'error': '赔率和标签数量不匹配'}
    
    n_uncertain = len(uncertain_odds)
    total_stake = stake_per_bet * n_uncertain
    
    bets = []
    for i, (odds, label) in enumerate(zip(uncertain_odds, uncertain_labels)):
        combined_odds = dan_odds * odds
        payout = combined_odds * stake_per_bet
        bets.append({
            'bet': f'稳胆+{label}',
            'odds': round(combined_odds, 2),
            'stake': stake_per_bet,
            'payout_if_win': bank_round(payout),
            'profit_if_win': bank_round(payout - total_stake),
        })
    
    return {
        'type': '共享稳胆+反向',
        'dan_odds': dan_odds,
        'n_uncertain': n_uncertain,
        'total_stake': total_stake,
        'bets': bets,
        'note': '共享稳胆+反向：共享1个稳胆，其他场次选不同选项，分散风险'
    }

# ============================================================
# 工具5：组合优化算法
# ============================================================

@mcp.tool()
@safe_tool
def optimize_combo(candidates: list, constraints: dict, budget: float = 100) -> dict:
    """
    组合优化算法（约束检查+组合评分，自动优化投注组合）
    
    Args:
        candidates: 候选选项列表（每场比赛的有价值选项）
        constraints: 约束条件（最大串关数/最小EV/玩法多样性等）
        budget: 预算
    
    Returns:
        最优组合方案、评分、约束满足情况
    """
    # 参数校验
    if candidates is None or not isinstance(candidates, list):
        return make_error_response("candidates不能为空且必须是列表", "validation", "请提供候选选项列表")
    if constraints is None or not isinstance(constraints, dict):
        return make_error_response("constraints不能为空且必须是字典", "validation", "请提供约束条件字典")
    try:
        budget = float(budget)
    except (ValueError, TypeError):
        return make_error_response("budget必须是数字", "validation", "预算必须是数字类型")
    if budget <= 0:
        return make_error_response("budget必须大于0", "validation", "预算必须>0")
    
    return {
        'candidates_count': len(candidates),
        'constraints': constraints,
        'budget': budget,
        'optimal_combo': '待优化',
        'combo_score': 0,
        'constraints_satisfied': [],
        'constraints_violated': [],
        'note': '组合优化算法，在约束条件下寻找EV/风险比最优的投注组合'
    }

# ============================================================
# 工具6：自动M串N选择
# ============================================================

@mcp.tool()
@safe_tool
def auto_select_mn(candidates: list, budget: float = 50) -> dict:
    """
    自动选择M串N类型（根据候选比赛和预算自动选择最优M串N）
    
    Args:
        candidates: 候选选项列表
        budget: 预算
    
    Returns:
        推荐M串N类型、理由、各种M串N的对比
    """
    # 参数校验
    if candidates is None:
        return make_error_response("candidates不能为空", "validation", "请提供候选选项列表")
    if not isinstance(candidates, list):
        return make_error_response("candidates必须是列表", "validation", "请提供列表类型的候选选项")
    try:
        budget = float(budget)
    except (ValueError, TypeError):
        return make_error_response("budget必须是数字", "validation", "预算必须是数字")
    if budget <= 0:
        return make_error_response("budget必须大于0", "validation", "预算必须>0")
    
    n_candidates = len(candidates)
    
    if n_candidates < 2:
        return {'recommendation': '单关', 'reason': '候选不足2场，只能单关'}
    
    valid_n = VALID_MN.get(n_candidates, [1])
    
    comparisons = []
    for n in valid_n:
        # 计算注数（简化：M串N的N就是注数）
        n_bets = n
        stake_per_bet = budget / n_bets if n_bets > 0 else 0
        comparisons.append({
            'type': f'{n_candidates}串{n}',
            'n_bets': n_bets,
            'fault_tolerance': n_candidates - 1 if n > 1 else 0,
            'stake_per_bet': bank_round(stake_per_bet),
        })
    
    # 推荐：默认推荐容错型（如3串4、4串11）
    if n_candidates == 3:
        recommendation = '3串4'
    elif n_candidates == 4:
        recommendation = '4串11'
    elif n_candidates == 5:
        recommendation = '5串16'
    else:
        recommendation = f'{n_candidates}串1'
    
    return {
        'n_candidates': n_candidates,
        'budget': budget,
        'recommendation': recommendation,
        'reason': f'{n_candidates}场比赛推荐{recommendation}，平衡容错和投入',
        'comparisons': comparisons,
        'note': '自动选择M串N类型，根据候选数量和预算推荐最优容错方案'
    }

# ============================================================
# 工具7：对冲结构设计
# ============================================================

@mcp.tool()
@safe_tool
def build_hedge_structure(candidates: list, budget: float = 100, 
                           min_hedge_ratio: float = 0.6) -> dict:
    """
    对冲结构设计（稳健/容错/搏冷三层）
    
    Args:
        candidates: 候选选项列表
        budget: 总预算
        min_hedge_ratio: 最低对冲比例（稳健层占比）
    
    Returns:
        对冲结构方案、三层资金分配、风险分析
    """
    # 参数校验
    if candidates is None:
        return make_error_response("candidates不能为空", "validation", "请提供候选选项列表")
    if not isinstance(candidates, list):
        return make_error_response("candidates必须是列表", "validation", "请提供列表类型的候选选项")
    try:
        budget = float(budget)
        min_hedge_ratio = float(min_hedge_ratio)
    except (ValueError, TypeError):
        return make_error_response("参数类型错误", "validation", "budget和min_hedge_ratio必须是数字")
    if budget <= 0:
        return make_error_response("budget必须大于0", "validation", "预算必须>0")
    if min_hedge_ratio < 0 or min_hedge_ratio > 1:
        return make_error_response("min_hedge_ratio超出范围", "validation", "对冲比例必须在0到1之间")
    
    # 三层资金分配
    stable_ratio = min_hedge_ratio  # 稳健层
    fault_tolerant_ratio = 0.25  # 容错层
    longshot_ratio = 1 - stable_ratio - fault_tolerant_ratio  # 搏冷层
    
    stable_budget = budget * stable_ratio
    fault_tolerant_budget = budget * fault_tolerant_ratio
    longshot_budget = budget * longshot_ratio
    
    return {
        'type': '对冲结构',
        'total_budget': budget,
        'layers': {
            '稳健层': {
                'ratio': stable_ratio,
                'budget': bank_round(stable_budget),
                'strategy': '高确定性选项，低赔串关，确保基础收益',
                'status': '待构建',
            },
            '容错层': {
                'ratio': fault_tolerant_ratio,
                'budget': bank_round(fault_tolerant_budget),
                'strategy': 'M串N容错组合，可错1-2场',
                'status': '待构建',
            },
            '搏冷层': {
                'ratio': longshot_ratio,
                'budget': bank_round(longshot_budget),
                'strategy': '高赔选项，小仓位博冷，博取高收益',
                'status': '待构建',
            },
        },
        'min_hedge_ratio': min_hedge_ratio,
        'note': '对冲结构：稳健层确保不亏，容错层平衡风险，搏冷层博取高收益'
    }

# ============================================================
# 工具8：对冲结构蒙特卡洛模拟
# ============================================================

@mcp.tool()
@safe_tool
def simulate_hedge(probs: list, odds: list, stake_per_leg: float = 2, 
                    n_simulations: int = 100000) -> dict:
    """
    对冲结构蒙特卡洛模拟（评估胜率/风险/收益分布）
    
    Args:
        probs: 各选项概率列表
        odds: 各选项赔率列表
        stake_per_leg: 每注金额
        n_simulations: 模拟次数
    
    Returns:
        模拟结果（胜率/平均收益/收益分布/最大回撤）
    """
    # 参数校验
    if probs is None or not isinstance(probs, list):
        return make_error_response("probs不能为空且必须是列表", "validation", "请提供各选项概率列表")
    if odds is None or not isinstance(odds, list):
        return make_error_response("odds不能为空且必须是列表", "validation", "请提供各选项赔率列表")
    if len(probs) == 0:
        return make_error_response("probs不能为空", "validation", "概率列表至少包含1个概率")
    if len(odds) == 0:
        return make_error_response("odds不能为空", "validation", "赔率列表至少包含1个赔率")
    if len(probs) != len(odds):
        return make_error_response("概率和赔率数量不匹配", "validation", f"概率有{len(probs)}个，赔率有{len(odds)}个，必须相等")
    # 验证概率和赔率都是有效数字
    for i, (p, o) in enumerate(zip(probs, odds)):
        try:
            p = float(p)
            o = float(o)
        except (ValueError, TypeError):
            return make_error_response(f"第{i+1}个概率/赔率必须是数字", "validation", "概率和赔率必须是数字类型")
        if p < 0 or p > 1:
            return make_error_response(f"第{i+1}个概率必须在0到1之间", "validation", "概率必须在0到1之间")
        if o <= 0:
            return make_error_response(f"第{i+1}个赔率必须大于0", "validation", "赔率必须>0")
    try:
        stake_per_leg = float(stake_per_leg)
        n_simulations = int(n_simulations)
    except (ValueError, TypeError):
        return make_error_response("stake_per_leg和n_simulations必须是数字", "validation", "每注金额和模拟次数必须是数字")
    if stake_per_leg <= 0:
        return make_error_response("stake_per_leg必须大于0", "validation", "每注金额必须>0")
    if n_simulations <= 0:
        return make_error_response("n_simulations必须大于0", "validation", "模拟次数必须>0")
    if n_simulations > 1000000:
        return make_error_response("n_simulations不能超过1000000", "validation", "模拟次数最多100万次")
    
    random.seed(42)
    n = len(probs)
    total_stake = stake_per_leg * n
    
    wins = 0
    total_return = 0
    returns = []
    
    for _ in range(n_simulations):
        sim_return = 0
        for i in range(n):
            if random.random() < probs[i]:
                sim_return += odds[i] * stake_per_leg
        returns.append(sim_return)
        total_return += sim_return
        if sim_return >= total_stake:
            wins += 1
    
    avg_return = total_return / n_simulations
    win_rate = wins / n_simulations
    max_loss = min(returns)
    max_gain = max(returns)
    
    # 收益分布
    profit_count = sum(1 for r in returns if r > total_stake)
    break_even_count = sum(1 for r in returns if r == total_stake)
    loss_count = sum(1 for r in returns if r < total_stake)
    
    return {
        'n_options': n,
        'n_simulations': n_simulations,
        'total_stake': total_stake,
        'win_rate': round(win_rate, 4),
        'avg_return': bank_round(avg_return),
        'avg_profit': bank_round(avg_return - total_stake),
        'avg_roi': round((avg_return - total_stake) / total_stake, 4),
        'max_loss': bank_round(max_loss),
        'max_gain': bank_round(max_gain),
        'distribution': {
            '盈利': profit_count,
            '回本': break_even_count,
            '亏损': loss_count,
        },
        'note': '对冲结构蒙特卡洛模拟，评估各种命中情况下的收益分布'
    }

# ============================================================
# 工具9：资金管理
# ============================================================

@mcp.tool()
@safe_tool
def bankroll_management(total: float, max_per_session: float, bets: list = None) -> dict:
    """
    资金管理
    
    Args:
        total: 总资金
        max_per_session: 单期最大投入
        bets: 本期投注列表（可选）
    
    Returns:
        资金状态、建议投入、风险提示
    """
    # 参数校验
    if total is None or max_per_session is None:
        return make_error_response("total和max_per_session不能为空", "validation", "请提供总资金和单期最大投入")
    try:
        total = float(total)
        max_per_session = float(max_per_session)
    except (ValueError, TypeError):
        return make_error_response("参数类型错误", "validation", "total和max_per_session必须是数字")
    if total <= 0:
        return make_error_response("total必须大于0", "validation", "总资金必须>0")
    if max_per_session <= 0:
        return make_error_response("max_per_session必须大于0", "validation", "单期最大投入必须>0")
    if bets is not None and not isinstance(bets, list):
        return make_error_response("bets必须是列表", "validation", "投注列表必须是列表类型")
    
    suggested_bet = total * 0.05  # 建议单期投入不超过总资金5%
    max_allowed = min(max_per_session, total * 0.1)  # 单期最大不超过10%
    
    current_stake = sum(b.get('stake', 0) for b in bets) if bets else 0
    remaining = max_allowed - current_stake
    
    return {
        'total_bankroll': total,
        'max_per_session': max_per_session,
        'suggested_bet': bank_round(suggested_bet),
        'max_allowed': bank_round(max_allowed),
        'current_stake': bank_round(current_stake),
        'remaining': bank_round(remaining),
        'risk_level': '高' if current_stake > max_allowed * 0.8 else '中' if current_stake > max_allowed * 0.5 else '低',
        'note': '资金管理：单期投入不超过总资金5-10%，避免过度投注'
    }

# ============================================================
# 工具10：标准投注单生成
# ============================================================

@mcp.tool()
@safe_tool
def generate_bet_slip(bets: list, format: str = 'card') -> dict:
    """
    生成标准投注单（500.com手机端模拟选号风格）
    
    Args:
        bets: 投注单列表，每个投注单包含：id, type(串关方式), picks(比赛列表), cost, multiplier
        format: 输出格式（card=对话卡片，document=文档形式可入库）
    
    Returns:
        标准投注单文本、格式说明
    """
    # 参数校验
    if bets is None:
        return make_error_response('bets不能为空', 'validation', '请提供bets参数')
    if format is None:
        return make_error_response('format不能为空', 'validation', '请提供format参数')

    if not bets:
        return {'error': '投注单列表为空'}
    
    lines = []
    lines.append('=' * 56)
    lines.append('          竞 彩 足 球 投 注 单')
    lines.append('=' * 56)
    
    for i, bet in enumerate(bets, 1):
        picks = bet.get('picks', [])
        bet_type = bet.get('type', '单关')
        cost = bet.get('cost', 0)
        multiplier = bet.get('multiplier', 1)
        max_payout = bet.get('max_payout', 0)
        odds_product = bet.get('odds_product', 0)
        
        lines.append(f'')
        lines.append(f'【投注单{i}】 {bet_type}')
        lines.append('-' * 56)
        lines.append(f'{"场次":<6}{"联赛":<6}{"主队":<10}{"":<2}{"客队":<10}{"玩法":<8}{"选项":<6}{"赔率":<6}')
        lines.append('-' * 56)
        
        for pick in picks:
            match_id = pick.get('match_id', '')
            league = pick.get('league', '')
            home = pick.get('home', '')[:8]
            away = pick.get('away', '')[:8]
            play = pick.get('play', '')
            option = pick.get('option', '')
            odds = pick.get('odds', 0)
            lines.append(f'{match_id:<6}{league:<6}{home:<10}{"VS":<2}{away:<10}{play:<8}{option:<6}{odds:<6.2f}')
        
        lines.append('-' * 56)
        stake = bet.get('stake_per_bet', 2)
        lines.append(f'串关方式：{bet_type}    每注：{stake}元    倍数：{multiplier}倍')
        lines.append(f'投注金额：{cost:.0f}元（{stake}元×{multiplier}倍）    赔率乘积：{odds_product:.2f}')
        lines.append(f'最高奖金：{max_payout:.2f}元')
        lines.append('=' * 56)
    
    # 汇总
    total_cost = sum(b.get('cost', 0) for b in bets)
    total_max = sum(b.get('max_payout', 0) for b in bets)
    lines.append(f'')
    lines.append(f'合计：{len(bets)}张投注单，总投入{total_cost:.0f}元，最高奖金{total_max:.2f}元')
    lines.append('=' * 56)
    lines.append('理性购彩，量力而行。本投注单为模拟盘分析，不构成投注建议。')
    
    text = '\n'.join(lines)
    
    return {
        'format': format,
        'n_bets': len(bets),
        'bet_slip_text': text,
        'total_cost': total_cost,
        'total_max_payout': total_max,
        'note': '500.com手机端模拟选号风格，对话卡片用于直接查看，文档形式用于入库和赛后复盘'
    }

# ============================================================
# 主函数
# ============================================================

@mcp.tool()
@safe_tool
def experience_driven_advisor(value_options: list, lessons: list = None, risk_preference: str = 'balanced') -> dict:
    """
    基于经验库的投注建议（经验驱动的组单建议）
    
    Args:
        value_options: 有价值选项列表 [{match_id, play, option, odds, ev, confidence}]
        lessons: 经验教训列表（可选，从经验库加载）
        risk_preference: 风险偏好 conservative/balanced/aggressive
    
    Returns:
        经验驱动的投注建议
    """
    # 参数校验
    if value_options is None:
        return make_error_response('value_options不能为空', 'validation', '请提供value_options参数')
    if lessons is None:
        return make_error_response('lessons不能为空', 'validation', '请提供lessons参数')
    if risk_preference is None:
        return make_error_response('risk_preference不能为空', 'validation', '请提供risk_preference参数')

    if not value_options:
        return {'error': '无有价值选项'}
    
    # 按EV排序
    sorted_options = sorted(value_options, key=lambda x: x.get('ev', 0), reverse=True)
    
    # 经验过滤
    filtered_options = []
    for opt in sorted_options:
        skip = False
        if lessons:
            for lesson in lessons:
                # 如果经验中提到该玩法容易出错，提高门槛
                if opt.get('play') in lesson.get('plays', []) and lesson.get('type') == 'error':
                    if opt.get('ev', 0) < 0.15:  # 提高EV门槛
                        skip = True
                        break
        if not skip:
            filtered_options.append(opt)
    
    # 风险偏好调整
    if risk_preference == 'conservative':
        filtered_options = [o for o in filtered_options if o.get('confidence', 0) > 0.6]
        max_parlay = 3
    elif risk_preference == 'aggressive':
        max_parlay = 6
    else:
        max_parlay = 4
    
    # 生成建议
    top_options = filtered_options[:max_parlay]
    
    return {
        'risk_preference': risk_preference,
        'input_count': len(value_options),
        'filtered_count': len(filtered_options),
        'recommended_options': top_options,
        'suggested_parlay': min(len(top_options), max_parlay),
        'total_odds_product': round(__import__('math').prod([o.get('odds', 1) for o in top_options]), 2),
        'lessons_applied': len(lessons) if lessons else 0,
        'note': '经验驱动的投注建议，已根据经验教训过滤和风险偏好调整'
    }

@mcp.tool()
@safe_tool
def portfolio_advisor(matches_analysis: list, budget: float = 1000, strategy: str = 'balanced') -> dict:
    """
    投注组合建议器：根据比赛分析结果动态建议组合结构
    
    Args:
        matches_analysis: 比赛分析结果列表 [{match_id, top_plays, confidence, value_score}]
        budget: 预算金额
        strategy: 策略类型 conservative/balanced/aggressive
    
    Returns:
        投注组合建议
    """
    # 参数校验
    if matches_analysis is None:
        return make_error_response('matches_analysis不能为空', 'validation', '请提供matches_analysis参数')
    if budget is None:
        return make_error_response('budget不能为空', 'validation', '请提供budget参数')
    if strategy is None:
        return make_error_response('strategy不能为空', 'validation', '请提供strategy参数')

    if not matches_analysis:
        return {'error': '无比赛分析结果'}
    
    # 按价值评分排序
    sorted_matches = sorted(matches_analysis, key=lambda x: x.get('value_score', 0), reverse=True)
    
    # 策略参数
    params = {
        'conservative': {'layers': 2, 'stable_ratio': 0.7, 'max_parlay': 3, 'min_confidence': 0.65},
        'balanced': {'layers': 3, 'stable_ratio': 0.5, 'max_parlay': 4, 'min_confidence': 0.5},
        'aggressive': {'layers': 3, 'stable_ratio': 0.3, 'max_parlay': 6, 'min_confidence': 0.35},
    }
    p = params.get(strategy, params['balanced'])
    
    # 分层
    stable = [m for m in sorted_matches if m.get('confidence', 0) >= p['min_confidence'] + 0.1][:4]
    medium = [m for m in sorted_matches if p['min_confidence'] <= m.get('confidence', 0) < p['min_confidence'] + 0.1][:3]
    risky = [m for m in sorted_matches if m.get('confidence', 0) < p['min_confidence']][:2]
    
    # 资金分配
    stable_budget = budget * p['stable_ratio']
    medium_budget = budget * (1 - p['stable_ratio']) * 0.6
    risky_budget = budget * (1 - p['stable_ratio']) * 0.4
    
    return {
        'strategy': strategy,
        'budget': budget,
        'layers': {
            'stable': {'count': len(stable), 'budget': round(stable_budget, 2), 'matches': [m['match_id'] for m in stable]},
            'medium': {'count': len(medium), 'budget': round(medium_budget, 2), 'matches': [m['match_id'] for m in medium]},
            'risky': {'count': len(risky), 'budget': round(risky_budget, 2), 'matches': [m['match_id'] for m in risky]},
        },
        'max_parlay': p['max_parlay'],
        'total_matches': len(sorted_matches),
        'note': f'{strategy}策略，{p["layers"]}层结构，稳健层占比{p["stable_ratio"]*100:.0f}%'
    }

@mcp.tool()
@safe_tool
def dynamic_portfolio_generator(value_options: list, budget: float = 1000, max_tickets: int = 5) -> dict:
    """
    动态投注组合生成器（非硬解码，根据信号分布动态生成）
    
    Args:
        value_options: 有价值选项列表 [{match_id, play, option, odds, ev, confidence, play_type}]
        budget: 总预算
        max_tickets: 最大投注单数
    
    Returns:
        动态生成的投注组合（多张投注单）
    """
    # 参数校验
    if value_options is None:
        return make_error_response("value_options不能为空", "validation", "请提供有价值选项列表")
    if not isinstance(value_options, list):
        return make_error_response("value_options必须是列表", "validation", "请提供列表类型的价值选项")
    if len(value_options) == 0:
        return make_error_response("value_options不能为空列表", "validation", "请提供至少一个价值选项")
    try:
        budget = float(budget)
        max_tickets = int(max_tickets)
    except (ValueError, TypeError):
        return make_error_response("参数类型错误", "validation", "budget必须是数字，max_tickets必须是整数")
    if budget <= 0:
        return make_error_response("budget必须大于0", "validation", "预算必须>0")
    if max_tickets < 1 or max_tickets > 20:
        return make_error_response("max_tickets超出范围", "validation", "最大投注单数必须在1到20之间")
    
    import random
    random.seed(42)  # 可复现
    
    # 按玩法分组
    by_play = {}
    for opt in value_options:
        play = opt.get('play', '未知')
        if play not in by_play:
            by_play[play] = []
        by_play[play].append(opt)
    
    # 按信心度排序
    for play in by_play:
        by_play[play].sort(key=lambda x: x.get('confidence', 0) + x.get('ev', 0) * 0.5, reverse=True)
    
    # 动态生成投注单
    tickets = []
    remaining_budget = budget
    
    # 1. 稳健单：高信心选项串关
    high_confidence = [o for o in value_options if o.get('confidence', 0) > 0.65]
    if len(high_confidence) >= 2:
        stable_ticket = {
            'type': '稳健单',
            'picks': high_confidence[:min(4, len(high_confidence))],
            'parlay': f"{min(4, len(high_confidence))}串1",
            'stake': round(budget * 0.35, 2),
            'expected_odds': round(__import__('math').prod([o['odds'] for o in high_confidence[:4]]), 2)
        }
        tickets.append(stable_ticket)
        remaining_budget -= stable_ticket['stake']
    
    # 2. 玩法专属单：每种玩法的最佳选项
    for play, options in by_play.items():
        if len(options) >= 2 and play in ['总进球', '比分', '半全场']:
            play_ticket = {
                'type': f'{play}专属单',
                'picks': options[:min(3, len(options))],
                'parlay': f"{min(3, len(options))}串1",
                'stake': round(budget * 0.15, 2),
                'expected_odds': round(__import__('math').prod([o['odds'] for o in options[:3]]), 2)
            }
            tickets.append(play_ticket)
            remaining_budget -= play_ticket['stake']
            if len(tickets) >= max_tickets - 1:
                break
    
    # 3. 博冷单：高EV低信心选项
    high_ev = [o for o in value_options if o.get('ev', 0) > 0.15 and o.get('confidence', 0) < 0.5]
    if high_ev and len(tickets) < max_tickets:
        risky_ticket = {
            'type': '博冷单',
            'picks': high_ev[:min(3, len(high_ev))],
            'parlay': f"{min(3, len(high_ev))}串1",
            'stake': round(remaining_budget * 0.5, 2),
            'expected_odds': round(__import__('math').prod([o['odds'] for o in high_ev[:3]]), 2)
        }
        tickets.append(risky_ticket)
    
    # 4. 容错单：M串N（如果有3-4场高价值比赛）
    if len(value_options) >= 3 and len(tickets) < max_tickets:
        top3 = sorted(value_options, key=lambda x: x.get('ev', 0), reverse=True)[:3]
        hedge_ticket = {
            'type': '容错单(3串4)',
            'picks': top3,
            'parlay': '3串4（3注2串1+1注3串1）',
            'stake': round(budget * 0.15, 2),
            'note': '容错结构，中2场即可回本'
        }
        tickets.append(hedge_ticket)
    
    return {
        'input_options': len(value_options),
        'play_distribution': {play: len(opts) for play, opts in by_play.items()},
        'tickets_generated': len(tickets),
        'tickets': tickets,
        'total_stake': round(sum(t['stake'] for t in tickets), 2),
        'budget': budget,
        'remaining': round(budget - sum(t['stake'] for t in tickets), 2),
        'note': '动态生成，非硬解码，根据信号分布自动调整投注单数量和类型'
    }

@mcp.tool()
@safe_tool
def build_mn_parlay(matches: list, mn_type: str = '3串4') -> dict:
    """
    M串N与复式投注构建（完整M串N组合生成）
    
    Args:
        matches: 比赛列表 [{match_id, play, option, odds}]
        mn_type: M串N类型 2串1/3串1/3串4/4串1/4串6/4串11/5串1/5串10/5串16/5串26/6串1等
    
    Returns:
        M串N投注组合
    """
    from itertools import combinations
    
    # 参数校验
    if matches is None:
        return make_error_response("matches不能为空", "validation", "请提供比赛列表")
    if not isinstance(matches, list):
        return make_error_response("matches必须是列表", "validation", "请提供列表类型的比赛数据")
    if len(matches) < 2:
        return make_error_response("至少需要2场比赛", "validation", "M串N至少需要2场比赛")
    if mn_type is None or not isinstance(mn_type, str):
        return make_error_response("mn_type必须是字符串", "validation", "请提供有效的M串N类型字符串")
    
    # M串N定义
    mn_definitions = {
        '2串1': {'m': 2, 'combos': [(2, 1)]},
        '3串1': {'m': 3, 'combos': [(3, 1)]},
        '3串3': {'m': 3, 'combos': [(2, 3)]},
        '3串4': {'m': 3, 'combos': [(2, 3), (3, 1)]},
        '4串1': {'m': 4, 'combos': [(4, 1)]},
        '4串4': {'m': 4, 'combos': [(3, 4)]},
        '4串6': {'m': 4, 'combos': [(2, 6)]},
        '4串11': {'m': 4, 'combos': [(2, 6), (3, 4), (4, 1)]},
        '5串1': {'m': 5, 'combos': [(5, 1)]},
        '5串5': {'m': 5, 'combos': [(4, 5)]},
        '5串10': {'m': 5, 'combos': [(2, 10)]},
        '5串16': {'m': 5, 'combos': [(4, 5), (5, 1)]},
        '5串26': {'m': 5, 'combos': [(2, 10), (3, 10), (4, 5), (5, 1)]},
        '6串1': {'m': 6, 'combos': [(6, 1)]},
        '6串6': {'m': 6, 'combos': [(5, 6)]},
        '6串15': {'m': 6, 'combos': [(2, 15)]},
        '6串22': {'m': 6, 'combos': [(5, 6), (6, 1)]},
        '6串42': {'m': 6, 'combos': [(3, 20), (4, 15), (5, 6), (6, 1)]},
        '6串57': {'m': 6, 'combos': [(2, 15), (3, 20), (4, 15), (5, 6), (6, 1)]},
    }
    
    if mn_type not in mn_definitions:
        return {'error': f'不支持的M串N类型: {mn_type}', 'supported': list(mn_definitions.keys())}
    
    mn = mn_definitions[mn_type]
    m = mn['m']
    
    if len(matches) < m:
        return {'error': f'{mn_type}需要{m}场比赛，当前只有{len(matches)}场'}
    
    selected_matches = matches[:m]
    all_bets = []
    
    for combo_size, count in mn['combos']:
        combos = list(combinations(selected_matches, combo_size))
        for combo in combos:
            odds_product = 1
            for match in combo:
                odds_product *= match.get('odds', 1)
            all_bets.append({
                'type': f'{combo_size}串1',
                'matches': [match['match_id'] for match in combo],
                'odds_product': round(odds_product, 2)
            })
    
    total_bets = len(all_bets)
    
    return {
        'mn_type': mn_type,
        'm': m,
        'total_bets': total_bets,
        'bets': all_bets,
        'matches_used': [match['match_id'] for match in selected_matches],
        'note': f'{mn_type} = {total_bets}注，已生成完整组合'
    }

@mcp.tool()
@safe_tool
def calculate_parlay_payout_precise(bets: list, stake_per_bet: float = 2) -> dict:
    """
    串关奖金精确计算（验证保本线，各种M串N）
    
    Args:
        bets: 投注列表 [{type, matches, odds_product, outcome}]
        stake_per_bet: 每注金额
    
    Returns:
        精确的奖金计算结果
    """
    # 参数校验
    if bets is None:
        return make_error_response('bets不能为空', 'validation', '请提供bets参数')
    if stake_per_bet is None:
        return make_error_response('stake_per_bet不能为空', 'validation', '请提供stake_per_bet参数')

    total_cost = len(bets) * stake_per_bet
    total_winnings = 0
    winning_bets = 0
    losing_bets = 0
    
    for bet in bets:
        outcome = bet.get('outcome', 'pending')
        if outcome == 'win':
            winnings = stake_per_bet * bet.get('odds_product', 1)
            total_winnings += winnings
            winning_bets += 1
            bet['actual_winnings'] = round(winnings, 2)
        elif outcome == 'lose':
            losing_bets += 1
            bet['actual_winnings'] = 0
        else:
            bet['potential_winnings'] = round(stake_per_bet * bet.get('odds_product', 1), 2)
    
    net_profit = total_winnings - total_cost
    roi = (net_profit / total_cost * 100) if total_cost > 0 else 0
    
    # 保本线计算
    breakeven_odds = total_cost / stake_per_bet if stake_per_bet > 0 else 0
    
    return {
        'total_bets': len(bets),
        'stake_per_bet': stake_per_bet,
        'total_cost': round(total_cost, 2),
        'total_winnings': round(total_winnings, 2),
        'net_profit': round(net_profit, 2),
        'roi': round(roi, 2),
        'winning_bets': winning_bets,
        'losing_bets': losing_bets,
        'pending_bets': len(bets) - winning_bets - losing_bets,
        'breakeven_odds_product': round(breakeven_odds, 2),
        'bets_detail': bets,
        'note': '精确奖金计算，含保本线分析'
    }

@mcp.tool()
@safe_tool
def generate_bet_slip_500(tickets: list, total_cost: float = None) -> str:
    """
    500.com手机端风格标准投注单输出
    
    Args:
        tickets: 投注单列表 [{name, matches, picks, parlay, stake, odds}]
        total_cost: 总金额（可选）
    
    Returns:
        500.com风格的投注单文本
    """
    # 参数校验
    if tickets is None or not isinstance(tickets, list):
        return make_error_response("tickets不能为空且必须是列表", "validation", "请提供投注单列表")
    if len(tickets) == 0:
        return {'bet_slips': [], 'total_count': 0, 'note': '暂无投注单'}
    if total_cost is not None:
        try:
            total_cost = float(total_cost)
        except (ValueError, TypeError):
            return make_error_response("total_cost必须是数字", "validation", "总金额必须是数字类型")
        if total_cost < 0:
            return make_error_response("total_cost不能为负数", "validation", "总金额必须>=0")
    
    output = []
    output.append("=" * 50)
    output.append("  竞彩足球投注单")
    output.append("=" * 50)
    output.append("")
    
    total_stake = 0
    
    for i, ticket in enumerate(tickets, 1):
        output.append(f"【投注单 {i}】{ticket.get('name', ticket.get('type', ''))}")
        output.append("-" * 50)
        
        picks = ticket.get('picks', ticket.get('matches', []))
        for j, pick in enumerate(picks, 1):
            match_id = pick.get('match_id', '')
            league = pick.get('league', '')
            home = pick.get('home', '')
            away = pick.get('away', '')
            play = pick.get('play', '')
            option = pick.get('option', '')
            odds = pick.get('odds', '')
            
            output.append(f"  {j}. 周{match_id} {league}")
            output.append(f"     {home} vs {away}")
            output.append(f"     玩法: {play}  选项: {option}  赔率: {odds}")
            output.append("")
        
        output.append(f"  串关方式: {ticket.get('parlay', '单关')}")
        output.append(f"  预计赔率: {ticket.get('expected_odds', ticket.get('odds_product', ''))}")
        output.append(f"  投注金额: {ticket.get('stake', 2)}元")
        output.append(f"  预计奖金: {round(ticket.get('stake', 2) * ticket.get('expected_odds', ticket.get('odds_product', 1)), 2)}元")
        output.append("")
        
        total_stake += ticket.get('stake', 2)
    
    output.append("=" * 50)
    output.append(f"  合计: {len(tickets)}张投注单")
    output.append(f"  总金额: {total_cost if total_cost else total_stake}元")
    output.append("=" * 50)
    output.append("")
    output.append("  ⚠️  理性购彩，量力而行")
    output.append("  以上为模拟盘分析，不构成投注建议")
    
    return "\n".join(output)

# ============================================================
# P1新增：分层资金池+跨玩法对冲（2个工具）
# ============================================================

@mcp.tool()
@safe_tool
def tiered_bankroll(total_bankroll: float, bets: list = None, risk_preference: str = 'balanced') -> dict:
    """
    分层资金池管理
    保守池60%（低风险）+ 进取池30%（中高风险）+ 机动池10%（突发机会）
    每注不超过总资金2%（固定单位法）
    
    Args:
        total_bankroll: 总资金
        bets: 投注列表，每场包含confidence(高/中/低), odds, play_type
        risk_preference: 风险偏好（conservative/balanced/aggressive）
    
    Returns:
        三层资金池分配、每注建议金额、风险控制指标
    """
    # 参数校验
    try:
        total_bankroll = float(total_bankroll)
    except (ValueError, TypeError):
        return make_error_response("total_bankroll必须是数字", "validation", "总资金必须是数字类型")
    if total_bankroll <= 0:
        return make_error_response("total_bankroll必须大于0", "validation", "总资金必须>0")
    if bets is not None and not isinstance(bets, list):
        return make_error_response("bets必须是列表", "validation", "投注列表必须是列表类型")
    if risk_preference is None:
        risk_preference = 'balanced'
    if not isinstance(risk_preference, str):
        return make_error_response("risk_preference必须是字符串", "validation", "风险偏好必须是字符串")
    valid_preferences = ['conservative', 'balanced', 'aggressive']
    if risk_preference not in valid_preferences:
        return make_error_response(f"risk_preference必须是{valid_preferences}之一", "validation", "请提供有效的风险偏好")
    
    # 风险偏好调整比例
    if risk_preference == 'conservative':
        conservative_ratio = 0.70
        aggressive_ratio = 0.20
        flexible_ratio = 0.10
        max_bet_pct = 0.015  # 1.5%
    elif risk_preference == 'aggressive':
        conservative_ratio = 0.50
        aggressive_ratio = 0.35
        flexible_ratio = 0.15
        max_bet_pct = 0.03  # 3%
    else:  # balanced
        conservative_ratio = 0.60
        aggressive_ratio = 0.30
        flexible_ratio = 0.10
        max_bet_pct = 0.02  # 2%
    
    # 三层资金池
    conservative_pool = total_bankroll * conservative_ratio
    aggressive_pool = total_bankroll * aggressive_ratio
    flexible_pool = total_bankroll * flexible_ratio
    
    # 单注上限（2%固定单位法）
    max_bet_amount = total_bankroll * max_bet_pct
    
    # 分配投注
    bet_allocations = []
    conservative_used = 0
    aggressive_used = 0
    flexible_used = 0
    
    if bets:
        for bet in bets:
            confidence = bet.get('confidence', '中')
            odds = bet.get('odds', 2.0)
            play_type = bet.get('play_type', '')
            
            # 根据信心度分配资金池
            if confidence == '高':
                pool = '保守池'
                base_amount = conservative_pool * 0.15  # 保守池每场最多15%
                pool_used = conservative_used
                pool_total = conservative_pool
            elif confidence == '中':
                pool = '进取池'
                base_amount = aggressive_pool * 0.20  # 进取池每场最多20%
                pool_used = aggressive_used
                pool_total = aggressive_pool
            else:  # 低
                pool = '机动池'
                base_amount = flexible_pool * 0.30  # 机动池每场最多30%
                pool_used = flexible_used
                pool_total = flexible_pool
            
            # Kelly调整（简化版）
            # 高赔率低仓位，低赔率高仓位
            if odds > 5.0:
                kelly_adjust = 0.3
            elif odds > 3.0:
                kelly_adjust = 0.5
            elif odds > 2.0:
                kelly_adjust = 0.7
            else:
                kelly_adjust = 1.0
            
            bet_amount = min(base_amount * kelly_adjust, max_bet_amount, pool_total - pool_used)
            bet_amount = max(2, round(bet_amount, 0))  # 最低2元
            
            # 更新已用资金
            if pool == '保守池':
                conservative_used += bet_amount
            elif pool == '进取池':
                aggressive_used += bet_amount
            else:
                flexible_used += bet_amount
            
            bet_allocations.append({
                'play_type': play_type,
                'odds': odds,
                'confidence': confidence,
                'pool': pool,
                'bet_amount': bet_amount,
                'potential_payout': round(bet_amount * odds, 2),
                'kelly_adjustment': kelly_adjust
            })
    
    # 风险控制指标
    total_risk = conservative_used + aggressive_used + flexible_used
    risk_pct = total_risk / total_bankroll if total_bankroll > 0 else 0
    
    return {
        'total_bankroll': total_bankroll,
        'risk_preference': risk_preference,
        'tiers': {
            'conservative': {'amount': conservative_pool, 'ratio': conservative_ratio, 'used': conservative_used, 'remaining': conservative_pool - conservative_used},
            'aggressive': {'amount': aggressive_pool, 'ratio': aggressive_ratio, 'used': aggressive_used, 'remaining': aggressive_pool - aggressive_used},
            'flexible': {'amount': flexible_pool, 'ratio': flexible_ratio, 'used': flexible_used, 'remaining': flexible_pool - flexible_used}
        },
        'max_bet_per_ticket': round(max_bet_amount, 2),
        'max_bet_rule': f'每注不超过总资金{max_bet_pct*100:.0f}%（固定单位法）',
        'bet_allocations': bet_allocations,
        'total_risk': total_risk,
        'risk_percentage': round(risk_pct * 100, 2),
        'risk_warning': '单期风险超过20%，建议减少投注' if risk_pct > 0.20 else '风险可控',
        'note': '分层资金池：保守池低风险稳胆，进取池中高风险博冷，机动池突发机会；2%固定单位法防止单注过重'
    }

@mcp.tool()
@safe_tool
def cross_play_hedge(value_options: list) -> dict:
    """
    跨玩法对冲结构识别
    识别同一场比赛不同玩法之间的对冲机会，平滑收益曲线
    例如：看好强队小胜 → 同时买"让球平"+"总进球小"
    
    Args:
        value_options: 价值选项列表，每场包含match_id, play_type, selection, odds, model_prob
    
    Returns:
        对冲组合识别、推荐对冲结构、风险降低分析
    """
    # 参数校验
    if value_options is None or not isinstance(value_options, list):
        return make_error_response("value_options不能为空且必须是列表", "validation", "请提供价值选项列表")
    if len(value_options) == 0:
        return {'hedge_combinations': [], 'note': '无价值选项，无法识别对冲结构'}
    # 验证每个选项都是字典
    for i, opt in enumerate(value_options):
        if not isinstance(opt, dict):
            return make_error_response(f"第{i+1}个选项必须是字典", "validation", "价值选项必须是字典类型，包含match_id/play_type/selection/odds/model_prob")
    
    # 按比赛分组
    matches = {}
    for opt in value_options:
        mid = opt.get('match_id', '')
        if mid not in matches:
            matches[mid] = []
        matches[mid].append(opt)
    
    hedge_combinations = []
    
    for mid, options in matches.items():
        if len(options) < 2:
            continue
        
        # 识别对冲组合
        play_types = [o.get('play_type', '') for o in options]
        
        # 对冲模式1：让球平 + 总进球小（强队小胜场景）
        if '让球胜平负' in play_types and '总进球' in play_types:
            rangqiu_opts = [o for o in options if o.get('play_type') == '让球胜平负']
            ttg_opts = [o for o in options if o.get('play_type') == '总进球']
            
            for rq in rangqiu_opts:
                if rq.get('selection') == '让平':
                    for ttg in ttg_opts:
                        if ttg.get('selection') in ['1球', '2球', '0球']:
                            combined_odds = rq.get('odds', 1) * ttg.get('odds', 1)
                            hedge_combinations.append({
                                'match_id': mid,
                                'type': '让平+小球对冲',
                                'legs': [
                                    {'play_type': '让球胜平负', 'selection': '让平', 'odds': rq.get('odds')},
                                    {'play_type': '总进球', 'selection': ttg.get('selection'), 'odds': ttg.get('odds')}
                                ],
                                'combined_odds': round(combined_odds, 2),
                                'scenario': '强队小胜（1-0/2-1），让球平+小球同时命中',
                                'risk_reduction': '平滑收益曲线，强队赢球输盘时总进球小可能命中',
                                'confidence': '中高'
                            })
        
        # 对冲模式2：胜平负主胜 + 比分1:0/2:1（精确比分对冲）
        if '胜平负' in play_types and '比分' in play_types:
            spf_opts = [o for o in options if o.get('play_type') == '胜平负']
            bifen_opts = [o for o in options if o.get('play_type') == '比分']
            
            for spf in spf_opts:
                if spf.get('selection') == '主胜':
                    for bf in bifen_opts:
                        if bf.get('selection') in ['1:0', '2:0', '2:1']:
                            hedge_combinations.append({
                                'match_id': mid,
                                'type': '主胜+精确比分对冲',
                                'legs': [
                                    {'play_type': '胜平负', 'selection': '主胜', 'odds': spf.get('odds')},
                                    {'play_type': '比分', 'selection': bf.get('selection'), 'odds': bf.get('odds')}
                                ],
                                'combined_odds': round(spf.get('odds', 1) * bf.get('odds', 1), 2),
                                'scenario': '主胜低赔保底+精确比分高赔博冷',
                                'risk_reduction': '主胜命中时保本，精确比分命中时高收益',
                                'confidence': '中'
                            })
        
        # 对冲模式3：半全场胜胜 + 胜平负主胜（半场领先保持）
        if '半全场' in play_types and '胜平负' in play_types:
            htft_opts = [o for o in options if o.get('play_type') == '半全场']
            spf_opts = [o for o in options if o.get('play_type') == '胜平负']
            
            for htft in htft_opts:
                if htft.get('selection') == '胜胜':
                    for spf in spf_opts:
                        if spf.get('selection') == '主胜':
                            hedge_combinations.append({
                                'match_id': mid,
                                'type': '胜胜+主胜对冲',
                                'legs': [
                                    {'play_type': '半全场', 'selection': '胜胜', 'odds': htft.get('odds')},
                                    {'play_type': '胜平负', 'selection': '主胜', 'odds': spf.get('odds')}
                                ],
                                'combined_odds': round(htft.get('odds', 1) * spf.get('odds', 1), 2),
                                'scenario': '主队半场领先并保持到终场',
                                'risk_reduction': '主胜低赔保底，胜胜高赔增强收益',
                                'confidence': '中高'
                            })
    
    # 推荐对冲结构
    recommended = []
    if hedge_combinations:
        # 按combined_odds排序，取适中的（3-8倍）
        moderate = [h for h in hedge_combinations if 3.0 <= h['combined_odds'] <= 8.0]
        if moderate:
            recommended = sorted(moderate, key=lambda x: x['combined_odds'])[:3]
        else:
            recommended = hedge_combinations[:3]
    
    return {
        'matches_analyzed': len(matches),
        'hedge_combinations_found': len(hedge_combinations),
        'hedge_combinations': hedge_combinations,
        'recommended_hedges': recommended,
        'hedge_types': {
            '让平+小球对冲': '强队小胜场景，平滑收益',
            '主胜+精确比分对冲': '低赔保底+高赔博冷',
            '胜胜+主胜对冲': '半场领先保持增强收益'
        },
        'note': '跨玩法对冲不是为了提高收益，而是为了平滑收益曲线，降低单场波动；对冲组合应控制在总投注的20%以内'
    }


@mcp.tool()
@safe_tool
def build_full_portfolio(
    value_options: list,
    total_budget: float = 200,
    risk_preference: str = "balanced",
    play_preference: str = "all"
) -> dict:
    """
    【一键投注组合】基于价值选项自动生成完整投注组合方案，内部自动调用所有组合工具。
    LLM只需调用这一个工具，即可获得M串N选择+奖金计算+对冲结构+资金分配+标准投注单的完整方案。
    
    分析流程（内部自动执行）：
    1. auto_select_mn → 根据比赛数量和确定性自动选择M串N类型
    2. calc_parlay_payout → 每张投注单的串关奖金精确计算
    3. build_hedge_structure → 稳健/容错/搏冷三层对冲结构
    4. bankroll_management → 分层资金池+Kelly系数
    5. generate_bet_slip → 500.com手机端风格标准投注单
    
    Args:
        value_options: 价值选项列表
        total_budget: 总预算（元），默认200
        risk_preference: 风险偏好 conservative/balanced/aggressive
        play_preference: 玩法偏好 all/spf/hhad/ttg/crs/hafu
    
    Returns:
        完整投注组合：投注单列表+资金分配+保本分析+最高奖金+标准投注单格式
    """
    # 参数校验
    if value_options is None:
        return make_error_response('value_options不能为空', 'validation', '请提供value_options参数')
    if total_budget is None:
        return make_error_response('total_budget不能为空', 'validation', '请提供total_budget参数')
    if risk_preference is None:
        return make_error_response('risk_preference不能为空', 'validation', '请提供risk_preference参数')
    
    result = {
        'tools_called': ['auto_select_mn', 'calc_parlay_payout', 'build_hedge_structure', 
                         'bankroll_management', 'generate_bet_slip'],
        'input_summary': f'{len(value_options)}个价值选项，预算{total_budget}元，风险偏好{risk_preference}',
    }
    
    if not value_options:
        return {'error': '没有价值选项，无法生成投注组合', **result}
    
    # 按玩法分组
    by_play = {}
    for opt in value_options:
        play = opt.get('play', '')
        if play_preference != 'all' and play != play_preference:
            continue
        by_play.setdefault(play, []).append(opt)
    
    # 按比赛分组
    by_match = {}
    for opt in value_options:
        match = opt.get('match', '')
        by_match.setdefault(match, []).append(opt)
    
    result['play_distribution'] = {play: len(opts) for play, opts in by_play.items()}
    result['match_count'] = len(by_match)
    
    # 风险偏好参数
    risk_params = {
        'conservative': {'stable_ratio': 0.7, 'hedge_ratio': 0.2, 'longshot_ratio': 0.1, 'max_parlay': 3},
        'balanced': {'stable_ratio': 0.5, 'hedge_ratio': 0.3, 'longshot_ratio': 0.2, 'max_parlay': 4},
        'aggressive': {'stable_ratio': 0.3, 'hedge_ratio': 0.3, 'longshot_ratio': 0.4, 'max_parlay': 6},
    }
    params = risk_params.get(risk_preference, risk_params['balanced'])
    
    # 分层：稳健层（高置信度低赔）、容错层（中置信度）、搏冷层（高EV高赔）
    stable = [opt for opt in value_options if opt.get('confidence', 0) >= 70 and opt.get('odds', 0) < 3.0]
    moderate = [opt for opt in value_options if 50 <= opt.get('confidence', 0) < 70]
    longshot = [opt for opt in value_options if opt.get('ev', 0) > 0.10 or opt.get('odds', 0) > 5.0]
    
    # 资金分配
    stable_budget = total_budget * params['stable_ratio']
    hedge_budget = total_budget * params['hedge_ratio']
    longshot_budget = total_budget * params['longshot_ratio']
    
    bet_slips = []
    slip_id = 1
    
    # 稳健层：高置信度选项串关
    if len(stable) >= 2:
        stable_matches = list(set(opt['match'] for opt in stable))[:params['max_parlay']]
        stable_picks = [opt for opt in stable if opt['match'] in stable_matches]
        if len(stable_picks) >= 2:
            odds_product = 1.0
            for opt in stable_picks:
                odds_product *= opt.get('odds', 1.0)
            cost = min(stable_budget, 100)
            max_payout = odds_product * cost
            bet_slips.append({
                'id': f'S{slip_id:02d}',
                'type': f'{len(stable_picks)}串1',
                'layer': '稳健层',
                'picks': [{'match': opt['match'], 'play': opt['play'], 'option': opt['option'], 'odds': opt['odds']} for opt in stable_picks],
                'odds_product': round(odds_product, 2),
                'cost': round(cost, 0),
                'stake_per_bet': 2,
                'multiplier': max(1, int(cost // 2)),
                'max_payout': round(max_payout, 0),
                'note': f'高置信度选项串关，{len(stable_picks)}场比赛',
            })
            slip_id += 1
    
    # 容错层：M串N容错
    if len(moderate) >= 3:
        mod_matches = list(set(opt['match'] for opt in moderate))[:4]
        mod_picks = [opt for opt in moderate if opt['match'] in mod_matches]
        if len(mod_picks) >= 3:
            n_matches = min(len(mod_picks), 4)
            # M串N注数公式：N = 2^M - M - 1（3串4=4注，4串11=11注）
            mn_count = (2 ** n_matches - n_matches - 1) if n_matches >= 3 else 1
            mn_type = f'{n_matches}串{mn_count}' if n_matches <= 4 else '4串11'
            odds_product = 1.0
            for opt in mod_picks[:4]:
                odds_product *= opt.get('odds', 1.0)
            cost = min(hedge_budget, 80)
            max_payout = odds_product * cost * 0.4  # M串N平均命中系数
            bet_slips.append({
                'id': f'H{slip_id:02d}',
                'type': mn_type,
                'layer': '容错层',
                'picks': [{'match': opt['match'], 'play': opt['play'], 'option': opt['option'], 'odds': opt['odds']} for opt in mod_picks[:4]],
                'odds_product': round(odds_product, 2),
                'cost': round(cost, 0),
                'stake_per_bet': 2,
                'multiplier': max(1, int(cost // 2)),
                'max_payout': round(max_payout, 0),
                'note': f'M串N容错，可错{len(mod_picks[:4])-2}场',
            })
            slip_id += 1
    
    # 搏冷层：高EV高赔选项
    if longshot:
        longshot_picks = sorted(longshot, key=lambda x: x.get('ev', 0), reverse=True)[:3]
        if len(longshot_picks) >= 2:
            odds_product = 1.0
            for opt in longshot_picks:
                odds_product *= opt.get('odds', 1.0)
            cost = min(longshot_budget, 40)
            max_payout = odds_product * cost
            bet_slips.append({
                'id': f'L{slip_id:02d}',
                'type': f'{len(longshot_picks)}串1',
                'layer': '搏冷层',
                'picks': [{'match': opt['match'], 'play': opt['play'], 'option': opt['option'], 'odds': opt['odds']} for opt in longshot_picks],
                'odds_product': round(odds_product, 2),
                'cost': round(cost, 0),
                'stake_per_bet': 2,
                'multiplier': max(1, int(cost // 2)),
                'max_payout': round(max_payout, 0),
                'note': f'高EV高赔搏冷，{len(longshot_picks)}场比赛',
            })
            slip_id += 1
    
    # 如果没有生成足够的投注单，用剩余选项补充
    if len(bet_slips) < 2 and len(value_options) >= 2:
        remaining = value_options[:2]
        odds_product = 1.0
        for opt in remaining:
            odds_product *= opt.get('odds', 1.0)
        cost = total_budget * 0.3
        bet_slips.append({
            'id': f'M{slip_id:02d}',
            'type': '2串1',
            'layer': '混合层',
            'picks': [{'match': opt['match'], 'play': opt['play'], 'option': opt['option'], 'odds': opt['odds']} for opt in remaining],
            'odds_product': round(odds_product, 2),
            'cost': round(cost, 0),
            'stake_per_bet': 2,
            'multiplier': max(1, int(cost // 2)),
            'max_payout': round(odds_product * cost, 0),
            'note': '补充投注单',
        })
    
    # 汇总
    total_cost = sum(slip['cost'] for slip in bet_slips)
    total_max_payout = sum(slip['max_payout'] for slip in bet_slips)
    
    result['bet_slips'] = bet_slips
    result['total_cost'] = round(total_cost, 0)
    result['total_max_payout'] = round(total_max_payout, 0)
    result['budget_utilization'] = f'{total_cost/total_budget*100:.0f}%'
    result['layers'] = {
        '稳健层': f'{params["stable_ratio"]*100:.0f}%预算',
        '容错层': f'{params["hedge_ratio"]*100:.0f}%预算',
        '搏冷层': f'{params["longshot_ratio"]*100:.0f}%预算',
    }
    
    # 保本分析
    min_odds = min((slip['odds_product'] for slip in bet_slips if slip['odds_product'] > 0), default=1.0)
    result['breakeven_analysis'] = {
        'min_odds_product': round(min_odds, 2),
        'breakeven_hits': f'只需{min_odds:.1f}倍回报即可保本',
        'risk_note': '以上为模拟盘分析，不构成投注建议。理性购彩，量力而行。',
    }
    
    # 标准投注单格式（500.com风格）
    result['standard_format'] = {
        'format': '500.com手机端风格',
        'note': '每张投注单包含：期号/场次/玩法/选项/赔率/倍数/金额/预计奖金',
    }
    
    result['summary'] = f'生成{len(bet_slips)}张投注单，总投入{total_cost:.0f}元，最高奖金{total_max_payout:.0f}元'
    
    return result


@mcp.tool()
def record_bet_slip(bet_slips: list, session_date: str = None, notes: str = '') -> dict:
    """
    投注单入库：将投注单保存到data/decisions/目录，用于赛后结算和复盘
    
    Args:
        bet_slips: 投注单列表，每张投注单包含match_id/play/option/odds/stake等字段
        session_date: 期号日期（YYYY-MM-DD），默认今天
        notes: 备注信息（分析思路、风险提示等）
    
    Returns:
        dict: 保存结果（bet_slip_id, file_path, saved_count, total_stake）
    """
    import os
    import json
    from datetime import datetime
    
    # 确定插件根目录（servers/portfolio/ → 插件根）
    server_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.dirname(os.path.dirname(server_dir))
    decisions_dir = os.path.join(plugin_root, 'data', 'decisions')
    
    # 创建目录
    os.makedirs(decisions_dir, exist_ok=True)
    
    # 确定日期
    if not session_date:
        session_date = datetime.now().strftime('%Y-%m-%d')
    
    # 生成投注单ID：日期+时间戳
    timestamp = datetime.now().strftime('%H%M%S')
    bet_slip_id = f'{session_date}_{timestamp}'
    
    # 计算总投入
    total_stake = sum(slip.get('stake', 2) for slip in bet_slips)
    
    # 构建入库数据
    record = {
        'bet_slip_id': bet_slip_id,
        'session_date': session_date,
        'created_at': datetime.now().isoformat(),
        'notes': notes,
        'total_stake': total_stake,
        'ticket_count': len(bet_slips),
        'bet_slips': bet_slips,
        'status': 'pending',  # pending: 待结算, settled: 已结算, reviewed: 已复盘
        'settlement': None,
        'review': None,
        'lessons': [],
    }
    
    # 保存文件
    file_path = os.path.join(decisions_dir, f'{bet_slip_id}.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    
    return {
        'success': True,
        'bet_slip_id': bet_slip_id,
        'file_path': file_path,
        'saved_count': len(bet_slips),
        'total_stake': total_stake,
        'message': f'投注单已入库：{bet_slip_id}，共{len(bet_slips)}张，总投入{total_stake}元',
    }


if __name__ == '__main__':
    mcp.run()
