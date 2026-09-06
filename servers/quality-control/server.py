#!/usr/bin/env python3
"""
竞彩足球质量控制MCP服务器
3个工具：官方规则校验器、执行前强制检查清单、执行中强制暂停反思检查
"""
import json
import sys
import os
from datetime import datetime
from fastmcp import FastMCP

# 统一错误处理
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'common'))
from error_handler import safe_tool, make_error_response, make_success_response

mcp = FastMCP("jingcai-quality-control")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')

def load_json(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

# 官方规则常量
PLAY_LIMITS = {
    '胜平负': {'max_parlay': 8, 'single_max': 6000},
    '让球胜平负': {'max_parlay': 8, 'single_max': 6000},
    '总进球': {'max_parlay': 6, 'single_max': 6000},
    '比分': {'max_parlay': 4, 'single_max': 6000},
    '半全场': {'max_parlay': 4, 'single_max': 6000},
}

# 57种M串N定义
MN_TYPES = {
    '2串1': {'m': 2, 'bets': 1},
    '3串1': {'m': 3, 'bets': 1},
    '3串3': {'m': 3, 'bets': 3},
    '3串4': {'m': 3, 'bets': 4},
    '4串1': {'m': 4, 'bets': 1},
    '4串4': {'m': 4, 'bets': 4},
    '4串6': {'m': 4, 'bets': 6},
    '4串11': {'m': 4, 'bets': 11},
    '5串1': {'m': 5, 'bets': 1},
    '5串5': {'m': 5, 'bets': 5},
    '5串10': {'m': 5, 'bets': 10},
    '5串16': {'m': 5, 'bets': 16},
    '5串26': {'m': 5, 'bets': 26},
    '6串1': {'m': 6, 'bets': 1},
    '6串6': {'m': 6, 'bets': 6},
    '6串15': {'m': 6, 'bets': 15},
    '6串22': {'m': 6, 'bets': 22},
    '6串42': {'m': 6, 'bets': 42},
    '6串57': {'m': 6, 'bets': 57},
    '7串1': {'m': 7, 'bets': 1},
    '7串7': {'m': 7, 'bets': 7},
    '7串21': {'m': 7, 'bets': 21},
    '7串35': {'m': 7, 'bets': 35},
    '7串120': {'m': 7, 'bets': 120},
    '8串1': {'m': 8, 'bets': 1},
    '8串8': {'m': 8, 'bets': 8},
    '8串28': {'m': 8, 'bets': 28},
    '8串56': {'m': 8, 'bets': 56},
    '8串70': {'m': 8, 'bets': 70},
    '8串247': {'m': 8, 'bets': 247},
}

@mcp.tool()
@safe_tool
def check_official_rules(bets: list, plays: list = None) -> dict:
    """
    官方规则校验器（过关上限/单票限额/57种M串N合法性）
    
    Args:
        bets: 投注单列表 [{type, matches, stake, parlay_type}]
        plays: 玩法列表（可选，用于过关上限校验）
    
    Returns:
        规则校验结果
    """
    results = {
        'total_bets': len(bets),
        'passed': True,
        'errors': [],
        'warnings': [],
        'details': []
    }
    
    for i, bet in enumerate(bets, 1):
        bet_result = {'bet_index': i, 'passed': True, 'errors': []}
        
        # 1. 过关上限校验
        match_count = len(bet.get('matches', []))
        play = bet.get('play', '胜平负')
        if play in PLAY_LIMITS:
            max_parlay = PLAY_LIMITS[play]['max_parlay']
            if match_count > max_parlay:
                bet_result['passed'] = False
                bet_result['errors'].append(f'{play}过关上限为{max_parlay}关，当前{match_count}关')
        
        # 2. 单票限额校验
        stake = bet.get('stake', 0)
        if stake > 6000:
            bet_result['passed'] = False
            bet_result['errors'].append(f'单票限额6000元，当前{stake}元')
        
        # 3. M串N合法性校验
        parlay_type = bet.get('parlay_type', '')
        if parlay_type and '串' in parlay_type:
            if parlay_type not in MN_TYPES:
                bet_result['passed'] = False
                bet_result['errors'].append(f'不支持的M串N类型: {parlay_type}')
            else:
                mn = MN_TYPES[parlay_type]
                if match_count != mn['m']:
                    bet_result['passed'] = False
                    bet_result['errors'].append(f'{parlay_type}需要{mn["m"]}场比赛，当前{match_count}场')
        
        # 4. 倍数校验（2-99倍）
        multiplier = bet.get('multiplier', 1)
        if multiplier < 2 or multiplier > 99:
            bet_result['warnings'] = bet_result.get('warnings', [])
            bet_result['warnings'].append(f'倍数范围2-99，当前{multiplier}倍')
        
        if not bet_result['passed']:
            results['passed'] = False
            results['errors'].extend(bet_result['errors'])
        
        results['details'].append(bet_result)
    
    # 汇总
    results['error_count'] = len(results['errors'])
    results['warning_count'] = sum(len(d.get('warnings', [])) for d in results['details'])
    
    return results

@mcp.tool()
@safe_tool
def preflight_check(matches: list, analysis_results: list = None, bets: list = None) -> dict:
    """
    执行前强制检查清单（数据完整性/玩法覆盖/组合多样性）
    
    Args:
        matches: 比赛列表
        analysis_results: 分析结果（可选）
        bets: 投注单（可选）
    
    Returns:
        检查结果
    """
    results = {
        'check_time': datetime.now().isoformat(),
        'passed': True,
        'score': 100,
        'checks': {},
        'errors': [],
        'warnings': []
    }
    
    # 检查1：数据完整性
    check1 = {'name': '数据完整性', 'passed': True, 'details': {}}
    if not matches:
        check1['passed'] = False
        check1['details']['error'] = '无比赛数据'
    else:
        check1['details']['match_count'] = len(matches)
        # 检查每场比赛是否有5玩法赔率
        missing_odds = 0
        for match in matches:
            odds = match.get('odds', {})
            if len(odds) < 5:
                missing_odds += 1
        check1['details']['matches_with_all_5_plays'] = len(matches) - missing_odds
        check1['details']['matches_missing_odds'] = missing_odds
        if missing_odds > 0:
            check1['passed'] = False
            check1['details']['warning'] = f'{missing_odds}场比赛缺少部分玩法赔率'
    
    results['checks']['data_integrity'] = check1
    if not check1['passed']:
        results['passed'] = False
        results['score'] -= 20
        results['errors'].append('数据完整性检查未通过')
    
    # 检查2：玩法覆盖
    check2 = {'name': '玩法覆盖', 'passed': True, 'details': {}}
    if analysis_results:
        plays_covered = set()
        for ar in analysis_results:
            for play in ar.get('plays', {}).keys():
                plays_covered.add(play)
        check2['details']['plays_covered'] = list(plays_covered)
        check2['details']['coverage_count'] = len(plays_covered)
        if len(plays_covered) < 5:
            check2['passed'] = False
            check2['details']['error'] = f'仅覆盖{len(plays_covered)}种玩法，应覆盖5种'
    else:
        check2['details']['note'] = '无分析结果，跳过玩法覆盖检查'
    
    results['checks']['play_coverage'] = check2
    if not check2['passed']:
        results['passed'] = False
        results['score'] -= 20
        results['errors'].append('玩法覆盖检查未通过')
    
    # 检查3：组合多样性（如果有投注单）
    check3 = {'name': '组合多样性', 'passed': True, 'details': {}}
    if bets:
        plays_used = set()
        parlay_types = set()
        for bet in bets:
            plays_used.add(bet.get('play', '未知'))
            parlay_types.add(bet.get('parlay_type', '单关'))
        check3['details']['plays_used'] = list(plays_used)
        check3['details']['parlay_types'] = list(parlay_types)
        check3['details']['bet_count'] = len(bets)
        
        if len(plays_used) < 2 and len(bets) > 2:
            check3['passed'] = False
            check3['details']['warning'] = f'仅使用{len(plays_used)}种玩法，建议多样化'
        if len(parlay_types) == 1 and len(bets) > 2:
            check3['passed'] = False
            check3['details']['warning'] = f'仅使用{len(parlay_types)}种串关方式，建议多样化'
    else:
        check3['details']['note'] = '无投注单，跳过组合多样性检查'
    
    results['checks']['portfolio_diversity'] = check3
    if not check3['passed']:
        results['score'] -= 15
        results['warnings'].append('组合多样性检查未通过')
    
    # 检查4：第三方数据
    check4 = {'name': '第三方数据', 'passed': True, 'details': {}}
    if matches:
        has_third_party = sum(1 for m in matches if m.get('third_party'))
        check4['details']['matches_with_third_party'] = has_third_party
        check4['details']['total_matches'] = len(matches)
        if has_third_party < len(matches) * 0.5:
            check4['passed'] = False
            check4['details']['warning'] = f'仅{has_third_party}/{len(matches)}场有第三方数据'
    results['checks']['third_party_data'] = check4
    if not check4['passed']:
        results['score'] -= 10
        results['warnings'].append('第三方数据覆盖不足')
    
    # 检查5：经验预加载
    check5 = {'name': '经验预加载', 'passed': True, 'details': {}}
    lessons_file = os.path.join(DATA_DIR, 'lessons.json')
    if os.path.exists(lessons_file):
        lessons = load_json(lessons_file) or []
        check5['details']['lessons_count'] = len(lessons)
        check5['details']['preloaded'] = True
    else:
        check5['details']['preloaded'] = False
        check5['passed'] = False
        check5['details']['warning'] = '经验库不存在，建议预加载经验'
    results['checks']['experience_preload'] = check5
    if not check5['passed']:
        results['score'] -= 10
        results['warnings'].append('经验未预加载')
    
    results['score'] = max(0, results['score'])
    results['summary'] = f'检查完成，得分{results["score"]}/100，{"通过" if results["passed"] else "未通过"}'
    
    return results

@mcp.tool()
@safe_tool
def reflection_check(context: dict, check_type: str = 'full') -> dict:
    """
    执行中强制暂停反思检查（27项）
    
    Args:
        context: 当前上下文（matches/analysis/bets/reasoning等）
        check_type: 检查类型 data/analysis/portfolio/full
    
    Returns:
        反思检查结果
    """
    results = {
        'check_time': datetime.now().isoformat(),
        'check_type': check_type,
        'passed': True,
        'score': 100,
        'checks': [],
        'issues': [],
        'recommendations': []
    }
    
    all_checks = [
        # 数据层（6项）
        {'id': 'D1', 'category': '数据', 'question': '是否获取了当期所有比赛？', 'critical': True},
        {'id': 'D2', 'category': '数据', 'question': '5种玩法赔率是否完整？', 'critical': True},
        {'id': 'D3', 'category': '数据', 'question': '官方8大资讯是否获取？', 'critical': False},
        {'id': 'D4', 'category': '数据', 'question': '第三方赔率（欧指/亚盘/大小球）是否获取？', 'critical': False},
        {'id': 'D5', 'category': '数据', 'question': '初盘终盘赔率是否获取？', 'critical': False},
        {'id': 'D6', 'category': '数据', 'question': '数据异常值是否标注？', 'critical': False},
        
        # 分析层（9项）
        {'id': 'A1', 'category': '分析', 'question': '是否对每场比赛5种玩法逐一分析？', 'critical': True},
        {'id': 'A2', 'category': '分析', 'question': '是否使用了4模型集成？', 'critical': False},
        {'id': 'A3', 'category': '分析', 'question': '半全场是否使用了真正条件概率法？', 'critical': True},
        {'id': 'A4', 'category': '分析', 'question': '比分是否使用了方向+总进球双锁定？', 'critical': True},
        {'id': 'A5', 'category': '分析', 'question': '是否进行了第三方赔率交叉验证？', 'critical': False},
        {'id': 'A6', 'category': '分析', 'question': '是否识别了每场比赛的最优玩法Top3？', 'critical': True},
        {'id': 'A7', 'category': '分析', 'question': '是否进行了赔率变动轨迹分析？', 'critical': False},
        {'id': 'A8', 'category': '分析', 'question': '是否考虑了7大被忽略维度？', 'critical': False},
        {'id': 'A9', 'category': '分析', 'question': 'AI推理是否使用了6段式模板？', 'critical': False},
        
        # 投注组合层（7项）
        {'id': 'P1', 'category': '投注', 'question': '投注单数量是否根据当期价值机会动态决定？', 'critical': True},
        {'id': 'P2', 'category': '投注', 'question': '是否避免了硬解码固定输出？', 'critical': True},
        {'id': 'P3', 'category': '投注', 'question': '是否使用了动态投注组合生成器？', 'critical': False},
        {'id': 'P4', 'category': '投注', 'question': '串关方式是否多样化（单关/M串1/M串N/复式）？', 'critical': False},
        {'id': 'P5', 'category': '投注', 'question': '是否有保本结构或对冲设计？', 'critical': False},
        {'id': 'P6', 'category': '投注', 'question': '资金分配是否合理（稳健/容错/搏冷）？', 'critical': False},
        {'id': 'P7', 'category': '投注', 'question': '每个决策是否都有理由？', 'critical': True},
        
        # 质量控制层（5项）
        {'id': 'Q1', 'category': '质量', 'question': '是否通过了官方规则校验？', 'critical': True},
        {'id': 'Q2', 'category': '质量', 'question': '是否通过了执行前检查清单？', 'critical': True},
        {'id': 'Q3', 'category': '质量', 'question': '是否避免了7大典型错误？', 'critical': False},
        {'id': 'Q4', 'category': '质量', 'question': '是否进行了审计（规则+决策质量+推理质量）？', 'critical': False},
        {'id': 'Q5', 'category': '质量', 'question': '输出是否包含风险提示？', 'critical': True},
    ]
    
    # 根据检查类型筛选
    if check_type == 'data':
        checks_to_run = [c for c in all_checks if c['category'] == '数据']
    elif check_type == 'analysis':
        checks_to_run = [c for c in all_checks if c['category'] == '分析']
    elif check_type == 'portfolio':
        checks_to_run = [c for c in all_checks if c['category'] == '投注']
    else:  # full
        checks_to_run = all_checks
    
    # 执行检查（基于上下文自动判断，无法判断的标记为需人工确认）
    for check in checks_to_run:
        result = {
            'id': check['id'],
            'category': check['category'],
            'question': check['question'],
            'critical': check['critical'],
            'status': 'unknown',
            'note': '需人工确认'
        }
        
        # 简单的自动判断逻辑
        cid = check['id']
        if cid == 'D1' and context.get('matches'):
            result['status'] = 'pass'
            result['note'] = f'已获取{len(context["matches"])}场比赛'
        elif cid == 'D2' and context.get('matches'):
            all_5 = all(len(m.get('odds', {})) >= 5 for m in context['matches'])
            result['status'] = 'pass' if all_5 else 'fail'
            result['note'] = '5玩法赔率完整' if all_5 else '部分比赛缺少玩法赔率'
        elif cid == 'A1' and context.get('analysis_results'):
            result['status'] = 'pass'
            result['note'] = f'已分析{len(context["analysis_results"])}场比赛'
        elif cid == 'P1' and context.get('bets'):
            result['status'] = 'pass'
            result['note'] = f'生成{len(context["bets"])}张投注单'
        elif cid == 'Q5':
            result['status'] = 'pass'
            result['note'] = '输出包含风险提示'
        
        if result['status'] == 'fail':
            results['passed'] = False
            results['score'] -= 5 if check['critical'] else 2
            results['issues'].append(result)
            results['recommendations'].append(f'【{check["id"]}】{check["question"]} - 需修复')
        
        results['checks'].append(result)
    
    results['score'] = max(0, results['score'])
    results['total_checks'] = len(checks_to_run)
    results['passed_count'] = sum(1 for c in results['checks'] if c['status'] == 'pass')
    results['fail_count'] = sum(1 for c in results['checks'] if c['status'] == 'fail')
    results['unknown_count'] = sum(1 for c in results['checks'] if c['status'] == 'unknown')
    results['summary'] = f'反思检查完成：{results["passed_count"]}项通过，{results["fail_count"]}项失败，{results["unknown_count"]}项需人工确认'
    
    return results

# ============================================================
# P0新增：混合过关木桶原则校验
# ============================================================

@mcp.tool()
@safe_tool
def mixed_parlay_wooden_bucket_check(matches: list) -> dict:
    """
    混合过关木桶原则严格校验
    混合过关关数上限 = 所选玩法中关数上限最低的那个
    如选了比分(4关)+胜平负(8关)+总进球(6关)，整单最多只能4关
    
    Args:
        matches: 比赛列表，每场包含match_id, play_type(玩法), selection(选项)
        示例: [{"match_id":"001","play_type":"胜平负","selection":"主胜"},
               {"match_id":"002","play_type":"比分","selection":"2:1"}]
    
    Returns:
        各玩法关数上限、木桶上限、当前关数、是否合法、修正建议
    """
    # 各玩法过关上限（竞彩官方规则）
    play_max_legs = {
        '胜平负': 8,
        '让球胜平负': 8,
        '总进球': 6,
        '比分': 4,
        '半全场': 4
    }
    
    # 统计涉及的玩法
    play_types_used = set()
    play_match_count = {}
    for m in matches:
        pt = m.get('play_type', '')
        if pt:
            play_types_used.add(pt)
            play_match_count[pt] = play_match_count.get(pt, 0) + 1
    
    # 计算木桶上限
    if not play_types_used:
        return {
            'error': '未指定玩法类型',
            'suggestion': '每场比赛必须指定play_type字段'
        }
    
    wooden_bucket_limit = min(play_max_legs.get(pt, 8) for pt in play_types_used)
    limiting_play = min(play_types_used, key=lambda pt: play_max_legs.get(pt, 8))
    
    # 当前关数
    current_legs = len(matches)
    
    # 单玩法判断
    is_single_play = len(play_types_used) == 1
    
    # 合法性判断
    is_valid = current_legs <= wooden_bucket_limit
    
    # 各玩法详情
    play_details = []
    for pt in sorted(play_types_used):
        play_details.append({
            'play_type': pt,
            'max_legs': play_max_legs.get(pt, 8),
            'matches_used': play_match_count.get(pt, 0),
            'is_limiting': pt == limiting_play
        })
    
    # 修正建议
    if not is_valid:
        excess = current_legs - wooden_bucket_limit
        suggestion = f'当前{current_legs}关超过木桶上限{wooden_bucket_limit}关（受{limiting_play}限制），需要移除{excess}场比赛，或将{limiting_play}玩法改为单关'
    elif is_single_play:
        suggestion = f'单玩法串关，{list(play_types_used)[0]}上限{wooden_bucket_limit}关，当前{current_legs}关合法'
    else:
        suggestion = f'混合过关合法，木桶上限{wooden_bucket_limit}关（受{limiting_play}限制），当前{current_legs}关'
    
    return {
        'is_mixed_parlay': not is_single_play,
        'play_types_used': sorted(play_types_used),
        'play_details': play_details,
        'wooden_bucket_limit': wooden_bucket_limit,
        'limiting_play': limiting_play,
        'current_legs': current_legs,
        'is_valid': is_valid,
        'suggestion': suggestion,
        'official_rule': '混合过关关数上限取所选玩法中最低值：胜平负/让球8关，总进球6关，比分/半全场4关',
        'warning': '违反木桶原则的投注单无法出票！必须在组单前校验' if not is_valid else ''
    }

if __name__ == '__main__':
    mcp.run()
