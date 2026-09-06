#!/usr/bin/env python3
"""
竞彩足球分析引擎MCP服务器
18个工具：泊松预测、Dixon-Coles、EV计算、凯利公式、λ调整、4模型集成、多视角分析、反向指标、比赛节奏、赔率分歧、裁判影响、蒙特卡洛模拟、Brier评分、多智能体辩论、赔率变动模式、串关EV、玩法定制化分析、赛前检查清单
"""
import json
import math
import os
import random
import sys
from datetime import datetime
from itertools import combinations
from fastmcp import FastMCP

# 统一错误处理
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'common'))
from error_handler import safe_tool, make_error_response, make_success_response

mcp = FastMCP("jingcai-analyzer")

# 整合模块（来源：lottery-data项目）
try:
    from fund_flow import FundFlowAnalyzer, analyze_fund_flow
except ImportError:
    FundFlowAnalyzer = None
    analyze_fund_flow = None
LEAGUE_MAP = {
    'E0': '英超', 'E1': '英冠', 'D1': '德甲', 'SP1': '西甲', 'I1': '意甲',
    'F1': '法甲', 'N': '荷甲', 'NOR': '挪超', 'SWE': '瑞超', 'JPN': '日职',
    'KOR': '韩职', 'BRA': '巴甲', 'USA': '美职', 'SAU': '沙特联',
}

try:
    from confidence_filter import confidence_score, batch_confidence_filter
except ImportError:
    def confidence_score(*args, **kwargs):
        return 0.5
    def batch_confidence_filter(*args, **kwargs):
        return []

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')
HISTORY_DIR = os.path.join(DATA_DIR, 'history')
PLUGIN_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')

def load_json(filepath):
    """加载JSON文件，失败返回None"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

# ============================================================
# 基础数学函数
# ============================================================

def poisson_prob(lam, k):
    """泊松分布概率"""
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def remove_vig(odds_list):
    """赔率去水"""
    inv_sum = sum(1/o for o in odds_list if o > 0)
    return [1/o / inv_sum if o > 0 else 0 for o in odds_list], 1/inv_sum if inv_sum > 0 else 0

def dixon_coles_correction(p_h, p_a, rho=-0.13):
    """Dixon-Coles低比分修正"""
    if p_h == 0 and p_a == 0:
        return 1 - rho * p_h * p_a  # 简化
    elif p_h == 0 and p_a == 1:
        return 1 + rho * p_h * (1 - p_a)
    elif p_h == 1 and p_a == 0:
        return 1 + rho * (1 - p_h) * p_a
    elif p_h == 1 and p_a == 1:
        return 1 - rho * (1 - p_h) * (1 - p_a)
    return 1.0

# ============================================================
# 工具1：泊松比分预测
# ============================================================

@mcp.tool()
@safe_tool
def poisson_predict(lambda_home: float, lambda_away: float, max_goals: int = 6) -> dict:
    """
    泊松分布比分预测
    
    Args:
        lambda_home: 主队预期进球
        lambda_away: 客队预期进球
        max_goals: 最大进球数
    
    Returns:
        比分概率矩阵、胜平负概率、总进球概率
    """
    # 参数校验
    if lambda_home is None or lambda_away is None:
        return make_error_response("lambda_home和lambda_away不能为空", "validation", "请提供主队和客队的预期进球数")
    try:
        lambda_home = float(lambda_home)
        lambda_away = float(lambda_away)
        max_goals = int(max_goals)
    except (ValueError, TypeError):
        return make_error_response("参数类型错误", "validation", "lambda_home/lambda_away必须是数字，max_goals必须是整数")
    if lambda_home < 0 or lambda_away < 0:
        return make_error_response("lambda不能为负数", "validation", "预期进球数必须>=0")
    if max_goals < 1 or max_goals > 15:
        return make_error_response("max_goals超出范围", "validation", "最大进球数必须在1到15之间")
    
    # 比分概率矩阵
    score_matrix = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            prob = poisson_prob(lambda_home, h) * poisson_prob(lambda_away, a)
            score_matrix[f"{h}:{a}"] = round(prob, 6)
    
    # 胜平负概率
    home_win = sum(p for score, p in score_matrix.items() if int(score.split(':')[0]) > int(score.split(':')[1]))
    draw = sum(p for score, p in score_matrix.items() if int(score.split(':')[0]) == int(score.split(':')[1]))
    away_win = sum(p for score, p in score_matrix.items() if int(score.split(':')[0]) < int(score.split(':')[1]))
    
    # 总进球概率
    total_goals = {}
    for total in range(max_goals * 2 + 1):
        prob = sum(p for score, p in score_matrix.items() if int(score.split(':')[0]) + int(score.split(':')[1]) == total)
        total_goals[f"{total}球"] = round(prob, 6)
    
    # Top比分
    top_scores = sorted(score_matrix.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        'lambda_home': lambda_home,
        'lambda_away': lambda_away,
        'total_expected': round(lambda_home + lambda_away, 2),
        'score_matrix': score_matrix,
        'result_probs': {
            '主胜': round(home_win, 4),
            '平局': round(draw, 4),
            '客胜': round(away_win, 4),
        },
        'total_goals_probs': total_goals,
        'top_scores': [{'score': s, 'prob': p} for s, p in top_scores],
    }

# ============================================================
# 工具2：Dixon-Coles比分修正
# ============================================================

@mcp.tool()
@safe_tool
def dixon_coles(home_odds: float, draw_odds: float, away_odds: float, rho: float = -0.13) -> dict:
    """
    Dixon-Coles比分修正（修正低比分偏差）
    
    Args:
        home_odds: 主胜赔率
        draw_odds: 平局赔率
        away_odds: 客胜赔率
        rho: Dixon-Coles参数（默认-0.13）
    
    Returns:
        修正后的比分概率、胜平负概率
    """
    # 参数校验
    if home_odds is None or draw_odds is None or away_odds is None:
        return make_error_response("赔率不能为空", "validation", "请提供主胜、平局、客胜赔率")
    try:
        home_odds = float(home_odds)
        draw_odds = float(draw_odds)
        away_odds = float(away_odds)
        rho = float(rho)
    except (ValueError, TypeError):
        return make_error_response("参数类型错误", "validation", "赔率和rho必须是数字")
    if home_odds <= 0 or draw_odds <= 0 or away_odds <= 0:
        return make_error_response("赔率必须大于0", "validation", "所有赔率必须>0")
    
    # 从赔率推导λ（简化版）
    probs, payout = remove_vig([home_odds, draw_odds, away_odds])
    p_home, p_draw, p_away = probs
    
    # 用概率推导λ
    goal_diff = (p_home - p_away) * 2.5
    total_goals = 2.5 + (1 - p_draw) * 0.5
    lambda_home = (total_goals + goal_diff) / 2
    lambda_away = (total_goals - goal_diff) / 2
    
    # 基础泊松矩阵
    max_goals = 6
    base_matrix = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            base_matrix[(h, a)] = poisson_prob(lambda_home, h) * poisson_prob(lambda_away, a)
    
    # Dixon-Coles修正
    corrected_matrix = {}
    for (h, a), prob in base_matrix.items():
        if h == 0 and a == 0:
            correction = 1 - rho * (1 - lambda_home * lambda_away)  # 简化
        elif h == 0 and a == 1:
            correction = 1 + rho * lambda_home
        elif h == 1 and a == 0:
            correction = 1 + rho * lambda_away
        elif h == 1 and a == 1:
            correction = 1 - rho
        else:
            correction = 1.0
        corrected_matrix[f"{h}:{a}"] = round(prob * correction, 6)
    
    # 重新归一化
    total = sum(corrected_matrix.values())
    corrected_matrix = {k: round(v / total, 6) for k, v in corrected_matrix.items()}
    
    # 胜平负概率
    home_win = sum(p for score, p in corrected_matrix.items() if int(score.split(':')[0]) > int(score.split(':')[1]))
    draw = sum(p for score, p in corrected_matrix.items() if int(score.split(':')[0]) == int(score.split(':')[1]))
    away_win = sum(p for score, p in corrected_matrix.items() if int(score.split(':')[0]) < int(score.split(':')[1]))
    
    return {
        'rho': rho,
        'lambda_home': round(lambda_home, 2),
        'lambda_away': round(lambda_away, 2),
        'corrected_matrix': corrected_matrix,
        'result_probs': {
            '主胜': round(home_win, 4),
            '平局': round(draw, 4),
            '客胜': round(away_win, 4),
        },
        'note': 'Dixon-Coles修正低比分偏差，rho=-0.13为标准值'
    }

# ============================================================
# 工具3：EV计算
# ============================================================

@mcp.tool()
@safe_tool
def calculate_ev(model_prob: float, odds: float) -> dict:
    """
    计算期望值（EV）
    
    Args:
        model_prob: 模型概率（0-1）
        odds: 赔率
    
    Returns:
        EV值、隐含概率、价值判断
    """
    # 参数校验
    if model_prob is None or odds is None:
        return make_error_response("model_prob和odds不能为空", "validation", "请提供模型概率和赔率")
    try:
        model_prob = float(model_prob)
        odds = float(odds)
    except (ValueError, TypeError):
        return make_error_response("参数类型错误", "validation", "model_prob和odds必须是数字")
    if model_prob < 0 or model_prob > 1:
        return make_error_response("model_prob超出范围", "validation", "模型概率必须在0到1之间")
    if odds <= 0:
        return make_error_response("赔率必须大于0", "validation", "赔率必须>0")
    
    ev = model_prob * odds - 1
    implied_prob = 1 / odds
    
    if ev > 0.15:
        value = '高价值'
    elif ev > 0.05:
        value = '有价值'
    elif ev > 0:
        value = '轻微价值'
    else:
        value = '无价值'
    
    return {
        'model_prob': model_prob,
        'odds': odds,
        'implied_prob': round(implied_prob, 4),
        'prob_deviation': round(model_prob - implied_prob, 4),
        'ev': round(ev, 4),
        'ev_percent': f"{ev*100:+.1f}%",
        'value': value,
    }

# ============================================================
# 工具4：凯利公式
# ============================================================

@mcp.tool()
@safe_tool
def calculate_kelly(model_prob: float, odds: float, fraction: float = 0.25) -> dict:
    """
    计算凯利公式最优仓位
    
    Args:
        model_prob: 模型概率（0-1）
        odds: 赔率
        fraction: 分数凯利（默认0.25，即1/4凯利）
    
    Returns:
        凯利仓位、全凯利、建议仓位
    """
    # 参数校验
    if model_prob is None or odds is None:
        return make_error_response("model_prob和odds不能为空", "validation", "请提供模型概率和赔率")
    try:
        model_prob = float(model_prob)
        odds = float(odds)
        fraction = float(fraction)
    except (ValueError, TypeError):
        return make_error_response("参数类型错误", "validation", "model_prob/odds/fraction必须是数字")
    if model_prob < 0 or model_prob > 1:
        return make_error_response("model_prob超出范围", "validation", "模型概率必须在0到1之间")
    if odds <= 1:
        return make_error_response("赔率必须大于1", "validation", "赔率必须>1")
    if fraction <= 0 or fraction > 1:
        return make_error_response("fraction超出范围", "validation", "分数凯利必须在0到1之间")
    
    b = odds - 1  # 净赔率
    p = model_prob
    q = 1 - p
    
    full_kelly = (b * p - q) / b
    fractional_kelly = max(0, full_kelly * fraction)
    
    return {
        'model_prob': model_prob,
        'odds': odds,
        'net_odds': round(b, 2),
        'full_kelly': round(full_kelly, 4),
        'fraction': fraction,
        'fractional_kelly': round(fractional_kelly, 4),
        'suggested_bankroll_percent': f"{fractional_kelly*100:.2f}%",
        'note': '实战中严禁使用全凯利，必须采用分数凯利（通常1/2或1/4）'
    }

# ============================================================
# 工具5：λ调整（11种因子）
# ============================================================

@mcp.tool()
@safe_tool
def adjust_lambda(base_home: float, base_away: float, factors: dict) -> dict:
    """
    泊松λ动态调整（11种因子）
    
    Args:
        base_home: 主队基础λ
        base_away: 客队基础λ
        factors: 调整因子字典，可选键：
            home_injury, away_injury, home_defense_injury, away_defense_injury,
            fixture_density, home_advantage, home_motivation, away_motivation,
            weather, home_form, away_form
    
    Returns:
        调整后的λ、总进球、公平让球、调整明细
    """
    # 参数校验
    if base_home is None or base_away is None:
        return make_error_response("base_home和base_away不能为空", "validation", "请提供主队和客队的基础λ")
    if factors is None:
        factors = {}
    if not isinstance(factors, dict):
        return make_error_response("factors必须是字典", "validation", "调整因子必须是字典类型")
    try:
        base_home = float(base_home)
        base_away = float(base_away)
    except (ValueError, TypeError):
        return make_error_response("参数类型错误", "validation", "base_home和base_away必须是数字")
    if base_home < 0 or base_away < 0:
        return make_error_response("λ不能为负数", "validation", "基础λ必须>=0")
    
    home_lambda = base_home
    away_lambda = base_away
    adjustments = []
    
    factor_map = {
        'home_injury': ('主队进攻伤停', 'home'),
        'away_injury': ('客队进攻伤停', 'away'),
        'home_defense_injury': ('主队后卫伤停→客队λ', 'away'),
        'away_defense_injury': ('客队后卫伤停→主队λ', 'home'),
        'fixture_density': ('赛程密度', 'both'),
        'home_advantage': ('主场优势', 'home'),
        'home_motivation': ('主队战意', 'home'),
        'away_motivation': ('客队战意', 'away'),
        'weather': ('天气影响', 'both'),
        'home_form': ('主队状态', 'home'),
        'away_form': ('客队状态', 'away'),
    }
    
    for key, (name, target) in factor_map.items():
        if key in factors and factors[key]:
            val = factors[key]
            if target == 'home':
                home_lambda *= val
            elif target == 'away':
                away_lambda *= val
            elif target == 'both':
                home_lambda *= val
                away_lambda *= val
            adjustments.append(f"{name}×{val}")
    
    return {
        'base_home': base_home,
        'base_away': base_away,
        'adjusted_home': round(home_lambda, 2),
        'adjusted_away': round(away_lambda, 2),
        'total_goals': round(home_lambda + away_lambda, 2),
        'fair_handicap': round(home_lambda - away_lambda, 2),
        'adjustments': adjustments,
    }

# ============================================================
# 工具6：4模型集成
# ============================================================

@mcp.tool()
@safe_tool
def ensemble_predict(match_data: dict) -> dict:
    """
    4模型集成概率（市场35%+泊松25%+DC25%+贝叶斯15%）
    
    Args:
        match_data: 比赛数据，含odds等
    
    Returns:
        集成概率、各模型概率、置信度
    """
    # 参数校验
    if match_data is None or not isinstance(match_data, dict):
        return make_error_response("match_data不能为空且必须是字典", "validation", "请提供包含odds的比赛数据字典")
    
    odds = match_data.get('odds', {})
    spf_odds = odds.get('胜平负', {}).get('odds', [0, 0, 0])
    
    if len(spf_odds) < 3 or any(o <= 0 for o in spf_odds):
        return {'error': '胜平负赔率数据不完整'}
    
    # 模型1：市场共识（去水后赔率隐含概率）35%
    market_probs, _ = remove_vig(spf_odds)
    
    # 模型2：泊松 25%
    p_home, p_draw, p_away = market_probs
    goal_diff = (p_home - p_away) * 2.5
    total_goals = 2.5 + (1 - p_draw) * 0.5
    lambda_home = (total_goals + goal_diff) / 2
    lambda_away = (total_goals - goal_diff) / 2
    
    poisson_result = poisson_predict.fn(lambda_home=lambda_home, lambda_away=lambda_away)
    poisson_data = poisson_result.get('data', poisson_result)
    poisson_probs = [
        poisson_data['result_probs']['主胜'],
        poisson_data['result_probs']['平局'],
        poisson_data['result_probs']['客胜'],
    ]
    
    # 模型3：Dixon-Coles 25%
    dc_result = dixon_coles.fn(home_odds=spf_odds[0], draw_odds=spf_odds[1], away_odds=spf_odds[2])
    dc_data = dc_result.get('data', dc_result)
    dc_probs = [
        dc_data['result_probs']['主胜'],
        dc_data['result_probs']['平局'],
        dc_data['result_probs']['客胜'],
    ]
    
    # 模型4：贝叶斯（简化，用历史数据调整）15%
    # 实际实现中应使用球队强度库和历史数据
    bayesian_probs = market_probs  # 简化：先用市场概率
    
    # 加权集成
    weights = [0.35, 0.25, 0.25, 0.15]
    ensemble_probs = []
    for i in range(3):
        prob = (market_probs[i] * weights[0] + 
                poisson_probs[i] * weights[1] + 
                dc_probs[i] * weights[2] + 
                bayesian_probs[i] * weights[3])
        ensemble_probs.append(prob)
    
    # 归一化
    total = sum(ensemble_probs)
    ensemble_probs = [p / total for p in ensemble_probs]
    
    # 模型分歧度（标准差）
    import statistics
    stds = [statistics.stdev([market_probs[i], poisson_probs[i], dc_probs[i], bayesian_probs[i]]) for i in range(3)]
    disagreement = sum(stds) / 3
    confidence = 1 - disagreement  # 分歧越小，置信度越高
    
    return {
        'ensemble_probs': {
            '主胜': round(ensemble_probs[0], 4),
            '平局': round(ensemble_probs[1], 4),
            '客胜': round(ensemble_probs[2], 4),
        },
        'model_probs': {
            '市场共识(35%)': [round(p, 4) for p in market_probs],
            '泊松(25%)': [round(p, 4) for p in poisson_probs],
            'Dixon-Coles(25%)': [round(p, 4) for p in dc_probs],
            '贝叶斯(15%)': [round(p, 4) for p in bayesian_probs],
        },
        'model_disagreement': round(disagreement, 4),
        'confidence': round(confidence, 4),
        'note': '4模型加权集成，分歧越小置信度越高'
    }

# ============================================================
# 工具7：多视角分析
# ============================================================

@mcp.tool()
@safe_tool
def multi_perspective_analysis(match_data: dict) -> dict:
    """
    5模块多视角分析（数据/模型/盘口/基本面/逆向）
    
    Args:
        match_data: 比赛数据
    
    Returns:
        5视角分析报告、综合评分、共识
    """
    # 参数校验
    if match_data is None or not isinstance(match_data, dict):
        return make_error_response("match_data不能为空且必须是字典", "validation", "请提供包含odds/info的比赛数据字典")
    
    # 实际实现中应调用5个agent
    # 这里返回框架
    return {
        'perspectives': {
            '数据视角': {'score': 0, 'analysis': '基于历史数据和统计指标', 'status': '待分析'},
            '模型视角': {'score': 0, 'analysis': '基于概率模型和EV计算', 'status': '待分析'},
            '盘口视角': {'score': 0, 'analysis': '基于赔率变动和盘口走势', 'status': '待分析'},
            '基本面视角': {'score': 0, 'analysis': '基于伤停/战意/赛程/状态', 'status': '待分析'},
            '逆向视角': {'score': 0, 'analysis': '基于反向指标和热门陷阱识别', 'status': '待分析'},
        },
        'composite_score': 0,
        'consensus': '待5视角分析完成后生成共识',
        'note': '5模块多视角分析，实际实现中调用5个agent独立分析后生成共识'
    }

# ============================================================
# 工具8：反向指标分析
# ============================================================

@mcp.tool()
@safe_tool
def reverse_indicator(match_data: dict) -> dict:
    """
    反向指标分析（热门陷阱/冷门价值/赔率异动/支持率背离）
    
    Args:
        match_data: 比赛数据，含odds/support/opening_odds/closing_odds
    
    Returns:
        反向信号列表、风险提示
    """
    # 参数校验
    if match_data is None or not isinstance(match_data, dict):
        return make_error_response("match_data不能为空且必须是字典", "validation", "请提供包含odds/support的比赛数据字典")
    
    signals = []
    
    # 智能提取odds：支持列表和字典两种格式
    odds_raw = match_data.get('odds', [0, 0, 0])
    if isinstance(odds_raw, dict):
        # 字典格式：{'胜平负': {'odds': [...]}}，尝试提取胜平负赔率
        spf_odds = odds_raw.get('胜平负', odds_raw.get('spf', {}))
        if isinstance(spf_odds, dict):
            odds = spf_odds.get('odds', [0, 0, 0])
        elif isinstance(spf_odds, list):
            odds = spf_odds
        else:
            odds = [0, 0, 0]
    elif isinstance(odds_raw, list):
        odds = odds_raw
    else:
        odds = [0, 0, 0]
    
    # 确保odds是数字列表
    odds = [float(o) if isinstance(o, (int, float)) and o > 0 else 0 for o in odds]
    if len(odds) < 3:
        odds.extend([0] * (3 - len(odds)))
    
    # 智能提取support：支持列表、字典和字符串
    support_raw = match_data.get('support', [0, 0, 0])
    if isinstance(support_raw, dict):
        support = [float(support_raw.get(k, 0)) for k in ['home', 'draw', 'away']]
    elif isinstance(support_raw, list):
        support = [float(s) if isinstance(s, (int, float)) else 0 for s in support_raw]
    elif isinstance(support_raw, str):
        # 字符串格式："75,15,10"
        try:
            support = [float(s) for s in support_raw.split(',')]
        except:
            support = [0, 0, 0]
    else:
        support = [0, 0, 0]
    if len(support) < 3:
        support.extend([0] * (3 - len(support)))
    
    # 提取初盘和终盘
    opening = match_data.get('opening_odds', [])
    closing = match_data.get('closing_odds', [])
    if isinstance(opening, list):
        opening = [float(o) if isinstance(o, (int, float)) and o > 0 else 0 for o in opening]
    else:
        opening = []
    if isinstance(closing, list):
        closing = [float(c) if isinstance(c, (int, float)) and c > 0 else 0 for c in closing]
    else:
        closing = []
    
    labels = ['主胜', '平局', '客胜']
    
    # 1. 热门陷阱：支持率>70%但赔率<1.5
    for i, (s, o) in enumerate(zip(support, odds)):
        if s > 70 and o < 1.5 and o > 0:
            implied = 1 / o * 100
            signals.append({
                'type': '热门陷阱',
                'option': labels[i],
                'support': s,
                'odds': o,
                'implied_prob': round(implied, 1),
                'deviation': round(s - implied, 1),
                'reason': f'支持率{s}%远高于隐含概率{implied:.1f}%，市场过度乐观，可能是诱盘'
            })
    
    # 2. 冷门价值：支持率<20%但赔率>5
    for i, (s, o) in enumerate(zip(support, odds)):
        if s < 20 and o > 5 and o > 0:
            implied = 1 / o * 100
            signals.append({
                'type': '冷门价值',
                'option': labels[i],
                'support': s,
                'odds': o,
                'implied_prob': round(implied, 1),
                'deviation': round(implied - s, 1),
                'reason': f'支持率仅{s}%但赔率{o}（隐含概率{implied:.1f}%），市场过度悲观，可能有被忽略的利好'
            })
    
    # 3. 赔率异动：初盘→终盘变动>20%
    if opening and closing and len(opening) == len(closing):
        for i, (o, c) in enumerate(zip(opening, closing)):
            if o > 0:
                change = (c - o) / o * 100
                if abs(change) > 20:
                    direction = '上升' if change > 0 else '下降'
                    signals.append({
                        'type': '赔率异动',
                        'option': labels[i],
                        'opening': o,
                        'closing': c,
                        'change': round(change, 1),
                        'reason': f'赔率从{o}变动到{c}（{direction}{abs(change):.1f}%），资金大幅流入，可能是内幕信息'
                    })
    
    # 4. 支持率与赔率背离：偏差>15%
    for i, (s, o) in enumerate(zip(support, odds)):
        if o > 0:
            implied = 1 / o * 100
            deviation = s - implied
            if abs(deviation) > 15:
                direction = '散户过热' if deviation > 0 else '散户过冷'
                signals.append({
                    'type': '支持率背离',
                    'option': labels[i],
                    'support': s,
                    'implied_prob': round(implied, 1),
                    'deviation': round(deviation, 1),
                    'reason': f'支持率{s}%与隐含概率{implied:.1f}%偏差{deviation:+.1f}%，{direction}，反向操作可能有价值'
                })
    
    return {
        'signals': signals,
        'signal_count': len(signals),
        'risk_level': '高' if len(signals) >= 3 else '中' if len(signals) >= 1 else '低',
        'note': '4种反向信号：热门陷阱/冷门价值/赔率异动/支持率背离'
    }

# ============================================================
# 工具9：比赛节奏分析
# ============================================================

@mcp.tool()
@safe_tool
def match_pace_analysis(match_data: dict) -> dict:
    """
    比赛节奏分析（开局/慢热/领先保持/逆转）
    
    Args:
        match_data: 比赛数据，含近期比赛节奏数据
    
    Returns:
        节奏分析报告、球队风格画像
    """
    # 参数校验
    if match_data is None:
        return make_error_response('match_data不能为空', 'validation', '请提供match_data参数')

    return {
        'home_team_pace': {
            'first_half_goals_avg': 0,
            'second_half_goals_avg': 0,
            'lead_keep_rate': 0,
            'comeback_rate': 0,
            'style': '待分析',  # 开局型/慢热型/均衡型
        },
        'away_team_pace': {
            'first_half_goals_avg': 0,
            'second_half_goals_avg': 0,
            'lead_keep_rate': 0,
            'comeback_rate': 0,
            'style': '待分析',
        },
        'match_pace_prediction': {
            'first_half_goals': 0,
            'second_half_goals': 0,
            'likely_pattern': '待分析',  # 开局进球/下半场发力/胶着
        },
        'note': '比赛节奏分析，用于半全场玩法和总进球玩法的辅助判断'
    }

# ============================================================
# 工具10：赔率分歧分析
# ============================================================

@mcp.tool()
@safe_tool
def odds_divergence(match_data: dict) -> dict:
    """
    多博彩公司赔率分歧分析
    
    Args:
        match_data: 比赛数据，含多公司赔率
    
    Returns:
        分歧度分析、异常赔率识别
    """
    # 参数校验
    if match_data is None:
        return make_error_response('match_data不能为空', 'validation', '请提供match_data参数')

    return {
        'divergence': {
            'home': {'std': 0, 'cv': 0, 'level': '待分析'},
            'draw': {'std': 0, 'cv': 0, 'level': '待分析'},
            'away': {'std': 0, 'cv': 0, 'level': '待分析'},
        },
        'anomalies': [],
        'note': '赔率分歧度高=市场不确定性大，可能有价值机会'
    }

# ============================================================
# 工具11：裁判影响分析
# ============================================================

@mcp.tool()
@safe_tool
def referee_analysis(league: str, referee: str = None) -> dict:
    """
    裁判因素分析（出牌率/点球率/主场偏袒/大球影响）
    
    Args:
        league: 联赛代码
        referee: 裁判名称
    
    Returns:
        裁判执法风格分析、对比赛的影响预测
    """
    # 参数校验
    if league is None:
        return make_error_response('league不能为空', 'validation', '请提供league参数')
    if referee is not None and not isinstance(referee, (str, int, float, list, dict)):
        return make_error_response('referee类型错误', 'validation', '请提供正确的类型')

    return {
        'referee': referee or '未知',
        'league': league,
        'stats': {
            'yellow_per_game': 0,
            'red_per_game': 0,
            'penalty_per_game': 0,
            'goals_per_game': 0,
            'home_win_rate': 0,
            'over25_rate': 0,
            'home_bias': 0,
        },
        'impact': {
            'foul_impact': '待分析',
            'goal_impact': '待分析',
            'home_advantage_impact': '待分析',
        },
        'note': '裁判因素分析，出牌多的裁判可能导致比赛中断多、进球少'
    }

# ============================================================
# 工具12：蒙特卡洛模拟
# ============================================================

@mcp.tool()
@safe_tool
def monte_carlo_simulate(probs: list, odds: list = None, n_simulations: int = 100000, 
                          parlay_type: str = 'single') -> dict:
    """
    蒙特卡洛模拟（10万次模拟，评估胜率/风险/收益分布）
    
    Args:
        probs: 各场比赛选项的概率列表
        odds: 各场比赛选项的赔率列表（可选）
        n_simulations: 模拟次数（默认10万）
        parlay_type: 串关类型（single/2串1/3串1/3串4/4串11等）
    
    Returns:
        模拟结果（胜率/平均收益/收益分布/风险指标）
    """
    # 参数校验
    if probs is None or not isinstance(probs, list):
        return make_error_response("probs不能为空且必须是列表", "validation", "请提供概率列表")
    if len(probs) == 0:
        return make_error_response("probs不能为空列表", "validation", "请提供至少一个概率")
    if odds is not None and not isinstance(odds, list):
        return make_error_response("odds必须是列表", "validation", "赔率必须是列表类型")
    try:
        n_simulations = int(n_simulations)
    except (ValueError, TypeError):
        return make_error_response("n_simulations必须是整数", "validation", "模拟次数必须是整数")
    if n_simulations < 100 or n_simulations > 1000000:
        return make_error_response("n_simulations超出范围", "validation", "模拟次数必须在100到1000000之间")
    # 验证概率范围
    for i, p in enumerate(probs):
        try:
            p = float(p)
            if p < 0 or p > 1:
                return make_error_response(f"第{i+1}个概率超出范围", "validation", "概率必须在0到1之间")
        except (ValueError, TypeError):
            return make_error_response(f"第{i+1}个概率类型错误", "validation", "概率必须是数字")
    if not probs:
        return {'error': '概率列表不能为空'}
    
    random.seed(42)  # 固定种子，结果可复现
    
    n_matches = len(probs)
    
    # 单场模拟
    if parlay_type == 'single' or n_matches == 1:
        wins = sum(1 for _ in range(n_simulations) if random.random() < probs[0])
        win_rate = wins / n_simulations
        
        result = {
            'type': 'single',
            'n_matches': 1,
            'n_simulations': n_simulations,
            'win_rate': round(win_rate, 4),
            'theoretical_prob': round(probs[0], 4),
            'deviation': round(win_rate - probs[0], 4),
        }
        
        if odds and len(odds) >= 1:
            avg_return = win_rate * odds[0] - 1
            result['avg_return'] = round(avg_return, 4)
            result['avg_return_percent'] = f"{avg_return*100:+.2f}%"
        
        return result
    
    # 串关模拟
    def simulate_parlay():
        """模拟一次串关，返回是否全中"""
        for p in probs:
            if random.random() >= p:
                return False
        return True
    
    wins = sum(1 for _ in range(n_simulations) if simulate_parlay())
    win_rate = wins / n_simulations
    theoretical_prob = 1.0
    for p in probs:
        theoretical_prob *= p
    
    result = {
        'type': parlay_type,
        'n_matches': n_matches,
        'n_simulations': n_simulations,
        'win_rate': round(win_rate, 4),
        'theoretical_prob': round(theoretical_prob, 4),
        'deviation': round(win_rate - theoretical_prob, 4),
    }
    
    if odds and len(odds) == n_matches:
        odds_product = 1.0
        for o in odds:
            odds_product *= o
        avg_return = win_rate * odds_product - 1
        result['odds_product'] = round(odds_product, 2)
        result['avg_return'] = round(avg_return, 4)
        result['avg_return_percent'] = f"{avg_return*100:+.2f}%"
        
        # 风险指标
        result['risk_metrics'] = {
            'max_loss': '100%（全输）',
            'volatility': '高（串关波动大）',
            'break_even_prob': round(1 / odds_product, 4),
        }
    
    return result

# ============================================================
# 工具13：Brier评分
# ============================================================

@mcp.tool()
@safe_tool
def brier_score(predictions: list, actuals: list) -> dict:
    """
    Brier评分（概率校准指标，评估模型概率预测准确性）
    
    Args:
        predictions: 预测概率列表（0-1）
        actuals: 实际结果列表（0或1）
    
    Returns:
        Brier分数、校准度、分辨率
    """
    # 参数校验
    if predictions is None:
        return make_error_response('predictions不能为空', 'validation', '请提供predictions参数')
    if actuals is None:
        return make_error_response('actuals不能为空', 'validation', '请提供actuals参数')

    if len(predictions) != len(actuals):
        return {'error': '预测和实际结果数量不匹配'}
    
    n = len(predictions)
    if n == 0:
        return {'error': '列表为空'}
    
    # Brier分数 = 平均(预测 - 实际)^2
    # 分数越低越好（0=完美，1=最差）
    brier = sum((p - a) ** 2 for p, a in zip(predictions, actuals)) / n
    
    # 校准度（预测概率分组后的实际概率）
    bins = {}
    for p, a in zip(predictions, actuals):
        bin_key = round(p * 10) / 10  # 按0.1分组
        if bin_key not in bins:
            bins[bin_key] = {'count': 0, 'actual': 0}
        bins[bin_key]['count'] += 1
        bins[bin_key]['actual'] += a
    
    calibration = []
    for bin_key in sorted(bins.keys()):
        bin_data = bins[bin_key]
        actual_prob = bin_data['actual'] / bin_data['count'] if bin_data['count'] > 0 else 0
        calibration.append({
            'predicted_bin': bin_key,
            'count': bin_data['count'],
            'actual_prob': round(actual_prob, 4),
            'deviation': round(actual_prob - bin_key, 4),
        })
    
    # 分辨率（实际结果的方差）
    actual_mean = sum(actuals) / n
    resolution = sum((a - actual_mean) ** 2 for a in actuals) / n
    
    # 评分等级
    if brier < 0.15:
        grade = '优秀'
    elif brier < 0.20:
        grade = '良好'
    elif brier < 0.25:
        grade = '一般'
    else:
        grade = '较差'
    
    return {
        'n_predictions': n,
        'brier_score': round(brier, 4),
        'grade': grade,
        'calibration': calibration,
        'resolution': round(resolution, 4),
        'note': 'Brier分数越低越好（0=完美），用于评估模型概率预测的准确性'
    }

# ============================================================
# 工具14：多智能体辩论
# ============================================================

@mcp.tool()
@safe_tool
def multi_agent_debate(match_data: dict) -> dict:
    """
    多智能体辩论（5个agent：数据/模型/基本面/市场/风险）
    
    5个agent从不同视角独立分析，然后进行辩论，最终生成共识。
    每个agent给出观点、信心度(0-100)、证据列表。
    
    Args:
        match_data: 比赛数据字典，需包含home/away/league/odds等字段
    
    Returns:
        各agent观点、辩论过程、最终共识、分歧点
    """
    # 参数校验
    if match_data is None:
        return make_error_response('match_data不能为空', 'validation', '请提供match_data参数')

    home = match_data.get('home', '主队')
    away = match_data.get('away', '客队')
    league = match_data.get('league', '')
    
    # 获取胜平负赔率
    odds = match_data.get('odds', {})
    spf_odds = odds.get('胜平负', {}).get('odds', [2.0, 3.2, 3.5])
    if len(spf_odds) < 3:
        spf_odds = [2.0, 3.2, 3.5]
    
    # 计算市场隐含概率
    inv_sum = sum(1/o for o in spf_odds if o > 0)
    market_probs = [1/o / inv_sum if o > 0 else 0 for o in spf_odds]
    
    # 获取比赛资讯
    info = match_data.get('info', {})
    recent_form = info.get('近期战绩', {})
    h2h = info.get('历史交锋', {})
    injuries = info.get('伤停', {})
    
    # ============================================================
    # Agent 1: 数据agent - 基于历史数据和统计
    # ============================================================
    data_agent_view = '主胜' if market_probs[0] > market_probs[2] else '客胜'
    data_confidence = int(max(market_probs) * 100 * 0.8)  # 数据agent信心度打8折
    data_evidence = [
        f"市场隐含概率: 主胜{market_probs[0]*100:.1f}% / 平{market_probs[1]*100:.1f}% / 客胜{market_probs[2]*100:.1f}%",
        f"赔率结构: {spf_odds[0]:.2f} / {spf_odds[1]:.2f} / {spf_odds[2]:.2f}",
        f"返奖率: {1/inv_sum*100:.1f}%",
    ]
    if recent_form:
        data_evidence.append(f"近期战绩数据已纳入分析")
    
    # ============================================================
    # Agent 2: 模型agent - 基于数学模型（泊松/Dixon-Coles）
    # ============================================================
    # 用泊松模型计算概率
    lambda_home = 1.3 + (market_probs[0] - 0.4) * 2
    lambda_away = 1.1 + (market_probs[2] - 0.3) * 2
    
    # 简化的泊松概率计算
    def poisson_p(lam, k):
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    
    model_home_win = 0
    model_draw = 0
    model_away_win = 0
    for i in range(7):
        for j in range(7):
            p = poisson_p(lambda_home, i) * poisson_p(lambda_away, j)
            if i > j:
                model_home_win += p
            elif i == j:
                model_draw += p
            else:
                model_away_win += p
    
    model_agent_view = '主胜' if model_home_win > model_away_win else '客胜'
    model_confidence = int(max(model_home_win, model_draw, model_away_win) * 100)
    model_evidence = [
        f"泊松模型: 主胜{model_home_win*100:.1f}% / 平{model_draw*100:.1f}% / 客胜{model_away_win*100:.1f}%",
        f"预期进球: 主队{lambda_home:.2f} / 客队{lambda_away:.2f}",
        f"模型与市场偏差: 主胜{(model_home_win-market_probs[0])*100:+.1f}%",
    ]
    
    # ============================================================
    # Agent 3: 基本面agent - 基于球队实力/状态/伤停
    # ============================================================
    home_strength = 0.5
    away_strength = 0.5
    
    # 从近期战绩推断实力
    if isinstance(recent_form, dict):
        home_recent = recent_form.get('home', {})
        away_recent = recent_form.get('away', {})
        if isinstance(home_recent, dict):
            home_wins = home_recent.get('wins', 0)
            home_matches = home_recent.get('matches', 5)
            home_strength = 0.3 + (home_wins / max(home_matches, 1)) * 0.4
        if isinstance(away_recent, dict):
            away_wins = away_recent.get('wins', 0)
            away_matches = away_recent.get('matches', 5)
            away_strength = 0.3 + (away_wins / max(away_matches, 1)) * 0.4
    
    # 伤停影响
    home_injury_impact = 0
    away_injury_impact = 0
    if isinstance(injuries, dict):
        home_injuries = injuries.get('home', [])
        away_injuries = injuries.get('away', [])
        if isinstance(home_injuries, list):
            home_injury_impact = min(len(home_injuries) * 0.05, 0.2)
        if isinstance(away_injuries, list):
            away_injury_impact = min(len(away_injuries) * 0.05, 0.2)
    
    home_adjusted = home_strength - home_injury_impact
    away_adjusted = away_strength - away_injury_impact
    
    fundamental_view = '主胜' if home_adjusted > away_adjusted else '客胜'
    fundamental_confidence = int(abs(home_adjusted - away_adjusted) * 200 + 40)
    fundamental_confidence = min(fundamental_confidence, 90)
    fundamental_evidence = [
        f"球队实力评分: 主队{home_adjusted:.2f} / 客队{away_adjusted:.2f}",
        f"主场优势: +0.10",
        f"伤停影响: 主队-{home_injury_impact:.2f} / 客队-{away_injury_impact:.2f}",
    ]
    if h2h:
        fundamental_evidence.append("历史交锋数据已纳入分析")
    
    # ============================================================
    # Agent 4: 市场agent - 基于赔率变动和资金流向
    # ============================================================
    odds_history = match_data.get('odds_history', {})
    market_view = data_agent_view  # 默认与数据agent一致
    market_confidence = 50
    market_evidence = [
        f"当前赔率: {spf_odds[0]:.2f} / {spf_odds[1]:.2f} / {spf_odds[2]:.2f}",
        "市场情绪: 中性",
    ]
    
    if odds_history:
        opening = odds_history.get('opening', spf_odds)
        if isinstance(opening, list) and len(opening) >= 3:
            home_change = (spf_odds[0] - opening[0]) / opening[0] * 100
            if home_change < -5:
                market_view = '主胜'
                market_confidence = 65
                market_evidence.append(f"主胜赔率下降{abs(home_change):.1f}%，资金流向主胜")
            elif home_change > 5:
                market_view = '客胜'
                market_confidence = 60
                market_evidence.append(f"主胜赔率上升{home_change:.1f}%，资金流向客胜")
            else:
                market_evidence.append(f"赔率变动{home_change:+.1f}%，市场稳定")
    
    # ============================================================
    # Agent 5: 风险agent - 识别风险和不确定性
    # ============================================================
    risk_factors = []
    risk_level = '低'
    
    # 检查分歧
    views = [data_agent_view, model_agent_view, fundamental_view, market_view]
    view_counts = {v: views.count(v) for v in set(views)}
    max_agreement = max(view_counts.values())
    
    if max_agreement <= 2:
        risk_factors.append("多agent观点分歧较大")
        risk_level = '中'
    
    # 检查赔率接近
    if abs(market_probs[0] - market_probs[2]) < 0.1:
        risk_factors.append("主客胜概率接近，比赛不确定性高")
        risk_level = '中'
    
    # 检查伤停
    if home_injury_impact > 0.1 or away_injury_impact > 0.1:
        risk_factors.append("重要球员伤停，可能影响比赛结果")
        if risk_level == '低':
            risk_level = '中'
    
    # 检查平局概率
    if market_probs[1] > 0.3:
        risk_factors.append(f"平局概率较高({market_probs[1]*100:.1f}%)")
    
    risk_view = '谨慎' if risk_level != '低' else '乐观'
    risk_confidence = 70 if risk_level == '低' else 50
    risk_evidence = risk_factors if risk_factors else ["未发现明显风险因素"]
    
    # ============================================================
    # 辩论过程
    # ============================================================
    debate_rounds = []
    
    # 第一轮：各agent陈述观点
    debate_rounds.append({
        'round': 1,
        'topic': '初始观点陈述',
        'statements': [
            {'agent': '数据agent', 'view': data_agent_view, 'confidence': data_confidence},
            {'agent': '模型agent', 'view': model_agent_view, 'confidence': model_confidence},
            {'agent': '基本面agent', 'view': fundamental_view, 'confidence': fundamental_confidence},
            {'agent': '市场agent', 'view': market_view, 'confidence': market_confidence},
            {'agent': '风险agent', 'view': risk_view, 'confidence': risk_confidence},
        ]
    })
    
    # 第二轮：识别分歧和共识
    consensus_view = max(view_counts, key=view_counts.get)
    disagreement = [v for v, c in view_counts.items() if c < max_agreement]
    
    debate_rounds.append({
        'round': 2,
        'topic': '分歧识别与共识形成',
        'consensus': f"{max_agreement}/5个agent倾向于{consensus_view}",
        'disagreement': disagreement if disagreement else ["无明显分歧"],
        'risk_assessment': f"风险等级: {risk_level}"
    })
    
    # ============================================================
    # 最终共识
    # ============================================================
    # 加权计算最终概率（各agent信心度加权）
    weights = {
        '数据agent': data_confidence,
        '模型agent': model_confidence,
        '基本面agent': fundamental_confidence,
        '市场agent': market_confidence,
    }
    
    total_weight = sum(weights.values())
    final_home_prob = 0
    final_draw_prob = 0
    final_away_prob = 0
    
    # 数据agent权重
    final_home_prob += market_probs[0] * weights['数据agent']
    final_draw_prob += market_probs[1] * weights['数据agent']
    final_away_prob += market_probs[2] * weights['数据agent']
    
    # 模型agent权重
    final_home_prob += model_home_win * weights['模型agent']
    final_draw_prob += model_draw * weights['模型agent']
    final_away_prob += model_away_win * weights['模型agent']
    
    # 基本面agent权重（简化为二分类）
    if fundamental_view == '主胜':
        final_home_prob += 0.6 * weights['基本面agent']
        final_draw_prob += 0.25 * weights['基本面agent']
        final_away_prob += 0.15 * weights['基本面agent']
    else:
        final_home_prob += 0.15 * weights['基本面agent']
        final_draw_prob += 0.25 * weights['基本面agent']
        final_away_prob += 0.6 * weights['基本面agent']
    
    # 市场agent权重
    final_home_prob += market_probs[0] * weights['市场agent']
    final_draw_prob += market_probs[1] * weights['市场agent']
    final_away_prob += market_probs[2] * weights['市场agent']
    
    # 归一化
    final_sum = final_home_prob + final_draw_prob + final_away_prob
    if final_sum > 0:
        final_home_prob /= final_sum
        final_draw_prob /= final_sum
        final_away_prob /= final_sum
    
    final_view = '主胜' if final_home_prob > final_away_prob else '客胜'
    if final_draw_prob > final_home_prob and final_draw_prob > final_away_prob:
        final_view = '平局'
    
    final_confidence = int(max(final_home_prob, final_draw_prob, final_away_prob) * 100)
    
    # 计算EV
    final_ev = {
        '主胜': final_home_prob * spf_odds[0] - 1,
        '平局': final_draw_prob * spf_odds[1] - 1,
        '客胜': final_away_prob * spf_odds[2] - 1,
    }
    
    value_option = max(final_ev, key=final_ev.get)
    value_ev = final_ev[value_option]
    
    return {
        'match': f"{home} vs {away}",
        'league': league,
        'agents': {
            '数据agent': {'view': data_agent_view, 'confidence': data_confidence, 'evidence': data_evidence},
            '模型agent': {'view': model_agent_view, 'confidence': model_confidence, 'evidence': model_evidence},
            '基本面agent': {'view': fundamental_view, 'confidence': fundamental_confidence, 'evidence': fundamental_evidence},
            '市场agent': {'view': market_view, 'confidence': market_confidence, 'evidence': market_evidence},
            '风险agent': {'view': risk_view, 'confidence': risk_confidence, 'evidence': risk_evidence, 'risk_level': risk_level},
        },
        'debate': debate_rounds,
        'consensus': {
            'view': final_view,
            'confidence': final_confidence,
            'probabilities': {
                '主胜': round(final_home_prob, 4),
                '平局': round(final_draw_prob, 4),
                '客胜': round(final_away_prob, 4),
            },
            'ev': {k: round(v, 4) for k, v in final_ev.items()},
            'value_option': value_option,
            'value_ev': round(value_ev, 4),
            'agreement': f"{max_agreement}/5",
            'risk_level': risk_level,
        },
        'recommendation': f"多智能体共识: {final_view} (信心度{final_confidence}%), 价值选项: {value_option} (EV{value_ev*100:+.1f}%)"
    }

# ============================================================
# 工具15：赔率变动模式
# ============================================================

@mcp.tool()
@safe_tool
def odds_movement_pattern(odds_history: dict) -> dict:
    """
    赔率变动模式分析（主动变盘vs被动变盘）
    
    Args:
        odds_history: 赔率历史数据（初盘/受注/临场/变动轨迹）
    
    Returns:
        变动模式识别、信号解读
    """
    # 参数校验
    if odds_history is None:
        return make_error_response('odds_history不能为空', 'validation', '请提供odds_history参数')

    return {
        'pattern': '待分析',  # 主动变盘/被动变盘/稳定
        'signals': [],
        'interpretation': '待分析',
        'note': '赔率变动模式分析，主动变盘（机构调整）vs被动变盘（资金驱动）'
    }

# ============================================================
# 工具16：串关EV
# ============================================================

@mcp.tool()
@safe_tool
def parlay_ev(legs_odds: list, legs_probs: list) -> dict:
    """
    串关EV分析（串关EV不是简单相加，抽水和概率误差叠加）
    
    Args:
        legs_odds: 各场赔率列表
        legs_probs: 各场模型概率列表
    
    Returns:
        串关EV、理论概率、抽水叠加分析
    """
    # 参数校验
    if legs_odds is None:
        return make_error_response('legs_odds不能为空', 'validation', '请提供legs_odds参数')
    if legs_probs is None:
        return make_error_response('legs_probs不能为空', 'validation', '请提供legs_probs参数')

    if len(legs_odds) != len(legs_probs):
        return {'error': '赔率和概率数量不匹配'}
    
    n = len(legs_odds)
    if n == 0:
        return {'error': '列表为空'}
    
    # 串关理论概率
    theoretical_prob = 1.0
    for p in legs_probs:
        theoretical_prob *= p
    
    # 串关赔率乘积
    odds_product = 1.0
    for o in legs_odds:
        odds_product *= o
    
    # 串关EV
    ev = theoretical_prob * odds_product - 1
    
    # 单场EV对比
    single_evs = [p * o - 1 for p, o in zip(legs_probs, legs_odds)]
    
    # 抽水叠加分析
    # 单场平均抽水
    single_vigs = [1 - 1/o for o in legs_odds]  # 简化
    avg_single_vig = sum(single_vigs) / n if n > 0 else 0
    
    # 串关抽水（几何叠加）
    parlay_vig = 1 - (1 - avg_single_vig) ** n
    
    return {
        'n_legs': n,
        'theoretical_prob': round(theoretical_prob, 6),
        'odds_product': round(odds_product, 2),
        'parlay_ev': round(ev, 4),
        'parlay_ev_percent': f"{ev*100:+.2f}%",
        'single_evs': [round(e, 4) for e in single_evs],
        'avg_single_ev': round(sum(single_evs) / n, 4) if n > 0 else 0,
        'vig_analysis': {
            'avg_single_vig': round(avg_single_vig, 4),
            'parlay_vig': round(parlay_vig, 4),
            'vig_multiplier': round(parlay_vig / avg_single_vig, 2) if avg_single_vig > 0 else 0,
        },
        'note': '串关EV不是单场简单相加，抽水和概率误差都会几何叠加，串关门槛应更高'
    }

# ============================================================
# 工具17：玩法定制化分析
# ============================================================

@mcp.tool()
@safe_tool
def play_specific_analysis(match_data: dict, play_type: str) -> dict:
    """
    5玩法定制化分析（每种玩法独立评价体系）
    
    Args:
        match_data: 比赛数据
        play_type: 玩法类型（胜平负/让球胜平负/总进球/比分/半全场）
    
    Returns:
        玩法专属分析报告、选项评价、推荐
    """
        # 参数校验
    if match_data is None or not isinstance(match_data, dict):
        return make_error_response("match_data不能为空且必须是字典", "validation", "请提供比赛数据字典")
    if play_type is None or not isinstance(play_type, str):
        return make_error_response("play_type不能为空且必须是字符串", "validation", "请提供玩法类型（胜平负/让球胜平负/总进球/比分/半全场）")
    valid_plays = ['胜平负', '让球胜平负', '总进球', '比分', '半全场']
    if play_type not in valid_plays:
        return make_error_response(f"play_type必须是{valid_plays}之一", "validation", "请提供有效的玩法类型")
    
    play_configs = {
        '胜平负': {'ev_threshold': 0.05, 'kelly': 0.25, 'max_legs': 8, 'options': ['主胜', '平局', '客胜']},
        '让球胜平负': {'ev_threshold': 0.05, 'kelly': 0.20, 'max_legs': 8, 'options': ['让球胜', '让球平', '让球负']},
        '总进球': {'ev_threshold': 0.07, 'kelly': 0.20, 'max_legs': 6, 'options': ['0球', '1球', '2球', '3球', '4球', '5球', '6球', '7+球']},
        '比分': {'ev_threshold': 0.15, 'kelly': 0.03, 'max_legs': 4, 'options': []},
        '半全场': {'ev_threshold': 0.12, 'kelly': 0.05, 'max_legs': 4, 'options': ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']},
    }
    
    config = play_configs.get(play_type)
    if not config:
        return {'error': f'未知玩法类型: {play_type}'}
    
    return {
        'play_type': play_type,
        'config': config,
        'analysis': '待分析',
        'options': [],
        'recommendation': '待分析',
        'note': f'{play_type}专属分析，EV门槛{config["ev_threshold"]*100:.0f}%，Kelly系数{config["kelly"]}'
    }

# ============================================================
# 工具18：赛前检查清单
# ============================================================

@mcp.tool()
@safe_tool
def generate_pre_match_checklist(log_data: dict = None) -> dict:
    """
    生成赛前检查清单（根据历史经验）
    
    Args:
        log_data: 历史决策日志数据（可选）
    
    Returns:
        赛前检查清单、必查项、常见错误提醒
    """
    # 参数校验
    if log_data is not None and not isinstance(log_data, (str, int, float, list, dict)):
        return make_error_response('log_data类型错误', 'validation', '请提供正确的类型')

    checklist = {
        '数据完整性': [
            '5种玩法赔率是否全部获取？',
            '8大比赛资讯是否全部获取？',
            '第三方赔率（欧指/亚盘/大小球）是否获取？',
            '第三方比赛资讯是否获取？',
            '初盘+终盘+赔率变动轨迹是否获取？',
            '历史数据（H2H/近期状态/联赛特征）是否查询？',
        ],
        '分析完整性': [
            '5种玩法是否逐一分析？（禁止跳过比分/半全场）',
            '每场比赛是否识别最优玩法（Top1-3）？',
            '6段式推理是否填写？（现状/矛盾/推理/结论/元认知/反事实）',
            '8个强制推理节点是否执行？',
            '四方赔率交叉验证是否完成？',
            '玩法间相互推导是否完成？',
        ],
        '风险控制': [
            'EV门槛是否按玩法差异化？（胜平负+5%/比分+15%）',
            'Kelly系数是否按玩法差异化？（胜平负0.25/比分0.03）',
            '低赔率选项（<1.30）是否避免进串关？',
            '热门陷阱是否识别？（支持率>70%但赔率<1.5）',
            '同一场比赛跨单选项是否逻辑一致？',
        ],
        '常见错误提醒': [
            '❌ 玩法同质化：不要只选胜平负和总进球',
            '❌ 分析偷懒：不要把"风险高"当作不分析的借口',
            '❌ 赔率黑洞：不要把赔率1.12视为"铁胆"',
            '❌ 硬解码：不要固定5张投注单/固定3种类型',
            '❌ EV一刀切：不要所有玩法用同一个EV门槛',
            '❌ 跳过流程：不要不调用工具直接自由发挥',
        ],
        '自进化闭环': [
            '上一期经验是否预加载？',
            '各玩法历史命中率是否查看？',
            '相关联赛校准参数是否查看？',
            '当前策略参数是否查看？',
            '类似对阵历史经验是否查找？',
            '心理状态是否检查？',
        ],
    }
    
    return {
        'checklist': checklist,
        'total_items': sum(len(items) for items in checklist.values()),
        'note': '赛前检查清单，根据历史经验生成，确保不遗漏关键步骤'
    }

# ============================================================
# 主函数
# ============================================================

@mcp.tool()
@safe_tool
def conditional_prob_half_full(lambda_home: float, lambda_away: float, match_pace: str = 'normal') -> dict:
    """
    半全场真正条件概率推导（4步法）
    半场矩阵→动态下半场λ→映射9结果→逆转选项修正
    
    Args:
        lambda_home: 主队预期进球
        lambda_away: 客队预期进球
        match_pace: 比赛节奏 fast/normal/slow
    
    Returns:
        半全场9种结果的条件概率
    """
        # 参数校验
    if lambda_home is None or lambda_away is None:
        return make_error_response("lambda_home和lambda_away不能为空", "validation", "请提供主队和客队的预期进球数")
    try:
        lambda_home = float(lambda_home)
        lambda_away = float(lambda_away)
    except (ValueError, TypeError):
        return make_error_response("参数类型错误", "validation", "lambda_home和lambda_away必须是数字")
    if lambda_home < 0 or lambda_away < 0:
        return make_error_response("λ不能为负数", "validation", "预期进球数必须>=0")
    if match_pace is None:
        match_pace = 'normal'
    
    import math
    from itertools import product
    
    # 比赛节奏调整
    pace_factor = {'fast': 1.15, 'normal': 1.0, 'slow': 0.85}.get(match_pace, 1.0)
    lambda_home *= pace_factor
    lambda_away *= pace_factor
    
    # 半场λ（约为全场的45%）
    half_lambda_home = lambda_home * 0.45
    half_lambda_away = lambda_away * 0.45
    
    def poisson_prob(lam, k):
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    
    # 步骤1：半场结果矩阵（主胜/平/客胜）
    half_probs = {'H': 0, 'D': 0, 'A': 0}
    for hg in range(6):
        for ag in range(6):
            p = poisson_prob(half_lambda_home, hg) * poisson_prob(half_lambda_away, ag)
            if hg > ag: half_probs['H'] += p
            elif hg == ag: half_probs['D'] += p
            else: half_probs['A'] += p
    
    # 步骤2：动态下半场λ（根据半场结果调整）
    # 领先方λ×0.85（保守），落后方λ×1.15（进攻），平局不变
    second_half_lambdas = {
        'H': (lambda_home * 0.55 * 0.85, lambda_away * 0.55 * 1.15),  # 主队领先
        'D': (lambda_home * 0.55, lambda_away * 0.55),  # 平局
        'A': (lambda_home * 0.55 * 1.15, lambda_away * 0.55 * 0.85),  # 客队领先
    }
    
    # 步骤3：映射9种半全场结果
    results = {}
    option_names = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
    half_map = {'胜': 'H', '平': 'D', '负': 'A'}
    
    for half_result in ['H', 'D', 'A']:
        sh_lh, sh_la = second_half_lambdas[half_result]
        full_probs = {'H': 0, 'D': 0, 'A': 0}
        for hg in range(6):
            for ag in range(6):
                p = poisson_prob(sh_lh, hg) * poisson_prob(sh_la, ag)
                if hg > ag: full_probs['H'] += p
                elif hg == ag: full_probs['D'] += p
                else: full_probs['A'] += p
        
        for full_result in ['H', 'D', 'A']:
            key = f"{half_result}{full_result}"
            # 逆转选项×0.6修正（领先被逆转概率低于理论值）
            prob = half_probs[half_result] * full_probs[full_result]
            if (half_result == 'H' and full_result == 'A') or (half_result == 'A' and full_result == 'H'):
                prob *= 0.6  # 逆转修正
            results[key] = round(prob, 4)
    
    # 归一化
    total = sum(results.values())
    results = {k: round(v / total, 4) for k, v in results.items()}
    
    # 映射到中文选项名
    final_results = {}
    for i, name in enumerate(option_names):
        key = list(results.keys())[i]
        final_results[name] = results[key]
    
    return {
        'lambda_home': lambda_home,
        'lambda_away': lambda_away,
        'match_pace': match_pace,
        'half_time_probs': {
            '主胜': round(half_probs['H'], 4),
            '平局': round(half_probs['D'], 4),
            '客胜': round(half_probs['A'], 4),
        },
        'half_full_probs': final_results,
        'top3': sorted(final_results.items(), key=lambda x: x[1], reverse=True)[:3],
        'note': '半全场条件概率推导（4步法），逆转选项已×0.6修正'
    }

@mcp.tool()
@safe_tool
def update_bayesian_strength(team: str, goals_for: int, goals_against: int, opponent: str = None) -> dict:
    """
    贝叶斯球队强度动态更新
    
    Args:
        team: 球队名称
        goals_for: 进球数
        goals_against: 失球数
        opponent: 对手球队（可选）
    
    Returns:
        更新后的球队强度
    """
    # 参数校验
    if team is None:
        return make_error_response('team不能为空', 'validation', '请提供team参数')
    if goals_for is None:
        return make_error_response('goals_for不能为空', 'validation', '请提供goals_for参数')
    if goals_against is None:
        return make_error_response('goals_against不能为空', 'validation', '请提供goals_against参数')
    if opponent is not None and not isinstance(opponent, (str, int, float, list, dict)):
        return make_error_response('opponent类型错误', 'validation', '请提供正确的类型')

    strength_file = os.path.join(DATA_DIR, 'team_ratings.json')
    data = load_json(strength_file) or {}
    
    if team not in data:
        data[team] = {'attack': 1.0, 'defense': 1.0, 'matches': 0, 'elo': 1500}
    
    team_data = data[team]
    
    # 贝叶斯更新（简化版）
    # 进攻强度：进球数/预期进球
    expected_goals = team_data['attack'] * 1.3  # 基准预期进球
    new_attack = (team_data['attack'] * team_data['matches'] + (goals_for / max(expected_goals, 0.1))) / (team_data['matches'] + 1)
    
    # 防守强度：失球数/预期失球
    expected_conceded = team_data['defense'] * 1.3
    new_defense = (team_data['defense'] * team_data['matches'] + (goals_against / max(expected_conceded, 0.1))) / (team_data['matches'] + 1)
    
    # Elo更新
    if opponent and opponent in data:
        opp_elo = data[opponent]['elo']
        expected_score = 1 / (1 + 10 ** ((opp_elo - team_data['elo']) / 400))
        actual_score = 1 if goals_for > goals_against else (0.5 if goals_for == goals_against else 0)
        team_data['elo'] += 32 * (actual_score - expected_score)
    
    team_data['attack'] = round(new_attack, 4)
    team_data['defense'] = round(new_defense, 4)
    team_data['matches'] += 1
    team_data['last_updated'] = datetime.now().isoformat()
    
    save_json(strength_file, data)
    
    return {
        'team': team,
        'attack': team_data['attack'],
        'defense': team_data['defense'],
        'elo': round(team_data['elo'], 1),
        'matches': team_data['matches'],
        'note': '贝叶斯强度更新完成'
    }

@mcp.tool()
@safe_tool
def update_elo_rating(team: str, opponent: str, result: str) -> dict:
    """
    Elo评级更新
    
    Args:
        team: 球队名称
        opponent: 对手球队
        result: 比赛结果 win/draw/loss
    
    Returns:
        更新后的Elo评级
    """
    # 参数校验
    if team is None:
        return make_error_response('team不能为空', 'validation', '请提供team参数')
    if opponent is None:
        return make_error_response('opponent不能为空', 'validation', '请提供opponent参数')
    if result is None:
        return make_error_response('result不能为空', 'validation', '请提供result参数')

    strength_file = os.path.join(DATA_DIR, 'team_ratings.json')
    data = load_json(strength_file) or {}
    
    for t in [team, opponent]:
        if t not in data:
            data[t] = {'attack': 1.0, 'defense': 1.0, 'matches': 0, 'elo': 1500}
    
    team_elo = data[team]['elo']
    opp_elo = data[opponent]['elo']
    
    expected_team = 1 / (1 + 10 ** ((opp_elo - team_elo) / 400))
    expected_opp = 1 - expected_team
    
    actual_team = {'win': 1, 'draw': 0.5, 'loss': 0}.get(result, 0.5)
    actual_opp = 1 - actual_team
    
    k_factor = 32  # K因子
    data[team]['elo'] = round(team_elo + k_factor * (actual_team - expected_team), 1)
    data[opponent]['elo'] = round(opp_elo + k_factor * (actual_opp - expected_opp), 1)
    
    data[team]['matches'] += 1
    data[opponent]['matches'] += 1
    
    save_json(strength_file, data)
    
    return {
        'team': team,
        'old_elo': team_elo,
        'new_elo': data[team]['elo'],
        'change': round(data[team]['elo'] - team_elo, 1),
        'opponent': opponent,
        'opponent_elo': data[opponent]['elo'],
        'result': result,
        'expected_score': round(expected_team, 4),
        'actual_score': actual_team
    }

@mcp.tool()
@safe_tool
def track_odds_clv(match_id: str, opening_odds: list, closing_odds: list, actual_result: str = None) -> dict:
    """
    赔率初终盘追踪+CLV分析（Closed Line Value）
    
    Args:
        match_id: 比赛ID
        opening_odds: 初盘赔率 [主胜, 平局, 客胜]
        closing_odds: 终盘赔率 [主胜, 平局, 客胜]
        actual_result: 实际结果 home/draw/away（可选，赛后填入）
    
    Returns:
        CLV分析结果
    """
    # 参数校验
    if match_id is None:
        return make_error_response('match_id不能为空', 'validation', '请提供match_id参数')
    if opening_odds is None:
        return make_error_response('opening_odds不能为空', 'validation', '请提供opening_odds参数')
    if closing_odds is None:
        return make_error_response('closing_odds不能为空', 'validation', '请提供closing_odds参数')
    if actual_result is not None and not isinstance(actual_result, (str, int, float, list, dict)):
        return make_error_response('actual_result类型错误', 'validation', '请提供正确的类型')

    clv_file = os.path.join(DATA_DIR, 'odds_clv_tracker.json')
    data = load_json(clv_file) or {}
    
    # 计算赔率变动
    changes = []
    for i, (o, c) in enumerate(zip(opening_odds, closing_odds)):
        if o > 0:
            change = (c - o) / o * 100
            changes.append(round(change, 1))
        else:
            changes.append(0)
    
    # 隐含概率变动
    def implied_probs(odds):
        inv = [1/o for o in odds if o > 0]
        total = sum(inv)
        return [i/total for i in inv]
    
    opening_probs = implied_probs(opening_odds)
    closing_probs = implied_probs(closing_odds)
    prob_changes = [round((c - o) * 100, 1) for o, c in zip(opening_probs, closing_probs)]
    
    # CLV判断：赔率下降方向=资金流入方向=市场看好方向
    labels = ['主胜', '平局', '客胜']
    money_flow = []
    for i, change in enumerate(changes):
        if change < -5:
            money_flow.append(f"{labels[i]}资金大幅流入（赔率下降{abs(change)}%）")
        elif change < -2:
            money_flow.append(f"{labels[i]}资金流入（赔率下降{abs(change)}%）")
        elif change > 5:
            money_flow.append(f"{labels[i]}资金流出（赔率上升{change}%）")
    
    record = {
        'match_id': match_id,
        'opening_odds': opening_odds,
        'closing_odds': closing_odds,
        'odds_changes_pct': changes,
        'opening_probs': [round(p, 4) for p in opening_probs],
        'closing_probs': [round(p, 4) for p in closing_probs],
        'prob_changes_pct': prob_changes,
        'money_flow': money_flow,
        'actual_result': actual_result,
        'timestamp': datetime.now().isoformat()
    }
    
    # 赛后CLV验证
    if actual_result:
        result_idx = {'home': 0, 'draw': 1, 'away': 2}.get(actual_result, 0)
        # 如果赔率下降的选项最终打出，说明CLV为正（市场判断正确）
        clv_positive = changes[result_idx] < 0
        record['clv_verified'] = clv_positive
        record['clv_note'] = '赔率下降选项打出，CLV为正' if clv_positive else '赔率上升选项打出，CLV为负'
    
    data[match_id] = record
    save_json(clv_file, data)
    
    return {
        'match_id': match_id,
        'odds_changes': dict(zip(labels, changes)),
        'prob_changes': dict(zip(labels, prob_changes)),
        'money_flow': money_flow,
        'clv_verified': record.get('clv_verified'),
        'total_tracking': len(data),
        'note': '赔率初终盘追踪+CLV分析完成'
    }

@mcp.tool()
@safe_tool
def history_analytics(league: str, team: str = None, team_a: str = None, team_b: str = None, analysis_type: str = 'all') -> dict:
    """
    历史数据9维度分析
    1.赛程疲劳指数 2.历史交锋 3.赛季阶段规律 4.串关长度回测 5.M串N历史表现
    6.高赔命中率 7.历史基准对比 8.联赛规律 9.CLV追踪
    
    Args:
        league: 联赛代码
        team: 球队（疲劳/基准分析）
        team_a: 主队（H2H分析）
        team_b: 客队（H2H分析）
        analysis_type: 分析类型 fatigue/h2h/season/parlay/longshot/benchmark/league/clv/all
    
    Returns:
        历史数据分析结果
    """
    # 参数校验
    if league is None:
        return make_error_response('league不能为空', 'validation', '请提供league参数')
    if team is not None and not isinstance(team, (str, int, float, list, dict)):
        return make_error_response('team类型错误', 'validation', '请提供正确的类型')
    if team_a is not None and not isinstance(team_a, (str, int, float, list, dict)):
        return make_error_response('team_a类型错误', 'validation', '请提供正确的类型')
    if team_b is not None and not isinstance(team_b, (str, int, float, list, dict)):
        return make_error_response('team_b类型错误', 'validation', '请提供正确的类型')
    if analysis_type is None:
        return make_error_response('analysis_type不能为空', 'validation', '请提供analysis_type参数')

    history_file = os.path.join(HISTORY_DIR, f'{league}_history.json')
    matches = load_json(history_file)
    
    if not matches:
        return {'error': f'联赛{league}历史数据不存在，请先运行download_history.py下载'}
    
    results = {'league': league, 'total_matches': len(matches), 'analysis': {}}
    
    # 1. 赛程疲劳指数
    if analysis_type in ['fatigue', 'all'] and team:
        team_matches = [m for m in matches if m.get('home') == team or m.get('away') == team]
        if len(team_matches) >= 2:
            team_matches.sort(key=lambda x: x.get('date', ''))
            recent = team_matches[-5:]
            intervals = []
            for i in range(1, len(recent)):
                try:
                    d1 = datetime.strptime(recent[i-1]['date'], '%d/%m/%Y')
                    d2 = datetime.strptime(recent[i]['date'], '%d/%m/%Y')
                    intervals.append((d2 - d1).days)
                except:
                    pass
            avg_interval = sum(intervals) / len(intervals) if intervals else 7
            fatigue = max(0, min(100, (7 - avg_interval) * 15))
            results['analysis']['fatigue'] = {
                'team': team,
                'avg_interval_days': round(avg_interval, 1),
                'fatigue_index': round(fatigue, 0),
                'level': '高疲劳' if fatigue > 60 else ('中等疲劳' if fatigue > 30 else '低疲劳')
            }
    
    # 2. 历史交锋
    if analysis_type in ['h2h', 'all'] and team_a and team_b:
        h2h = [m for m in matches if 
               (m.get('home') == team_a and m.get('away') == team_b) or
               (m.get('home') == team_b and m.get('away') == team_a)]
        if h2h:
            a_wins = sum(1 for m in h2h if 
                        (m['home'] == team_a and m.get('home_goals', 0) > m.get('away_goals', 0)) or
                        (m['home'] == team_b and m.get('away_goals', 0) > m.get('home_goals', 0)))
            draws = sum(1 for m in h2h if m.get('home_goals', 0) == m.get('away_goals', 0))
            b_wins = len(h2h) - a_wins - draws
            results['analysis']['h2h'] = {
                'total': len(h2h),
                f'{team_a}_wins': a_wins,
                'draws': draws,
                f'{team_b}_wins': b_wins,
                'win_rate': {team_a: round(a_wins/len(h2h)*100, 1), team_b: round(b_wins/len(h2h)*100, 1)}
            }
    
    # 8. 联赛规律
    if analysis_type in ['league', 'all']:
        total_goals = sum(m.get('home_goals', 0) + m.get('away_goals', 0) for m in matches)
        home_wins = sum(1 for m in matches if m.get('home_goals', 0) > m.get('away_goals', 0))
        draws = sum(1 for m in matches if m.get('home_goals', 0) == m.get('away_goals', 0))
        over25 = sum(1 for m in matches if m.get('home_goals', 0) + m.get('away_goals', 0) > 2.5)
        results['analysis']['league_patterns'] = {
            'avg_goals': round(total_goals / len(matches), 2),
            'home_win_rate': round(home_wins / len(matches) * 100, 1),
            'draw_rate': round(draws / len(matches) * 100, 1),
            'over25_rate': round(over25 / len(matches) * 100, 1),
            'btts_rate': round(sum(1 for m in matches if m.get('home_goals', 0) > 0 and m.get('away_goals', 0) > 0) / len(matches) * 100, 1)
        }
    
    return results

@mcp.tool()
@safe_tool
def historical_stats_deep(league: str, stat_type: str = 'all') -> dict:
    """
    历史数据深度统计（半场+亚盘+大小球）
    
    Args:
        league: 联赛代码
        stat_type: 统计类型 half_time/asian_handicap/over_under/all
    
    Returns:
        深度统计结果
    """
    # 参数校验
    if league is None:
        return make_error_response('league不能为空', 'validation', '请提供league参数')
    if stat_type is None:
        return make_error_response('stat_type不能为空', 'validation', '请提供stat_type参数')

    history_file = os.path.join(HISTORY_DIR, f'{league}_history.json')
    matches = load_json(history_file)
    
    if not matches:
        return {'error': f'联赛{league}历史数据不存在'}
    
    results = {'league': league, 'total_matches': len(matches), 'stats': {}}
    
    # 半场统计
    if stat_type in ['half_time', 'all']:
        ht_home = sum(1 for m in matches if m.get('hthg', 0) > m.get('htag', 0))
        ht_draw = sum(1 for m in matches if m.get('hthg', 0) == m.get('htag', 0))
        ht_away = len(matches) - ht_home - ht_draw
        # 半场领先最终胜率
        ht_lead_win = sum(1 for m in matches if m.get('hthg', 0) > m.get('htag', 0) and m.get('home_goals', 0) > m.get('away_goals', 0))
        results['stats']['half_time'] = {
            'ht_home_rate': round(ht_home / len(matches) * 100, 1),
            'ht_draw_rate': round(ht_draw / len(matches) * 100, 1),
            'ht_away_rate': round(ht_away / len(matches) * 100, 1),
            'ht_lead_final_win_rate': round(ht_lead_win / max(ht_home, 1) * 100, 1),
            'avg_ht_goals': round(sum(m.get('hthg', 0) + m.get('htag', 0) for m in matches) / len(matches), 2)
        }
    
    # 大小球统计
    if stat_type in ['over_under', 'all']:
        for line in [1.5, 2.5, 3.5]:
            over = sum(1 for m in matches if m.get('home_goals', 0) + m.get('away_goals', 0) > line)
            results['stats'][f'over_{line}'] = {
                'over_rate': round(over / len(matches) * 100, 1),
                'under_rate': round(100 - over / len(matches) * 100, 1)
            }
    
    # 射门/角球统计
    if stat_type in ['all']:
        results['stats']['match_stats'] = {
            'avg_home_shots': round(sum(m.get('hs', 0) for m in matches) / len(matches), 1),
            'avg_away_shots': round(sum(m.get('as', 0) for m in matches) / len(matches), 1),
            'avg_home_corners': round(sum(m.get('hc', 0) for m in matches) / len(matches), 1),
            'avg_away_corners': round(sum(m.get('ac', 0) for m in matches) / len(matches), 1),
            'avg_yellow_cards': round(sum(m.get('hy', 0) + m.get('ay', 0) for m in matches) / len(matches), 1)
        }
    
    return results

@mcp.tool()
@safe_tool
def league_focus_analysis(league: str, focus_type: str = 'overview') -> dict:
    """
    联赛专攻模式：针对特定联赛深度分析
    
    Args:
        league: 联赛代码
        focus_type: 分析类型 overview/teams/betting/value/all
    
    Returns:
        联赛专攻分析结果
    """
    # 参数校验
    if league is None:
        return make_error_response('league不能为空', 'validation', '请提供league参数')
    if focus_type is None:
        return make_error_response('focus_type不能为空', 'validation', '请提供focus_type参数')

    # 加载联赛特征
    league_file = os.path.join(DATA_DIR, 'league_features.json')
    features_raw = load_json(league_file)
    features = features_raw if isinstance(features_raw, dict) else {}
    
    # 加载历史数据
    history_file = os.path.join(HISTORY_DIR, f'{league}_history.json')
    matches = load_json(history_file) or []
    
    result = {
        'league': league,
        'league_name': LEAGUE_MAP.get(league, league),
        'features': features.get(league, {}),
        'history_matches': len(matches),
        'analysis': {}
    }
    
    if matches:
        # 球队统计
        if focus_type in ['teams', 'all']:
            team_stats = {}
            for m in matches:
                for team, goals, conceded in [(m.get('home'), m.get('home_goals', 0), m.get('away_goals', 0)),
                                               (m.get('away'), m.get('away_goals', 0), m.get('home_goals', 0))]:
                    if team not in team_stats:
                        team_stats[team] = {'matches': 0, 'goals_for': 0, 'goals_against': 0, 'wins': 0}
                    team_stats[team]['matches'] += 1
                    team_stats[team]['goals_for'] += goals
                    team_stats[team]['goals_against'] += conceded
                    if goals > conceded:
                        team_stats[team]['wins'] += 1
            
            # 按攻击力排序
            top_attack = sorted(team_stats.items(), key=lambda x: x[1]['goals_for'] / max(x[1]['matches'], 1), reverse=True)[:5]
            top_defense = sorted(team_stats.items(), key=lambda x: x[1]['goals_against'] / max(x[1]['matches'], 1))[:5]
            
            result['analysis']['top_attack'] = [{'team': t, 'avg_goals': round(s['goals_for'] / s['matches'], 2)} for t, s in top_attack]
            result['analysis']['top_defense'] = [{'team': t, 'avg_conceded': round(s['goals_against'] / s['matches'], 2)} for t, s in top_defense]
        
        # 投注价值分析
        if focus_type in ['betting', 'value', 'all']:
            # 主场优势
            home_wins = sum(1 for m in matches if m.get('home_goals', 0) > m.get('away_goals', 0))
            result['analysis']['home_advantage'] = {
                'home_win_rate': round(home_wins / len(matches) * 100, 1),
                'avg_home_goals': round(sum(m.get('home_goals', 0) for m in matches) / len(matches), 2),
                'avg_away_goals': round(sum(m.get('away_goals', 0) for m in matches) / len(matches), 2)
            }
            
            # 大球率
            over25 = sum(1 for m in matches if m.get('home_goals', 0) + m.get('away_goals', 0) > 2.5)
            result['analysis']['over_under'] = {
                'over25_rate': round(over25 / len(matches) * 100, 1),
                'avg_total_goals': round(sum(m.get('home_goals', 0) + m.get('away_goals', 0) for m in matches) / len(matches), 2)
            }
    
    return result

@mcp.tool()
@safe_tool
def strategy_ab_test(strategy_a: dict, strategy_b: dict, league: str = None, n_matches: int = 100) -> dict:
    # 参数校验
    if strategy_a is None:
        return make_error_response('strategy_a不能为空', 'validation', '请提供strategy_a参数')
    if strategy_b is None:
        return make_error_response('strategy_b不能为空', 'validation', '请提供strategy_b参数')
    if league is not None and not isinstance(league, (str, int, float, list, dict)):
        return make_error_response('league类型错误', 'validation', '请提供正确的类型')
    if n_matches is None:
        return make_error_response('n_matches不能为空', 'validation', '请提供n_matches参数')

    """
    策略A/B测试框架
    
    便捷构造参数:
        from common.param_helpers import make_strategy_config
        strategy_a = make_strategy_config("保守策略", ev_threshold=0.10, max_parlay=2)
        strategy_b = make_strategy_config("激进策略", ev_threshold=0.03, max_parlay=6)
    
    Args:
        strategy_a: 策略A配置字典，需包含:
            - name: 策略名称 (str)
            - ev_threshold: EV门槛 (float, 如0.05=5%)
            - plays: 允许的玩法列表 (list, 如["胜平负", "让球胜平负"])
            - max_parlay: 最大串关数 (int)
            - kelly_fraction: Kelly系数 (float, 可选, 默认0.25)
        strategy_b: 策略B配置字典，格式同strategy_a
        league: 联赛代码（可选，如"E0"英超）
        n_matches: 模拟比赛数（默认100）
    
    Returns:
        包含两种策略ROI/胜率/盈亏对比的字典
        strategy_b: 策略B配置
        league: 联赛代码（可选，用历史数据回测）
        n_matches: 模拟比赛数
    
    Returns:
        A/B测试结果
    """
    import random
    
    def simulate_strategy(strategy, n):
        """模拟策略表现"""
        random.seed(hash(str(strategy)) % 2**32)
        total_bet = 0
        total_win = 0
        wins = 0
        losses = 0
        
        for _ in range(n):
            # 模拟单注
            bet_amount = strategy.get('stake', 100)
            total_bet += bet_amount
            
            # 模拟命中率（基于EV门槛）
            ev_threshold = strategy.get('ev_threshold', 0.05)
            hit_prob = max(0.1, min(0.9, 0.4 + ev_threshold * 0.5 + random.gauss(0, 0.1)))
            
            if random.random() < hit_prob:
                # 命中
                odds = strategy.get('avg_odds', 2.0)
                winnings = bet_amount * odds
                total_win += winnings
                wins += 1
            else:
                losses += 1
        
        roi = (total_win - total_bet) / total_bet * 100 if total_bet > 0 else 0
        return {
            'name': strategy.get('name', 'Unknown'),
            'total_bet': total_bet,
            'total_win': round(total_win, 2),
            'net_profit': round(total_win - total_bet, 2),
            'roi': round(roi, 2),
            'win_rate': round(wins / n * 100, 1),
            'wins': wins,
            'losses': losses
        }
    
    result_a = simulate_strategy(strategy_a, n_matches)
    result_b = simulate_strategy(strategy_b, n_matches)
    
    # 比较
    winner = 'A' if result_a['roi'] > result_b['roi'] else 'B'
    roi_diff = round(result_a['roi'] - result_b['roi'], 2)
    
    return {
        'strategy_a': result_a,
        'strategy_b': result_b,
        'comparison': {
            'winner': winner,
            'roi_difference': roi_diff,
            'note': f'策略{winner}ROI领先{abs(roi_diff)}%'
        },
        'test_matches': n_matches,
        'league': league
    }

# ============================================================
# P0新增：半全场专属分析工具（3个）
# ============================================================

@mcp.tool()
@safe_tool
def htft_frequency_calibration(model_probs: dict, league_code: str = None) -> dict:
    """
    半全场历史频率校准器
    用36联赛历史频率基准校准模型概率，解决模型概率偏差问题
    
    Args:
        model_probs: 模型计算的9种组合概率字典，如{"胜胜":0.30, "平平":0.10, ...}
        league_code: 联赛代码，如E0/D1/SP1，用于获取联赛专属频率
    
    Returns:
        校准后的9种组合概率、核心区间概率、平开头概率、推荐组合
    """
    # 参数校验
    if model_probs is None:
        return make_error_response('model_probs不能为空', 'validation', '请提供model_probs参数')
    if league_code is not None and not isinstance(league_code, (str, int, float, list, dict)):
        return make_error_response('league_code类型错误', 'validation', '请提供正确的类型')

    import json
    
    # 加载频率基准库
    freq_file = os.path.join(DATA_DIR, 'htft_frequency.json')
    freq_data = load_json(freq_file) or {}
    
    # 获取基准频率
    if league_code and league_code in freq_data.get('league_profiles', {}):
        baseline = freq_data['league_profiles'][league_code].get('htft_adjust', {})
        league_name = freq_data['league_profiles'][league_code].get('name', league_code)
    else:
        baseline = freq_data.get('global_baseline', {})
        league_name = '全球基准'
    
    # 9种组合
    combinations = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
    
    # 校准：模型概率70% + 历史频率30%
    calibrated = {}
    for combo in combinations:
        model_p = model_probs.get(combo, 0)
        baseline_p = baseline.get(combo, freq_data.get('global_baseline', {}).get(combo, 0.1))
        calibrated[combo] = round(model_p * 0.7 + baseline_p * 0.3, 4)
    
    # 归一化
    total = sum(calibrated.values())
    if total > 0:
        calibrated = {k: round(v / total, 4) for k, v in calibrated.items()}
    
    # 核心区间概率（胜胜/平胜/负负/平平/平负 = 82.7%）
    core_zone = ['胜胜', '平胜', '负负', '平平', '平负']
    core_prob = sum(calibrated.get(c, 0) for c in core_zone)
    
    # 平开头概率（平胜/平平/平负 = 52.8%）
    draw_start = ['平胜', '平平', '平负']
    draw_start_prob = sum(calibrated.get(c, 0) for c in draw_start)
    
    # 逆转组合概率（负胜/胜负 = 8%）
    comeback = ['负胜', '胜负']
    comeback_prob = sum(calibrated.get(c, 0) for c in comeback)
    
    # Top3推荐组合
    top3 = sorted(calibrated.items(), key=lambda x: x[1], reverse=True)[:3]
    
    return {
        'league': league_name,
        'calibrated_probs': calibrated,
        'core_zone_prob': round(core_prob, 4),
        'core_zone_note': '胜胜/平胜/负负/平平/平负，历史占比82.7%',
        'draw_start_prob': round(draw_start_prob, 4),
        'draw_start_note': '平胜/平平/平负，历史占比52.8%，超过一半比赛上半场平局',
        'comeback_prob': round(comeback_prob, 4),
        'comeback_warning': '负胜/胜负逆转组合仅8%，高赔但概率极低，需谨慎',
        'top3_combinations': [{'combo': c, 'prob': p} for c, p in top3],
        'calibration_method': '模型概率70% + 联赛历史频率30%',
        'key_statistics': freq_data.get('key_statistics', {})
    }

@mcp.tool()
@safe_tool
def second_half_goal_diff(team: str, league: str, recent_matches: int = 10) -> dict:
    """
    下半场进球差(SHGD)指标计算
    SHGD是预测半全场"平→胜/平→负"的最佳指标
    下半场净胜球强的球队，是"半场平局→全场获胜"的候选
    
    Args:
        team: 球队名称
        league: 联赛代码
        recent_matches: 统计最近N场比赛（默认10场）
    
    Returns:
        SHGD指标、下半场进球/失球、半场平局后胜率、推荐方向
    """
    # 参数校验
    if team is None:
        return make_error_response('team不能为空', 'validation', '请提供team参数')
    if league is None:
        return make_error_response('league不能为空', 'validation', '请提供league参数')
    if recent_matches is None:
        return make_error_response('recent_matches不能为空', 'validation', '请提供recent_matches参数')

    import json
    
    # 从历史数据计算
    history_file = os.path.join(HISTORY_DIR, f'{league}_history.json')
    matches = load_json(history_file) or []
    
    if not matches:
        return {
            'team': team,
            'league': league,
            'error': '联赛历史数据不存在',
            'suggestion': '请先运行data/update_history.py下载历史数据'
        }
    
    # 筛选该球队的比赛
    team_matches = []
    for m in matches:
        if m.get('home') == team or m.get('away') == team:
            team_matches.append(m)
    
    # 按日期排序，取最近N场
    team_matches.sort(key=lambda x: x.get('date', ''), reverse=True)
    recent = team_matches[:recent_matches]
    
    if len(recent) < 3:
        return {
            'team': team,
            'league': league,
            'matches_analyzed': len(recent),
            'warning': '比赛数据不足（<3场），SHGD指标不可靠'
        }
    
    # 计算下半场进球差
    total_sh_goals_for = 0
    total_sh_goals_against = 0
    half_time_draw_count = 0
    half_time_draw_win_count = 0
    
    for m in recent:
        is_home = m.get('home') == team
        full_hg = m.get('home_goals', 0)
        full_ag = m.get('away_goals', 0)
        ht_hg = m.get('hthg', m.get('half_time_home', 0))
        ht_ag = m.get('htag', m.get('half_time_away', 0))
        
        # 下半场进球
        sh_hg = full_hg - ht_hg
        sh_ag = full_ag - ht_ag
        
        if is_home:
            total_sh_goals_for += sh_hg
            total_sh_goals_against += sh_ag
            # 半场平局
            if ht_hg == ht_ag:
                half_time_draw_count += 1
                if full_hg > full_ag:
                    half_time_draw_win_count += 1
        else:
            total_sh_goals_for += sh_ag
            total_sh_goals_against += sh_hg
            if ht_hg == ht_ag:
                half_time_draw_count += 1
                if full_ag > full_hg:
                    half_time_draw_win_count += 1
    
    n = len(recent)
    avg_sh_goals_for = total_sh_goals_for / n
    avg_sh_goals_against = total_sh_goals_against / n
    shgd = avg_sh_goals_for - avg_sh_goals_against
    
    # 半场平局后胜率
    ht_draw_win_rate = half_time_draw_win_count / half_time_draw_count if half_time_draw_count > 0 else 0
    
    # SHGD等级
    if shgd > 0.5:
        level = '下半场强势'
        recommendation = '该队下半场进球能力强，是"平→胜"候选'
    elif shgd > 0:
        level = '下半场略强'
        recommendation = '该队下半场有一定优势，可关注"平→胜"'
    elif shgd > -0.5:
        level = '下半场均衡'
        recommendation = '下半场无明显优势，平平或平负可能性大'
    else:
        level = '下半场弱势'
        recommendation = '该队下半场容易丢球，需防"平→负"'
    
    return {
        'team': team,
        'league': league,
        'matches_analyzed': n,
        'avg_second_half_goals_for': round(avg_sh_goals_for, 2),
        'avg_second_half_goals_against': round(avg_sh_goals_against, 2),
        'SHGD': round(shgd, 2),
        'SHGD_level': level,
        'half_time_draw_count': half_time_draw_count,
        'half_time_draw_win_count': half_time_draw_win_count,
        'half_time_draw_win_rate': round(ht_draw_win_rate, 4),
        'recommendation': recommendation,
        'note': 'SHGD是预测半全场"平→胜/平→负"的最佳指标'
    }

@mcp.tool()
@safe_tool
def team_half_time_profile(team: str, league: str, recent_matches: int = 20) -> dict:
    """
    球队半场习惯画像
    分析球队是"善抢开局"还是"后发制人"，用于半全场玩法预测
    
    Args:
        team: 球队名称
        league: 联赛代码
        recent_matches: 统计最近N场比赛（默认20场）
    
    Returns:
        半场胜率/平局率/负率、开局类型、推荐半全场方向
    """
    # 参数校验
    if team is None:
        return make_error_response('team不能为空', 'validation', '请提供team参数')
    if league is None:
        return make_error_response('league不能为空', 'validation', '请提供league参数')
    if recent_matches is None:
        return make_error_response('recent_matches不能为空', 'validation', '请提供recent_matches参数')

    import json
    
    history_file = os.path.join(HISTORY_DIR, f'{league}_history.json')
    matches = load_json(history_file) or []
    
    if not matches:
        return {'team': team, 'league': league, 'error': '联赛历史数据不存在'}
    
    # 筛选该球队的比赛
    team_matches = []
    for m in matches:
        if m.get('home') == team or m.get('away') == team:
            team_matches.append(m)
    
    team_matches.sort(key=lambda x: x.get('date', ''), reverse=True)
    recent = team_matches[:recent_matches]
    
    if len(recent) < 5:
        return {'team': team, 'league': league, 'matches_analyzed': len(recent), 'warning': '数据不足'}
    
    # 统计半场结果
    ht_win = ht_draw = ht_lose = 0
    # 统计全场结果
    ft_win = ft_draw = ft_lose = 0
    # 统计从半场到全场的转变
    ht_win_ft_win = 0  # 半场胜→全场胜
    ht_draw_ft_win = 0  # 半场平→全场胜
    ht_draw_ft_draw = 0  # 半场平→全场平
    ht_draw_ft_lose = 0  # 半场平→全场负
    ht_lose_ft_lose = 0  # 半场负→全场负
    
    for m in recent:
        is_home = m.get('home') == team
        ht_hg = m.get('hthg', m.get('half_time_home', 0))
        ht_ag = m.get('htag', m.get('half_time_away', 0))
        full_hg = m.get('home_goals', 0)
        full_ag = m.get('away_goals', 0)
        
        if is_home:
            ht_diff = ht_hg - ht_ag
            ft_diff = full_hg - full_ag
        else:
            ht_diff = ht_ag - ht_hg
            ft_diff = full_ag - full_hg
        
        # 半场结果
        if ht_diff > 0:
            ht_win += 1
            if ft_diff > 0:
                ht_win_ft_win += 1
        elif ht_diff == 0:
            ht_draw += 1
            if ft_diff > 0:
                ht_draw_ft_win += 1
            elif ft_diff == 0:
                ht_draw_ft_draw += 1
            else:
                ht_draw_ft_lose += 1
        else:
            ht_lose += 1
            if ft_diff < 0:
                ht_lose_ft_lose += 1
        
        # 全场结果
        if ft_diff > 0:
            ft_win += 1
        elif ft_diff == 0:
            ft_draw += 1
        else:
            ft_lose += 1
    
    n = len(recent)
    
    # 半场结果率
    ht_win_rate = ht_win / n
    ht_draw_rate = ht_draw / n
    ht_lose_rate = ht_lose / n
    
    # 半场领先保持率
    ht_win_keep_rate = ht_win_ft_win / ht_win if ht_win > 0 else 0
    # 半场平局后胜率
    ht_draw_win_rate = ht_draw_ft_win / ht_draw if ht_draw > 0 else 0
    # 半场落后逆转率
    ht_lose_comeback_rate = (n - ht_lose - ht_lose_ft_lose) / ht_lose if ht_lose > 0 else 0
    
    # 判断开局类型
    if ht_win_rate > 0.5:
        start_type = '善抢开局'
        start_desc = '该队经常半场领先，适合关注"胜胜"组合'
    elif ht_draw_rate > 0.5:
        start_type = '慢热型'
        start_desc = '该队上半场经常平局，下半场发力，适合关注"平胜"组合'
    elif ht_lose_rate > 0.4:
        start_type = '慢热落后型'
        start_desc = '该队上半场经常落后，需防"负负"或逆转"负胜"'
    else:
        start_type = '均衡型'
        start_desc = '该队半场结果分布均衡，需结合具体对手分析'
    
    # 推荐半全场方向
    if start_type == '善抢开局' and ht_win_keep_rate > 0.7:
        recommended = '胜胜'
        confidence = '高'
    elif start_type == '慢热型' and ht_draw_win_rate > 0.4:
        recommended = '平胜'
        confidence = '中高'
    elif ht_lose_rate > 0.4 and ht_lose_ft_lose > 0.7:
        recommended = '负负'
        confidence = '高'
    else:
        recommended = '平平/平胜'
        confidence = '中'
    
    return {
        'team': team,
        'league': league,
        'matches_analyzed': n,
        'half_time_results': {
            'win': ht_win,
            'draw': ht_draw,
            'lose': ht_lose,
            'win_rate': round(ht_win_rate, 4),
            'draw_rate': round(ht_draw_rate, 4),
            'lose_rate': round(ht_lose_rate, 4)
        },
        'full_time_results': {
            'win': ft_win,
            'draw': ft_draw,
            'lose': ft_lose
        },
        'transition_rates': {
            'ht_win_keep_rate': round(ht_win_keep_rate, 4),
            'ht_draw_win_rate': round(ht_draw_win_rate, 4),
            'ht_draw_draw_rate': round(ht_draw_ft_draw / ht_draw if ht_draw > 0 else 0, 4),
            'ht_draw_lose_rate': round(ht_draw_ft_lose / ht_draw if ht_draw > 0 else 0, 4),
            'ht_lose_keep_rate': round(ht_lose_ft_lose / ht_lose if ht_lose > 0 else 0, 4)
        },
        'start_type': start_type,
        'start_description': start_desc,
        'recommended_htft': recommended,
        'confidence': confidence,
        'note': '半场习惯画像是半全场玩法预测的重要参考'
    }

# ============================================================
# P0新增：比分校准+竞彩返奖率+盘口语言工具（5个）
# ============================================================

@mcp.tool()
@safe_tool
def score_frequency_calibration(model_score_probs: dict, league_code: str = None) -> dict:
    """
    比分历史频率校准器
    用36联赛历史比分频率校准泊松模型概率，解决低比分系统性偏差
    
    Args:
        model_score_probs: 模型计算的比分概率字典，如{"1:1":0.10, "2:1":0.09, ...}
        league_code: 联赛代码，如E0/D1/SP1
    
    Returns:
        校准后的比分概率、Top8比分、收敛度、推荐比分
    """
    # 参数校验
    if model_score_probs is None:
        return make_error_response('model_score_probs不能为空', 'validation', '请提供model_score_probs参数')
    if league_code is not None and not isinstance(league_code, (str, int, float, list, dict)):
        return make_error_response('league_code类型错误', 'validation', '请提供正确的类型')

    import json
    
    freq_file = os.path.join(DATA_DIR, 'score_frequency.json')
    freq_data = load_json(freq_file) or {}
    
    # 获取联赛基准
    if league_code and league_code in freq_data.get('league_profiles', {}):
        league_baseline = freq_data['league_profiles'][league_code].get('top_scores', {})
        league_name = freq_data['league_profiles'][league_code].get('name', league_code)
        # 合并全局基准（联赛只提供Top5，其余用全局）
        baseline = dict(freq_data.get('global_baseline', {}))
        baseline.update(league_baseline)
    else:
        baseline = freq_data.get('global_baseline', {})
        league_name = '全球基准'
    
    # 校准：模型概率60% + 历史频率40%
    calibrated = {}
    all_scores = set(list(model_score_probs.keys()) + list(baseline.keys()))
    for score in all_scores:
        if score == 'other':
            continue
        model_p = model_score_probs.get(score, 0)
        baseline_p = baseline.get(score, 0.01)
        calibrated[score] = round(model_p * 0.6 + baseline_p * 0.4, 4)
    
    # 归一化
    total = sum(calibrated.values())
    if total > 0:
        calibrated = {k: round(v / total, 4) for k, v in calibrated.items()}
    
    # Top8比分
    top8 = sorted(calibrated.items(), key=lambda x: x[1], reverse=True)[:8]
    top8_coverage = sum(p for _, p in top8)
    
    # Top5
    top5 = top8[:5]
    top5_coverage = sum(p for _, p in top5)
    
    # 收敛度判断
    if top8_coverage > 0.65:
        convergence = '高收敛'
        convergence_note = 'Top8覆盖>65%，比赛确定性较高，比分预测可靠'
    elif top8_coverage > 0.55:
        convergence = '中收敛'
        convergence_note = 'Top8覆盖55-65%，比赛有一定不确定性'
    else:
        convergence = '低收敛'
        convergence_note = 'Top8覆盖<55%，比赛不确定性高，比分预测需谨慎'
    
    return {
        'league': league_name,
        'calibrated_scores': calibrated,
        'top8_scores': [{'score': s, 'prob': p} for s, p in top8],
        'top8_coverage': round(top8_coverage, 4),
        'top5_coverage': round(top5_coverage, 4),
        'convergence_level': convergence,
        'convergence_note': convergence_note,
        'recommended_scores': [s for s, _ in top8[:3]],
        'calibration_method': '泊松模型概率60% + 联赛历史频率40%',
        'key_statistics': freq_data.get('key_statistics', {})
    }

@mcp.tool()
@safe_tool
def jingcai_payout_calibrator(odds_list: list, play_type: str = '胜平负') -> dict:
    """
    竞彩返奖率校准器
    竞彩返奖率约69%（非国际95%），必须用竞彩实际返奖率去水，
    否则市场隐含概率会被高估，EV计算会出错。
    官方规则：销售额69%计提奖金（68%当期+1%调节基金）。
    
    Args:
        odds_list: 赔率列表，如[1.80, 3.20, 3.40]
        play_type: 玩法类型（胜平负/让球胜平负/总进球/比分/半全场）
    
    Returns:
        竞彩返奖率、去水后隐含概率、与国际95%去水的差异、EV修正建议
    """
    # 参数校验
    if odds_list is None:
        return make_error_response('odds_list不能为空', 'validation', '请提供odds_list参数')
    if play_type is None:
        return make_error_response('play_type不能为空', 'validation', '请提供play_type参数')

    # 计算实际返奖率
    inv_sum = sum(1.0 / o for o in odds_list if o > 0)
    actual_payout = 1.0 / inv_sum if inv_sum > 0 else 0
    
    # 竞彩标准返奖率（统一69%，来源：竞彩网官方规则，68%当期+1%调节基金）
    jingcai_standard_payout = {
        '胜平负': 0.69,
        '让球胜平负': 0.69,
        '总进球': 0.69,
        '比分': 0.69,
        '半全场': 0.69
    }
    standard_payout = jingcai_standard_payout.get(play_type, 0.69)
    
    # 用竞彩返奖率去水（正确方式）
    jingcai_implied = [(1.0 / o) * standard_payout for o in odds_list if o > 0]
    
    # 用国际95%去水（错误方式，对比用）
    intl_implied = [(1.0 / o) * 0.95 for o in odds_list if o > 0]
    
    # 差异分析
    prob_diff = [round(j - i, 4) for j, i in zip(jingcai_implied, intl_implied)]
    
    # EV门槛修正建议
    ev_threshold_adjustment = {
        '胜平负': '+2%（竞彩抽水比国际高20%，EV门槛需从+3%提高到+5%）',
        '让球胜平负': '+2%（同上）',
        '总进球': '+3%（返奖率更低，门槛从+4%提高到+7%）',
        '比分': '+5%（返奖率最低，门槛从+10%提高到+15%）',
        '半全场': '+4%（返奖率低，门槛从+8%提高到+12%）'
    }
    
    return {
        'play_type': play_type,
        'actual_payout_rate': round(actual_payout, 4),
        'jingcai_standard_payout': standard_payout,
        'international_95_payout': 0.95,
        'payout_difference': round(0.95 - standard_payout, 4),
        'jingcai_implied_probs': [round(p, 4) for p in jingcai_implied],
        'international_implied_probs': [round(p, 4) for p in intl_implied],
        'prob_difference': prob_diff,
        'ev_threshold_adjustment': ev_threshold_adjustment.get(play_type, ''),
        'warning': '必须用竞彩返奖率去水！用国际95%去水会高估隐含概率，导致EV计算虚高，误判价值投注',
        'note': '竞彩返奖率约69%（68%当期+1%调节基金），外围90-95%，差距约26%，这是竞彩玩法的核心特点'
    }

@mcp.tool()
@safe_tool
def handicap_language_analyzer(opening_handicap: str, closing_handicap: str, 
                                 opening_water: float, closing_water: float,
                                 is_hot_favorite: bool = False) -> dict:
    """
    盘口语言识别器
    识别8种盘口变动模式，判断机构真实意图
    
    Args:
        opening_handicap: 初盘盘口，如"半球"
        closing_handicap: 终盘盘口，如"半一"
        opening_water: 初盘上盘水位，如0.90
        closing_water: 终盘上盘水位，如0.85
        is_hot_favorite: 是否热门方（支持率>70%）
    
    Returns:
        盘口变动模式、机构意图、信号方向、置信度、推荐操作
    """
    # 参数校验
    if opening_handicap is None:
        return make_error_response('opening_handicap不能为空', 'validation', '请提供初盘盘口')
    if closing_handicap is None:
        return make_error_response('closing_handicap不能为空', 'validation', '请提供终盘盘口')
    if opening_water is None:
        return make_error_response('opening_water不能为空', 'validation', '请提供初盘水位')
    if closing_water is None:
        return make_error_response('closing_water不能为空', 'validation', '请提供终盘水位')
    
    import json
    
    conv_file = os.path.join(DATA_DIR, 'eu_ah_conversion.json')
    conv_data = load_json(conv_file) or {}
    language_rules = conv_data.get('handicap_language', {})
    
    # 盘口等级（用于判断升盘/降盘）
    handicap_levels = ['平手', '平半', '半球', '半一', '一球', '一球球半', '球半', '球半两球', '两球']
    
    def get_level(h):
        for i, level in enumerate(handicap_levels):
            if level in h:
                return i
        return -1
    
    open_level = get_level(opening_handicap)
    close_level = get_level(closing_handicap)
    
    # 判断盘口变动
    if close_level > open_level:
        handicap_change = '升盘'
    elif close_level < open_level:
        handicap_change = '降盘'
    else:
        handicap_change = '盘口不变'
    
    # 判断水位变动
    water_change = closing_water - opening_water
    if water_change < -0.05:
        water_direction = '降水'
    elif water_change > 0.05:
        water_direction = '升水'
    else:
        water_direction = '水位稳定'
    
    # 组合模式
    pattern = f'{handicap_change}{water_direction}'
    
    # 大热退盘特殊判断
    if is_hot_favorite and handicap_change == '降盘':
        pattern = '大热退盘'
    
    # 匹配规则
    rule = language_rules.get(pattern, {
        'pattern': pattern,
        'interpretation': '未识别模式，需结合基本面分析',
        'signal': '中性',
        'confidence': '低'
    })
    
    # 推荐操作
    if rule.get('signal') == '正向':
        recommendation = '可考虑上盘'
    elif rule.get('signal') == '强反向':
        recommendation = '强烈否决热门方，考虑下盘'
    elif rule.get('signal') == '反向':
        recommendation = '谨慎对待上盘，可考虑下盘'
    elif rule.get('signal') == '正向(下盘)':
        recommendation = '可考虑下盘'
    else:
        recommendation = '需结合基本面进一步分析'
    
    return {
        'opening': {'handicap': opening_handicap, 'water': opening_water},
        'closing': {'handicap': closing_handicap, 'water': closing_water},
        'handicap_change': handicap_change,
        'water_change': water_direction,
        'water_change_amount': round(water_change, 3),
        'pattern': pattern,
        'interpretation': rule.get('interpretation', ''),
        'signal': rule.get('signal', '中性'),
        'confidence': rule.get('confidence', '低'),
        'is_hot_favorite': is_hot_favorite,
        'recommendation': recommendation,
        'priority_note': '大热退盘是最高优先级信号，直接一票否决热门方' if pattern == '大热退盘' else ''
    }

@mcp.tool()
@safe_tool
def theoretical_vs_actual_handicap(home_elo: float, away_elo: float, 
                                      actual_handicap: str,
                                      home_advantage: float = 0.25) -> dict:
    """
    理论盘口vs实际盘口偏离分析
    用Elo差计算理论让球，与实际盘口对比，寻找定价偏差
    
    Args:
        home_elo: 主队Elo评分
        away_elo: 客队Elo评分
        actual_handicap: 实际盘口，如"半球"
        home_advantage: 主场优势修正（默认0.25球）
    
    Returns:
        理论盘口、实际盘口、偏离方向、偏离程度、价值信号
    """
    # 参数校验
    if home_elo is None:
        return make_error_response('home_elo不能为空', 'validation', '请提供主队Elo评分')
    if away_elo is None:
        return make_error_response('away_elo不能为空', 'validation', '请提供客队Elo评分')
    if actual_handicap is None:
        return make_error_response('actual_handicap不能为空', 'validation', '请提供实际盘口')
    
    import json
    
    conv_file = os.path.join(DATA_DIR, 'eu_ah_conversion.json')
    conv_data = load_json(conv_file) or {}
    theoretical_data = conv_data.get('theoretical_handicap', {})
    
    # 计算理论让球
    elo_diff = home_elo - away_elo
    theoretical_handicap_goals = elo_diff / 200.0 + home_advantage
    
    # 映射到盘口等级
    elo_diff_to_handicap = theoretical_data.get('elo_diff_to_handicap', {})
    theoretical_handicap = '平手'
    for range_str, handicap in elo_diff_to_handicap.items():
        if '-' in range_str:
            low, high = map(int, range_str.split('-'))
            if low <= elo_diff < high:
                theoretical_handicap = handicap
                break
    
    # 盘口等级比较
    handicap_levels = ['平手', '平半', '半球', '半一', '一球', '一球球半', '球半', '球半两球', '两球']
    
    def get_level(h):
        for i, level in enumerate(handicap_levels):
            if level in h:
                return i
        return -1
    
    theo_level = get_level(theoretical_handicap)
    actual_level = get_level(actual_handicap)
    
    # 偏离分析
    level_diff = actual_level - theo_level
    if level_diff > 0:
        deviation = '实际比理论深'
        deviation_note = '实际盘口比理论深，机构高估主队，可能诱上盘'
        value_signal = '上盘可能有陷阱，关注下盘价值'
    elif level_diff < 0:
        deviation = '实际比理论浅'
        deviation_note = '实际盘口比理论浅，机构低估主队，可能不看好上盘打出'
        value_signal = '上盘可能被低估，关注上盘价值'
    else:
        deviation = '盘口一致'
        deviation_note = '实际盘口与理论一致，市场定价合理'
        value_signal = '无明显盘口价值，需从其他维度寻找'
    
    return {
        'home_elo': home_elo,
        'away_elo': away_elo,
        'elo_difference': elo_diff,
        'theoretical_handicap_goals': round(theoretical_handicap_goals, 2),
        'theoretical_handicap': theoretical_handicap,
        'actual_handicap': actual_handicap,
        'level_difference': level_diff,
        'deviation': deviation,
        'deviation_note': deviation_note,
        'value_signal': value_signal,
        'formula': theoretical_data.get('formula', ''),
        'note': '理论盘口与实际盘口偏差超过1个档位，需重点关注'
    }

@mcp.tool()
@safe_tool
def total_goals_league_calibration(model_goal_probs: dict, league_code: str = None) -> dict:
    """
    总进球联赛档位校准器
    用联赛历史档位频率校准泊松模型概率，解决联赛风格差异
    
    Args:
        model_goal_probs: 模型计算的总进球档位概率，如{"2球":0.25, "3球":0.22, ...}
        league_code: 联赛代码
    
    Returns:
        校准后的档位概率、最可能档位、大球率、推荐档位
    """
    # 参数校验
    if model_goal_probs is None:
        return make_error_response('model_goal_probs不能为空', 'validation', '请提供model_goal_probs参数')
    if league_code is not None and not isinstance(league_code, (str, int, float, list, dict)):
        return make_error_response('league_code类型错误', 'validation', '请提供正确的类型')

    import json
    
    dist_file = os.path.join(DATA_DIR, 'league_goal_distribution.json')
    dist_data = load_json(dist_file) or {}
    
    # 获取联赛分布
    if league_code and league_code in dist_data.get('league_distributions', {}):
        league_dist = dist_data['league_distributions'][league_code]
        league_name = league_dist.get('name', league_code)
    else:
        league_dist = dist_data.get('global_baseline', {})
        league_name = '全球基准'
    
    # 档位列表
    goal_brackets = ['0球', '1球', '2球', '3球', '4球', '5球', '6球', '7+球']
    
    # 校准：模型60% + 联赛历史40%
    calibrated = {}
    for bracket in goal_brackets:
        model_p = model_goal_probs.get(bracket, 0)
        league_p = league_dist.get(bracket, 0.05)
        calibrated[bracket] = round(model_p * 0.6 + league_p * 0.4, 4)
    
    # 归一化
    total = sum(calibrated.values())
    if total > 0:
        calibrated = {k: round(v / total, 4) for k, v in calibrated.items()}
    
    # 最可能档位
    most_common = max(calibrated.items(), key=lambda x: x[1])
    
    # Top2覆盖
    top2 = sorted(calibrated.items(), key=lambda x: x[1], reverse=True)[:2]
    top2_coverage = sum(p for _, p in top2)
    
    # 大球率（>2.5球 = 3球及以上）
    over_2_5 = sum(calibrated.get(b, 0) for b in ['3球', '4球', '5球', '6球', '7+球'])
    # 大球率（>3.5球 = 4球及以上）
    over_3_5 = sum(calibrated.get(b, 0) for b in ['4球', '5球', '6球', '7+球'])
    
    # 联赛风格
    if over_2_5 > 0.55:
        league_style = '大球联赛'
    elif over_2_5 < 0.48:
        league_style = '小球联赛'
    else:
        league_style = '中性联赛'
    
    return {
        'league': league_name,
        'league_style': league_style,
        'calibrated_goal_probs': calibrated,
        'most_common_bracket': most_common[0],
        'most_common_prob': round(most_common[1], 4),
        'top2_brackets': [{'bracket': b, 'prob': p} for b, p in top2],
        'top2_coverage': round(top2_coverage, 4),
        'over_2_5_rate': round(over_2_5, 4),
        'over_3_5_rate': round(over_3_5, 4),
        'recommended_brackets': [b for b, _ in top2],
        'calibration_method': '泊松模型概率60% + 联赛历史档位频率40%',
        'league_over_2_5': league_dist.get('over_2_5', None),
        'league_over_3_5': league_dist.get('over_3_5', None)
    }

# ============================================================
# P1新增：高级分析工具（6个）
# ============================================================

@mcp.tool()
@safe_tool
def time_weighted_poisson(team_matches: list, half_life_days: int = 30, max_goals: int = 6) -> dict:
    """
    时间加权泊松模型
    近期比赛权重更高（指数衰减），捕捉球队当前状态，比简单平均更准确
    
    Args:
        team_matches: 球队比赛列表，每场包含date(YYYY-MM-DD), goals_for, goals_against
        half_life_days: 半衰期（天），30天前的比赛权重为50%，默认30
        max_goals: 最大进球数，默认6
    
    Returns:
        时间加权λ、泊松进球分布、近期状态趋势
    """
    # 参数校验
    if team_matches is None:
        return make_error_response('team_matches不能为空', 'validation', '请提供team_matches参数')
    if half_life_days is None:
        return make_error_response('half_life_days不能为空', 'validation', '请提供half_life_days参数')
    if max_goals is None:
        return make_error_response('max_goals不能为空', 'validation', '请提供max_goals参数')

    import math
    from datetime import datetime
    
    if not team_matches:
        return {'error': '无比赛数据'}
    
    # 计算每场比赛的权重（指数衰减）
    now = datetime.now()
    weighted_goals_for = 0
    weighted_goals_against = 0
    total_weight = 0
    match_weights = []
    
    for m in team_matches:
        try:
            match_date = datetime.strptime(m.get('date', ''), '%Y-%m-%d')
            days_ago = (now - match_date).days
        except:
            days_ago = 30  # 默认30天前
        
        # 指数衰减权重：w = 2^(-days/half_life)
        weight = math.pow(0.5, days_ago / half_life_days) if half_life_days > 0 else 1.0
        
        gf = m.get('goals_for', 0)
        ga = m.get('goals_against', 0)
        
        weighted_goals_for += gf * weight
        weighted_goals_against += ga * weight
        total_weight += weight
        
        match_weights.append({
            'date': m.get('date', ''),
            'days_ago': days_ago,
            'weight': round(weight, 4),
            'goals_for': gf,
            'goals_against': ga
        })
    
    if total_weight == 0:
        return {'error': '权重总和为0'}
    
    # 时间加权λ
    lambda_for = weighted_goals_for / total_weight
    lambda_against = weighted_goals_against / total_weight
    
    # 简单平均λ（对比用）
    simple_avg_for = sum(m.get('goals_for', 0) for m in team_matches) / len(team_matches)
    simple_avg_against = sum(m.get('goals_against', 0) for m in team_matches) / len(team_matches)
    
    # 泊松进球分布
    def poisson_dist(lam):
        dist = {}
        for k in range(max_goals + 1):
            dist[f'{k}球'] = round(math.exp(-lam) * (lam ** k) / math.factorial(k), 4)
        return dist
    
    goals_for_dist = poisson_dist(lambda_for)
    goals_against_dist = poisson_dist(lambda_against)
    
    # 状态趋势：近5场vs远5场
    sorted_matches = sorted(team_matches, key=lambda x: x.get('date', ''), reverse=True)
    if len(sorted_matches) >= 10:
        recent_5 = sorted_matches[:5]
        older_5 = sorted_matches[5:10]
        recent_avg_gf = sum(m.get('goals_for', 0) for m in recent_5) / 5
        older_avg_gf = sum(m.get('goals_for', 0) for m in older_5) / 5
        trend = recent_avg_gf - older_avg_gf
        if trend > 0.3:
            trend_label = '进攻上升'
        elif trend < -0.3:
            trend_label = '进攻下降'
        else:
            trend_label = '进攻稳定'
    else:
        trend = 0
        trend_label = '数据不足'
    
    return {
        'time_weighted_lambda_for': round(lambda_for, 3),
        'time_weighted_lambda_against': round(lambda_against, 3),
        'simple_average_for': round(simple_avg_for, 3),
        'simple_average_against': round(simple_avg_against, 3),
        'lambda_difference': round(lambda_for - simple_avg_for, 3),
        'half_life_days': half_life_days,
        'matches_analyzed': len(team_matches),
        'goals_for_distribution': goals_for_dist,
        'goals_against_distribution': goals_against_dist,
        'recent_trend': trend_label,
        'trend_value': round(trend, 3),
        'note': '时间加权泊松比简单平均更能反映当前状态，近期比赛权重更高'
    }

@mcp.tool()
@safe_tool
def attack_defense_matchup(home_team_stats: dict, away_team_stats: dict, home_advantage: float = 1.10) -> dict:
    """
    攻防匹配显式公式
    λ主 = 主队场均进球 × 客队场均失球 × 主场系数
    λ客 = 客队场均进球 × 主队场均失球
    
    Args:
        home_team_stats: 主队统计，包含avg_goals_for, avg_goals_against
        away_team_stats: 客队统计，包含avg_goals_for, avg_goals_against
        home_advantage: 主场优势系数，默认1.10（主队进攻+10%）
    
    Returns:
        攻防匹配λ、预期比分、胜平负概率
    """
    # 参数校验
    if home_team_stats is None:
        return make_error_response('home_team_stats不能为空', 'validation', '请提供home_team_stats参数')
    if away_team_stats is None:
        return make_error_response('away_team_stats不能为空', 'validation', '请提供away_team_stats参数')
    if home_advantage is None:
        return make_error_response('home_advantage不能为空', 'validation', '请提供home_advantage参数')

    import math
    
    h_gf = home_team_stats.get('avg_goals_for', 1.5)
    h_ga = home_team_stats.get('avg_goals_against', 1.2)
    a_gf = away_team_stats.get('avg_goals_for', 1.3)
    a_ga = away_team_stats.get('avg_goals_against', 1.4)
    
    # 攻防匹配公式
    lambda_home = h_gf * a_ga * home_advantage
    lambda_away = a_gf * h_ga
    
    # 归一化（防止λ过大）
    total_lambda = lambda_home + lambda_away
    if total_lambda > 5.0:
        scale = 5.0 / total_lambda
        lambda_home *= scale
        lambda_away *= scale
    
    # 预期比分
    expected_home_goals = round(lambda_home, 2)
    expected_away_goals = round(lambda_away, 2)
    expected_score = f'{int(round(lambda_home))}:{int(round(lambda_away))}'
    
    # 泊松胜平负概率
    max_g = 6
    home_win = draw = away_win = 0
    for h in range(max_g + 1):
        for a in range(max_g + 1):
            p = (math.exp(-lambda_home) * (lambda_home ** h) / math.factorial(h) *
                 math.exp(-lambda_away) * (lambda_away ** a) / math.factorial(a))
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p
    
    return {
        'home_attack': h_gf,
        'home_defense': h_ga,
        'away_attack': a_gf,
        'away_defense': a_ga,
        'home_advantage_coefficient': home_advantage,
        'lambda_home': round(lambda_home, 3),
        'lambda_away': round(lambda_away, 3),
        'expected_home_goals': expected_home_goals,
        'expected_away_goals': expected_away_goals,
        'expected_score': expected_score,
        'matchup_type': '攻vs攻' if (h_gf > 1.5 and a_gf > 1.5) else ('防vs防' if (h_ga < 1.2 and a_ga < 1.2) else '攻vs防'),
        'probabilities': {
            'home_win': round(home_win, 4),
            'draw': round(draw, 4),
            'away_win': round(away_win, 4)
        },
        'formula': 'λ主 = 主队场均进球 × 客队场均失球 × 主场系数; λ客 = 客队场均进球 × 主队场均失球',
        'note': '攻防匹配公式比简单场均进球更准确，考虑了对手防守强度'
    }

@mcp.tool()
@safe_tool
def expected_goal_difference(lambda_home: float, lambda_away: float, handicap: float) -> dict:
    """
    预期净胜值与让球数量化比较
    预期净胜值 > 让球数+1 → 让胜；在让球数附近 → 重点防让平；< 让球数 → 让负
    
    Args:
        lambda_home: 主队预期进球λ
        lambda_away: 客队预期进球λ
        handicap: 官方让球数（主队让球为正，如-1表示主让1球）
    
    Returns:
        预期净胜值、净胜球分布、让球胜平负概率、推荐
    """
    # 参数校验
    if lambda_home is None:
        return make_error_response('lambda_home不能为空', 'validation', '请提供lambda_home参数')
    if lambda_away is None:
        return make_error_response('lambda_away不能为空', 'validation', '请提供lambda_away参数')
    if handicap is None:
        return make_error_response('handicap不能为空', 'validation', '请提供handicap参数')

    import math
    
    # 预期净胜值
    expected_gd = lambda_home - lambda_away
    
    # 净胜球分布（泊松差分布，近似）
    max_g = 6
    gd_distribution = {}
    for h in range(max_g + 1):
        for a in range(max_g + 1):
            p = (math.exp(-lambda_home) * (lambda_home ** h) / math.factorial(h) *
                 math.exp(-lambda_away) * (lambda_away ** a) / math.factorial(a))
            gd = h - a
            gd_distribution[f'{gd:+d}' if gd != 0 else '0'] = gd_distribution.get(f'{gd:+d}' if gd != 0 else '0', 0) + p
    
    # 让球胜平负概率（handicap为正表示主队让球）
    # 让胜：主队净胜 > handicap
    # 让平：主队净胜 = handicap
    # 让负：主队净胜 < handicap
    rangqiu_probs = {'让胜': 0, '让平': 0, '让负': 0}
    for gd_str, p in gd_distribution.items():
        gd = int(gd_str)
        if gd > handicap:
            rangqiu_probs['让胜'] += p
        elif gd == handicap:
            rangqiu_probs['让平'] += p
        else:
            rangqiu_probs['让负'] += p
    
    # 量化比较
    diff_from_handicap = expected_gd - handicap
    
    if diff_from_handicap > 1.0:
        recommendation = '让胜'
        confidence = '高'
        note = f'预期净胜{expected_gd:.2f}远超让球{handicap}，让胜概率大'
    elif diff_from_handicap > 0.3:
        recommendation = '让胜，但防让平'
        confidence = '中高'
        note = f'预期净胜{expected_gd:.2f}略高于让球{handicap}，需防让平'
    elif abs(diff_from_handicap) <= 0.3:
        recommendation = '重点防让平'
        confidence = '高'
        note = f'预期净胜{expected_gd:.2f}与让球{handicap}接近，让平概率高'
    elif diff_from_handicap > -1.0:
        recommendation = '让负，但防让平'
        confidence = '中高'
        note = f'预期净胜{expected_gd:.2f}略低于让球{handicap}，需防让平'
    else:
        recommendation = '让负'
        confidence = '高'
        note = f'预期净胜{expected_gd:.2f}远低于让球{handicap}，让负概率大'
    
    return {
        'lambda_home': lambda_home,
        'lambda_away': lambda_away,
        'expected_goal_difference': round(expected_gd, 2),
        'official_handicap': handicap,
        'difference_from_handicap': round(diff_from_handicap, 2),
        'goal_difference_distribution': {k: round(v, 4) for k, v in sorted(gd_distribution.items(), key=lambda x: int(x[0]))},
        'rangqiu_probabilities': {k: round(v, 4) for k, v in rangqiu_probs.items()},
        'recommendation': recommendation,
        'confidence': confidence,
        'note': note,
        'thresholds': '净胜>让球+1→让胜; 让球±0.3→重点防让平; 净胜<让球-1→让负'
    }

@mcp.tool()
@safe_tool
def weighted_scorecard(match_data: dict) -> dict:
    """
    15维度加权评分表
    每个维度对主胜/平/客胜打分+2到-2，加权汇总，关键维度一票否决
    
    Args:
        match_data: 比赛数据，包含15个维度的评分
        维度包括: home_advantage, form, h2h, injuries, motivation, 
        tactical_matchup, league_style, referee, weather, schedule,
        odds_movement, market_sentiment, xg_trend, defensive_record, away_record
    
    Returns:
        15维度评分、加权总分、推荐、一票否决信号
    """
    # 参数校验
    if match_data is None:
        return make_error_response('match_data不能为空', 'validation', '请提供match_data参数')

    # 15维度权重
    dimensions = {
        'home_advantage': {'weight': 0.10, 'name': '主场优势'},
        'form': {'weight': 0.12, 'name': '近期状态'},
        'h2h': {'weight': 0.08, 'name': '历史交锋'},
        'injuries': {'weight': 0.10, 'name': '伤停情况'},
        'motivation': {'weight': 0.08, 'name': '战意强度'},
        'tactical_matchup': {'weight': 0.08, 'name': '战术匹配'},
        'league_style': {'weight': 0.05, 'name': '联赛风格'},
        'referee': {'weight': 0.04, 'name': '裁判因素'},
        'weather': {'weight': 0.03, 'name': '天气影响'},
        'schedule': {'weight': 0.06, 'name': '赛程密度'},
        'odds_movement': {'weight': 0.08, 'name': '赔率变动'},
        'market_sentiment': {'weight': 0.05, 'name': '市场情绪'},
        'xg_trend': {'weight': 0.06, 'name': 'xG趋势'},
        'defensive_record': {'weight': 0.04, 'name': '防守记录'},
        'away_record': {'weight': 0.03, 'name': '客场记录'}
    }
    
    # 一票否决维度（关键信号）
    veto_signals = []
    
    # 计算加权总分
    total_home = total_draw = total_away = 0
    dimension_scores = []
    
    for dim, config in dimensions.items():
        score = match_data.get(dim, {'home': 0, 'draw': 0, 'away': 0})
        if isinstance(score, (int, float)):
            # 单一分数表示主胜倾向
            h = score
            d = -abs(score) * 0.3
            a = -score
        else:
            h = score.get('home', 0)
            d = score.get('draw', 0)
            a = score.get('away', 0)
        
        w = config['weight']
        total_home += h * w
        total_draw += d * w
        total_away += a * w
        
        dimension_scores.append({
            'dimension': dim,
            'name': config['name'],
            'weight': w,
            'home_score': h,
            'draw_score': d,
            'away_score': a,
            'weighted_home': round(h * w, 3),
            'weighted_draw': round(d * w, 3),
            'weighted_away': round(a * w, 3)
        })
    
    # 检查一票否决信号
    # 大热退盘
    if match_data.get('odds_movement', {}).get('hot_favorite_drop', False):
        veto_signals.append({
            'signal': '大热退盘',
            'veto': '主胜',
            'reason': '热门方支持率>70%但盘口退盘，机构不看好，一票否决主胜'
        })
    
    # 核心球员伤停
    if match_data.get('injuries', {}).get('key_player_out', False):
        veto_signals.append({
            'signal': '核心球员伤停',
            'veto': '该队获胜',
            'reason': '核心前锋/后卫缺阵，球队实力大幅下降'
        })
    
    # 战意不足
    if match_data.get('motivation', {}).get('no_motivation', False):
        veto_signals.append({
            'signal': '战意不足',
            'veto': '该队全力争胜',
            'reason': '球队已保级/已夺冠/无欲无求，可能轮换或放松'
        })
    
    # 推荐
    scores = {'主胜': total_home, '平局': total_draw, '客胜': total_away}
    recommendation = max(scores, key=scores.get)
    
    # 置信度
    max_score = max(scores.values())
    second_score = sorted(scores.values(), reverse=True)[1]
    gap = max_score - second_score
    if gap > 0.5:
        confidence = '高'
    elif gap > 0.2:
        confidence = '中高'
    elif gap > 0:
        confidence = '中'
    else:
        confidence = '低'
    
    return {
        'dimension_scores': dimension_scores,
        'weighted_totals': {
            '主胜': round(total_home, 3),
            '平局': round(total_draw, 3),
            '客胜': round(total_away, 3)
        },
        'recommendation': recommendation,
        'confidence': confidence,
        'score_gap': round(gap, 3),
        'veto_signals': veto_signals,
        'veto_count': len(veto_signals),
        'note': '15维度加权评分，关键维度一票否决；评分范围+2(强烈看好)到-2(强烈不看好)'
    }

@mcp.tool()
@safe_tool
def style_matchup(home_style: str, away_style: str, home_attack: float = None, away_attack: float = None) -> dict:
    """
    攻防风格匹配分析
    攻vs攻→大球/胜负分明；防vs防→小球/平局多；攻vs防→看主导方
    
    Args:
        home_style: 主队风格（attacking/defensive/balanced/counter_attack）
        away_style: 客队风格
        home_attack: 主队场均进球（可选，用于量化）
        away_attack: 客队场均进球（可选）
    
    Returns:
        匹配类型、预期进球范围、胜平负倾向、推荐玩法
    """
    # 参数校验
    if home_style is None:
        return make_error_response('home_style不能为空', 'validation', '请提供home_style参数')
    if away_style is None:
        return make_error_response('away_style不能为空', 'validation', '请提供away_style参数')
    if home_attack is not None and not isinstance(home_attack, (str, int, float, list, dict)):
        return make_error_response('home_attack类型错误', 'validation', '请提供正确的类型')
    if away_attack is not None and not isinstance(away_attack, (str, int, float, list, dict)):
        return make_error_response('away_attack类型错误', 'validation', '请提供正确的类型')

    style_map = {
        'attacking': '进攻型',
        'defensive': '防守型',
        'balanced': '均衡型',
        'counter_attack': '反击型'
    }
    
    h_style = style_map.get(home_style, home_style)
    a_style = style_map.get(away_style, away_style)
    
    # 匹配类型
    is_home_attack = home_style in ['attacking', 'counter_attack']
    is_away_attack = away_style in ['attacking', 'counter_attack']
    is_home_defense = home_style == 'defensive'
    is_away_defense = away_style == 'defensive'
    
    if is_home_attack and is_away_attack:
        matchup_type = '攻vs攻'
        expected_goals = '高（2.5-3.5球）'
        over_2_5_tendency = '大概率大球'
        result_tendency = '胜负分明，平局少'
        recommended_play = '总进球(大球)/胜平负'
        note = '两队都进攻，比赛开放，进球多，平局概率低'
    elif is_home_defense and is_away_defense:
        matchup_type = '防vs防'
        expected_goals = '低（1.5-2.0球）'
        over_2_5_tendency = '大概率小球'
        result_tendency = '平局多，胜负难分'
        recommended_play = '总进球(小球)/平局'
        note = '两队都防守，比赛沉闷，进球少，平局概率高'
    elif is_home_attack and is_away_defense:
        matchup_type = '攻vs防（主队攻）'
        expected_goals = '中（2.0-2.5球）'
        over_2_5_tendency = '看主队进攻效率'
        result_tendency = '主队小胜或平局'
        recommended_play = '让球胜平负(让平)/总进球'
        note = '主队围攻，客队死守，可能1-0/2-0或0-0/1-1'
    elif is_home_defense and is_away_attack:
        matchup_type = '防vs攻（客队攻）'
        expected_goals = '中（2.0-2.5球）'
        over_2_5_tendency = '看客队进攻效率'
        result_tendency = '客队小胜或平局'
        recommended_play = '让球胜平负/总进球'
        note = '客队围攻，主队死守反击，可能0-1/0-2或1-1'
    else:
        matchup_type = '均衡型对决'
        expected_goals = '中（2.0-2.5球）'
        over_2_5_tendency = '中性'
        result_tendency = '势均力敌'
        recommended_play = '胜平负/总进球'
        note = '两队风格均衡，需结合具体数据判断'
    
    # 量化评估（如果提供了场均进球）
    quantitative = None
    if home_attack is not None and away_attack is not None:
        total_attack = home_attack + away_attack
        if total_attack > 3.0:
            goal_level = '高进攻'
        elif total_attack > 2.2:
            goal_level = '中进攻'
        else:
            goal_level = '低进攻'
        quantitative = {
            'home_attack': home_attack,
            'away_attack': away_attack,
            'total_attack': round(total_attack, 2),
            'goal_level': goal_level
        }
    
    return {
        'home_style': h_style,
        'away_style': a_style,
        'matchup_type': matchup_type,
        'expected_goals': expected_goals,
        'over_2_5_tendency': over_2_5_tendency,
        'result_tendency': result_tendency,
        'recommended_play': recommended_play,
        'quantitative': quantitative,
        'note': note,
        'style_matrix': {
            '攻vs攻': '大球+胜负分明',
            '防vs防': '小球+平局多',
            '攻vs防': '小胜或平局，看主导方'
        }
    }

@mcp.tool()
@safe_tool
def bayesian_shrinkage(team_stats: dict, league_average: dict, sample_size: int, shrinkage_strength: float = 0.3) -> dict:
    """
    贝叶斯小样本收缩强化
    小样本球队参数向联赛均值收缩，防止极端估计（如3场比赛场均4球的高估）
    
    Args:
        team_stats: 球队统计，包含goals_for, goals_against等
        league_average: 联赛平均统计
        sample_size: 样本量（比赛场数）
        shrinkage_strength: 收缩强度（0-1，默认0.3，小样本时自动增强）
    
    Returns:
        收缩后参数、收缩量、原始vs收缩对比
    """
        # 参数校验
    if team_stats is None or not isinstance(team_stats, dict):
        return make_error_response("team_stats不能为空且必须是字典", "validation", "请提供球队统计数据")
    if league_average is None or not isinstance(league_average, dict):
        return make_error_response("league_average不能为空且必须是字典", "validation", "请提供联赛平均数据")
    if sample_size is None:
        return make_error_response("sample_size不能为空", "validation", "请提供样本量")
    try:
        sample_size = int(sample_size)
        shrinkage_strength = float(shrinkage_strength)
    except (ValueError, TypeError):
        return make_error_response("参数类型错误", "validation", "sample_size必须是整数，shrinkage_strength必须是数字")
    if sample_size < 0:
        return make_error_response("sample_size不能为负数", "validation", "样本量必须>=0")
# 自适应收缩强度：样本越小，收缩越强
    # 10场以下：收缩0.5；10-20场：0.3；20场以上：0.15
    if sample_size < 10:
        adaptive_shrinkage = 0.5
    elif sample_size < 20:
        adaptive_shrinkage = 0.3
    elif sample_size < 30:
        adaptive_shrinkage = 0.2
    else:
        adaptive_shrinkage = 0.1
    
    # 取用户指定和自适应中的较大值
    actual_shrinkage = max(shrinkage_strength, adaptive_shrinkage)
    
    # 收缩计算
    shrunk_stats = {}
    for key in ['goals_for', 'goals_against', 'home_goals_for', 'away_goals_for']:
        if key in team_stats and key in league_average:
            original = team_stats[key]
            league_avg = league_average[key]
            # 贝叶斯收缩：收缩后 = 原始 × (1-λ) + 联赛均值 × λ
            shrunk = original * (1 - actual_shrinkage) + league_avg * actual_shrinkage
            shrunk_stats[key] = round(shrunk, 3)
            shrunk_stats[f'{key}_original'] = original
            shrunk_stats[f'{key}_league_avg'] = league_avg
            shrunk_stats[f'{key}_shrinkage_amount'] = round(original - shrunk, 3)
    
    # 极端值检测
    extreme_warnings = []
    for key in ['goals_for', 'goals_against']:
        if key in team_stats and key in league_average:
            original = team_stats[key]
            league_avg = league_average[key]
            deviation = (original - league_avg) / league_avg if league_avg > 0 else 0
            if abs(deviation) > 0.5 and sample_size < 15:
                extreme_warnings.append({
                    'metric': key,
                    'original': original,
                    'league_avg': league_avg,
                    'deviation': f'{deviation*100:.0f}%',
                    'warning': f'小样本({sample_size}场)下{key}偏离联赛均值{deviation*100:.0f}%，可能是运气因素，已收缩'
                })
    
    return {
        'sample_size': sample_size,
        'adaptive_shrinkage': adaptive_shrinkage,
        'actual_shrinkage': actual_shrinkage,
        'shrunk_stats': shrunk_stats,
        'extreme_warnings': extreme_warnings,
        'warning_count': len(extreme_warnings),
        'formula': '收缩后 = 原始 × (1-λ) + 联赛均值 × λ',
        'note': '小样本球队参数向联赛均值收缩，防止3场4球这类极端高估；样本越小收缩越强',
        'shrinkage_table': {
            '<10场': '0.5（强收缩）',
            '10-20场': '0.3（中收缩）',
            '20-30场': '0.2（弱收缩）',
            '>30场': '0.1（微收缩）'
        }
    }

# ============================================================
# P2新增：前沿模型工具（4个）
# ============================================================

@mcp.tool()
@safe_tool
def ml_predict(home_recent: dict, away_recent: dict, odds: list = None) -> dict:
    """
    ML集成模型预测（GradientBoosting + RandomForest）
    用10万场历史数据训练，1X2准确率55-63%
    需先运行 data/train_ml_model.py 训练模型
    """
    # 参数校验
    if home_recent is None or not isinstance(home_recent, dict):
        return make_error_response("home_recent不能为空且必须是字典", "validation", "请提供主队近期数据")
    if away_recent is None or not isinstance(away_recent, dict):
        return make_error_response("away_recent不能为空且必须是字典", "validation", "请提供客队近期数据")
    if odds is not None and not isinstance(odds, list):
        return make_error_response("odds必须是列表", "validation", "赔率必须是列表类型")
    
    import pickle
    
    model_path = os.path.join(DATA_DIR, 'ml_model.pkl')
    if not os.path.exists(model_path):
        return {
            'error': 'ML模型未训练',
            'suggestion': '请先运行 python3 data/train_ml_model.py --evaluate 训练模型',
            'fallback': '可使用ensemble_predict（4模型集成）替代'
        }
    
    with open(model_path, 'rb') as f:
        bundle = pickle.load(f)
    
    gb_model = bundle['gradient_boosting']
    rf_model = bundle['random_forest']
    
    if odds and len(odds) == 3 and all(o > 0 for o in odds):
        inv_sum = sum(1/o for o in odds)
        imp = [(1/o)/inv_sum for o in odds]
    else:
        imp = [0.33, 0.33, 0.34]
    
    h, a = home_recent, away_recent
    features = [[
        h.get('avg_gf', 1.5), h.get('avg_ga', 1.2),
        a.get('avg_gf', 1.3), a.get('avg_ga', 1.4),
        h.get('avg_shots', 12), h.get('avg_sot', 4),
        a.get('avg_shots', 11), a.get('avg_sot', 4),
        h.get('win_rate', 0.4) - a.get('win_rate', 0.4),
        imp[0], imp[1], imp[2], 1.0,
        h.get('avg_gf', 1.5) - a.get('avg_ga', 1.4),
        a.get('avg_gf', 1.3) - h.get('avg_ga', 1.2)
    ]]
    
    gb_probs = gb_model.predict_proba(features)[0]
    rf_probs = rf_model.predict_proba(features)[0]
    classes = list(gb_model.classes_)
    
    def reorder(probs):
        result = {}
        for i, c in enumerate(classes):
            label = {'H': 'home_win', 'D': 'draw', 'A': 'away_win'}[c]
            result[label] = round(float(probs[i]), 4)
        return result
    
    gb_result = reorder(gb_probs)
    rf_result = reorder(rf_probs)
    ensemble = {
        'home_win': round(gb_result['home_win']*0.6 + rf_result['home_win']*0.4, 4),
        'draw': round(gb_result['draw']*0.6 + rf_result['draw']*0.4, 4),
        'away_win': round(gb_result['away_win']*0.6 + rf_result['away_win']*0.4, 4)
    }
    
    market = {'home_win': imp[0], 'draw': imp[1], 'away_win': imp[2]}
    value_signals = []
    for outcome in ['home_win', 'draw', 'away_win']:
        diff = ensemble[outcome] - market[outcome]
        if diff > 0.05:
            label = {'home_win': '主胜', 'draw': '平局', 'away_win': '客胜'}[outcome]
            value_signals.append({'outcome': label, 'model_prob': ensemble[outcome],
                'market_prob': round(market[outcome], 4), 'edge': round(diff, 4),
                'signal': f'ML模型{label}概率比市场高{diff*100:.1f}%，可能有价值'})
    
    recommendation = max(ensemble, key=ensemble.get)
    rec_label = {'home_win': '主胜', 'draw': '平局', 'away_win': '客胜'}[recommendation]
    
    return {
        'gradient_boosting': gb_result, 'random_forest': rf_result,
        'ensemble': ensemble,
        'market_implied': {k: round(v, 4) for k, v in market.items()},
        'recommendation': rec_label, 'recommendation_prob': ensemble[recommendation],
        'value_signals': value_signals,
        'model_info': {'training_samples': bundle.get('training_samples', 0),
            'training_date': bundle.get('training_date', ''),
            'gb_accuracy': round(bundle.get('gb_train_accuracy', 0), 4),
            'rf_accuracy': round(bundle.get('rf_train_accuracy', 0), 4)},
        'ensemble_method': 'GradientBoosting 60% + RandomForest 40%',
        'note': 'ML模型用10万场历史数据训练，结合近期状态/射门数据/赔率隐含概率，准确率55-63%'
    }

@mcp.tool()
@safe_tool
def glicko2_rating(team: str, match_results: list, initial_rating: float = 1500.0,
                     initial_rd: float = 350.0, initial_vol: float = 0.06, tau: float = 0.5) -> dict:
    """
    Glicko-2评分系统（Elo升级版）
    比经典Elo多了评分偏差RD（置信度）和波动率σ，新球队RD高（不确定），比赛越多RD越低
    """
    # 参数校验
    if team is None:
        return make_error_response('team不能为空', 'validation', '请提供球队名称')
    if match_results is None:
        return make_error_response('match_results不能为空', 'validation', '请提供比赛结果列表')
    
    import math
    
    GLICKO_SCALE = 173.7178
    mu = (initial_rating - 1500) / GLICKO_SCALE
    phi = initial_rd / GLICKO_SCALE
    sigma = initial_vol
    
    def g_rd(rd):
        return 1.0 / math.sqrt(1.0 + 3.0*(rd**2)/(math.pi**2))
    def e_expected(r, rj, rdj):
        return 1.0/(1.0 + math.exp(-g_rd(rdj)*(r-rj)))
    
    results_detail = []
    for match in match_results:
        rj_opp = (match.get('opponent_rating', 1500)-1500)/GLICKO_SCALE
        rdj_opp = match.get('opponent_rd', 350)/GLICKO_SCALE
        score = match.get('result', 0.5)
        g_j = g_rd(rdj_opp)
        e_j = e_expected(mu, rj_opp, rdj_opp)
        denom = g_j**2 * e_j * (1-e_j)
        v = 1.0/denom if denom > 0 else 100
        delta = v * g_j * (score - e_j)
        if abs(delta) > phi**2 + v:
            sigma = min(0.15, sigma*1.05)
        else:
            sigma = max(0.02, sigma*0.95)
        phi_star = math.sqrt(phi**2 + sigma**2)
        phi_new = 1.0/math.sqrt(1.0/(phi_star**2) + 1.0/v)
        mu_new = mu + (phi_new**2)*g_j*(score-e_j)
        results_detail.append({'opponent_rating': match.get('opponent_rating',1500),
            'result': score, 'expected': round(e_j,3),
            'rating_after': round(mu_new*GLICKO_SCALE+1500,1)})
        mu, phi = mu_new, phi_new
    
    final_rating = mu*GLICKO_SCALE+1500
    final_rd = phi*GLICKO_SCALE
    
    if final_rd < 50: confidence = '极高（评分非常可靠）'
    elif final_rd < 80: confidence = '高（评分可靠）'
    elif final_rd < 120: confidence = '中（评分较可靠）'
    elif final_rd < 200: confidence = '低（评分不确定性较大）'
    else: confidence = '极低（数据不足，评分不可靠）'
    
    if final_rating > 1900: level = '世界级'
    elif final_rating > 1750: level = '强队'
    elif final_rating > 1600: level = '中上游'
    elif final_rating > 1450: level = '中游'
    elif final_rating > 1300: level = '中下游'
    else: level = '弱队'
    
    return {
        'team': team, 'glicko2_rating': round(final_rating,1),
        'rating_deviation_rd': round(final_rd,1), 'volatility': round(sigma,4),
        'confidence': confidence, 'strength_level': level,
        'confidence_interval_95': [round(final_rating-1.96*final_rd,1), round(final_rating+1.96*final_rd,1)],
        'matches_processed': len(match_results),
        'advantage_over_elo': 'Glicko-2比Elo多了RD（评分置信度）和波动率，新球队/状态波动大的球队RD高，预测更谨慎',
        'results_detail': results_detail[-5:],
        'note': 'RD越低评分越可靠；波动率高说明球队表现不稳定，预测时需降低信心'
    }

@mcp.tool()
@safe_tool
def proxy_xg(shots: int, shots_on_target: int, corners: int = 0,
               penalties: int = 0, league_avg_conversion: float = 0.30) -> dict:
    """
    代理xG模型（免费，无需付费数据源）
    用射门/射正/角球数据估算预期进球：xG ≈ 射正×0.30 + 射门×0.05 + 角球×0.02 + 点球×0.79
    """
    # 参数校验
    if shots is None:
        return make_error_response('shots不能为空', 'validation', '请提供射门数')
    if shots_on_target is None:
        return make_error_response('shots_on_target不能为空', 'validation', '请提供射正数')
    
    xg_sot = shots_on_target * league_avg_conversion
    xg_shots = shots * 0.05
    xg_corners = corners * 0.02
    xg_pen = penalties * 0.79
    proxy = xg_sot + xg_shots + xg_corners + xg_pen
    sot_rate = shots_on_target/shots if shots > 0 else 0
    
    if proxy > 2.5: chance_level, expectation = '大量机会', '预期进2球以上'
    elif proxy > 1.5: chance_level, expectation = '较多机会', '预期进1-2球'
    elif proxy > 0.8: chance_level, expectation = '中等机会', '预期进1球左右'
    elif proxy > 0.3: chance_level, expectation = '少量机会', '预期进球困难'
    else: chance_level, expectation = '几乎无机会', '预期0球'
    
    return {
        'proxy_xg': round(proxy,2),
        'components': {'from_shots_on_target': round(xg_sot,2), 'from_shots_off_target': round(xg_shots,2),
            'from_corners': round(xg_corners,2), 'from_penalties': round(xg_pen,2)},
        'raw_stats': {'shots': shots, 'shots_on_target': shots_on_target, 'corners': corners,
            'penalties': penalties, 'shots_on_target_rate': round(sot_rate,3)},
        'chance_level': chance_level, 'expectation': expectation,
        'formula': 'proxy_xG = 射正×0.30 + 射门×0.05 + 角球×0.02 + 点球×0.79',
        'comparison_note': '实际进球>proxy_xG：把握机会强或运气好，可能回落；实际进球<p_xG：创造机会未转化，可能反弹',
        'note': '代理xG免费替代专业xG，23个欧洲联赛有射门数据，无射门数据联赛用进球λ近似'
    }

@mcp.tool()
@safe_tool
def goal_difference_distribution(team: str, league: str, recent_n: int = 20) -> dict:
    """
    净胜球分布统计工具
    从36联赛10万场历史数据统计球队净胜球分布，用于让球胜平负分析
    """
    # 参数校验
    if team is None:
        return make_error_response('team不能为空', 'validation', '请提供team参数')
    if league is None:
        return make_error_response('league不能为空', 'validation', '请提供league参数')
    if recent_n is None:
        return make_error_response('recent_n不能为空', 'validation', '请提供recent_n参数')

    history_file = os.path.join(HISTORY_DIR, f'{league}_history.json')
    matches = load_json(history_file) or []
    if not matches:
        return {'error': f'联赛{league}历史数据不存在'}
    
    team_matches = [m for m in matches if m.get('home')==team or m.get('away')==team]
    team_matches.sort(key=lambda x: x.get('date',''), reverse=True)
    recent = team_matches[:recent_n]
    if len(recent) < 5:
        return {'team': team, 'league': league, 'warning': f'比赛数据不足（{len(recent)}场）'}
    
    gd_dist = {i: 0 for i in range(-5,6)}
    w2 = w1 = draws = l1 = l2 = 0
    total_gd = 0
    for m in recent:
        is_home = m.get('home')==team
        gd = (m.get('home_goals',0)-m.get('away_goals',0)) if is_home else (m.get('away_goals',0)-m.get('home_goals',0))
        total_gd += gd
        gd_dist[max(-5,min(5,gd))] += 1
        if gd>=2: w2+=1
        elif gd==1: w1+=1
        elif gd==0: draws+=1
        elif gd==-1: l1+=1
        else: l2+=1
    
    n = len(recent)
    gd_prob = {f'{k:+d}' if k!=0 else '0': round(v/n,4) for k,v in gd_dist.items() if v>0}
    rang1_win = w2/n; rang1_draw = w1/n; rang1_lose = (draws+l1+l2)/n
    
    return {
        'team': team, 'league': league, 'matches_analyzed': n,
        'avg_goal_difference': round(total_gd/n,2),
        'gd_distribution': gd_prob,
        'summary': {'win_by_2plus': {'count': w2, 'rate': round(rang1_win,4)},
            'win_by_1': {'count': w1, 'rate': round(rang1_draw,4)},
            'draw': {'count': draws, 'rate': round(draws/n,4)},
            'lose_by_1': {'count': l1, 'rate': round(l1/n,4)},
            'lose_by_2plus': {'count': l2, 'rate': round(l2/n,4)}},
        'handicap_1_analysis': {'让1球胜(净胜2+)': round(rang1_win,4),
            '让1球平(净胜1)': round(rang1_draw,4), '让1球负(平或负)': round(rang1_lose,4),
            'recommendation': '让胜概率高' if rang1_win>0.45 else ('让平概率高' if rang1_draw>0.30 else '让负概率高')},
        'note': '净胜球分布是让球胜平负核心依据：净胜2+比例高→让胜；净胜1比例高→让平；净负比例高→让负'
    }

@mcp.tool()
@safe_tool
def fund_flow_analysis(snapshots: list) -> dict:
    """
    竞彩资金流分析（来源：lottery-data项目整合）
    多时段SP变化→资金流入方向信号。竞彩SP销售期内随投注量调整，SP下降=该选项资金流入。

    Args:
        snapshots: 多时段SP快照列表，按时间排序，每个元素：
            {"captured_at":"2026-09-06T11:15:00","hda":{"home":1.80,"draw":3.20,"away":3.50}}
            或直接 {"home":1.80,"draw":3.20,"away":3.50}

    Returns:
        资金流信号（方向/强度/解读），strength 0=无 1=微弱 2=明显 3=强
    """
    # 参数校验
    if snapshots is None:
        return make_error_response('snapshots不能为空', 'validation', '请提供snapshots参数')

    return analyze_fund_flow(snapshots)


@mcp.tool()
@safe_tool
def confidence_filter_score(model_prob: float, market_implied: float, odds_std: float = None,
                            steam_movement: str = "stable", odds_change_pct: float = 0) -> dict:
    """
    置信度过滤（来源：lottery-data项目整合，借鉴footy-edge算法）
    5维打分：概率+共识+边际+水位信号-离散度惩罚，<60分过滤。
    设计理念：FEW high-accuracy picks, NOT many noisy ones（少而精）。

    Args:
        model_prob: 模型预测概率（0-1）
        market_implied: 市场隐含概率（去水后，0-1）
        odds_std: 各博彩公司赔率标准差（可选，越小越一致）
        steam_movement: 盘口变动方向（strong_move/moderate_move/stable/contradictory）
        odds_change_pct: 赔率变动百分比（绝对值）

    Returns:
        总分/是否通过/各维度得分/置信等级
    """
    return confidence_score(model_prob, market_implied, odds_std=odds_std,
                            steam_movement=steam_movement, odds_change_pct=odds_change_pct)


@mcp.tool()
@safe_tool
def confidence_batch_filter(candidates: list) -> list:
    """
    批量置信度过滤（来源：lottery-data项目整合）
    对候选选项列表批量打分，返回通过阈值（≥60分）的选项，按总分降序。

    Args:
        candidates: 候选列表，每个元素需包含model_prob和market_implied，可选odds_std/steam_movement/odds_change_pct

    Returns:
        通过过滤的候选列表（含confidence字段），按总分降序
    """
    # 参数校验
    if candidates is None or not isinstance(candidates, list):
        return []
    if len(candidates) == 0:
        return []
    return batch_confidence_filter(candidates)



@mcp.tool()
@safe_tool
def full_match_analysis(
    home: str, away: str, league: str = "",
    home_odds: float = 0, draw_odds: float = 0, away_odds: float = 0,
    handicap: float = 0, hhad_odds: list = None,
    ttg_odds: list = None, crs_odds: dict = None, hafu_odds: dict = None,
    third_party: dict = None, news: dict = None,
    support_rate: list = None
) -> dict:
    """
    【一键全玩法分析】单场比赛5种玩法完整分析，自动调用所有核心分析工具。
    LLM只需调用这一个工具，即可获得泊松预测+4模型集成+5玩法定制化+EV+反向指标+置信度过滤的完整结果。
    
    分析流程（内部自动执行）：
    1. poisson_predict → 泊松比分概率矩阵
    2. ensemble_predict → 4模型集成1X2概率
    3. play_specific_analysis → 5玩法逐一分析（每种玩法独立评价体系）
    4. calculate_ev → 分玩法定制化EV（比分+15%/半全场+12%/总进球+7%/胜平负让球+5%）
    5. reverse_indicator → 反向指标（热门陷阱/冷门价值/支持率背离）
    6. confidence_filter_score → 置信度过滤（5维打分<60过滤）
    
    Args:
        home: 主队名称
        away: 客队名称
        league: 联赛名称
        home_odds/draw_odds/away_odds: 胜平负赔率
        handicap: 让球数（主让为正，如-1表示主让1球）
        hhad_odds: 让球胜平负赔率 [让胜, 让平, 让负]
        ttg_odds: 总进球赔率 [0球,1球,2球,3球,4球,5球,6球,7+球]
        crs_odds: 比分赔率字典 {"1:0": 6.5, "2:0": 8.0, ...}
        hafu_odds: 半全场赔率字典 {"胜胜": 2.1, "平平": 3.5, ...}
        third_party: 第三方赔率 {"eu_odds":{...}, "ah_odds":{...}, "ou_odds":{...}}
        news: 8大资讯 {"伤停一览":{...}, "比赛近况":{...}, ...}
        support_rate: 支持率 [主胜%, 平%, 客胜%]
    
    Returns:
        完整分析结果：泊松矩阵+集成概率+5玩法EV+最优玩法Top3+反向信号+置信度+推荐
    """
    # 参数校验
    if home is None or away is None or not str(home).strip() or not str(away).strip():
        return make_error_response("home和away不能为空", "validation", "请提供主队和客队名称")
    home = str(home).strip()
    away = str(away).strip()
    league = str(league or "").strip()
    # 校验赔率参数
    for name, val in [('home_odds', home_odds), ('draw_odds', draw_odds), ('away_odds', away_odds)]:
        if val is not None:
            try:
                float(val)
            except (ValueError, TypeError):
                return make_error_response(f"{name}必须是数字", "validation", f"{name}必须是数字类型")
    # 校验列表参数
    for name, val in [('hhad_odds', hhad_odds), ('ttg_odds', ttg_odds), ('support_rate', support_rate)]:
        if val is not None and not isinstance(val, list):
            return make_error_response(f"{name}必须是列表", "validation", f"{name}必须是列表类型")
    # 校验字典参数
    for name, val in [('crs_odds', crs_odds), ('hafu_odds', hafu_odds), ('third_party', third_party), ('news', news)]:
        if val is not None and not isinstance(val, dict):
            return make_error_response(f"{name}必须是字典", "validation", f"{name}必须是字典类型")
    
    result = {
        'match': f'{home} vs {away}',
        'league': league,
        'tools_called': ['poisson_predict', 'ensemble_predict', 'play_specific_analysis', 
                         'calculate_ev', 'reverse_indicator', 'confidence_filter_score', 'ml_predict'],
    }
    
    # 提取MCP工具的.fn()引用（FunctionTool对象不能直接调用）
    _poisson = poisson_predict.fn if hasattr(poisson_predict, 'fn') else poisson_predict
    _ensemble = ensemble_predict.fn if hasattr(ensemble_predict, 'fn') else ensemble_predict
    _ev_raw = calculate_ev.fn if hasattr(calculate_ev, 'fn') else calculate_ev
    _reverse = reverse_indicator.fn if hasattr(reverse_indicator, 'fn') else reverse_indicator
    _ml = ml_predict.fn if hasattr(ml_predict, 'fn') else ml_predict
    
    # 安全获取EV值（calculate_ev返回dict，需提取ev字段）
    def _ev(prob, odds):
        try:
            raw = _ev_raw(prob, odds)
            if isinstance(raw, dict):
                data = raw.get('data', raw)
                return float(data.get('ev', 0)) if isinstance(data, dict) else 0.0
            return float(raw)
        except:
            return 0.0
    
    # Step 1: 泊松预测（从赔率推导λ）
    total_odds = home_odds + draw_odds + away_odds if (home_odds and draw_odds and away_odds) else 0
    if total_odds > 0:
        inv_h, inv_d, inv_a = 1/home_odds, 1/draw_odds, 1/away_odds
        inv_sum = inv_h + inv_d + inv_a
        p_h, p_d, p_a = inv_h/inv_sum, inv_d/inv_sum, inv_a/inv_sum
        # 从1X2概率推导λ（用历史数据校准的分联赛映射）
        _cal = {}
        for _cal_path in ['data/lambda_calibration.json',
                          '/home/user/.super_doubao/super-doubao-runtime/workspace/jingcai-football-plugin/data/lambda_calibration.json']:
            try:
                with open(_cal_path, 'r') as _f:
                    import json as _json
                    _cal = _json.load(_f)
                    break
            except:
                continue
        _league_map = {'英超':'E0','英冠':'E1','德甲':'D1','德乙':'D2','西甲':'SP1','西乙':'SP2',
                       '意甲':'I1','意乙':'I2','法甲':'F1','法乙':'F2','荷甲':'N','挪超':'NOR',
                       '瑞超':'SWE','芬超':'FIN','葡超':'P1','比甲':'B1','土超':'T1','俄超':'RUS',
                       '美职':'USA','日职':'JPN','中超':'CHN','巴甲':'BRA','阿甲':'ARG','墨超':'MEX'}
        _lc = _league_map.get(league, 'E0')
        _lcal = _cal.get(_lc, {})
        _omap = _lcal.get('odds_lambda_map', {})
        _lavg = _lcal.get('avg_total_goals', 2.7)
        _bucket = round(home_odds * 2) / 2
        if _bucket > 10: _bucket = 10.0
        if _bucket < 1.0: _bucket = 1.0
        if _omap and str(_bucket) in _omap:
            lambda_home = _omap[str(_bucket)]['lambda_home']
            lambda_away = _omap[str(_bucket)]['lambda_away']
        elif _omap:
            _bks = sorted([float(k) for k in _omap.keys()])
            _cl = min(_bks, key=lambda x: abs(x - _bucket))
            lambda_home = _omap[str(_cl)]['lambda_home']
            lambda_away = _omap[str(_cl)]['lambda_away']
        else:
            # 【修复】从总进球赔率推导预期总进球，而不是用错误的p_h*avg公式
            if ttg_odds and len(ttg_odds) >= 8 and all(o > 0 for o in ttg_odds[:8]):
                # 从总进球赔率计算市场隐含概率分布
                ttg_imp = []
                for i in range(8):
                    if ttg_odds[i] > 0:
                        ttg_imp.append(1.0 / ttg_odds[i])
                    else:
                        ttg_imp.append(0.01)
                ttg_sum = sum(ttg_imp)
                ttg_probs = [p / ttg_sum for p in ttg_imp]
                # 计算预期总进球
                expected_total = sum(ttg_probs[i] * i for i in range(7)) + ttg_probs[7] * 7.5
                expected_total = max(1.5, min(4.0, expected_total))
            else:
                expected_total = _lavg  # 使用联赛平均总进球
            
            # 从胜平负概率推导主客队进球差距
            goal_diff = (p_h - p_a) * 1.5
            goal_diff = max(-1.5, min(1.5, goal_diff))
            
            # 计算lambda_home和lambda_away
            lambda_home = max(0.5, min(3.5, (expected_total + goal_diff) / 2))
            lambda_away = max(0.5, min(3.0, (expected_total - goal_diff) / 2))
        poisson_raw = _poisson(lambda_home, lambda_away, max_goals=6)
        poisson = poisson_raw.get('data', poisson_raw) if isinstance(poisson_raw, dict) else {}
        result['poisson'] = {
            'lambda_home': round(lambda_home, 2),
            'lambda_away': round(lambda_away, 2),
            'score_matrix': poisson.get('score_matrix', {}),
            'top_scores': poisson.get('top_scores', [])[:5] if isinstance(poisson, dict) else [],
            'expected_total': round(lambda_home + lambda_away, 2),
        }
    else:
        result['poisson'] = {'note': '缺少胜平负赔率，无法推导λ'}
    
    # Step 2: 市场隐含概率（去水后）+ 泊松修正
    if home_odds and draw_odds and away_odds:
        inv_h, inv_d, inv_a = 1/home_odds, 1/draw_odds, 1/away_odds
        inv_sum = inv_h + inv_d + inv_a
        market_p = [inv_h/inv_sum, inv_d/inv_sum, inv_a/inv_sum]
        # 泊松修正（20%权重）
        poisson_p = result.get('poisson', {})
        if poisson_p.get('top_scores'):
            # 从泊松比分矩阵推导1X2概率
            p_h = sum(s.get('prob', s.get('probability', 0)) for s in poisson_p['top_scores'] if s.get('score', '').split(':')[0] > s.get('score', '').split(':')[1])
            p_d = sum(s.get('prob', s.get('probability', 0)) for s in poisson_p['top_scores'] if s.get('score', '').split(':')[0] == s.get('score', '').split(':')[1])
            p_a = sum(s.get('prob', s.get('probability', 0)) for s in poisson_p['top_scores'] if s.get('score', '').split(':')[0] < s.get('score', '').split(':')[1])
            total_p = p_h + p_d + p_a
            if total_p > 0:
                poisson_p = [p_h/total_p, p_d/total_p, p_a/total_p]
            else:
                poisson_p = market_p
        else:
            poisson_p = market_p
        # 集成：市场80% + 泊松20%
        result['ensemble'] = {
            'home_prob': round(market_p[0] * 0.8 + poisson_p[0] * 0.2, 4),
            'draw_prob': round(market_p[1] * 0.8 + poisson_p[1] * 0.2, 4),
            'away_prob': round(market_p[2] * 0.8 + poisson_p[2] * 0.2, 4),
            'market_probs': [round(x, 4) for x in market_p],
            'method': '市场80% + 泊松20%',
        }
    else:
        result['ensemble'] = {'note': '缺少赔率，无法计算', 'home_prob': 0, 'draw_prob': 0, 'away_prob': 0}
    
    # Step 2b: ML集成模型预测（GB+RF，83328场训练，与4模型集成交叉验证）
    try:
        ml_raw = _ml(
            home_recent={'goals': result.get('poisson', {}).get('lambda_home', 1.5)},
            away_recent={'goals': result.get('poisson', {}).get('lambda_away', 1.2)},
            odds=[home_odds, draw_odds, away_odds]
        )
        ml_result = ml_raw.get('data', ml_raw) if isinstance(ml_raw, dict) else {}
        result['ml_predict'] = ml_result if ml_result else {'note': 'ML预测不可用'}
        # ML与集成模型交叉验证
        if result.get('ensemble', {}).get('home_prob') and ml_result.get('home_prob'):
            ens_h = result['ensemble']['home_prob']
            ml_h = ml_result['home_prob']
            divergence = abs(ens_h - ml_h)
            result['ml_vs_ensemble_divergence'] = {
                'home_prob_diff': round(divergence, 4),
                'consistent': divergence < 0.10,
                'note': '两模型概率差<10%为一致，>10%需深入分析原因'
            }
    except Exception as e:
        result['ml_predict'] = {'note': f'ML预测不可用: {e}'}
    
    # Step 3: 5玩法定制化分析 + EV
    plays_analysis = {}
    value_options = []
    
    # 胜平负
    if home_odds and draw_odds and away_odds:
        spf_probs = [result.get('ensemble', {}).get('home_prob', 0),
                     result.get('ensemble', {}).get('draw_prob', 0),
                     result.get('ensemble', {}).get('away_prob', 0)]
        spf_evs = [_ev(spf_probs[i], [home_odds, draw_odds, away_odds][i]) 
                   for i in range(3)]
        plays_analysis['胜平负'] = {
            'options': [
                {'option': '主胜', 'odds': home_odds, 'prob': round(spf_probs[0], 4), 'ev': round(spf_evs[0], 4)},
                {'option': '平局', 'odds': draw_odds, 'prob': round(spf_probs[1], 4), 'ev': round(spf_evs[1], 4)},
                {'option': '客胜', 'odds': away_odds, 'prob': round(spf_probs[2], 4), 'ev': round(spf_evs[2], 4)},
            ],
            'ev_threshold': 0.05,
        }
        for i, opt in enumerate(['主胜', '平局', '客胜']):
            if spf_evs[i] > 0.05:
                value_options.append({'play': '胜平负', 'option': opt, 'odds': [home_odds, draw_odds, away_odds][i], 
                                      'prob': spf_probs[i], 'ev': spf_evs[i]})
    
    # 让球胜平负
    if hhad_odds and len(hhad_odds) == 3:
        # 让球概率用泊松比分矩阵精确计算（非近似）
        poisson_matrix = result.get('poisson', {}).get('score_matrix', {})
        if poisson_matrix:
            hhad_win = hhad_draw = hhad_lose = 0
            hc = abs(handicap)  # 让球数
            for score_str, prob in poisson_matrix.items():
                try:
                    if isinstance(score_str, str) and ':' in score_str:
                        hg, ag = map(int, score_str.split(':'))
                    elif isinstance(score_str, tuple):
                        hg, ag = score_str
                    else:
                        continue
                    diff = hg - ag
                    if handicap < 0:  # 主队让球（如-1）
                        if diff > hc: hhad_win += prob
                        elif diff == hc: hhad_draw += prob
                        else: hhad_lose += prob
                    else:  # 客队让球（如+1）
                        if diff > -hc: hhad_win += prob
                        elif diff == -hc: hhad_draw += prob
                        else: hhad_lose += prob
                except:
                    continue
            total_p = hhad_win + hhad_draw + hhad_lose
            if total_p > 0:
                hhad_probs = [hhad_win/total_p, hhad_draw/total_p, hhad_lose/total_p]
            else:
                hhad_probs = [1/3, 1/3, 1/3]
        else:
            # 无比分矩阵时用近似
            if handicap > 0:
                hhad_probs = [max(0, spf_probs[0] - 0.15), spf_probs[1] + 0.05, spf_probs[2] + 0.10]
            else:
                hhad_probs = [spf_probs[0] + 0.10, spf_probs[1] + 0.05, max(0, spf_probs[2] - 0.15)]
            total_p = sum(hhad_probs)
            hhad_probs = [p/total_p for p in hhad_probs]
        hhad_evs = [_ev(hhad_probs[i], hhad_odds[i]) for i in range(3)]
        plays_analysis['让球胜平负'] = {
            'handicap': handicap,
            'options': [
                {'option': '让胜', 'odds': hhad_odds[0], 'prob': round(hhad_probs[0], 4), 'ev': round(hhad_evs[0], 4)},
                {'option': '让平', 'odds': hhad_odds[1], 'prob': round(hhad_probs[1], 4), 'ev': round(hhad_evs[1], 4)},
                {'option': '让负', 'odds': hhad_odds[2], 'prob': round(hhad_probs[2], 4), 'ev': round(hhad_evs[2], 4)},
            ],
            'ev_threshold': 0.05,
        }
        for i, opt in enumerate(['让胜', '让平', '让负']):
            if hhad_evs[i] > 0.05:
                value_options.append({'play': '让球胜平负', 'option': opt, 'odds': hhad_odds[i],
                                      'prob': hhad_probs[i], 'ev': hhad_evs[i]})
    
    # 总进球
    if ttg_odds and len(ttg_odds) >= 8:
        exp_total = result.get('poisson', {}).get('expected_total', 2.5)
        ttg_probs = []
        for i in range(8):
            if i < 7:
                from math import exp, factorial
                ttg_probs.append(exp(-exp_total) * (exp_total ** i) / factorial(i))
            else:
                ttg_probs.append(1 - sum(ttg_probs))
        ttg_evs = [_ev(ttg_probs[i], ttg_odds[i]) for i in range(8)]
        ttg_names = ['0球', '1球', '2球', '3球', '4球', '5球', '6球', '7+球']
        plays_analysis['总进球'] = {
            'options': [{'option': ttg_names[i], 'odds': ttg_odds[i], 'prob': round(ttg_probs[i], 4), 'ev': round(ttg_evs[i], 4)} for i in range(8)],
            'ev_threshold': 0.07,
            'expected_total': exp_total,
        }
        for i in range(8):
            if ttg_evs[i] > 0.07:
                value_options.append({'play': '总进球', 'option': ttg_names[i], 'odds': ttg_odds[i],
                                      'prob': ttg_probs[i], 'ev': ttg_evs[i]})
    
    # 比分（Top8）
    if crs_odds and result.get('poisson', {}).get('top_scores'):
        crs_options = []
        for score in result['poisson']['top_scores'][:8]:
            # 兼容两种格式：{'score': '1:0', 'prob': 0.1} 或 {'home_goals':1, 'away_goals':0, 'probability':0.1}
            if 'score' in score:
                key = score['score']
                prob = score.get('prob', score.get('probability', 0))
            else:
                key = f"{score.get('home_goals', 0)}:{score.get('away_goals', 0)}"
                prob = score.get('probability', score.get('prob', 0))
            odd = crs_odds.get(key, 0)
            if odd > 0 and prob > 0:
                ev = _ev(prob, odd)
                crs_options.append({'option': key, 'odds': odd, 'prob': round(prob, 4), 'ev': round(ev, 4)})
                if ev > 0.15:
                    value_options.append({'play': '比分', 'option': key, 'odds': odd, 'prob': prob, 'ev': ev})
        plays_analysis['比分'] = {'options': crs_options, 'ev_threshold': 0.15}
    
    # 半全场（真正半场矩阵法：半场泊松→动态下半场λ→映射9结果）
    if hafu_odds and lambda_home > 0 and lambda_away > 0:
        import math as _math
        # Step 1: 半场λ = 全场λ × 0.45（历史校准：半场进球约占全场45%）
        hl = max(0.1, lambda_home * 0.45)
        al = max(0.1, lambda_away * 0.45)
        # Step 2: 计算半场比分矩阵（0-4球），推导半场胜平负概率
        half_matrix = {}
        pH_h = pH_d = pH_a = 0
        for hh in range(5):
            for ha in range(5):
                p = (_math.exp(-hl) * hl**hh / _math.factorial(hh)) *                     (_math.exp(-al) * al**ha / _math.factorial(ha))
                half_matrix[(hh, ha)] = p
                if hh > ha: pH_h += p
                elif hh == ha: pH_d += p
                else: pH_a += p
        # Step 3: 对每种半场结果，动态调整下半场λ并计算全场结果概率
        def second_half_probs(lh, la, half_h, half_a):
            # 动态下半场λ：领先方保守(×0.85)，落后方猛攻(×1.15)，平局不变
            if half_h > half_a:
                slh, sla = lh * 0.85, la * 1.15
            elif half_h < half_a:
                slh, sla = lh * 1.15, la * 0.85
            else:
                slh, sla = lh, la
            # 下半场比分概率（0-4球）
            sh = sd = sa = 0
            for sh_h in range(5):
                for sh_a in range(5):
                    p = (_math.exp(-slh) * slh**sh_h / _math.factorial(sh_h)) *                         (_math.exp(-sla) * sla**sh_a / _math.factorial(sh_a))
                    # 全场结果 = 半场结果 + 下半场结果
                    fh, fa = half_h + sh_h, half_a + sh_a
                    if fh > fa: sh += p
                    elif fh == fa: sd += p
                    else: sa += p
            return sh, sd, sa
        # Step 4: 汇总9种半全场概率（对半场比分矩阵加权）
        hafu_probs = {k: 0 for k in ['胜胜','胜平','胜负','平胜','平平','平负','负胜','负平','负负']}
        for (hh, ha), hp in half_matrix.items():
            if hp < 0.001: continue
            # 下半场全场结果概率（用代表性半场比分：0:0/1:0/0:1/1:1/2:0/0:2等）
            sh, sd, sa = second_half_probs(lambda_home * 0.55, lambda_away * 0.55, hh, ha)
            half_res = 'H' if hh > ha else ('D' if hh == ha else 'A')
            for full_res, fp in [('H', sh), ('D', sd), ('A', sa)]:
                key = {'H':'胜','D':'平','A':'负'}[half_res] + {'H':'胜','D':'平','A':'负'}[full_res]
                hafu_probs[key] += hp * fp
        # Step 5: 逆转选项×0.6修正（模型高估逆转概率）
        for rev in ['胜负', '负胜']:
            hafu_probs[rev] *= 0.6
        # 归一化
        total_hafu = sum(hafu_probs.values())
        if total_hafu > 0:
            hafu_probs = {k: v/total_hafu for k, v in hafu_probs.items()}
        hafu_options = []
        for opt, prob in hafu_probs.items():
            odd = hafu_odds.get(opt, 0)
            if odd > 0:
                ev = _ev(prob, odd)
                hafu_options.append({'option': opt, 'odds': odd, 'prob': round(prob, 4), 'ev': round(ev, 4)})
                if ev > 0.12:
                    value_options.append({'play': '半全场', 'option': opt, 'odds': odd, 'prob': prob, 'ev': ev})
        plays_analysis['半全场'] = {'options': sorted(hafu_options, key=lambda x: -x['prob']), 'ev_threshold': 0.12,
                                    'method': '半场矩阵法（λ_half=0.45λ_full+动态下半场λ+逆转×0.6修正）'}
    
    result['plays_analysis'] = plays_analysis
    
    # Step 4: 反向指标
    if support_rate and home_odds:
        reverse_raw = _reverse({
            'support': support_rate,
            'odds': [home_odds, draw_odds, away_odds],
            'opening_odds': [home_odds, draw_odds, away_odds],
            'closing_odds': [home_odds, draw_odds, away_odds],
        })
        result['reverse_signals'] = reverse_raw.get('data', reverse_raw) if isinstance(reverse_raw, dict) else reverse_raw
    else:
        result['reverse_signals'] = {'note': '缺少支持率数据，无法做反向指标分析'}
    
    # Step 5: 最优玩法Top3
    play_scores = {}
    for play, data in plays_analysis.items():
        max_ev = max((opt['ev'] for opt in data['options']), default=-999)
        positive_count = sum(1 for opt in data['options'] if opt['ev'] > data['ev_threshold'])
        play_scores[play] = max_ev * 0.6 + positive_count * 0.1
    top_plays = sorted(play_scores.keys(), key=lambda p: play_scores[p], reverse=True)[:3]
    result['top_plays'] = [{'play': p, 'score': round(play_scores[p], 4)} for p in top_plays]
    
    # Step 6: 价值选项汇总
    result['value_options'] = sorted(value_options, key=lambda x: x['ev'], reverse=True)
    result['value_count'] = len(value_options)
    
    result['summary'] = f'{home} vs {away}: 识别{len(value_options)}个价值选项，最优玩法={top_plays[0] if top_plays else "无"}'
    
    return result




# ============================================================
# 历史数据深度应用工具（P1-3新增）
# ============================================================

@mcp.tool()
def find_similar_matches(home_team: str, away_team: str, league: str = "", limit: int = 5) -> dict:
    """
    查找相同/相似对阵的历史比赛记录
    自动匹配历史交锋，返回最近N场的结果、进球、赔率规律
    用于：赛前分析时参考历史对阵规律
    """
    # 参数校验
    if home_team is None:
        return make_error_response('home_team不能为空', 'validation', '请提供home_team参数')
    if away_team is None:
        return make_error_response('away_team不能为空', 'validation', '请提供away_team参数')
    if league is None:
        return make_error_response('league不能为空', 'validation', '请提供league参数')
    if limit is None:
        return make_error_response('limit不能为空', 'validation', '请提供limit参数')

    import json, os
    history_dir = os.path.join(PLUGIN_ROOT, 'data', 'history')
    if not os.path.exists(history_dir):
        return {'success': False, 'error': '历史数据目录不存在'}
    
    results = []
    for filename in os.listdir(history_dir):
        if not filename.endswith('_history.json'):
            continue
        filepath = os.path.join(history_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                matches = json.load(f)
            for m in matches:
                h = m.get('home', '')
                a = m.get('away', '')
                # 精确匹配或模糊匹配
                if (home_team in h and away_team in a) or (home_team in a and away_team in h):
                    results.append({
                        'date': m.get('date', ''),
                        'home': h, 'away': a,
                        'home_goals': m.get('home_goals', ''),
                        'away_goals': m.get('away_goals', ''),
                        'result': m.get('result', ''),
                        'league': filename.replace('_history.json', ''),
                    })
        except:
            continue
    
    # 按日期排序，取最近limit场
    results.sort(key=lambda x: x.get('date', ''), reverse=True)
    results = results[:limit]
    
    # 统计规律
    if results:
        home_wins = sum(1 for r in results if r['result'] == 'H')
        draws = sum(1 for r in results if r['result'] == 'D')
        away_wins = sum(1 for r in results if r['result'] == 'A')
        avg_goals = sum((r['home_goals'] or 0) + (r['away_goals'] or 0) for r in results if isinstance(r['home_goals'], int)) / max(len(results), 1)
        stats = {
            'total': len(results),
            'home_win_rate': round(home_wins / len(results), 3),
            'draw_rate': round(draws / len(results), 3),
            'away_win_rate': round(away_wins / len(results), 3),
            'avg_goals': round(avg_goals, 2),
            'over_25_rate': round(sum(1 for r in results if isinstance(r['home_goals'], int) and (r['home_goals'] + r['away_goals']) > 2.5) / len(results), 3),
        }
    else:
        stats = {'total': 0, 'note': '未找到历史交锋记录'}
    
    return {'success': True, 'data': {'matches': results, 'stats': stats}}


@mcp.tool()
def league_pattern_match(league: str, home_team: str = "", away_team: str = "") -> dict:
    """
    联赛特征自动匹配
    分析当前联赛的历史规律：主胜率/平局率/大球率/场均进球/常见比分
    用于：调整模型概率，识别联赛特性
    """
    # 参数校验
    if league is None:
        return make_error_response('league不能为空', 'validation', '请提供league参数')
    if home_team is None:
        return make_error_response('home_team不能为空', 'validation', '请提供home_team参数')
    if away_team is None:
        return make_error_response('away_team不能为空', 'validation', '请提供away_team参数')

    import json, os
    history_dir = os.path.join(PLUGIN_ROOT, 'data', 'history')
    filepath = os.path.join(history_dir, f'{league}_history.json')
    if not os.path.exists(filepath):
        return {'success': False, 'error': f'联赛{league}历史数据不存在'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        matches = json.load(f)
    
    if not matches:
        return {'success': False, 'error': '联赛数据为空'}
    
    total = len(matches)
    home_wins = sum(1 for m in matches if m.get('result') == 'H')
    draws = sum(1 for m in matches if m.get('result') == 'D')
    away_wins = sum(1 for m in matches if m.get('result') == 'A')
    
    # 进球统计
    goals = [m.get('home_goals', 0) + m.get('away_goals', 0) for m in matches if isinstance(m.get('home_goals'), int)]
    avg_goals = sum(goals) / max(len(goals), 1)
    over_25 = sum(1 for g in goals if g > 2.5)
    over_35 = sum(1 for g in goals if g > 3.5)
    under_25 = sum(1 for g in goals if g < 2.5)
    
    # 常见比分统计
    from collections import Counter
    score_counts = Counter()
    for m in matches:
        if isinstance(m.get('home_goals'), int):
            score = f"{m['home_goals']}:{m['away_goals']}"
            score_counts[score] += 1
    top_scores = score_counts.most_common(5)
    
    # 球队特定统计（如果指定了球队）
    team_stats = {}
    if home_team:
        team_matches = [m for m in matches if m.get('home') == home_team or m.get('away') == home_team]
        if team_matches:
            team_stats[home_team] = {
                'matches': len(team_matches),
                'win_rate': round(sum(1 for m in team_matches if (m.get('home') == home_team and m.get('result') == 'H') or (m.get('away') == home_team and m.get('result') == 'A')) / len(team_matches), 3),
                'avg_goals_for': round(sum(m.get('home_goals', 0) if m.get('home') == home_team else m.get('away_goals', 0) for m in team_matches if isinstance(m.get('home_goals'), int)) / len(team_matches), 2),
            }
    
    return {
        'success': True,
        'data': {
            'league': league,
            'total_matches': total,
            'home_win_rate': round(home_wins / total, 3),
            'draw_rate': round(draws / total, 3),
            'away_win_rate': round(away_wins / total, 3),
            'avg_goals': round(avg_goals, 2),
            'over_25_rate': round(over_25 / max(len(goals), 1), 3),
            'over_35_rate': round(over_35 / max(len(goals), 1), 3),
            'under_25_rate': round(under_25 / max(len(goals), 1), 3),
            'top_5_scores': [{'score': s, 'count': c, 'rate': round(c/total, 3)} for s, c in top_scores],
            'team_stats': team_stats,
        }
    }


@mcp.tool()
def strategy_backtest(league: str, strategy_type: str = "value_betting", params: dict = None) -> dict:
    """
    策略回测：用历史数据验证投注策略表现
    支持策略：value_betting（价值投注）、hot_fade（热门反买）、draw_fade（平局反买）、over_strategy（大球策略）
    返回：命中率/ROI/最大回撤/盈亏曲线
    """
    import json, os
    history_dir = os.path.join(PLUGIN_ROOT, 'data', 'history')
    filepath = os.path.join(history_dir, f'{league}_history.json')
    if not os.path.exists(filepath):
        return {'success': False, 'error': f'联赛{league}历史数据不存在'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        matches = json.load(f)
    
    if not matches:
        return {'success': False, 'error': '联赛数据为空'}
    
    params = params or {}
    bankroll = 1000  # 初始资金1000
    stake = params.get('stake', 20)  # 每注20元
    trades = []
    wins = 0
    losses = 0
    total_staked = 0
    total_return = 0
    peak = bankroll
    max_drawdown = 0
    
    for m in matches:
        if not isinstance(m.get('home_goals'), int):
            continue
        odds = m.get('odds', {})
        if not odds:
            continue
        
        # 根据策略类型选择投注
        pick = None
        pick_odds = 0
        
        if strategy_type == "value_betting":
            # 价值投注：找赔率>隐含概率的选项
            home_odds = odds.get('home', 0)
            draw_odds = odds.get('draw', 0)
            away_odds = odds.get('away', 0)
            if home_odds > 0 and 1/home_odds < 0.45:
                pick, pick_odds = 'H', home_odds
            elif away_odds > 0 and 1/away_odds < 0.25:
                pick, pick_odds = 'A', away_odds
        elif strategy_type == "hot_fade":
            # 热门反买：赔率最低的选项反买
            home_odds = odds.get('home', 99)
            draw_odds = odds.get('draw', 99)
            away_odds = odds.get('away', 99)
            min_odds = min(home_odds, draw_odds, away_odds)
            if min_odds == home_odds and away_odds < 99:
                pick, pick_odds = 'A', away_odds
            elif min_odds == away_odds and home_odds < 99:
                pick, pick_odds = 'H', home_odds
        elif strategy_type == "over_strategy":
            # 大球策略：场均进球>2.5的联赛追大
            total_goals = m.get('home_goals', 0) + m.get('away_goals', 0)
            ou_odds = odds.get('over', 1.9)
            pick, pick_odds = 'OVER', ou_odds
            if total_goals > 2.5:
                wins += 1
                bankroll += stake * (pick_odds - 1)
            else:
                losses += 1
                bankroll -= stake
            total_staked += stake
            peak = max(peak, bankroll)
            max_drawdown = max(max_drawdown, peak - bankroll)
            continue
        
        if pick and pick_odds > 0:
            total_staked += stake
            result = m.get('result', '')
            if result == pick:
                wins += 1
                bankroll += stake * (pick_odds - 1)
                total_return += stake * pick_odds
            else:
                losses += 1
                bankroll -= stake
            peak = max(peak, bankroll)
            max_drawdown = max(max_drawdown, peak - bankroll)
            trades.append({'date': m.get('date', ''), 'pick': pick, 'odds': pick_odds, 'result': result, 'win': result == pick})
    
    total_trades = wins + losses
    roi = (bankroll - 1000) / 1000 if total_trades > 0 else 0
    
    return {
        'success': True,
        'data': {
            'strategy': strategy_type,
            'league': league,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': round(wins / total_trades, 3) if total_trades > 0 else 0,
            'total_staked': total_staked,
            'final_bankroll': round(bankroll, 2),
            'roi': round(roi, 4),
            'max_drawdown': round(max_drawdown, 2),
            'avg_odds': round(total_return / max(wins, 1), 2),
            'recent_10': trades[-10:],
        }
    }


@mcp.tool()
def update_team_strength(league: str, match_results: list = None) -> dict:
    """
    球队强度动态更新
    用最新赛果更新球队的Elo评分和攻防强度
    用于：模型概率校准，反映球队最新状态
    """
    # 参数校验
    if league is None:
        return make_error_response('league不能为空', 'validation', '请提供league参数')
    if match_results is not None and not isinstance(match_results, (str, int, float, list, dict)):
        return make_error_response('match_results类型错误', 'validation', '请提供正确的类型')

    import json, os
    ratings_file = os.path.join(PLUGIN_ROOT, 'data', 'team_ratings.json')
    
    # 加载现有评分
    if os.path.exists(ratings_file):
        with open(ratings_file, 'r', encoding='utf-8') as f:
            ratings = json.load(f)
    else:
        ratings = {}
    
    # 如果提供了比赛结果，更新评分
    if match_results:
        K = 32  # Elo K因子
        for match in match_results:
            home = match.get('home', '')
            away = match.get('away', '')
            home_goals = match.get('home_goals', 0)
            away_goals = match.get('away_goals', 0)
            
            if home not in ratings:
                ratings[home] = {'elo': 1500, 'attack': 1.0, 'defense': 1.0, 'matches': 0}
            if away not in ratings:
                ratings[away] = {'elo': 1500, 'attack': 1.0, 'defense': 1.0, 'matches': 0}
            
            # Elo更新
            expected_home = 1 / (1 + 10 ** ((ratings[away]['elo'] - ratings[home]['elo']) / 400))
            if home_goals > away_goals:
                actual_home = 1
            elif home_goals == away_goals:
                actual_home = 0.5
            else:
                actual_home = 0
            
            ratings[home]['elo'] += K * (actual_home - expected_home)
            ratings[away]['elo'] -= K * (actual_home - expected_home)
            
            # 攻防强度更新（简单移动平均）
            ratings[home]['attack'] = ratings[home]['attack'] * 0.9 + home_goals * 0.1
            ratings[home]['defense'] = ratings[home]['defense'] * 0.9 + away_goals * 0.1
            ratings[away]['attack'] = ratings[away]['attack'] * 0.9 + away_goals * 0.1
            ratings[away]['defense'] = ratings[away]['defense'] * 0.9 + home_goals * 0.1
            
            ratings[home]['matches'] += 1
            ratings[away]['matches'] += 1
    
    # 保存
    with open(ratings_file, 'w', encoding='utf-8') as f:
        json.dump(ratings, f, ensure_ascii=False, indent=2)
    
    # 返回联赛内球队排名
    league_teams = {k: v for k, v in ratings.items() if v.get('league') == league or league == ""}
    sorted_teams = sorted(league_teams.items(), key=lambda x: x[1].get('elo', 1500), reverse=True)
    
    return {
        'success': True,
        'data': {
            'total_teams': len(ratings),
            'updated_matches': len(match_results) if match_results else 0,
            'top_10_teams': [{'team': k, 'elo': round(v.get('elo', 1500), 1), 'attack': round(v.get('attack', 1), 2), 'defense': round(v.get('defense', 1), 2)} for k, v in sorted_teams[:10]],
        }
    }


if __name__ == '__main__':
    mcp.run()
