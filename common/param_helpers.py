#!/usr/bin/env python3
"""
参数辅助模块
为复杂参数的MCP工具提供参数构造辅助函数和验证函数
"""
from typing import Any, Dict, List, Optional


def make_strategy_config(
    name: str,
    ev_threshold: float = 0.05,
    plays: List[str] = None,
    max_parlay: int = 4,
    kelly_fraction: float = 0.25,
    min_odds: float = 1.5,
    max_odds: float = 10.0
) -> Dict[str, Any]:
    """
    构造策略配置（用于strategy_ab_test工具）

    Args:
        name: 策略名称
        ev_threshold: EV门槛（默认0.05=5%）
        plays: 允许的玩法列表（默认全部5种）
        max_parlay: 最大串关数（默认4）
        kelly_fraction: Kelly系数（默认0.25）
        min_odds: 最低赔率（默认1.5）
        max_odds: 最高赔率（默认10.0）

    Returns:
        策略配置字典

    示例:
        strategy_a = make_strategy_config("保守策略", ev_threshold=0.10, max_parlay=2)
        strategy_b = make_strategy_config("激进策略", ev_threshold=0.03, max_parlay=6)
    """
    if plays is None:
        plays = ["胜平负", "让球胜平负", "总进球", "比分", "半全场"]

    return {
        "name": name,
        "ev_threshold": ev_threshold,
        "plays": plays,
        "max_parlay": max_parlay,
        "kelly_fraction": kelly_fraction,
        "min_odds": min_odds,
        "max_odds": max_odds,
    }


def make_value_option(
    match_id: str,
    play: str,
    option: str,
    odds: float,
    model_prob: float,
    ev: float,
    reason: str = ""
) -> Dict[str, Any]:
    """
    构造价值选项（用于dynamic_portfolio_generator工具）

    Args:
        match_id: 比赛编号（如"001"）
        play: 玩法（胜平负/让球胜平负/总进球/比分/半全场）
        option: 选项（如"主胜"/"让平"/"2球"）
        odds: 赔率
        model_prob: 模型概率
        ev: 期望值
        reason: 推荐理由

    Returns:
        价值选项字典

    示例:
        option1 = make_value_option("001", "胜平负", "主胜", 1.85, 0.58, 0.073, "主队状态火热")
    """
    return {
        "match_id": match_id,
        "play": play,
        "option": option,
        "odds": odds,
        "model_prob": model_prob,
        "ev": ev,
        "reason": reason,
    }


def make_match_data(
    match_id: str,
    league: str,
    home: str,
    away: str,
    spf_odds: List[float] = None,
    rq_odds: List[float] = None,
    handicap: str = "",
    info: Dict = None
) -> Dict[str, Any]:
    """
    构造比赛数据（用于multi_agent_debate等工具）

    Args:
        match_id: 比赛编号
        league: 联赛名称
        home: 主队名称
        away: 客队名称
        spf_odds: 胜平负赔率 [主胜, 平, 客胜]
        rq_odds: 让球胜平负赔率 [让胜, 让平, 让负]
        handicap: 让球数（如"-1"）
        info: 比赛资讯字典

    Returns:
        比赛数据字典

    示例:
        match = make_match_data("001", "英超", "利物浦", "阿森纳", [1.95, 3.40, 3.80], handicap="0")
    """
    if spf_odds is None:
        spf_odds = [2.0, 3.2, 3.5]
    if info is None:
        info = {}

    return {
        "match_id": match_id,
        "league": league,
        "home": home,
        "away": away,
        "handicap": handicap,
        "odds": {
            "胜平负": {"odds": spf_odds, "option_names": ["主胜", "平局", "客胜"]},
            "让球胜平负": {"odds": rq_odds or [2.0, 3.2, 3.5], "option_names": ["让胜", "让平", "让负"]},
        },
        "info": info,
    }


def validate_strategy_config(config: Dict) -> Optional[str]:
    """
    验证策略配置格式

    Args:
        config: 策略配置字典

    Returns:
        如果验证失败返回错误消息，否则返回None
    """
    required_fields = ["name", "ev_threshold", "plays", "max_parlay"]
    for field in required_fields:
        if field not in config:
            return f"策略配置缺少必填字段: {field}"

    if not isinstance(config["ev_threshold"], (int, float)):
        return "ev_threshold必须是数字"

    if not isinstance(config["plays"], list):
        return "plays必须是列表"

    if not isinstance(config["max_parlay"], int):
        return "max_parlay必须是整数"

    return None


def validate_value_options(options: List) -> Optional[str]:
    """
    验证价值选项列表格式

    Args:
        options: 价值选项列表

    Returns:
        如果验证失败返回错误消息，否则返回None
    """
    if not isinstance(options, list):
        return "value_options必须是列表"

    if len(options) == 0:
        return "value_options不能为空"

    required_fields = ["match_id", "play", "option", "odds"]
    for i, opt in enumerate(options):
        if not isinstance(opt, dict):
            return f"第{i+1}个选项必须是字典"
        for field in required_fields:
            if field not in opt:
                return f"第{i+1}个选项缺少必填字段: {field}"

    return None


# 便捷导入
__all__ = [
    'make_strategy_config',
    'make_value_option',
    'make_match_data',
    'validate_strategy_config',
    'validate_value_options',
]
