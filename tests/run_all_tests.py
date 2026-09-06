#!/usr/bin/env python3
"""
竞彩足球插件 - 统一测试运行脚本
运行单元测试、集成测试、端到端测试，并生成综合测试报告
"""
import os
import sys
import json
import subprocess
from datetime import datetime

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(PLUGIN_ROOT, 'tests')


def run_test(test_file, test_name):
    """运行单个测试文件"""
    print(f"\n{'='*60}")
    print(f"运行: {test_name}")
    print(f"{'='*60}")
    
    result = subprocess.run(
        [sys.executable, test_file],
        capture_output=True, text=True, timeout=300,
        cwd=PLUGIN_ROOT
    )
    
    # 输出测试结果
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:500])
    
    # 解析测试报告
    report_file = os.path.join(TESTS_DIR, f'{test_name}_report.json')
    report = None
    if os.path.exists(report_file):
        with open(report_file, 'r', encoding='utf-8') as f:
            report = json.load(f)
    
    return {
        'name': test_name,
        'success': result.returncode == 0,
        'returncode': result.returncode,
        'report': report,
    }


def main():
    print("=" * 70)
    print("竞彩足球插件 - 自动化测试套件")
    print(f"插件根目录: {PLUGIN_ROOT}")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 测试文件列表
    test_files = [
        (os.path.join(TESTS_DIR, 'unit', 'test_core_tools.py'), 'unit_test'),
        (os.path.join(TESTS_DIR, 'integration', 'test_workflows.py'), 'integration_test'),
        (os.path.join(TESTS_DIR, 'e2e', 'test_full_workflow.py'), 'e2e_test'),
    ]
    
    # 运行所有测试
    results = []
    for test_file, test_name in test_files:
        if os.path.exists(test_file):
            result = run_test(test_file, test_name)
            results.append(result)
        else:
            print(f"\n⚠️  测试文件不存在: {test_file}")
            results.append({'name': test_name, 'success': False, 'report': None})
    
    # 生成综合报告
    print("\n" + "=" * 70)
    print("综合测试报告")
    print("=" * 70)
    
    total_tests = 0
    total_passed = 0
    total_failed = 0
    
    for result in results:
        status = "✅ 通过" if result['success'] else "❌ 失败"
        print(f"\n{status} - {result['name']}")
        
        if result['report']:
            r = result['report']
            print(f"  总计: {r.get('total', 0)}, 通过: {r.get('passed', 0)}, 失败: {r.get('failed', 0)}, 通过率: {r.get('pass_rate', 0):.1f}%")
            total_tests += r.get('total', 0)
            total_passed += r.get('passed', 0)
            total_failed += r.get('failed', 0)
    
    print(f"\n{'='*70}")
    print(f"总体统计: 总计 {total_tests} 项测试, 通过 {total_passed} 项, 失败 {total_failed} 项")
    if total_tests > 0:
        print(f"总体通过率: {total_passed/total_tests*100:.1f}%")
    print(f"{'='*70}")
    
    # 保存综合报告
    summary = {
        'test_suite': '竞彩足球插件自动化测试套件',
        'run_at': datetime.now().isoformat(),
        'plugin_root': PLUGIN_ROOT,
        'total_test_suites': len(results),
        'passed_suites': sum(1 for r in results if r['success']),
        'failed_suites': sum(1 for r in results if not r['success']),
        'total_tests': total_tests,
        'total_passed': total_passed,
        'total_failed': total_failed,
        'overall_pass_rate': total_passed / total_tests * 100 if total_tests > 0 else 0,
        'details': [
            {
                'name': r['name'],
                'success': r['success'],
                'report': r['report'],
            }
            for r in results
        ],
    }
    
    summary_file = os.path.join(TESTS_DIR, 'test_summary.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n综合测试报告已保存: {summary_file}")
    
    # 返回总体成功状态
    return total_failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
