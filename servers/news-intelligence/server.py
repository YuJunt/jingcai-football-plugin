#!/usr/bin/env python3
"""
竞彩足球资讯智能服务器
8大资讯智能聚合、伤停量化、战意分析、裁判因素、赛程疲劳、资讯→λ调整映射
由于竞彩网8大资讯API云IP被封，本服务器提供搜索关键词生成+文本解析框架
LLM用general_search获取资讯后，用本服务器工具解析和量化
"""
import json
import os
import sys
from datetime import datetime

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PLUGIN_ROOT, 'data')

try:
    from fastmcp import FastMCP
    mcp = FastMCP("jingcai-news-intelligence")
except ImportError:
    print("fastmcp未安装，使用模拟模式")
    class FakeMCP:
        def tool(self, fn):
            return fn
    mcp = FakeMCP()


@mcp.tool()
def generate_news_search_keywords(home_team: str, away_team: str, league: str = "") -> dict:
    """
    生成8大资讯的搜索关键词
    LLM用这些关键词调用general_search获取资讯后，再用parse_news_text解析
    """
    keywords = {
        '赛事前瞻': f"{home_team} {away_team} 赛前分析 预测 首发",
        '特征分析': f"{home_team} {away_team} 战术分析 打法特点",
        '历史交锋': f"{home_team} {away_team} 历史交锋 战绩",
        '近期战绩': f"{home_team} 近期战绩 {away_team} 近期状态",
        '伤停信息': f"{home_team} 伤停 {away_team} 伤病 停赛 阵容",
        '积分榜': f"{league} 积分榜 {home_team} 排名 {away_team} 排名" if league else f"{home_team} {away_team} 联赛排名",
        '未来赛程': f"{home_team} 赛程 {away_team} 下一场比赛",
        '射手信息': f"{home_team} 射手榜 {away_team} 进球球员",
        '综合预测': f"{home_team} {away_team} 欧赔 亚盘 大小球 伤停 预测",
    }
    return {
        'success': True,
        'data': {
            'keywords': keywords,
            'search_order': ['综合预测', '伤停信息', '近期战绩', '历史交锋', '赛事前瞻'],
            'note': 'LLM按顺序用general_search搜索，优先获取综合预测和伤停信息',
        }
    }


@mcp.tool()
def parse_news_text(news_text: str, home_team: str, away_team: str) -> dict:
    """
    解析资讯文本，提取结构化信息
    LLM用general_search获取资讯文本后，调用此工具解析
    """
    result = {
        'home_team': home_team,
        'away_team': away_team,
        'injuries': {'home': [], 'away': []},
        'form': {'home': '', 'away': ''},
        'h2h': '',
        'tactics': '',
        'prediction': '',
        'odds_info': '',
        'key_players': {'home': [], 'away': []},
        'confidence': 0,
    }
    
    text = news_text.lower()
    
    # 伤停信息提取
    injury_keywords = ['伤', '缺阵', '停赛', '伤病', '出战成疑', '无法出场', '替补']
    for kw in injury_keywords:
        if kw in news_text:
            # 提取包含关键词的句子
            sentences = news_text.replace('。', '.').replace('！', '!').split('.')
            for s in sentences:
                if kw in s and len(s) < 100:
                    if home_team in s or any(h in s for h in home_team.split()):
                        result['injuries']['home'].append(s.strip())
                    elif away_team in s or any(a in s for a in away_team.split()):
                        result['injuries']['away'].append(s.strip())
    
    # 预测信息提取
    pred_keywords = ['预测', '看好', '预计', '分析认为', '大概率']
    for kw in pred_keywords:
        if kw in news_text:
            sentences = news_text.replace('。', '.').split('.')
            for s in sentences:
                if kw in s and len(s) < 150:
                    result['prediction'] = s.strip()
                    break
    
    # 赔率信息提取
    if '欧赔' in news_text or '亚盘' in news_text or '大小球' in news_text:
        sentences = news_text.replace('。', '.').split('.')
        for s in sentences:
            if ('欧赔' in s or '亚盘' in s or '大小球' in s) and len(s) < 150:
                result['odds_info'] = s.strip()
                break
    
    # 信心度评估
    if result['injuries']['home'] or result['injuries']['away']:
        result['confidence'] += 30
    if result['prediction']:
        result['confidence'] += 30
    if result['odds_info']:
        result['confidence'] += 20
    if len(news_text) > 500:
        result['confidence'] += 20
    result['confidence'] = min(result['confidence'], 100)
    
    return {'success': True, 'data': result}


@mcp.tool()
def quantify_injury_impact(injuries: dict, home_team: str, away_team: str) -> dict:
    """
    量化伤停对比赛的影响
    输入：parse_news_text返回的injuries字段
    输出：伤停影响评分（0-100）和λ调整建议
    """
    home_injuries = injuries.get('home', []) if isinstance(injuries, dict) else []
    away_injuries = injuries.get('away', []) if isinstance(injuries, dict) else []
    
    # 伤停影响评分
    home_impact = min(len(home_injuries) * 15, 60)
    away_impact = min(len(away_injuries) * 15, 60)
    
    # 核心球员伤停加权
    core_keywords = ['前锋', '核心', '主力', '门将', '队长', '最佳射手']
    for inj in home_injuries:
        if any(kw in inj for kw in core_keywords):
            home_impact += 20
    for inj in away_injuries:
        if any(kw in inj for kw in core_keywords):
            away_impact += 20
    
    home_impact = min(home_impact, 100)
    away_impact = min(away_impact, 100)
    
    # λ调整建议
    lambda_adjustments = {
        'home_attack': round(1 - home_impact * 0.003, 3),  # 主队进攻λ乘数
        'away_attack': round(1 - away_impact * 0.003, 3),  # 客队进攻λ乘数
        'home_defense_impact': round(1 + home_impact * 0.002, 3),  # 主队防守→客队λ乘数
        'away_defense_impact': round(1 + away_impact * 0.002, 3),  # 客队防守→主队λ乘数
    }
    
    return {
        'success': True,
        'data': {
            'home_injury_count': len(home_injuries),
            'away_injury_count': len(away_injuries),
            'home_impact_score': home_impact,
            'away_impact_score': away_impact,
            'net_impact': home_impact - away_impact,  # 正=主队伤停更严重
            'lambda_adjustments': lambda_adjustments,
            'recommendation': '主队伤停更严重，下调主队进攻预期' if home_impact > away_impact + 10 else 
                              '客队伤停更严重，下调客队进攻预期' if away_impact > home_impact + 10 else
                              '双方伤停影响相当',
        }
    }


@mcp.tool()
def analyze_motivation(home_team: str, away_team: str, league: str = "", 
                       home_position: int = 0, away_position: int = 0,
                       stage: str = "regular") -> dict:
    """
    战意分析
    根据联赛排名、赛季阶段、杯赛重要性分析双方战意
    """
    motivation = {'home': 50, 'away': 50}  # 基础战意50
    
    # 赛季阶段影响
    stage_factors = {
        'season_start': 0,      # 赛季初，战意一般
        'regular': 0,           # 常规赛，战意一般
        'title_race': 20,       # 争冠阶段，战意高
        'relegation': 25,       # 保级阶段，战意极高
        'european_race': 15,    # 欧战资格争夺，战意高
        'cup_final': 30,        # 杯赛决赛，战意极高
        'cup_semifinal': 20,    # 杯赛半决赛，战意高
        'dead_rubber': -20,     # 无欲无求，战意低
    }
    factor = stage_factors.get(stage, 0)
    motivation['home'] += factor
    motivation['away'] += factor
    
    # 排名影响
    if home_position > 0:
        if home_position <= 4:
            motivation['home'] += 15  # 欧冠区
        elif home_position <= 6:
            motivation['home'] += 10  # 欧战区
        elif home_position >= 18:
            motivation['home'] += 20  # 保级区
    
    if away_position > 0:
        if away_position <= 4:
            motivation['away'] += 15
        elif away_position <= 6:
            motivation['away'] += 10
        elif away_position >= 18:
            motivation['away'] += 20
    
    # 主场加成
    motivation['home'] += 5
    
    # 限制范围
    motivation['home'] = max(0, min(100, motivation['home']))
    motivation['away'] = max(0, min(100, motivation['away']))
    
    # λ调整建议
    lambda_adjustments = {
        'home_motivation': round(1 + (motivation['home'] - 50) * 0.003, 3),
        'away_motivation': round(1 + (motivation['away'] - 50) * 0.003, 3),
    }
    
    return {
        'success': True,
        'data': {
            'home_motivation': motivation['home'],
            'away_motivation': motivation['away'],
            'motivation_gap': motivation['home'] - motivation['away'],
            'stage': stage,
            'lambda_adjustments': lambda_adjustments,
            'recommendation': '主队战意更强' if motivation['home'] > motivation['away'] + 10 else
                              '客队战意更强' if motivation['away'] > motivation['home'] + 10 else
                              '双方战意相当',
        }
    }


@mcp.tool()
def analyze_fixture_congestion(team: str, recent_matches: list = None, days_rest: int = 7) -> dict:
    """
    赛程疲劳分析
    计算球队近期比赛间隔和疲劳程度
    """
    if not recent_matches:
        return {
            'success': True,
            'data': {
                'team': team,
                'fatigue_score': max(0, (7 - days_rest) * 10),
                'days_rest': days_rest,
                'recommendation': '赛程正常' if days_rest >= 5 else '赛程密集，体能可能不足',
                'lambda_adjustment': round(1 - max(0, (7 - days_rest) * 0.01), 3),
            }
        }
    
    intervals = []
    for i in range(1, len(recent_matches)):
        try:
            d1 = datetime.strptime(recent_matches[i-1].get('date', ''), '%Y-%m-%d')
            d2 = datetime.strptime(recent_matches[i].get('date', ''), '%Y-%m-%d')
            intervals.append((d2 - d1).days)
        except:
            continue
    
    avg_interval = sum(intervals) / len(intervals) if intervals else 7
    fatigue = max(0, min(100, (7 - avg_interval) * 15))
    
    return {
        'success': True,
        'data': {
            'team': team,
            'recent_matches': len(recent_matches),
            'avg_interval_days': round(avg_interval, 1),
            'fatigue_score': fatigue,
            'lambda_adjustment': round(1 - fatigue * 0.002, 3),
            'recommendation': '高疲劳，体能可能不足' if fatigue > 60 else
                              '中等疲劳，需关注轮换' if fatigue > 30 else
                              '低疲劳，体能充足',
        }
    }


@mcp.tool()
def news_to_lambda_mapping(injury_impact: dict = None, motivation: dict = None,
                           fixture_congestion: dict = None, base_home_lambda: float = 1.5,
                           base_away_lambda: float = 1.2) -> dict:
    """
    资讯→λ调整因子自动映射
    整合伤停/战意/赛程疲劳，输出最终的λ调整建议
    """
    home_lambda = base_home_lambda
    away_lambda = base_away_lambda
    adjustments = []
    
    # 伤停影响
    if injury_impact:
        lambda_adj = injury_impact.get('lambda_adjustments', {})
        home_lambda *= lambda_adj.get('home_attack', 1.0)
        away_lambda *= lambda_adj.get('away_attack', 1.0)
        home_lambda *= lambda_adj.get('away_defense_impact', 1.0)  # 客队防守差→主队λ上升
        away_lambda *= lambda_adj.get('home_defense_impact', 1.0)  # 主队防守差→客队λ上升
        adjustments.append(f"伤停调整: 主×{lambda_adj.get('home_attack', 1):.3f} 客×{lambda_adj.get('away_attack', 1):.3f}")
    
    # 战意影响
    if motivation:
        lambda_adj = motivation.get('lambda_adjustments', {})
        home_lambda *= lambda_adj.get('home_motivation', 1.0)
        away_lambda *= lambda_adj.get('away_motivation', 1.0)
        adjustments.append(f"战意调整: 主×{lambda_adj.get('home_motivation', 1):.3f} 客×{lambda_adj.get('away_motivation', 1):.3f}")
    
    # 赛程疲劳
    if fixture_congestion:
        adj = fixture_congestion.get('lambda_adjustment', 1.0)
        home_lambda *= adj
        away_lambda *= adj
        adjustments.append(f"赛程疲劳调整: ×{adj:.3f}")
    
    return {
        'success': True,
        'data': {
            'base_home_lambda': base_home_lambda,
            'base_away_lambda': base_away_lambda,
            'adjusted_home_lambda': round(home_lambda, 3),
            'adjusted_away_lambda': round(away_lambda, 3),
            'total_goals': round(home_lambda + away_lambda, 3),
            'adjustments': adjustments,
            'recommendation': f"将λ从({base_home_lambda},{base_away_lambda})调整为({home_lambda:.2f},{away_lambda:.2f})",
        }
    }


@mcp.tool()
def aggregate_news_intelligence(home_team: str, away_team: str, league: str = "",
                                news_text: str = "", home_position: int = 0,
                                away_position: int = 0, days_rest_home: int = 7,
                                days_rest_away: int = 7) -> dict:
    """
    资讯智能聚合一键工具
    整合：资讯解析→伤停量化→战意分析→赛程疲劳→λ调整映射
    LLM用general_search获取news_text后，调用此工具获得完整资讯分析
    """
    # 1. 解析资讯
    parsed = parse_news_text(news_text, home_team, away_team) if news_text else {'data': {'injuries': {'home': [], 'away': []}}}
    parsed_data = parsed.get('data', {})
    
    # 2. 伤停量化
    injury = quantify_injury_impact(parsed_data.get('injuries', {}), home_team, away_team)
    
    # 3. 战意分析
    mot = analyze_motivation(home_team, away_team, league, home_position, away_position)
    
    # 4. 赛程疲劳
    fatigue_home = analyze_fixture_congestion(home_team, days_rest=days_rest_home)
    fatigue_away = analyze_fixture_congestion(away_team, days_rest=days_rest_away)
    
    # 5. λ调整映射
    lambda_map = news_to_lambda_mapping(
        injury_impact=injury.get('data'),
        motivation=mot.get('data'),
        fixture_congestion=fatigue_home.get('data'),
    )
    
    return {
        'success': True,
        'data': {
            'parsed_news': parsed_data,
            'injury_impact': injury.get('data'),
            'motivation': mot.get('data'),
            'fatigue_home': fatigue_home.get('data'),
            'fatigue_away': fatigue_away.get('data'),
            'lambda_mapping': lambda_map.get('data'),
            'news_confidence': parsed_data.get('confidence', 0),
            'summary': f"伤停影响(主{injury['data']['home_impact_score']}/客{injury['data']['away_impact_score']}) "
                       f"战意(主{mot['data']['home_motivation']}/客{mot['data']['away_motivation']}) "
                       f"λ建议({lambda_map['data']['adjusted_home_lambda']},{lambda_map['data']['adjusted_away_lambda']})",
        }
    }


if __name__ == '__main__':
    mcp.run()
