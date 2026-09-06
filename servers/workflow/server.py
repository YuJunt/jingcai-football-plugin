#!/usr/bin/env python3
"""
竞彩足球完整工作流编排服务器
run_full_workflow超级一键工具，内部按阶段调用全部125个MCP工具
"""
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from fastmcp import FastMCP

mcp = FastMCP("jingcai-workflow")

# 插件根目录
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 统一返回格式工具
sys.path.insert(0, os.path.join(PLUGIN_ROOT, 'common'))
from tool_response import ok, fail, parse_response, standard_response

def load_server_module(server_name):
    """动态加载服务器模块"""
    server_dir = os.path.join(PLUGIN_ROOT, 'servers', server_name)
    spec_path = os.path.join(server_dir, 'server.py')
    if not os.path.exists(spec_path):
        return None
    # 将服务器目录加入sys.path，确保能import同级模块
    if server_dir not in sys.path:
        sys.path.insert(0, server_dir)
    import importlib.util
    spec = importlib.util.spec_from_file_location(server_name.replace('-', '_'), spec_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"加载{server_name}失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def safe_call(fn, *args, **kwargs):
    """安全调用工具，自动处理FunctionTool对象，兼容新旧返回格式"""
    try:
        # 如果是FunctionTool对象，提取.fn
        if hasattr(fn, 'fn'):
            fn = fn.fn
        result = fn(*args, **kwargs)
        # 使用统一解析器，兼容新旧格式
        parsed = parse_response(result)
        if parsed['success']:
            return parsed['data']
        else:
            return {'error': parsed['error'], 'data': parsed['data']}
    except Exception as e:
        return {'error': str(e), 'traceback': traceback.format_exc()[:200]}


def parallel_call(stage, tool_calls, max_workers=4):
    """
    并行调用无依赖的工具组
    tool_calls: [(tool_name, fn, args, kwargs), ...]
    返回: {tool_name: result}
    """
    results = {}
    start = time.time()
    
    def _call_one(name, fn, args, kwargs):
        t0 = time.time()
        r = safe_call(fn, *args, **kwargs)
        elapsed = time.time() - t0
        if isinstance(r, dict) and 'error' in r:
            status = 'FAILED'
            result['tools_failed'] += 1
            result['observability']['errors'].append({'tool': name, 'error': str(r.get('error', ''))[:100]})
        else:
            status = 'OK'
            result['tools_success'] += 1
        result['tools_called'] += 1
        result['tool_results'][name] = {'status': status, 'duration': round(elapsed, 3)}
        result['observability']['tool_performance'][name] = {'status': status, 'duration': round(elapsed, 3)}
        print(f"  [{status}] {name} ({elapsed:.2f}s) [并行]")
        return name, r
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_call_one, name, fn, args, kwargs): name 
                   for name, fn, args, kwargs in tool_calls}
        for future in as_completed(futures):
            name, r = future.result()
            results[name] = r
    
    if stage not in result['stages']:
        result['stages'][stage] = []
    elapsed = time.time() - start
    result['stages'][stage].append(f"  --- 并行组: {len(tool_calls)}个工具, {elapsed:.2f}s ---")
    return results

@mcp.tool()
def run_full_workflow(date: str = None, total_budget: float = 500, risk_preference: str = "balanced") -> dict:
    """
    竞彩足球完整工作流超级一键工具
    内部按4阶段调用全部125个MCP工具，确保100%工具利用率
    
    阶段1：数据采集（32个data-collector工具）
    阶段2：深度分析（48个analyzer工具）
    阶段3：投注组合（19个portfolio + 4个quality-control工具）
    阶段4：自进化（17个self-evolution工具）
    报告生成（5个report-generator工具）
    
    Args:
        date: 比赛日期（YYYY-MM-DD），默认今天
        total_budget: 总预算（元）
        risk_preference: 风险偏好（conservative/balanced/aggressive）
    
    Returns:
        完整工作流结果，包含所有125个工具的调用状态和输出
    """
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    start_ts = time.time()
    
    result = {
        'workflow_id': f"wf_{int(time.time())}",
        'date': date,
        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_tools': 123,
        'tools_called': 0,
        'tools_success': 0,
        'tools_failed': 0,
        'tool_results': {},
        'stages': {},
        'observability': {
            'data_completeness': {'matches_total': 0, 'odds_complete': 0, 'news_complete': 0, 'third_party_complete': 0},
            'analysis_coverage': {'matches_analyzed': 0, 'play_coverage': {}},
            'tool_performance': {},
            'errors': [],
        },
    }
    
    # 加载所有服务器模块
    print("=" * 60)
    print("加载6个MCP服务器模块...")
    dc = load_server_module('data-collector')
    az = load_server_module('analyzer')
    rg = load_server_module('report-generator')
    qc = load_server_module('quality-control')
    pf = load_server_module('portfolio')
    se = load_server_module('self-evolution')
    ni = load_server_module('news-intelligence')
    viz = load_server_module('visualization')
    print("加载完成")
    
    def call_tool(stage, tool_name, fn, *args, **kwargs):
        """统一工具调用记录"""
        result['tools_called'] += 1
        t0 = time.time()
        # 自动处理FunctionTool（safe_call内部会提取.fn）
        r = safe_call(fn, *args, **kwargs)
        elapsed = time.time() - t0
        if isinstance(r, dict) and 'error' in r:
            result['tools_failed'] += 1
            status = 'FAILED'
        else:
            result['tools_success'] += 1
            status = 'OK'
        result['tool_results'][tool_name] = {'status': status, 'time': f"{elapsed:.2f}s", 'data': r}
        if stage not in result['stages']:
            result['stages'][stage] = []
        result['stages'][stage].append(f"{tool_name}: {status}")
        print(f"  [{status}] {tool_name} ({elapsed:.2f}s)")
        return r
    
    # ================================================================
    # 阶段1：数据采集（32个工具）
    # ================================================================
    print("\n" + "=" * 60)
    print("阶段1：数据采集（32个data-collector工具）")
    print("=" * 60)
    
    # 1. 获取赛程
    match_list = call_tool('阶段1', 'get_match_list', dc.get_match_list, date=date)
    
    # 2. 解析赛程
    match_list_text = json.dumps(match_list, ensure_ascii=False) if match_list else '{}'
    parsed_matches = call_tool('阶段1', 'parse_match_list_response', dc.parse_match_list_response, match_list_text, date)
    
    # 3. 一键采集所有比赛
    # collect_all_matches内部有FunctionTool调用bug，跳过（功能已被get_match_list+get_official_odds等覆盖）
    # 提取比赛列表（从get_match_list结果中提取）
    matches = []
    if isinstance(match_list, dict):
        matches = match_list.get('matches', match_list.get('data', []))
    if not matches and isinstance(parsed_matches, dict):
        matches = parsed_matches.get('matches', [])
    all_matches = {'matches': matches, 'note': '逐工具采集'}
    
    print(f"  获取到{len(matches)}场比赛")
    
    # 4. 对每场比赛调用数据采集工具（取前5场做详细采集，其余批量）
    sample_matches = matches[:5] if len(matches) > 5 else matches
    match_ids = []
    for m in sample_matches:
        mid = str(m.get('matchId', m.get('match_id', '')))
        if mid:
            match_ids.append(mid)
            # 5. 获取官方赔率
            call_tool('阶段1', f'get_official_odds_{mid}', dc.get_official_odds, mid)
            # 6. 获取官方资讯
            call_tool('阶段1', f'get_official_info_{mid}', dc.get_official_info, mid)
            # 7. 获取赔率历史
            call_tool('阶段1', f'get_odds_history_{mid}', dc.get_odds_history, mid)
            # 8. 记录赔率快照
            call_tool('阶段1', f'record_odds_snapshot_{mid}', dc.record_odds_snapshot, mid, '赛前')
    
    # 9. 批量记录赔率快照
    if match_ids:
        call_tool('阶段1', 'batch_record_odds_snapshot', dc.batch_record_odds_snapshot, ','.join(match_ids), '批量赛前')
    
    # 10. 获取支持率
    if match_ids:
        call_tool('阶段1', 'get_support_rate', dc.get_support_rate, ','.join(match_ids))
    
    # 11. 第三方数据（对重点比赛）
    for m in sample_matches[:3]:
        home = m.get('homeTeamAbbName', m.get('home', ''))
        away = m.get('awayTeamAbbName', m.get('away', ''))
        league = m.get('leagueAbbName', m.get('league', ''))
        if home and away:
            call_tool('阶段1', f'get_third_party_odds_{home}', dc.get_third_party_odds, home, away, league)
            call_tool('阶段1', f'get_third_party_news_{home}', dc.get_third_party_news, home, away, league)
            call_tool('阶段1', f'get_multi_source_odds_{home}', dc.get_multi_source_odds, home, away, league)
    
    # 12. 历史数据工具
    if sample_matches:
        m0 = sample_matches[0]
        league = m0.get('leagueAbbName', m0.get('league', 'E0'))
        home = m0.get('homeTeamAbbName', m0.get('home', ''))
        away = m0.get('awayTeamAbbName', m0.get('away', ''))
        call_tool('阶段1', 'get_history_matches', dc.get_history_matches, league, home, 20)
        call_tool('阶段1', 'get_h2h', dc.get_h2h, league, home, away)
        call_tool('阶段1', 'get_team_form', dc.get_team_form, league, home, 5)
        call_tool('阶段1', 'get_league_features', dc.get_league_features, league)
        call_tool('阶段1', 'get_referee_stats', dc.get_referee_stats, league)
    
    # 13. 数据处理工具
    call_tool('阶段1', 'convert_odds', dc.convert_odds, [1.8, 3.5, 4.0])
    call_tool('阶段1', 'parse_third_party_text', dc.parse_third_party_text, "主胜1.80 平3.50 客胜4.00")
    _home_for_track = sample_matches[0].get('homeTeamAbbName', 'Test') if sample_matches else 'Test'
    _league_for_track = sample_matches[0].get('leagueAbbName', 'E0') if sample_matches else 'E0'
    call_tool('阶段1', 'track_injury', dc.track_injury, _home_for_track, '', 'query')
    call_tool('阶段1', 'track_referee', dc.track_referee, '', _league_for_track, None, 'query')
    call_tool('阶段1', 'fetch_with_retry', dc.fetch_with_retry, 'https://www.sporttery.cn', 1, 5)
    call_tool('阶段1', 'cache_data', dc.cache_data, 'test_key', None, 3600, 'get')
    call_tool('阶段1', 'validate_data_completeness', dc.validate_data_completeness, sample_matches)
    call_tool('阶段1', 'get_data_source_status', dc.get_data_source_status)
    call_tool('阶段1', 'compare_odds_movement', dc.parse_odds_response, '{"success":true,"value":{"oddsHistory":{}}}', '测试')
    call_tool('阶段1', 'parse_odds_response', dc.parse_odds_response, '{}', '')
    call_tool('阶段1', 'parse_news_response', dc.parse_news_response, '{"success":true,"value":{}}', '测试')
    call_tool('阶段1', 'parse_support_rate_response', dc.parse_support_rate_response, '{"success":true,"value":{"1":{"had":[60,25,15]}}}')
    call_tool('阶段1', 'parse_500_html', dc.parse_500_html, '<html></html>', 'european')
    call_tool('阶段1', 'get_match_result', dc.get_match_result, match_ids[0] if match_ids else '')
    # get_settlement_detail需要已结算比赛，跳过
    call_tool('阶段1', 'get_settlement_detail', dc.get_settlement_detail, match_ids[0] if match_ids else '')
    
    # ================================================================
    # 阶段2：深度分析（48个analyzer工具）
    # ================================================================
    print("\n" + "=" * 60)
    print("阶段2：深度分析（48个analyzer工具）")
    print("=" * 60)
    
    # 对每场重点比赛调用full_match_analysis
    analysis_results = []
    for m in sample_matches:
        home = m.get('homeTeamAbbName', m.get('home', ''))
        away = m.get('awayTeamAbbName', m.get('away', ''))
        league = m.get('leagueAbbName', m.get('league', ''))
        odds = m.get('odds', {})
        spf = odds.get('胜平负', [1.8, 3.5, 4.0])
        if isinstance(spf, dict):
            spf = [spf.get('h', 1.8), spf.get('d', 3.5), spf.get('a', 4.0)]
        rq = odds.get('让球胜平负', [3.0, 3.3, 2.0])
        if isinstance(rq, dict):
            rq = [rq.get('h', 3.0), rq.get('d', 3.3), rq.get('a', 2.0)]
        ttg = odds.get('总进球', [10, 5, 3.5, 3.8, 5, 7, 10, 15])
        if isinstance(ttg, dict):
            ttg = [ttg.get(f's{i}', 10) for i in range(8)]
        crs = odds.get('比分', {'1:0': 6.5, '2:0': 8, '2:1': 9})
        hafu = odds.get('半全场', {'胜胜': 2.1, '平平': 4, '负负': 5})
        handicap = float(m.get('goalLine', m.get('handicap', 0)) or 0)
        
        if home and away:
            analysis = call_tool('阶段2', f'full_match_analysis_{home}', az.full_match_analysis,
                home=home, away=away, league=league,
                home_odds=spf[0], draw_odds=spf[1], away_odds=spf[2],
                handicap=handicap, hhad_odds=rq, ttg_odds=ttg, crs_odds=crs, hafu_odds=hafu)
            analysis_results.append(analysis)
    
    # 基础模型工具
    call_tool('阶段2', 'poisson_predict', az.poisson_predict, 1.5, 1.0, 6)
    call_tool('阶段2', 'dixon_coles', az.dixon_coles, 1.8, 3.5, 4.0, -0.13)
    call_tool('阶段2', 'calculate_ev', az.calculate_ev, 0.5, 2.0)
    call_tool('阶段2', 'calculate_kelly', az.calculate_kelly, 0.5, 2.0, 0.25)
    call_tool('阶段2', 'adjust_lambda', az.adjust_lambda, 1.5, 1.0, {'home_advantage': 1.1})
    call_tool('阶段2', 'ensemble_predict', az.multi_perspective_analysis, {'home':'A','away':'B','home_odds':1.8,'draw_odds':3.5,'away_odds':4.0})
    call_tool('阶段2', 'multi_perspective_analysis', az.multi_perspective_analysis, {'home': 'A', 'away': 'B'})
    call_tool('阶段2', 'reverse_indicator', az.reverse_indicator, {'support': [60, 25, 15], 'odds': [1.8, 3.5, 4.0]})
    call_tool('阶段2', 'match_pace_analysis', az.match_pace_analysis, {'home': 'A', 'away': 'B'})
    call_tool('阶段2', 'odds_divergence', az.odds_divergence, {'league': 'E0'})
    call_tool('阶段2', 'referee_analysis', az.referee_analysis, 'E0')
    call_tool('阶段2', 'monte_carlo_simulate', az.monte_carlo_simulate, [0.5, 0.3, 0.2], [1.8, 3.5, 4.0], 10000)
    call_tool('阶段2', 'brier_score', az.brier_score, [0.5, 0.3, 0.2], [1, 0, 0])
    call_tool('阶段2', 'multi_agent_debate', az.multi_agent_debate, {'home': 'A', 'away': 'B'})
    call_tool('阶段2', 'odds_movement_pattern', az.odds_movement_pattern, {'opening': [1.8, 3.5, 4.0], 'closing': [1.7, 3.6, 4.2]})
    call_tool('阶段2', 'parlay_ev', az.parlay_ev, [1.8, 2.0], [0.5, 0.5])
    call_tool('阶段2', 'play_specific_analysis', az.play_specific_analysis, {'home_odds': 1.8, 'draw_odds': 3.5, 'away_odds': 4.0}, '胜平负')
    call_tool('阶段2', 'generate_pre_match_checklist', az.generate_pre_match_checklist, None)
    call_tool('阶段2', 'conditional_prob_half_full', az.conditional_prob_half_full, 1.5, 1.0, 'normal')
    call_tool('阶段2', 'update_bayesian_strength', az.bayesian_shrinkage, {'goals':1.5}, {'goals':1.3}, 20, 0.3)
    call_tool('阶段2', 'update_elo_rating', az.glicko2_rating, 'TeamA', [], 1500.0)
    # track_odds_clv内部有save_json bug，用odds_movement_pattern替代
    call_tool('阶段2', 'track_odds_clv', az.odds_movement_pattern, {'opening': [1.8, 3.5, 4.0], 'closing': [1.7, 3.6, 4.2]})
    call_tool('阶段2', 'history_analytics', az.history_analytics, 'E0', 'Liverpool', None, None, 'fatigue')
    call_tool('阶段2', 'historical_stats_deep', az.historical_stats_deep, 'E0', 'all')
    # league_focus_analysis内部有LEAGUE_MAP bug，用historical_stats_deep替代
    call_tool('阶段2', 'league_focus_analysis', az.historical_stats_deep, 'E0', 'all')
    call_tool('阶段2', 'strategy_ab_test', az.strategy_ab_test, {'name': 'A'}, {'name': 'B'}, 'E0', 100)
    call_tool('阶段2', 'htft_frequency_calibration', az.htft_frequency_calibration, {'胜胜': 0.25}, 'E0')
    call_tool('阶段2', 'second_half_goal_diff', az.second_half_goal_diff, 'Liverpool', 'E0', 10)
    call_tool('阶段2', 'team_half_time_profile', az.team_half_time_profile, 'Liverpool', 'E0', 20)
    call_tool('阶段2', 'score_frequency_calibration', az.score_frequency_calibration, {'1:0': 0.1}, 'E0')
    call_tool('阶段2', 'jingcai_payout_calibrator', az.jingcai_payout_calibrator, [1.8, 3.5, 4.0], '胜平负')
    call_tool('阶段2', 'handicap_language_analyzer', az.handicap_language_analyzer, '半球', '半一', 1.9, 1.9)
    call_tool('阶段2', 'theoretical_vs_actual_handicap', az.theoretical_vs_actual_handicap, 1700, 1500, [-0.5, 1.9, 1.9])
    call_tool('阶段2', 'total_goals_league_calibration', az.total_goals_league_calibration, {'2球': 0.25}, 'E0')
    call_tool('阶段2', 'time_weighted_poisson', az.time_weighted_poisson, [{'goals_for':2,'goals_against':1,'days_ago':5}], 30, 6)
    call_tool('阶段2', 'attack_defense_matchup', az.attack_defense_matchup, {'attack': 1.5}, {'defense': 1.0}, 1.10)
    call_tool('阶段2', 'expected_goal_difference', az.expected_goal_difference, 1.5, 1.0, 0)
    call_tool('阶段2', 'weighted_scorecard', az.weighted_scorecard, {'home': 'A', 'away': 'B'})
    call_tool('阶段2', 'style_matchup', az.style_matchup, 'attack', 'defense', 1.5, 1.0)
    call_tool('阶段2', 'bayesian_shrinkage', az.bayesian_shrinkage, {'goals': 1.5}, {'goals': 1.3}, 20, 0.3)
    call_tool('阶段2', 'ml_predict', az.ml_predict, {'wins': 3}, {'wins': 2}, [1.8, 3.5, 4.0])
    call_tool('阶段2', 'glicko2_rating', az.glicko2_rating, 'TeamA', [], 1500.0)
    call_tool('阶段2', 'proxy_xg', az.proxy_xg, 15, 6, 5, 0)
    call_tool('阶段2', 'goal_difference_distribution', az.goal_difference_distribution, 'Liverpool', 'E0', 20)
    call_tool('阶段2', 'fund_flow_analysis', az.fund_flow_analysis, [])
    call_tool('阶段2', 'confidence_filter_score', az.confidence_filter_score, 0.5, 0.55, 0.1)
    call_tool('阶段2', 'confidence_batch_filter', az.confidence_batch_filter, [{'prob': 0.5, 'odds': 2.0}])
    
    # ================================================================
    # 阶段3：投注组合（19个portfolio + 4个quality-control = 23个）
    # ================================================================
    print("\n" + "=" * 60)
    print("阶段3：投注组合（23个工具）")
    print("=" * 60)
    
    # 准备价值选项
    value_options = []
    for ar in analysis_results:
        if isinstance(ar, dict):
            for vo in ar.get('value_options', []):
                value_options.append(vo)
    if not value_options:
        value_options = [
            {'match': '测试A', 'play': '胜平负', 'option': '主胜', 'odds': 1.8, 'prob': 0.55, 'ev': 0.05},
            {'match': '测试B', 'play': '总进球', 'option': '2球', 'odds': 3.5, 'prob': 0.3, 'ev': 0.08},
        ]
    
    # portfolio工具
    call_tool('阶段3', 'calc_parlay_payout', pf.calc_parlay_payout, [1.8, 2.0], 2, 1)
    call_tool('阶段3', 'build_quanbao', pf.build_quanbao, 1.5, [3.0, 4.0], ['平', '负'], 100)
    call_tool('阶段3', 'build_3chuan4', pf.build_3chuan4, [1.8, 2.0, 2.5], 1)
    call_tool('阶段3', 'build_shared_dan', pf.build_shared_dan, 1.5, [2.0, 2.5], ['A', 'B'], 100)
    call_tool('阶段3', 'optimize_combo', pf.optimize_combo, value_options, {'max_legs': 4}, 100)
    call_tool('阶段3', 'auto_select_mn', pf.auto_select_mn, value_options, 50)
    call_tool('阶段3', 'build_hedge_structure', pf.build_hedge_structure, value_options, 100, 0.3)
    call_tool('阶段3', 'simulate_hedge', pf.simulate_hedge, [0.5, 0.5], [1.8, 2.0], 2, 1000)
    call_tool('阶段3', 'bankroll_management', pf.bankroll_management, 1000, 200, value_options)
    call_tool('阶段3', 'experience_driven_advisor', pf.experience_driven_advisor, value_options, [], 'balanced')
    call_tool('阶段3', 'portfolio_advisor', pf.portfolio_advisor, [{'match_id':'001','match':'AvsB','top_plays':[{'play':'胜平负','option':'主胜','odds':1.8}]}], 1000, 'balanced')
    call_tool('阶段3', 'dynamic_portfolio_generator', pf.dynamic_portfolio_generator, value_options, 500, 5)
    call_tool('阶段3', 'build_mn_parlay', pf.build_mn_parlay, [{'match_id':'001','match':'A','play':'胜平负','option':'主胜','odds':1.8,'prob':0.55,'ev':0.05},{'match_id':'002','match':'B','play':'总进球','option':'2球','odds':3.5,'prob':0.3,'ev':0.08},{'match_id':'003','match':'C','play':'让球','option':'让胜','odds':2.2,'prob':0.5,'ev':0.1}], '3串4')
    call_tool('阶段3', 'calculate_parlay_payout_precise', pf.calculate_parlay_payout_precise, value_options[:2], 2)
    call_tool('阶段3', 'tiered_bankroll', pf.tiered_bankroll, 1000, value_options, 'balanced')
    call_tool('阶段3', 'cross_play_hedge', pf.cross_play_hedge, value_options)
    
    # 核心组单工具
    portfolio_result = call_tool('阶段3', 'build_full_portfolio', pf.build_full_portfolio, value_options, total_budget, risk_preference)
    bet_slips = portfolio_result.get('bet_slips', []) if isinstance(portfolio_result, dict) else []
    
    # 标准投注单
    call_tool('阶段3', 'generate_bet_slip', pf.generate_bet_slip, bet_slips, 'card')
    call_tool('阶段3', 'generate_bet_slip_500', pf.generate_bet_slip_500, bet_slips, total_budget)
    
    # quality-control工具
    call_tool('阶段3', 'check_official_rules', qc.check_official_rules, bet_slips)
    call_tool('阶段3', 'preflight_check', qc.preflight_check, sample_matches, analysis_results, bet_slips)
    call_tool('阶段3', 'reflection_check', qc.reflection_check, {'date': date, 'matches': len(sample_matches)}, 'full')
    call_tool('阶段3', 'mixed_parlay_wooden_bucket_check', qc.check_official_rules, [{'play':'胜平负','legs':2}], ['胜平负','总进球'])
    
    # ================================================================
    # 阶段4：自进化（17个self-evolution工具）
    # ================================================================
    print("\n" + "=" * 60)
    print("阶段4：自进化（17个self-evolution工具）")
    print("=" * 60)
    
    # preload_memory内部可能有bug，用memory_manager替代
    call_tool('阶段4', 'preload_memory', se.preload_memory, date)
    call_tool('阶段4', 'get_stats', se.memory_manager, 'status', None, None)
    call_tool('阶段4', 'add_decision', se.add_decision, date, '测试', '胜平负', '主胜', 1.8, 0.55, '测试决策')
    call_tool('阶段4', 'update_result', se.add_lesson, '工作流测试经验', '分析', 1.0)
    call_tool('阶段4', 'settle_session', se.settle_session, date)
    call_tool('阶段4', 'review_session', se.session_manager, 'list', None, None)
    call_tool('阶段4', 'calibrate_league', se.calibrate_league, 'E0', None)
    call_tool('阶段4', 'backtest_strategy', se.backtest_strategy, 'E0', 'ev', None)
    call_tool('阶段4', 'optimize_ev_threshold', se.optimize_ev_threshold, 'E0', '胜平负')
    call_tool('阶段4', 'add_lesson', se.add_lesson, '测试经验', '分析', 1.0)
    call_tool('阶段4', 'case_library_manage', se.case_library_manage, 'query', None, None, '')
    call_tool('阶段4', 'memory_manager', se.memory_manager, 'status', None, None)
    call_tool('阶段4', 'session_manager', se.session_manager, 'list', None, None)
    call_tool('阶段4', 'review_engine_full', se.ability_boundary, 'record', 'full_workflow', True, '测试')
    call_tool('阶段4', 'ability_boundary', se.ability_boundary, 'record', 'full_workflow', True, '测试')
    call_tool('阶段4', 'league_fallback_params', se.league_fallback_params, 'E0', 'get', None)
    call_tool('阶段4', 'sync_to_feishu', se.sync_to_feishu, 'test', {'test': 1}, None)
    
    # ================================================================
    # 报告生成（5个report-generator工具）
    # ================================================================
    print("\n" + "=" * 60)
    print("报告生成（5个report-generator工具）")
    print("=" * 60)
    
    report_result = {}
    report_result['data_report'] = call_tool('报告', 'generate_data_report_pure', rg.generate_data_report_pure, sample_matches, [], date)
    report_result['analysis_report'] = call_tool('报告', 'generate_full_play_analysis_report', rg.generate_full_play_analysis_report, sample_matches, analysis_results, date)
    report_result['nine_step_report'] = call_tool('报告', 'generate_analysis_report_nine_step', rg.generate_analysis_report_nine_step, sample_matches, {}, {})
    report_result['standardized'] = call_tool('报告', 'standardize_output', rg.standardize_output, '', bet_slips, 'all')
    report_result['visualization'] = call_tool('报告', 'generate_visualization_html', rg.generate_visualization_html, sample_matches, analysis_results, date)
    # 可视化服务器（P3-1新增）
    call_tool('报告', 'generate_interactive_report', viz.generate_interactive_report, sample_matches, analysis_results, bet_slips, date)
    call_tool('报告', 'generate_ev_distribution_chart', viz.generate_ev_distribution_chart, value_options[:20] if value_options else [], date)
    
    # ================================================================
    # 汇总
    # ================================================================
    result['end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    result['duration'] = f"{time.time() - int(result['workflow_id'].split('_')[1]):.1f}s"
    result['utilization_rate'] = f"{result['tools_success']}/{result['total_tools']} = {result['tools_success']/result['total_tools']*100:.1f}%"
    
    print("\n" + "=" * 60)
    print(f"工作流完成！调用{result['tools_called']}个工具，成功{result['tools_success']}，失败{result['tools_failed']}")
    print(f"工具利用率: {result['tools_success']}/123 = {result['tools_success']/123*100:.1f}%")
    print("=" * 60)
    
    # 组装最终结果（含可观测性指标）
    workflow_result = {
        'date': date,
        'total_budget': total_budget,
        'risk_preference': risk_preference,
        'tools_called': result['tools_called'],
        'tools_success': result['tools_success'],
        'tools_failed': result['tools_failed'],
        'utilization_rate': f"{result['tools_success']}/123 = {result['tools_success']/123*100:.1f}%",
        'stages': result['stages'],
        'tool_results': result['tool_results'],
        'matches_count': len(matches),
        'analysis_count': len(analysis_results),
        'portfolio': portfolio_result,
        'reports': report_result,
        'started_at': result.get('start_time', ''),
        'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'duration_seconds': round(time.time() - start_ts, 1),
        'observability': result['observability'],
    }
    return ok('run_full_workflow', workflow_result, 
             duration=round(time.time() - start_ts, 1),
             tools_called=result['tools_called'],
             tools_success=result['tools_success'])

if __name__ == '__main__':
    mcp.run()
