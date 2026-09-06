#!/usr/bin/env python3
"""
竞彩足球插件统一测试运行入口
用法:
  python3 tests/run_tests.py              # 运行所有测试
  python3 tests/run_tests.py --unit       # 仅运行单元测试（test_core）
  python3 tests/run_tests.py --integration # 仅运行集成测试（test_all）
  python3 tests/run_tests.py --e2e        # 仅运行端到端测试（e2e_test）
  python3 tests/run_tests.py --quick      # 快速模式（跳过耗时测试）
  python3 tests/run_tests.py --verbose    # 详细输出
"""
import argparse
import os
import sys
import time
import subprocess

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(TESTS_DIR)

def run_test_file(test_file, description="", verbose=False):
    """运行单个测试文件"""
    filepath = os.path.join(TESTS_DIR, test_file)
    if not os.path.exists(filepath):
        print(f"  ⚠️  {test_file} 不存在，跳过")
        return True, 0, 0
    
    print(f"\n{'='*60}")
    print(f"  运行: {test_file} ({description})")
    print(f"{'='*60}")
    
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, filepath],
            capture_output=True, text=True, timeout=300,
            cwd=PLUGIN_ROOT
        )
        elapsed = time.time() - start
        
        if verbose:
            print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr[-500:])
        
        # 解析测试结果
        output = result.stdout + result.stderr
        passed = 0
        failed = 0
        
        # test_all.py格式
        if '测试完成' in output:
            for line in output.split('\n'):
                if '测试完成' in line:
                    print(f"  {line.strip()}")
                    import re
                    m = re.search(r'通过(\d+).*失败(\d+)', line)
                    if m:
                        passed = int(m.group(1))
                        failed = int(m.group(2))
        
        # pytest格式
        elif 'passed' in output or 'failed' in output:
            for line in output.split('\n'):
                if 'passed' in line or 'failed' in line:
                    print(f"  {line.strip()}")
                    import re
                    m = re.search(r'(\d+)\s+passed', line)
                    if m:
                        passed = int(m.group(1))
                    m = re.search(r'(\d+)\s+failed', line)
                    if m:
                        failed = int(m.group(1))
        
        success = result.returncode == 0 and failed == 0
        status = "✅ 通过" if success else "❌ 失败"
        print(f"\n  结果: {status} | 耗时: {elapsed:.1f}秒 | 通过: {passed} | 失败: {failed}")
        return success, passed, failed
        
    except subprocess.TimeoutExpired:
        print(f"  ❌ 超时（300秒）")
        return False, 0, 1
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return False, 0, 1

def main():
    parser = argparse.ArgumentParser(description='竞彩足球插件统一测试运行入口')
    parser.add_argument('--unit', action='store_true', help='仅运行单元测试')
    parser.add_argument('--integration', action='store_true', help='仅运行集成测试')
    parser.add_argument('--e2e', action='store_true', help='仅运行端到端测试')
    parser.add_argument('--quick', action='store_true', help='快速模式（跳过e2e）')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    args = parser.parse_args()
    
    print("=" * 60)
    print("  竞彩足球插件 - 统一测试运行")
    print("=" * 60)
    
    # 确定要运行的测试
    tests_to_run = []
    if args.unit:
        tests_to_run.append(('test_core.py', '单元测试'))
    elif args.integration:
        tests_to_run.append(('test_all.py', '集成测试'))
    elif args.e2e:
        tests_to_run.append(('e2e_test.py', '端到端测试'))
    else:
        # 默认运行所有
        tests_to_run.append(('test_all.py', '集成测试'))
        if not args.quick:
            tests_to_run.append(('e2e_test.py', '端到端测试'))
    
    print(f"\n测试模式: {'自定义' if any([args.unit, args.integration, args.e2e]) else '全部'}")
    print(f"测试文件: {', '.join(t[0] for t in tests_to_run)}")
    
    # 运行测试
    total_passed = 0
    total_failed = 0
    all_success = True
    
    for test_file, description in tests_to_run:
        success, passed, failed = run_test_file(test_file, description, args.verbose)
        total_passed += passed
        total_failed += failed
        if not success:
            all_success = False
    
    # 汇总
    print(f"\n{'='*60}")
    print("  测试汇总")
    print(f"{'='*60}")
    print(f"  总通过: {total_passed}")
    print(f"  总失败: {total_failed}")
    print(f"  总体结果: {'✅ 全部通过' if all_success else '❌ 存在失败'}")
    print(f"{'='*60}")
    
    sys.exit(0 if all_success else 1)

if __name__ == '__main__':
    main()
