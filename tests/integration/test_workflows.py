#!/usr/bin/env python3
"""
集成测试：测试多个MCP工具协作的工作流
包括：投注流程闭环（入库→结算→复盘→经验提取→账户更新）
"""
import os
import sys
import json
import tempfile

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

test_results = {'total': 0, 'passed': 0, 'failed': 0, 'errors': []}


def test_case(name):
    def decorator(func):
        def wrapper(*args, **kwargs):
            test_results['total'] += 1
            try:
                func(*args, **kwargs)
                test_results['passed'] += 1
                print(f"  ✅ {name}")
                return True
            except Exception as e:
                test_results['failed'] += 1
                test_results['errors'].append({'test': name, 'error': str(e)})
                print(f"  ❌ {name}: {str(e)[:100]}")
                return False
        return wrapper
    return decorator


def import_module(server_name, module_name):
    import importlib.util
    server_path = os.path.join(PLUGIN_ROOT, 'servers', server_name, 'server.py')
    spec = importlib.util.spec_from_file_location(module_name, server_path)
    module = importlib.util.module_from_spec(spec)
    original_argv = sys.argv
    sys.argv = ['server.py']
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = original_argv
    return module


@test_case("投注流程闭环 - 完整流程")
def test_full_bet_flow():
    """测试完整的投注流程闭环：入库→扣减→结算→复盘→经验提取→入账"""
    pf = import_module('portfolio', 'test_integration_pf')
    se = import_module('self-evolution', 'test_integration_se')
    
    # 步骤1：投注单入库
    bet_slips = [
        {'match_id': 'integration_001', 'play': '胜平负', 'option': '主胜', 'odds': 1.85, 'stake': 10},
        {'match_id': 'integration_002', 'play': '总进球', 'option': '2球', 'odds': 3.20, 'stake': 10},
    ]
    record_result = pf.record_bet_slip(
        bet_slips=bet_slips,
        session_date='2026-01-02',
        notes='集成测试'
    )
    assert record_result['success'] == True
    bet_slip_id = record_result['bet_slip_id']
    
    # 步骤2：账户扣减
    deduct_result = se.deduct_stake(
        amount=20,
        bet_slip_id=bet_slip_id,
        description='集成测试扣减'
    )
    assert deduct_result['success'] == True
    
    # 步骤3：赛后结算
    match_results = {
        'integration_001': {'home_goals': 2, 'away_goals': 0, 'result': '主胜'},
        'integration_002': {'home_goals': 1, 'away_goals': 1, 'result': '平局'},
    }
    settle_result = se.settle_bet_slip(
        bet_slip_id=bet_slip_id,
        match_results=match_results
    )
    assert settle_result['success'] == True
    assert settle_result['hit_count'] >= 1  # 至少命中1注
    
    # 步骤4：赛后复盘
    review_result = se.review_bet_slip(
        bet_slip_id=bet_slip_id,
        analysis_notes='集成测试复盘'
    )
    assert review_result['success'] == True
    
    # 步骤5：经验提取
    lessons_result = se.extract_and_save_lessons(bet_slip_id=bet_slip_id)
    assert lessons_result['success'] == True
    assert lessons_result['lessons_extracted'] >= 1
    
    # 步骤6：奖金入账
    if settle_result['total_payout'] > 0:
        payout_result = se.add_payout(
            amount=settle_result['total_payout'],
            bet_slip_id=bet_slip_id,
            is_hit=(settle_result['hit_count'] > 0),
            description='集成测试入账'
        )
        assert payout_result['success'] == True


@test_case("参数自校准 - 完整流程")
def test_calibration_flow():
    """测试参数自校准完整流程"""
    wf = import_module('workflow', 'test_integration_wf')
    
    # 执行参数自校准
    result = wf.calibrate_parameters(
        play_type='胜平负',
        param_name='ev_threshold',
        min_value=0.0,
        max_value=0.15,
        step=0.03,
        max_matches=1000
    )
    assert result['success'] == True
    assert 'best_param' in result
    assert 'best_performance' in result
    assert 'top_3_params' in result
    assert len(result['top_3_params']) == 3
    
    # 验证校准结果已保存
    assert os.path.exists(result['config_file'])


@test_case("数据持久化 - 完整流程")
def test_persistence_flow():
    """测试数据持久化完整流程：保存→查询→统计"""
    dc = import_module('data-collector', 'test_integration_dc')
    
    # 保存多条数据
    for i in range(3):
        dc.save_match_info(
            match_id=f'persist_test_{i}',
            match_info={'test': f'data_{i}'},
            info_type='official',
            date='2026-01-03'
        )
    
    # 查询
    query_result = dc.query_persistent_data(
        data_type='match_info',
        date='2026-01-03',
        limit=10
    )
    assert query_result['success'] == True
    assert query_result['total_count'] >= 3
    
    # 统计
    stats_result = dc.get_persistence_stats()
    assert stats_result['success'] == True
    assert stats_result['total']['file_count'] > 0


def main():
    print("=" * 60)
    print("竞彩足球插件 - 集成测试")
    print("=" * 60)
    print()
    
    test_full_bet_flow()
    test_calibration_flow()
    test_persistence_flow()
    
    print()
    print("=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"  总计: {test_results['total']}")
    print(f"  通过: {test_results['passed']}")
    print(f"  失败: {test_results['failed']}")
    print(f"  通过率: {test_results['passed']/test_results['total']*100:.1f}%")
    
    report = {
        'test_type': 'integration',
        'total': test_results['total'],
        'passed': test_results['passed'],
        'failed': test_results['failed'],
        'pass_rate': test_results['passed'] / test_results['total'] * 100,
        'errors': test_results['errors'],
        'timestamp': __import__('datetime').datetime.now().isoformat(),
    }
    
    report_file = os.path.join(PLUGIN_ROOT, 'tests', 'integration_test_report.json')
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n测试报告已保存: {report_file}")
    return test_results['failed'] == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
