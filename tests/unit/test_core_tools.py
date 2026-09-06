#!/usr/bin/env python3
"""
单元测试：测试核心MCP工具的基本功能
包括：参数加载/更新、投注单入库、模拟账户、数据持久化
"""
import os
import sys
import json
import tempfile
import shutil

# 插件根目录
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试结果统计
test_results = {
    'total': 0,
    'passed': 0,
    'failed': 0,
    'errors': [],
}


def test_case(name):
    """测试用例装饰器"""
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
    """动态导入服务器模块，并自动处理FunctionTool的.fn()调用"""
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
    
    # 自动处理FunctionTool：如果函数有.fn属性，就替换为.fn
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if hasattr(attr, 'fn') and callable(attr.fn):
            # 这是一个FunctionTool对象，替换为.fn方法
            setattr(module, attr_name, attr.fn)
    
    return module


def call_tool(module, func_name, **kwargs):
    """安全调用工具函数，自动处理FunctionTool和普通函数"""
    func = getattr(module, func_name)
    if hasattr(func, 'fn') and callable(func.fn):
        return func.fn(**kwargs)
    return func(**kwargs)


# ============================================================
# 测试1：参数配置工具
# ============================================================

@test_case("参数加载 - 全部参数")
def test_load_all_parameters():
    wf = import_module('workflow', 'test_workflow_1')
    result = wf.load_parameters.fn()
    assert result['success'] == True
    assert 'parameters' in result
    assert 'play_specific' in result['parameters']
    assert 'composite_scoring' in result['parameters']


@test_case("参数加载 - 指定类别")
def test_load_parameters_by_category():
    wf = import_module('workflow', 'test_workflow_2')
    result = wf.load_parameters.fn(category='play_specific')
    assert result['success'] == True
    assert len(result['parameters']) == 5  # 5个玩法


@test_case("参数更新")
def test_update_parameters():
    wf = import_module('workflow', 'test_workflow_3')
    result = wf.update_parameters.fn(
        category='portfolio',
        updates={'default_budget': 500},
        reason='单元测试更新'
    )
    assert result['success'] == True
    assert result['after']['default_budget'] == 500
    
    # 恢复原值
    wf.update_parameters.fn(
        category='portfolio',
        updates={'default_budget': 100},
        reason='恢复原值'
    )


# ============================================================
# 测试2：投注单入库工具
# ============================================================

@test_case("投注单入库")
def test_record_bet_slip():
    pf = import_module('portfolio', 'test_portfolio_1')
    bet_slips = [
        {'match_id': 'unit_test_001', 'play': '胜平负', 'option': '主胜', 'odds': 1.85, 'stake': 2},
    ]
    result = pf.record_bet_slip.fn(bet_slips=bet_slips, session_date='2026-01-01', notes='单元测试')
    assert result['success'] == True
    assert result['saved_count'] == 1
    assert result['total_stake'] == 2
    assert os.path.exists(result['file_path'])


# ============================================================
# 测试3：模拟账户工具
# ============================================================

@test_case("模拟账户 - 初始化")
def test_init_account():
    se = import_module('self-evolution', 'test_se_1')
    result = se.init_account.fn(initial_balance=1000, account_name='单元测试账户')
    assert result['success'] == True


@test_case("模拟账户 - 投注扣减")
def test_deduct_stake():
    se = import_module('self-evolution', 'test_se_2')
    before = se.get_account.fn()
    before_balance = before['balance']
    
    result = se.deduct_stake.fn(amount=50, bet_slip_id='unit_test', description='单元测试扣减')
    assert result['success'] == True
    assert result['after_balance'] == before_balance - 50


@test_case("模拟账户 - 奖金入账")
def test_add_payout():
    se = import_module('self-evolution', 'test_se_3')
    before = se.get_account.fn()
    before_balance = before['balance']
    
    result = se.add_payout.fn(amount=100, bet_slip_id='unit_test', is_hit=True, description='单元测试入账')
    assert result['success'] == True
    assert result['after_balance'] == before_balance + 100


@test_case("模拟账户 - 查询")
def test_get_account():
    se = import_module('self-evolution', 'test_se_4')
    result = se.get_account.fn()
    assert result['success'] == True
    assert 'balance' in result
    assert 'performance' in result


# ============================================================
# 测试4：数据持久化工具
# ============================================================

@test_case("数据持久化 - 保存比赛资讯")
def test_save_match_info():
    dc = import_module('data-collector', 'test_dc_1')
    result = dc.save_match_info.fn(
        match_id='unit_test_001',
        match_info={'league': '测试联赛', 'home': '主队', 'away': '客队'},
        info_type='official',
        date='2026-01-01'
    )
    assert result['success'] == True
    assert os.path.exists(result['file_path'])


@test_case("数据持久化 - 保存第三方赔率")
def test_save_third_party_odds():
    dc = import_module('data-collector', 'test_dc_2')
    result = dc.save_third_party_odds.fn(
        match_id='unit_test_001',
        odds_data={'european': {'home': 1.85, 'draw': 3.50, 'away': 4.20}},
        odds_type='all',
        date='2026-01-01'
    )
    assert result['success'] == True


@test_case("数据持久化 - 查询")
def test_query_persistent_data():
    dc = import_module('data-collector', 'test_dc_3')
    result = dc.query_persistent_data.fn(data_type='all', date='2026-01-01', limit=10)
    assert result['success'] == True
    assert result['total_count'] >= 2  # 至少有刚才保存的2条


@test_case("数据持久化 - 统计")
def test_get_persistence_stats():
    dc = import_module('data-collector', 'test_dc_4')
    result = dc.get_persistence_stats.fn()
    assert result['success'] == True
    assert 'total' in result
    assert 'stats' in result


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 60)
    print("竞彩足球插件 - 单元测试")
    print("=" * 60)
    print()
    
    # 运行所有测试
    test_load_all_parameters()
    test_load_parameters_by_category()
    test_update_parameters()
    test_record_bet_slip()
    test_init_account()
    test_deduct_stake()
    test_add_payout()
    test_get_account()
    test_save_match_info()
    test_save_third_party_odds()
    test_query_persistent_data()
    test_get_persistence_stats()
    
    # 输出总结
    print()
    print("=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"  总计: {test_results['total']}")
    print(f"  通过: {test_results['passed']}")
    print(f"  失败: {test_results['failed']}")
    print(f"  通过率: {test_results['passed']/test_results['total']*100:.1f}%")
    
    if test_results['errors']:
        print()
        print("失败详情:")
        for err in test_results['errors']:
            print(f"  - {err['test']}: {err['error'][:100]}")
    
    # 保存测试报告
    report = {
        'test_type': 'unit',
        'total': test_results['total'],
        'passed': test_results['passed'],
        'failed': test_results['failed'],
        'pass_rate': test_results['passed'] / test_results['total'] * 100,
        'errors': test_results['errors'],
        'timestamp': __import__('datetime').datetime.now().isoformat(),
    }
    
    report_file = os.path.join(PLUGIN_ROOT, 'tests', 'unit_test_report.json')
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print()
    print(f"测试报告已保存: {report_file}")
    
    return test_results['failed'] == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
