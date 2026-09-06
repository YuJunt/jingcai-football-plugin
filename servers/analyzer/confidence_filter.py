#!/usr/bin/env python3
"""
置信度过滤模块
来源：lottery-data项目 confidence_filter.py 整合
算法：借鉴 footy-edge，决策层"少而精"

对每个候选选择多维打分（0-100），只留高置信：
总分 = prob_score + consensus_score + edge_score + steam_score - disp_penalty

1. prob_score: 模型概率（0.5→50, 0.8→80）
2. consensus_score: 欧指凯利方差共识（<0.005→25, <0.02→10）
3. edge_score: 模型概率-市场隐含（边际越大市场越错，≤20）
4. steam_score: 盘口水位变化方向确认（强→30, 温和→15, 稳定→5）
5. disp_penalty: 欧指离散度惩罚（std>0.03→-15）

阈值：total < 60 过滤。设计目标：FEW high-accuracy picks, NOT many noisy ones.
"""
import math
from typing import Dict, List, Optional


# 阈值
MIN_TOTAL = 60.0
MIN_PROB = 0.45
MIN_EDGE = 0.02


def calc_prob_score(model_prob: float) -> float:
    """概率得分：0.5→50, 0.8→80, 线性映射，上限90"""
    if model_prob <= 0:
        return 0
    score = model_prob * 100
    return min(90, max(0, score))


def calc_consensus_score(kelly_variance: float = None, odds_std: float = None) -> float:
    """
    共识得分：博彩公司之间的赔率一致性
    方式1：凯利方差（越小越一致）
    方式2：赔率标准差（越小越一致）
    """
    if kelly_variance is not None:
        if kelly_variance < 0.005:
            return 25
        elif kelly_variance < 0.02:
            return 10
        elif kelly_variance < 0.05:
            return 5
        else:
            return 0
    if odds_std is not None:
        if odds_std < 0.03:
            return 25
        elif odds_std < 0.08:
            return 10
        elif odds_std < 0.15:
            return 5
        else:
            return 0
    return 5  # 默认中性


def calc_edge_score(model_prob: float, market_implied: float) -> float:
    """
    边际得分：模型概率 - 市场隐含概率
    边际越大说明市场越错，上限20
    """
    edge = model_prob - market_implied
    if edge <= 0:
        return 0
    return min(20, edge * 100)


def calc_steam_score(steam_movement: str = "stable", odds_change_pct: float = 0) -> float:
    """
    盘口水位变化方向确认
    steam_movement: "strong_move" / "moderate_move" / "stable" / "contradictory"
    odds_change_pct: 赔率变动百分比（绝对值）
    """
    if steam_movement == "strong_move" or odds_change_pct > 3:
        return 30
    elif steam_movement == "moderate_move" or odds_change_pct > 1:
        return 15
    elif steam_movement == "contradictory":
        return 0
    else:
        return 5  # stable


def calc_disp_penalty(odds_std: float = None, kelly_variance: float = None) -> float:
    """
    离散度惩罚：赔率分歧越大惩罚越重
    返回负值（惩罚）
    """
    if odds_std is not None:
        if odds_std > 0.15:
            return -15
        elif odds_std > 0.08:
            return -8
        elif odds_std > 0.03:
            return -3
        else:
            return 0
    if kelly_variance is not None:
        if kelly_variance > 0.05:
            return -15
        elif kelly_variance > 0.02:
            return -8
        elif kelly_variance > 0.005:
            return -3
        else:
            return 0
    return 0


def confidence_score(
    model_prob: float,
    market_implied: float,
    odds_std: float = None,
    kelly_variance: float = None,
    steam_movement: str = "stable",
    odds_change_pct: float = 0,
) -> Dict:
    """
    计算单选项的置信度总分

    Args:
        model_prob: 模型预测概率
        market_implied: 市场隐含概率（去水后）
        odds_std: 各博彩公司赔率标准差（可选）
        kelly_variance: 凯利方差（可选，与odds_std二选一）
        steam_movement: 盘口变动方向
        odds_change_pct: 赔率变动百分比

    Returns:
        {
            "total": 总分,
            "pass": 是否通过阈值,
            "breakdown": 各维度得分,
            "level": 置信等级(高/中/低)
        }
    """
    prob = calc_prob_score(model_prob)
    consensus = calc_consensus_score(kelly_variance, odds_std)
    edge = calc_edge_score(model_prob, market_implied)
    steam = calc_steam_score(steam_movement, odds_change_pct)
    disp = calc_disp_penalty(odds_std, kelly_variance)

    total = prob + consensus + edge + steam + disp

    # 硬门槛：概率太低或无边际直接不通过
    hard_fail = model_prob < MIN_PROB or (model_prob - market_implied) < MIN_EDGE

    return {
        "total": round(total, 1),
        "pass": (total >= MIN_TOTAL) and (not hard_fail),
        "hard_fail": hard_fail,
        "level": "高" if total >= 75 else ("中" if total >= 60 else "低"),
        "breakdown": {
            "prob_score": round(prob, 1),
            "consensus_score": round(consensus, 1),
            "edge_score": round(edge, 1),
            "steam_score": round(steam, 1),
            "disp_penalty": round(disp, 1),
        },
        "threshold": MIN_TOTAL,
        "recommendation": "保留" if (total >= MIN_TOTAL and not hard_fail) else "过滤",
    }


def batch_confidence_filter(candidates: List[Dict]) -> List[Dict]:
    """
    批量过滤候选选项

    Args:
        candidates: 候选列表，每个元素需包含：
            - match_num: 场次编号
            - play: 玩法
            - option: 选项
            - model_prob: 模型概率
            - market_implied: 市场隐含概率
            - odds_std / kelly_variance（可选）
            - steam_movement / odds_change_pct（可选）

    Returns:
        通过过滤的候选列表，按总分降序
    """
    results = []
    for c in candidates:
        score = confidence_score(
            model_prob=c.get("model_prob", 0),
            market_implied=c.get("market_implied", 0),
            odds_std=c.get("odds_std"),
            kelly_variance=c.get("kelly_variance"),
            steam_movement=c.get("steam_movement", "stable"),
            odds_change_pct=c.get("odds_change_pct", 0),
        )
        c["confidence"] = score
        if score["pass"]:
            results.append(c)

    results.sort(key=lambda x: x["confidence"]["total"], reverse=True)
    return results
