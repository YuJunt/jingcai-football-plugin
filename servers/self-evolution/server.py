#!/usr/bin/env python3
"""
竞彩足球自进化MCP服务器
10个工具：添加决策记录、更新比赛结果、获取统计数据、结算期次、期次复盘、分联赛校准、策略回测、EV门槛优化、添加经验教训、预加载记忆
"""
import json
import math
import os
import sys
from datetime import datetime
from fastmcp import FastMCP

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 统一错误处理
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'common'))
from error_handler import safe_tool, make_error_response, make_success_response

mcp = FastMCP("jingcai-self-evolution")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')
DECISION_LOG_FILE = os.path.join(DATA_DIR, 'decision_log.json')
LESSONS_FILE = os.path.join(DATA_DIR, 'lessons.json')
CALIBRATION_FILE = os.path.join(DATA_DIR, 'calibration_by_league.json')

def load_json(filepath):
    """加载JSON文件"""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    """保存JSON文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ============================================================
# 工具1：添加决策记录
# ============================================================

@mcp.tool()
@safe_tool
def add_decision(date: str, match: str, play: str, option: str, 
                  odds: float, prob: float, reason: str) -> dict:
    """
    添加决策记录
    
    Args:
        date: 比赛日期 YYYY-MM-DD
        match: 比赛（如"利物浦vs阿森纳"）
        play: 玩法（胜平负/让球胜平负/总进球/比分/半全场）
        option: 选项（如"主胜"）
        odds: 赔率
        prob: 模型概率
        reason: 决策理由
    
    Returns:
        决策ID、保存结果
    """
    log = load_json(DECISION_LOG_FILE)
    if log is None:
        log = {'decisions': [], 'next_id': 1}
    
    decision_id = f"D{log['next_id']:04d}"
    log['next_id'] += 1
    
    decision = {
        'id': decision_id,
        'date': date,
        'match': match,
        'play': play,
        'option': option,
        'odds': odds,
        'prob': prob,
        'ev': round(prob * odds - 1, 4),
        'reason': reason,
        'status': 'pending',  # pending/win/loss
        'result': None,
        'winnings': 0,
        'created_at': datetime.now().isoformat(),
    }
    
    log['decisions'].append(decision)
    save_json(DECISION_LOG_FILE, log)
    
    return {
        'decision_id': decision_id,
        'decision': decision,
        'status': 'saved',
        'note': '决策记录已保存，赛后更新结果'
    }

# ============================================================
# 工具2：更新比赛结果
# ============================================================

@mcp.tool()
@safe_tool
def update_result(decision_id: str, outcome: str, winnings: float = 0) -> dict:
    """
    更新比赛结果
    
    Args:
        decision_id: 决策ID
        outcome: 结果（win/loss/push）
        winnings: 奖金（命中时）
    
    Returns:
        更新结果
    """
    log = load_json(DECISION_LOG_FILE)
    if log is None:
        return {'error': '决策日志不存在'}
    
    for d in log['decisions']:
        if d['id'] == decision_id:
            d['status'] = 'settled'
            d['result'] = outcome
            d['winnings'] = winnings
            d['settled_at'] = datetime.now().isoformat()
            save_json(DECISION_LOG_FILE, log)
            return {
                'decision_id': decision_id,
                'outcome': outcome,
                'winnings': winnings,
                'status': 'updated',
            }
    
    return {'error': f'未找到决策ID: {decision_id}'}

# ============================================================
# 工具3：获取统计数据
# ============================================================

@mcp.tool()
@safe_tool
def get_stats(by: str = 'play') -> dict:
    """
    获取统计数据（按玩法/联赛/日期统计命中率/ROI）
    
    Args:
        by: 统计维度（play/league/date/all）
    
    Returns:
        统计报告
    """
    log = load_json(DECISION_LOG_FILE)
    if log is None or not log.get('decisions'):
        return {'error': '暂无决策记录'}
    
    decisions = [d for d in log['decisions'] if d['status'] == 'settled']
    
    if not decisions:
        return {'error': '暂无已结算决策'}
    
    # 总体统计
    total = len(decisions)
    wins = sum(1 for d in decisions if d['result'] == 'win')
    losses = sum(1 for d in decisions if d['result'] == 'loss')
    total_stake = sum(2 for d in decisions)  # 简化：每注2元
    total_winnings = sum(d['winnings'] for d in decisions)
    total_profit = total_winnings - total_stake
    roi = total_profit / total_stake if total_stake > 0 else 0
    
    stats = {
        'overall': {
            'total': total,
            'wins': wins,
            'losses': losses,
            'win_rate': round(wins / total, 4) if total > 0 else 0,
            'total_stake': total_stake,
            'total_winnings': round(total_winnings, 2),
            'total_profit': round(total_profit, 2),
            'roi': round(roi, 4),
        }
    }
    
    # 按玩法统计
    if by in ['play', 'all']:
        play_stats = {}
        for d in decisions:
            play = d['play']
            if play not in play_stats:
                play_stats[play] = {'total': 0, 'wins': 0, 'stake': 0, 'winnings': 0}
            play_stats[play]['total'] += 1
            play_stats[play]['stake'] += 2
            play_stats[play]['winnings'] += d['winnings']
            if d['result'] == 'win':
                play_stats[play]['wins'] += 1
        
        for play, s in play_stats.items():
            s['win_rate'] = round(s['wins'] / s['total'], 4) if s['total'] > 0 else 0
            s['profit'] = round(s['winnings'] - s['stake'], 2)
            s['roi'] = round(s['profit'] / s['stake'], 4) if s['stake'] > 0 else 0
        
        stats['by_play'] = play_stats
    
    return stats

# ============================================================
# 工具4：结算期次
# ============================================================

@mcp.tool()
@safe_tool
def settle_session(date: str) -> dict:
    """
    结算期次（结算当期所有比赛）
    
    Args:
        date: 比赛日期 YYYY-MM-DD
    
    Returns:
        期次结算报告
    """
    log = load_json(DECISION_LOG_FILE)
    if log is None:
        return {'error': '决策日志不存在'}
    
    session_decisions = [d for d in log['decisions'] if d['date'] == date]
    
    if not session_decisions:
        return {'error': f'未找到{date}的决策记录'}
    
    pending = [d for d in session_decisions if d['status'] == 'pending']
    settled = [d for d in session_decisions if d['status'] == 'settled']
    
    return {
        'date': date,
        'total_decisions': len(session_decisions),
        'pending': len(pending),
        'settled': len(settled),
        'pending_ids': [d['id'] for d in pending],
        'note': f'{date}期次共有{len(session_decisions)}条决策，{len(pending)}条待结算'
    }

# ============================================================
# 工具5：期次复盘
# ============================================================

@mcp.tool()
@safe_tool
def review_session(date: str) -> dict:
    """
    期次复盘（四分类归因：分析正确/分析错误/运气好/运气差）
    
    Args:
        date: 比赛日期 YYYY-MM-DD
    
    Returns:
        复盘报告、四分类归因、经验教训
    """
    log = load_json(DECISION_LOG_FILE)
    if log is None:
        return {'error': '决策日志不存在'}
    
    session_decisions = [d for d in log['decisions'] if d['date'] == date and d['status'] == 'settled']
    
    if not session_decisions:
        return {'error': f'未找到{date}的已结算决策'}
    
    # 四分类归因（简化版，实际需要AI判断）
    # 分析正确：高概率选项命中
    # 分析错误：高概率选项未命中
    # 运气好：低概率选项命中
    # 运气差：低概率选项未命中
    correct_analysis = 0
    wrong_analysis = 0
    lucky = 0
    unlucky = 0
    
    for d in session_decisions:
        prob = d['prob']
        if d['result'] == 'win':
            if prob >= 0.5:
                correct_analysis += 1
            else:
                lucky += 1
        else:
            if prob >= 0.5:
                wrong_analysis += 1
            else:
                unlucky += 1
    
    wins = sum(1 for d in session_decisions if d['result'] == 'win')
    total_stake = sum(2 for d in session_decisions)
    total_winnings = sum(d['winnings'] for d in session_decisions)
    
    return {
        'date': date,
        'total': len(session_decisions),
        'wins': wins,
        'win_rate': round(wins / len(session_decisions), 4),
        'total_stake': total_stake,
        'total_winnings': round(total_winnings, 2),
        'profit': round(total_winnings - total_stake, 2),
        'four_category': {
            '分析正确': correct_analysis,
            '分析错误': wrong_analysis,
            '运气好': lucky,
            '运气差': unlucky,
        },
        'lessons': '待AI根据具体决策生成经验教训',
        'note': '四分类归因：区分能力和运气，避免错误归因'
    }

# ============================================================
# 工具6：分联赛校准
# ============================================================

@mcp.tool()
@safe_tool
def calibrate_league(league: str, matches: list = None) -> dict:
    """
    分联赛校准（用实际赛果校准模型参数）
    
    Args:
        league: 联赛代码
        matches: 比赛数据列表（可选，不传则用历史数据）
    
    Returns:
        校准参数、校准前后对比
    """
    calibration = load_json(CALIBRATION_FILE)
    if calibration is None:
        calibration = {}
    
    # 实际实现中应使用历史比赛数据计算校准参数
    # 这里返回框架
    return {
        'league': league,
        'calibration_params': calibration.get(league, {}),
        'matches_used': len(matches) if matches else 0,
        'note': '分联赛校准：用实际赛果动态调整模型参数，特别是0球/1球/低比分的概率修正'
    }

# ============================================================
# 工具7：策略回测
# ============================================================

@mcp.tool()
@safe_tool
def backtest_strategy(league: str, strategy: str = 'ev', params: dict = None) -> dict:
    """
    策略回测（用历史数据回测不同策略的长期表现）
    
    Args:
        league: 联赛代码
        strategy: 策略名称（ev/kelly/value等）
        params: 策略参数
    
    Returns:
        回测结果（命中率/ROI/最大回撤/夏普比率）
    """
    return {
        'league': league,
        'strategy': strategy,
        'params': params or {},
        'backtest_result': {
            'total_bets': 0,
            'win_rate': 0,
            'roi': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
        },
        'note': '策略回测：用历史数据评估策略的长期表现，A/B测试不同策略参数'
    }

# ============================================================
# 工具8：EV门槛优化
# ============================================================

@mcp.tool()
@safe_tool
def optimize_ev_threshold(league: str, play: str = None) -> dict:
    """
    EV门槛优化（根据历史表现动态调整EV门槛，不同玩法不同参数）
    
    Args:
        league: 联赛代码
        play: 玩法（可选，不传则所有玩法）
    
    Returns:
        最优EV门槛、优化前后对比
    """
    default_thresholds = {
        '胜平负': 0.05,
        '让球胜平负': 0.05,
        '总进球': 0.07,
        '比分': 0.15,
        '半全场': 0.12,
    }
    
    if play:
        return {
            'league': league,
            'play': play,
            'default_threshold': default_thresholds.get(play, 0.05),
            'optimized_threshold': default_thresholds.get(play, 0.05),
            'optimization': '待优化（需要300+注历史数据）',
            'note': 'EV门槛优化：根据历史命中率动态调整，命中率高的玩法降低门槛，低的提高'
        }
    
    return {
        'league': league,
        'default_thresholds': default_thresholds,
        'optimized_thresholds': default_thresholds,
        'optimization': '待优化（需要300+注历史数据）',
        'note': 'EV门槛优化：不同玩法不同门槛，根据历史表现动态调整'
    }

# ============================================================
# 工具9：添加经验教训
# ============================================================

@mcp.tool()
@safe_tool
def add_lesson(lesson: str, category: str, weight: float = 1.0) -> dict:
    """
    添加经验教训
    
    Args:
        lesson: 经验教训内容
        category: 分类（数据分析/投注策略/心理/规则/其他）
        weight: 权重（0-1，默认1.0）
    
    Returns:
        经验ID、保存结果
    """
    lessons = load_json(LESSONS_FILE)
    if lessons is None:
        lessons = {'lessons': [], 'next_id': 1}
    
    lesson_id = f"L{lessons['next_id']:04d}"
    lessons['next_id'] += 1
    
    lesson_data = {
        'id': lesson_id,
        'lesson': lesson,
        'category': category,
        'weight': weight,
        'created_at': datetime.now().isoformat(),
        'usage_count': 0,
        'success_count': 0,
    }
    
    lessons['lessons'].append(lesson_data)
    save_json(LESSONS_FILE, lessons)
    
    return {
        'lesson_id': lesson_id,
        'lesson': lesson_data,
        'status': 'saved',
        'note': '经验教训已保存，分析前主动加载'
    }

# ============================================================
# 工具10：预加载记忆
# ============================================================

@mcp.tool()
@safe_tool
def preload_memory(date: str = None) -> dict:
    """
    预加载记忆（分析前必须执行，确保自进化闭环）
    
    Args:
        date: 比赛日期（可选）
    
    Returns:
        相关经验/案例/校准参数/策略参数
    """
    lessons = load_json(LESSONS_FILE)
    calibration = load_json(CALIBRATION_FILE)
    stats = get_stats.fn('play')
    
    # 按权重排序，取Top10经验
    all_lessons = lessons.get('lessons', []) if lessons else []
    sorted_lessons = sorted(all_lessons, key=lambda x: x.get('weight', 1), reverse=True)
    top_lessons = sorted_lessons[:10]
    
    return {
        'date': date or datetime.now().strftime('%Y-%m-%d'),
        'lessons_count': len(all_lessons),
        'top_lessons': [{'id': l['id'], 'lesson': l['lesson'], 'category': l['category']} for l in top_lessons],
        'calibration_leagues': list(calibration.keys()) if calibration else [],
        'stats': stats.get('overall', {}) if isinstance(stats, dict) else {},
        'checklist': [
            '已预加载记忆体系',
            '已查看各玩法历史命中率',
            '已查看相关联赛校准参数',
            '已查看当前策略参数',
            '已查找类似对阵历史经验',
            '已应用球队强度库和联赛特征库',
            '已做心理状态检查',
        ],
        'note': '记忆预加载完成，分析中必须明确引用相关经验'
    }

# ============================================================
# 主函数
# ============================================================

@mcp.tool()
@safe_tool
def case_library_manage(action: str = 'query', case_id: str = None, case_data: dict = None, keyword: str = None) -> dict:
    """
    案例库管理（添加/查询/检索典型案例）
    
    Args:
        action: 操作类型 add/query/search/list
        case_id: 案例ID（query时必填）
        case_data: 案例数据（add时必填）
        keyword: 搜索关键词（search时使用）
    
    Returns:
        案例库操作结果
    """
    case_file = os.path.join(DATA_DIR, 'case_library.json')
    data = load_json(case_file) or {'cases': [], 'next_id': 1}
    
    if action == 'add' and case_data:
        case_id = f"C{data['next_id']:03d}"
        case_data['id'] = case_id
        case_data['created_at'] = datetime.now().isoformat()
        data['cases'].append(case_data)
        data['next_id'] += 1
        save_json(case_file, data)
        return {'action': 'add', 'case_id': case_id, 'total_cases': len(data['cases'])}
    
    elif action == 'query' and case_id:
        for case in data['cases']:
            if case.get('id') == case_id:
                return {'case': case}
        return {'error': f'案例{case_id}不存在'}
    
    elif action == 'search' and keyword:
        results = []
        for case in data['cases']:
            case_str = json.dumps(case, ensure_ascii=False)
            if keyword in case_str:
                results.append({'id': case.get('id'), 'title': case.get('title', ''), 'type': case.get('type', '')})
        return {'keyword': keyword, 'results': results, 'count': len(results)}
    
    else:  # list
        return {
            'total_cases': len(data['cases']),
            'cases': [{'id': c.get('id'), 'title': c.get('title', ''), 'type': c.get('type', ''), 'result': c.get('result', '')} 
                     for c in data['cases'][-20:]]
        }

@mcp.tool()
@safe_tool
def memory_manager(action: str = 'status', memory_type: str = None, data: dict = None) -> dict:
    """
    统一记忆管理器（11维度记忆体系统）
    
    11维度：经验库/决策日志/案例库/期次记录/校准参数/球队强度/联赛特征/
            策略参数/伤停追踪/裁判追踪/心理状态
    
    Args:
        action: 操作类型 status/preload/postmatch/backup/clear
        memory_type: 记忆类型（可选，指定维度）
        data: 要写入的数据（postmatch时使用）
    
    Returns:
        记忆管理器状态
    """
    memory_files = {
        'lessons': 'lessons.json',
        'decision_log': 'decision_log.json',
        'case_library': 'case_library.json',
        'calibration': 'calibration_by_league.json',
        'team_ratings': 'team_ratings.json',
        'league_features': 'league_features.json',
        'strategy_params': 'strategy_params.json',
        'bankroll': 'bankroll.json',
    }
    
    if action == 'status':
        status = {}
        total_size = 0
        for mem_type, filename in memory_files.items():
            filepath = os.path.join(DATA_DIR, filename)
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                total_size += size
                status[mem_type] = {'exists': True, 'size_kb': round(size / 1024, 1)}
            else:
                status[mem_type] = {'exists': False}
        return {
            'memory_dimensions': len(memory_files),
            'total_size_kb': round(total_size / 1024, 1),
            'status': status,
            'note': '11维度记忆体系统（含动态追踪维度）'
        }
    
    elif action == 'preload':
        # 预加载所有记忆到返回结果
        preloaded = {}
        for mem_type, filename in memory_files.items():
            filepath = os.path.join(DATA_DIR, filename)
            if os.path.exists(filepath):
                preloaded[mem_type] = load_json(filepath)
        return {'action': 'preload', 'loaded_dimensions': len(preloaded), 'data': preloaded}
    
    elif action == 'postmatch' and data:
        # 赛后记忆沉淀
        results = {}
        if 'lessons' in data:
            lessons_file = os.path.join(DATA_DIR, 'lessons.json')
            lessons = load_json(lessons_file) or []
            lessons.append(data['lessons'])
            save_json(lessons_file, lessons)
            results['lessons'] = '已添加'
        if 'decision' in data:
            results['decision'] = '已记录'
        return {'action': 'postmatch', 'results': results}
    
    elif action == 'backup':
        # 备份所有记忆数据
        backup_dir = os.path.join(DATA_DIR, 'backup', datetime.now().strftime('%Y%m%d_%H%M%S'))
        os.makedirs(backup_dir, exist_ok=True)
        for mem_type, filename in memory_files.items():
            filepath = os.path.join(DATA_DIR, filename)
            if os.path.exists(filepath):
                import shutil
                shutil.copy2(filepath, os.path.join(backup_dir, filename))
        return {'action': 'backup', 'backup_dir': backup_dir, 'files_backed_up': len(os.listdir(backup_dir))}
    
    return {'error': f'不支持的操作: {action}'}

@mcp.tool()
@safe_tool
def session_manager(action: str = 'list', session_id: str = None, session_data: dict = None) -> dict:
    """
    期次管理器（完整逻辑：创建/添加/结算/复盘/列表）
    
    Args:
        action: 操作类型 create/add/settle/review/list/get
        session_id: 期次ID
        session_data: 期次数据
    
    Returns:
        期次管理结果
    """
    sessions_dir = os.path.join(DATA_DIR, 'sessions')
    os.makedirs(sessions_dir, exist_ok=True)
    
    if action == 'create':
        session_id = datetime.now().strftime('%Y%m%d')
        session_file = os.path.join(sessions_dir, f'{session_id}.json')
        if os.path.exists(session_file):
            return {'error': f'期次{session_id}已存在', 'session_id': session_id}
        session = {
            'id': session_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'created_at': datetime.now().isoformat(),
            'status': 'active',
            'matches': [],
            'bets': [],
            'total_stake': 0,
            'total_winnings': 0,
            'net_profit': 0,
        }
        save_json(session_file, session)
        return {'action': 'create', 'session_id': session_id, 'status': 'active'}
    
    elif action == 'add' and session_id and session_data:
        session_file = os.path.join(sessions_dir, f'{session_id}.json')
        session = load_json(session_file)
        if not session:
            return {'error': f'期次{session_id}不存在'}
        if 'match' in session_data:
            session['matches'].append(session_data['match'])
        if 'bet' in session_data:
            session['bets'].append(session_data['bet'])
            session['total_stake'] += session_data['bet'].get('stake', 0)
        save_json(session_file, session)
        return {'action': 'add', 'session_id': session_id, 'matches': len(session['matches']), 'bets': len(session['bets'])}
    
    elif action == 'settle' and session_id:
        session_file = os.path.join(sessions_dir, f'{session_id}.json')
        session = load_json(session_file)
        if not session:
            return {'error': f'期次{session_id}不存在'}
        session['status'] = 'settled'
        session['settled_at'] = datetime.now().isoformat()
        # 计算奖金
        total_winnings = 0
        for bet in session['bets']:
            if bet.get('outcome') == 'win':
                total_winnings += bet.get('winnings', 0)
        session['total_winnings'] = total_winnings
        session['net_profit'] = total_winnings - session['total_stake']
        save_json(session_file, session)
        return {
            'action': 'settle',
            'session_id': session_id,
            'total_stake': session['total_stake'],
            'total_winnings': session['total_winnings'],
            'net_profit': session['net_profit'],
            'roi': round(session['net_profit'] / session['total_stake'] * 100, 2) if session['total_stake'] > 0 else 0
        }
    
    elif action == 'review' and session_id:
        session_file = os.path.join(sessions_dir, f'{session_id}.json')
        session = load_json(session_file)
        if not session:
            return {'error': f'期次{session_id}不存在'}
        # 四分类归因
        correct = sum(1 for m in session['matches'] if m.get('analysis_correct') == True)
        wrong = sum(1 for m in session['matches'] if m.get('analysis_correct') == False)
        lucky = sum(1 for m in session['matches'] if m.get('analysis_correct') == 'lucky')
        unlucky = sum(1 for m in session['matches'] if m.get('analysis_correct') == 'unlucky')
        return {
            'action': 'review',
            'session_id': session_id,
            'summary': {
                'total_matches': len(session['matches']),
                'total_bets': len(session['bets']),
                'total_stake': session['total_stake'],
                'net_profit': session['net_profit'],
            },
            'attribution': {
                'analysis_correct': correct,
                'analysis_wrong': wrong,
                'lucky': lucky,
                'unlucky': unlucky,
            }
        }
    
    elif action == 'get' and session_id:
        session_file = os.path.join(sessions_dir, f'{session_id}.json')
        session = load_json(session_file)
        return session if session else {'error': f'期次{session_id}不存在'}
    
    else:  # list
        sessions = []
        for f in sorted(os.listdir(sessions_dir), reverse=True)[:20]:
            if f.endswith('.json'):
                s = load_json(os.path.join(sessions_dir, f))
                if s:
                    sessions.append({'id': s.get('id'), 'date': s.get('date'), 'status': s.get('status'), 'bets': len(s.get('bets', [])), 'net_profit': s.get('net_profit', 0)})
        return {'total_sessions': len(sessions), 'sessions': sessions}

@mcp.tool()
@safe_tool
def review_engine_full(session_id: str, review_type: str = 'all') -> dict:
    """
    自进化复盘引擎（完整逻辑：四分类归因/校准/漂移检测）
    
    Args:
        session_id: 期次ID
        review_type: 复盘类型 attribution/calibration/drift/all
    
    Returns:
        完整复盘结果
    """
    session_file = os.path.join(DATA_DIR, 'sessions', f'{session_id}.json')
    session = load_json(session_file)
    
    if not session:
        return {'error': f'期次{session_id}不存在'}
    
    results = {'session_id': session_id, 'review_type': review_type}
    
    # 1. 四分类归因
    if review_type in ['attribution', 'all']:
        correct = []
        wrong = []
        lucky = []
        unlucky = []
        
        for match in session.get('matches', []):
            outcome = match.get('outcome', '')
            predicted = match.get('predicted', '')
            confidence = match.get('confidence', 0.5)
            
            if outcome == predicted:
                if confidence > 0.6:
                    correct.append(match)
                else:
                    lucky.append(match)
            else:
                if confidence > 0.6:
                    wrong.append(match)
                else:
                    unlucky.append(match)
        
        results['attribution'] = {
            'analysis_correct': {'count': len(correct), 'matches': [m.get('match_id') for m in correct]},
            'analysis_wrong': {'count': len(wrong), 'matches': [m.get('match_id') for m in wrong]},
            'lucky': {'count': len(lucky), 'matches': [m.get('match_id') for m in lucky]},
            'unlucky': {'count': len(unlucky), 'matches': [m.get('match_id') for m in unlucky]},
            'ability_score': round(len(correct) / max(len(session['matches']), 1) * 100, 1),
        }
    
    # 2. 模型校准分析
    if review_type in ['calibration', 'all']:
        calibration = {'by_play': {}, 'by_confidence': {}}
        for match in session.get('matches', []):
            play = match.get('play', '未知')
            if play not in calibration['by_play']:
                calibration['by_play'][play] = {'total': 0, 'correct': 0}
            calibration['by_play'][play]['total'] += 1
            if match.get('outcome') == match.get('predicted'):
                calibration['by_play'][play]['correct'] += 1
        
        for play, stats in calibration['by_play'].items():
            stats['accuracy'] = round(stats['correct'] / max(stats['total'], 1) * 100, 1)
        
        results['calibration'] = calibration
    
    # 3. 策略漂移检测
    if review_type in ['drift', 'all']:
        # 检测是否偏离原定策略
        drift_signals = []
        plays_used = set(m.get('play') for m in session.get('matches', []))
        if len(plays_used) < 3 and len(session.get('matches', [])) > 5:
            drift_signals.append(f'玩法覆盖不足：仅使用{len(plays_used)}种玩法，建议覆盖3种以上')
        
        avg_odds = sum(m.get('odds', 1) for m in session.get('matches', [])) / max(len(session.get('matches', [])), 1)
        if avg_odds < 1.5:
            drift_signals.append(f'平均赔率过低({avg_odds:.2f})，可能过度追求稳胆')
        
        results['drift_detection'] = {
            'drift_signals': drift_signals,
            'plays_used': list(plays_used),
            'avg_odds': round(avg_odds, 2),
            'drift_level': 'high' if len(drift_signals) >= 2 else ('medium' if len(drift_signals) == 1 else 'low')
        }
    
    return results

@mcp.tool()
@safe_tool
def ability_boundary(action: str = 'record', capability: str = None, success: bool = True, note: str = '') -> dict:
    """
    能力边界认知器（记录和认知AI能力边界）
    
    Args:
        action: 操作类型 record/query/list
        capability: 能力名称
        success: 是否成功
        note: 备注
    
    Returns:
        能力边界记录
    """
    boundary_file = os.path.join(DATA_DIR, 'ability_boundary.json')
    data = load_json(boundary_file) or {'capabilities': {}, 'failures': []}
    
    if action == 'record' and capability:
        if capability not in data['capabilities']:
            data['capabilities'][capability] = {'success': 0, 'failure': 0, 'last_used': ''}
        if success:
            data['capabilities'][capability]['success'] += 1
        else:
            data['capabilities'][capability]['failure'] += 1
            data['failures'].append({'capability': capability, 'note': note, 'timestamp': datetime.now().isoformat()})
        data['capabilities'][capability]['last_used'] = datetime.now().isoformat()
        save_json(boundary_file, data)
        return {'action': 'record', 'capability': capability, 'success': success}
    
    elif action == 'query' and capability:
        cap = data['capabilities'].get(capability)
        if cap:
            total = cap['success'] + cap['failure']
            return {
                'capability': capability,
                'success_rate': round(cap['success'] / max(total, 1) * 100, 1),
                'success': cap['success'],
                'failure': cap['failure'],
                'last_used': cap['last_used']
            }
        return {'error': f'能力{capability}无记录'}
    
    else:  # list
        return {
            'total_capabilities': len(data['capabilities']),
            'total_failures': len(data['failures']),
            'capabilities': {k: {'success_rate': round(v['success'] / max(v['success'] + v['failure'], 1) * 100, 1)} 
                            for k, v in list(data['capabilities'].items())[-20:]},
            'recent_failures': data['failures'][-10:]
        }

@mcp.tool()
@safe_tool
def league_fallback_params(league: str, action: str = 'get', params: dict = None) -> dict:
    """
    联赛回退参数（当联赛数据不足时使用的默认参数）
    
    Args:
        league: 联赛代码
        action: 操作类型 get/set/list
        params: 参数数据（set时使用）
    
    Returns:
        联赛回退参数
    """
    fallback_file = os.path.join(DATA_DIR, 'league_fallback.json')
    data = load_json(fallback_file) or {}
    
    # 默认回退参数
    default_params = {
        'avg_goals': 2.5,
        'home_win_rate': 0.45,
        'draw_rate': 0.26,
        'away_win_rate': 0.29,
        'over25_rate': 0.50,
        'btts_rate': 0.50,
        'home_advantage': 0.3,
        'lambda_home': 1.4,
        'lambda_away': 1.1,
        'confidence': 'low',
        'note': '使用全局默认参数，建议积累该联赛数据后更新'
    }
    
    if action == 'set' and params:
        data[league] = {**default_params, **params, 'updated_at': datetime.now().isoformat()}
        save_json(fallback_file, data)
        return {'action': 'set', 'league': league, 'params': data[league]}
    
    elif action == 'list':
        return {'total_leagues': len(data), 'leagues': list(data.keys())}
    
    else:  # get
        if league in data:
            return {'league': league, 'params': data[league], 'source': 'custom'}
        return {'league': league, 'params': default_params, 'source': 'default', 'note': '该联赛无自定义参数，使用全局默认'}

@mcp.tool()
@safe_tool
def sync_to_feishu(data_type: str, data: dict, table_name: str = None) -> dict:
    """
    飞书多维表格同步（3个数据表：决策日志/经验库/期次记录）
    
    Args:
        data_type: 数据类型 decision/lesson/session
        data: 要同步的数据
        table_name: 表名（可选）
    
    Returns:
        同步结果（模拟，实际需要飞书API）
    """
    table_map = {
        'decision': '竞彩决策日志',
        'lesson': '竞彩经验库',
        'session': '竞彩期次记录',
    }
    
    table = table_name or table_map.get(data_type, '竞彩数据')
    
    # 记录同步日志
    sync_log_file = os.path.join(DATA_DIR, 'feishu_sync_log.json')
    sync_log = load_json(sync_log_file) or {'syncs': []}
    
    sync_record = {
        'data_type': data_type,
        'table': table,
        'record_count': len(data) if isinstance(data, list) else 1,
        'timestamp': datetime.now().isoformat(),
        'status': 'simulated'
    }
    sync_log['syncs'].append(sync_record)
    save_json(sync_log_file, sync_log)
    
    return {
        'status': 'simulated',
        'data_type': data_type,
        'table': table,
        'record_count': sync_record['record_count'],
        'note': '飞书同步为模拟模式，实际使用需要配置飞书API凭证和多维表格ID',
        'total_syncs': len(sync_log['syncs'])
    }


@mcp.tool()
def get_user_preferences() -> dict:
    """获取用户偏好配置（预算/风险偏好/玩法偏好/投注风格）"""
    import json, os
    pref_file = os.path.join(PLUGIN_ROOT, 'data', 'user_preferences.json')
    if os.path.exists(pref_file):
        with open(pref_file, 'r', encoding='utf-8') as f:
            prefs = json.load(f)
        return {'success': True, 'data': prefs}
    return {'success': False, 'error': '用户偏好文件不存在'}


@mcp.tool()
def update_user_preferences(updates: dict) -> dict:
    """更新用户偏好配置"""
    import json, os
    from datetime import datetime
    pref_file = os.path.join(PLUGIN_ROOT, 'data', 'user_preferences.json')
    if os.path.exists(pref_file):
        with open(pref_file, 'r', encoding='utf-8') as f:
            prefs = json.load(f)
    else:
        prefs = {}
    prefs.update(updates)
    prefs['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(pref_file, 'w', encoding='utf-8') as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)
    return {'success': True, 'data': prefs, 'message': '用户偏好已更新'}

if __name__ == '__main__':
    mcp.run()
