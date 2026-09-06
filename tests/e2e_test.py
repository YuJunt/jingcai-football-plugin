#!/usr/bin/env python3
"""
竞彩足球插件端到端测试脚本
验证完整工作流：数据采集→深度分析→报告生成→投注组合→自进化

用法：
  python3 e2e_test.py --full          # 完整端到端测试
  python3 e2e_test.py --stage 1       # 只测试阶段1（数据采集）
  python3 e2e_test.py --report        # 生成测试报告
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

# 添加路径
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)

# 测试结果记录
test_results = {
    'start_time': None,
    'end_time': None,
    'stages': {},
    'total_tests': 0,
    'passed_tests': 0,
    'failed_tests': 0,
    'errors': []
}


def log_test(stage, name, passed, details="", duration=0):
    """记录测试结果"""
    if stage not in test_results['stages']:
        test_results['stages'][stage] = {'tests': [], 'passed': 0, 'failed': 0}

    test_results['stages'][stage]['tests'].append({
        'name': name,
        'passed': passed,
        'details': details,
        'duration': round(duration, 3)
    })

    if passed:
        test_results['stages'][stage]['passed'] += 1
        test_results['passed_tests'] += 1
        status = "✅"
    else:
        test_results['stages'][stage]['failed'] += 1
        test_results['failed_tests'] += 1
        test_results['errors'].append(f"{stage}/{name}: {details}")
        status = "❌"

    test_results['total_tests'] += 1
    print(f"  {status} {name} ({duration:.3f}s) - {details}")


def test_stage1_data_collection():
    """阶段1：数据采集测试"""
    print("\n" + "="*60)
    print("阶段1：数据采集测试")
    print("="*60)

    stage = "数据采集"

    # 测试1：导入data-collector模块
    start = time.time()
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("data_collector", os.path.join(PLUGIN_ROOT, "servers/data-collector/server.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        log_test(stage, "导入data-collector模块", True, "成功导入", time.time()-start)
    except Exception as e:
        log_test(stage, "导入data-collector模块", False, str(e), time.time()-start)
        return

    # 测试2：验证工具数量
    mcp_tools = [attr for attr in dir(mod) if not attr.startswith('_') and hasattr(getattr(mod, attr, None), 'fn')]
    log_test(stage, "验证MCP工具数量", len(mcp_tools) >= 15, f"{len(mcp_tools)}个工具（预期>=15）")

    # 测试3：测试get_match_list
    start = time.time()
    try:
        result = mod.get_match_list.fn("2026-09-06")
        log_test(stage, "get_match_list", result.get('success', False) or 'matches' in result, f"返回{result.get('total_matches', 'N/A')}场比赛", time.time()-start)
    except Exception as e:
        log_test(stage, "get_match_list", False, str(e), time.time()-start)

    # 测试4：测试validate_data_completeness（新增工具）
    start = time.time()
    try:
        mock_matches = [{'match_id': '001', 'league': '英超', 'home': '利物浦', 'away': '曼城',
                         'odds': {'胜平负': {'odds': [1.5, 3.8, 5.0]}}, 'info': {'赛事特征': '测试'}}]
        result = mod.validate_data_completeness.fn(mock_matches)
        log_test(stage, "validate_data_completeness", 'completeness_rate' in result, f"完整性{result.get('completeness_rate', 'N/A')}", time.time()-start)
    except Exception as e:
        log_test(stage, "validate_data_completeness", False, str(e), time.time()-start)

    # 测试5：测试get_data_source_status（新增工具）
    start = time.time()
    try:
        result = mod.get_data_source_status.fn()
        log_test(stage, "get_data_source_status", 'total_sources' in result, f"{result.get('total_sources', 0)}个数据源", time.time()-start)
    except Exception as e:
        log_test(stage, "get_data_source_status", False, str(e), time.time()-start)


def test_stage2_analysis():
    """阶段2：深度分析测试"""
    print("\n" + "="*60)
    print("阶段2：深度分析测试")
    print("="*60)

    stage = "深度分析"

    # 测试1：导入analyzer模块
    start = time.time()
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("analyzer", os.path.join(PLUGIN_ROOT, "servers/analyzer/server.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        log_test(stage, "导入analyzer模块", True, "成功导入", time.time()-start)
    except Exception as e:
        log_test(stage, "导入analyzer模块", False, str(e), time.time()-start)
        return

    # 测试2：验证工具数量
    mcp_tools = [attr for attr in dir(mod) if not attr.startswith('_') and hasattr(getattr(mod, attr, None), 'fn')]
    log_test(stage, "验证MCP工具数量", len(mcp_tools) >= 26, f"{len(mcp_tools)}个工具（预期>=26）")

    # 测试3：测试poisson_predict
    start = time.time()
    try:
        result = mod.poisson_predict.fn(1.5, 1.0)
        log_test(stage, "poisson_predict", 'result_probs' in result or 'home_win_prob' in result, "泊松预测成功", time.time()-start)
    except Exception as e:
        log_test(stage, "poisson_predict", False, str(e), time.time()-start)

    # 测试4：测试calculate_ev
    start = time.time()
    try:
        result = mod.calculate_ev.fn(0.6, 2.0)
        expected_ev = 0.6 * 2.0 - 1  # 0.2
        log_test(stage, "calculate_ev", abs(result.get('ev', 0) - expected_ev) < 0.01, f"EV={result.get('ev', 'N/A')}（预期{expected_ev}）", time.time()-start)
    except Exception as e:
        log_test(stage, "calculate_ev", False, str(e), time.time()-start)

    # 测试5：测试multi_agent_debate（新填充的完整业务逻辑）
    start = time.time()
    try:
        match_data = {
            'home': '利物浦', 'away': '曼城', 'league': '英超',
            'odds': {'胜平负': {'odds': [2.1, 3.4, 3.2]}},
            'info': {'近期战绩': {}, '历史交锋': {}, '伤停': {}}
        }
        result = mod.multi_agent_debate.fn(match_data)
        has_consensus = 'consensus' in result and 'view' in result['consensus']
        has_agents = 'agents' in result and len(result['agents']) == 5
        log_test(stage, "multi_agent_debate", has_consensus and has_agents,
                 f"共识:{result.get('consensus', {}).get('view', 'N/A')}, 5个agent", time.time()-start)
    except Exception as e:
        log_test(stage, "multi_agent_debate", False, str(e), time.time()-start)

    # 测试6：测试conditional_prob_half_full
    start = time.time()
    try:
        result = mod.conditional_prob_half_full.fn(1.5, 1.0, "normal")
        log_test(stage, "conditional_prob_half_full", 'half_full_probs' in result or 'probabilities' in result, "半全场条件概率成功", time.time()-start)
    except Exception as e:
        log_test(stage, "conditional_prob_half_full", False, str(e), time.time()-start)

    # 测试7：测试monte_carlo_simulate
    start = time.time()
    try:
        result = mod.monte_carlo_simulate.fn([0.6, 0.55], [2.0, 1.8], 1000)
        log_test(stage, "monte_carlo_simulate", 'simulations' in result or 'win_rate' in result, "蒙特卡洛模拟成功", time.time()-start)
    except Exception as e:
        log_test(stage, "monte_carlo_simulate", False, str(e), time.time()-start)


def test_stage3_portfolio():
    """阶段3：投注组合测试"""
    print("\n" + "="*60)
    print("阶段3：投注组合测试")
    print("="*60)

    stage = "投注组合"

    # 测试1：导入portfolio模块
    start = time.time()
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("portfolio", os.path.join(PLUGIN_ROOT, "servers/portfolio/server.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        log_test(stage, "导入portfolio模块", True, "成功导入", time.time()-start)
    except Exception as e:
        log_test(stage, "导入portfolio模块", False, str(e), time.time()-start)
        return

    # 测试2：验证工具数量
    mcp_tools = [attr for attr in dir(mod) if not attr.startswith('_') and hasattr(getattr(mod, attr, None), 'fn')]
    log_test(stage, "验证MCP工具数量", len(mcp_tools) >= 16, f"{len(mcp_tools)}个工具（预期>=16）")

    # 测试3：测试calculate_parlay_payout
    start = time.time()
    try:
        result = mod.calculate_parlay_payout.fn([1.5, 2.0, 3.0], 2, 100)
        expected_payout = 1.5 * 2.0 * 3.0 * 100  # 900
        log_test(stage, "calculate_parlay_payout", abs(result.get('payout', 0) - expected_payout) < 1,
                 f"奖金={result.get('payout', 'N/A')}（预期{expected_payout}）", time.time()-start)
    except Exception as e:
        log_test(stage, "calculate_parlay_payout", False, str(e), time.time()-start)

    # 测试4：测试generate_bet_slip_500
    start = time.time()
    try:
        bets = [{'match_id': '001', 'play': '胜平负', 'option': '主胜', 'odds': 1.5}]
        result = mod.generate_bet_slip_500.fn(bets, 100, 1)
        log_test(stage, "generate_bet_slip_500", 'bet_slip' in result or 'formatted' in result, "500风格投注单生成成功", time.time()-start)
    except Exception as e:
        log_test(stage, "generate_bet_slip_500", False, str(e), time.time()-start)


def test_stage4_self_evolution():
    """阶段4：自进化测试"""
    print("\n" + "="*60)
    print("阶段4：自进化测试")
    print("="*60)

    stage = "自进化"

    # 测试1：导入self-evolution模块
    start = time.time()
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("self_evolution", os.path.join(PLUGIN_ROOT, "servers/self-evolution/server.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        log_test(stage, "导入self-evolution模块", True, "成功导入", time.time()-start)
    except Exception as e:
        log_test(stage, "导入self-evolution模块", False, str(e), time.time()-start)
        return

    # 测试2：验证工具数量
    mcp_tools = [attr for attr in dir(mod) if not attr.startswith('_') and hasattr(getattr(mod, attr, None), 'fn')]
    log_test(stage, "验证MCP工具数量", len(mcp_tools) >= 17, f"{len(mcp_tools)}个工具（预期>=17）")

    # 测试3：测试add_decision_record
    start = time.time()
    try:
        result = mod.add_decision_record.fn("2026-09-06", "001", "胜平负", "主胜", 1.5, "测试记录")
        log_test(stage, "add_decision_record", result.get('success', False), "决策记录添加成功", time.time()-start)
    except Exception as e:
        log_test(stage, "add_decision_record", False, str(e), time.time()-start)

    # 测试4：测试add_lesson
    start = time.time()
    try:
        result = mod.add_lesson.fn("测试教训", "测试分类", "测试解决方案")
        log_test(stage, "add_lesson", result.get('success', False), "经验教训添加成功", time.time()-start)
    except Exception as e:
        log_test(stage, "add_lesson", False, str(e), time.time()-start)


def generate_report():
    """生成测试报告"""
    print("\n" + "="*60)
    print("端到端测试报告")
    print("="*60)

    total = test_results['total_tests']
    passed = test_results['passed_tests']
    failed = test_results['failed_tests']
    pass_rate = passed / total * 100 if total > 0 else 0

    print(f"\n总测试数: {total}")
    print(f"通过: {passed}")
    print(f"失败: {failed}")
    print(f"通过率: {pass_rate:.1f}%")

    print("\n各阶段详情:")
    for stage, data in test_results['stages'].items():
        stage_pass = data['passed']
        stage_total = stage_pass + data['failed']
        stage_rate = stage_pass / stage_total * 100 if stage_total > 0 else 0
        print(f"  {stage}: {stage_pass}/{stage_total} ({stage_rate:.1f}%)")

    if test_results['errors']:
        print(f"\n失败详情 ({len(test_results['errors'])}个):")
        for i, error in enumerate(test_results['errors'][:10], 1):
            print(f"  {i}. {error}")

    # 保存报告
    report_file = os.path.join(PLUGIN_ROOT, "tests", "e2e_test_report.json")
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(test_results, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存到: {report_file}")

    return pass_rate >= 80


def main():
    parser = argparse.ArgumentParser(description='竞彩足球插件端到端测试')
    parser.add_argument('--full', action='store_true', help='完整端到端测试')
    parser.add_argument('--stage', type=int, help='只测试指定阶段（1-4）')
    parser.add_argument('--report', action='store_true', help='生成测试报告')
    args = parser.parse_args()

    test_results['start_time'] = datetime.now().isoformat()

    if args.full or args.stage == 1:
        test_stage1_data_collection()
    if args.full or args.stage == 2:
        test_stage2_analysis()
    if args.full or args.stage == 3:
        test_stage3_portfolio()
    if args.full or args.stage == 4:
        test_stage4_self_evolution()

    test_results['end_time'] = datetime.now().isoformat()

    if args.report or args.full:
        success = generate_report()
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
