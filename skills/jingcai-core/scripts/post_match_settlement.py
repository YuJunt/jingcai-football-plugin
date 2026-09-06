#!/usr/bin/env python3
"""
赛后一键闭环脚本
自动执行：赛果获取 → 赛后结算 → 赛后复盘 → 经验提取 → 账户更新 → 经验回流

用法：
  python3 post_match_settlement.py --date 2026-09-07
  python3 post_match_settlement.py --bet-slip-id 2026-09-07_012538
  python3 post_match_settlement.py --date 2026-09-07 --skip-account  # 跳过账户更新
"""
import argparse
import json
import os
import sys
from datetime import datetime

# 插件根目录：skills/jingcai-core/scripts/ → 3层dirname = 插件根目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))

# 添加服务器路径
sys.path.insert(0, os.path.join(PLUGIN_ROOT, 'servers', 'self-evolution'))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, 'servers', 'data-collector'))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, 'servers', 'workflow'))


def _import_self_evolution_tools():
    """动态导入self-evolution服务器的工具，避免命名冲突"""
    import importlib.util
    
    server_path = os.path.join(PLUGIN_ROOT, 'servers', 'self-evolution', 'server.py')
    spec = importlib.util.spec_from_file_location("jingcai_self_evolution_server", server_path)
    module = importlib.util.module_from_spec(spec)
    
    # 防止导入时执行mcp.run()
    import sys
    original_argv = sys.argv
    sys.argv = ['server.py']  # 伪装成直接运行
    
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = original_argv
    
    return module


def log_step(step_num, step_name, message=''):
    """打印步骤日志"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"\n{'='*60}")
    print(f"[{timestamp}] 步骤{step_num}: {step_name}")
    if message:
        print(f"  {message}")
    print(f"{'='*60}")


def get_pending_bet_slips(date=None):
    """获取待结算的投注单列表"""
    decisions_dir = os.path.join(PLUGIN_ROOT, 'data', 'decisions')
    if not os.path.exists(decisions_dir):
        return []
    
    pending = []
    for filename in os.listdir(decisions_dir):
        if not filename.endswith('.json'):
            continue
        filepath = os.path.join(decisions_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            record = json.load(f)
        
        # 按日期过滤
        if date and record.get('session_date') != date:
            continue
        
        # 只处理待结算的
        if record.get('status') == 'pending':
            pending.append({
                'bet_slip_id': record['bet_slip_id'],
                'session_date': record.get('session_date'),
                'ticket_count': record.get('ticket_count', 0),
                'total_stake': record.get('total_stake', 0),
                'file_path': filepath,
            })
    
    return pending


def get_match_results_from_bet_slip(bet_slip_id):
    """
    从投注单中提取比赛ID，然后获取赛果
    注意：实际使用时需要调用data-collector的get_match_result工具
    这里提供框架，赛果由LLM获取后传入或手动输入
    """
    filepath = os.path.join(PLUGIN_ROOT, 'data', 'decisions', f'{bet_slip_id}.json')
    if not os.path.exists(filepath):
        return None, "投注单文件不存在"
    
    with open(filepath, 'r', encoding='utf-8') as f:
        record = json.load(f)
    
    # 提取所有比赛ID
    match_ids = set()
    for bet in record.get('bet_slips', []):
        if bet.get('match_id'):
            match_ids.add(bet['match_id'])
    
    return list(match_ids), None


def run_full_settlement(bet_slip_id, match_results, analysis_notes='', skip_account=False):
    """
    执行完整的赛后闭环流程
    
    Args:
        bet_slip_id: 投注单ID
        match_results: 赛果字典 {match_id: {home_goals, away_goals, result}}
        analysis_notes: 分析备注
        skip_account: 是否跳过账户更新
    
    Returns:
        dict: 完整闭环结果
    """
    results = {}
    errors = []
    
    # 动态导入self-evolution工具
    try:
        se_module = _import_self_evolution_tools()
        settle_bet_slip = se_module.settle_bet_slip
        review_bet_slip = se_module.review_bet_slip
        extract_and_save_lessons = se_module.extract_and_save_lessons
        add_payout = se_module.add_payout
        preload_memory = se_module.preload_memory
    except Exception as e:
        print(f"❌ 导入self-evolution工具失败：{str(e)}")
        return {'success': False, 'error': f'导入工具失败: {str(e)}'}
    
    # 步骤1：赛后结算
    log_step(1, "赛后结算", f"投注单ID: {bet_slip_id}")
    try:
        result = settle_bet_slip.fn(bet_slip_id=bet_slip_id, match_results=match_results)
        results['settlement'] = result
        if result.get('success'):
            print(f"  ✅ 结算完成：命中{result['hit_count']}注，盈亏{result['profit_loss']}元")
        else:
            print(f"  ❌ 结算失败：{result.get('error', '未知错误')}")
            errors.append(f"结算失败: {result.get('error')}")
    except Exception as e:
        print(f"  ❌ 结算异常：{str(e)}")
        errors.append(f"结算异常: {str(e)}")
    
    # 步骤2：赛后复盘
    log_step(2, "赛后复盘")
    try:
        result = review_bet_slip.fn(bet_slip_id=bet_slip_id, analysis_notes=analysis_notes)
        results['review'] = result
        if result.get('success'):
            review = result['review']
            print(f"  ✅ 复盘完成：命中率{review['summary']['hit_rate']}%，盈亏{review['summary']['profit_loss']}元")
        else:
            print(f"  ❌ 复盘失败：{result.get('error', '未知错误')}")
            errors.append(f"复盘失败: {result.get('error')}")
    except Exception as e:
        print(f"  ❌ 复盘异常：{str(e)}")
        errors.append(f"复盘异常: {str(e)}")
    
    # 步骤3：经验提取
    log_step(3, "经验提取")
    try:
        result = extract_and_save_lessons.fn(bet_slip_id=bet_slip_id)
        results['lessons'] = result
        if result.get('success'):
            print(f"  ✅ 经验提取完成：提取{result['lessons_extracted']}条经验教训")
            for lesson in result.get('lessons', []):
                print(f"    - [{lesson['category']}] {lesson['content']}")
        else:
            print(f"  ❌ 经验提取失败：{result.get('error', '未知错误')}")
            errors.append(f"经验提取失败: {result.get('error')}")
    except Exception as e:
        print(f"  ❌ 经验提取异常：{str(e)}")
        errors.append(f"经验提取异常: {str(e)}")
    
    # 步骤4：账户更新（奖金入账）
    if not skip_account:
        log_step(4, "账户更新（奖金入账）")
        try:
            settlement = results.get('settlement', {})
            if settlement.get('success') and settlement.get('total_payout', 0) > 0:
                payout_amount = settlement['total_payout']
                hit_count = settlement.get('hit_count', 0)
                result = add_payout.fn(
                    amount=payout_amount,
                    bet_slip_id=bet_slip_id,
                    is_hit=(hit_count > 0),
                    description=f'赛后结算入账，命中{hit_count}注'
                )
                results['account_update'] = result
                if result.get('success'):
                    print(f"  ✅ 账户更新完成：入账{payout_amount}元，余额{result['after_balance']}元")
                else:
                    print(f"  ❌ 账户更新失败：{result.get('error', '未知错误')}")
                    errors.append(f"账户更新失败: {result.get('error')}")
            else:
                print(f"  ⏭️  跳过账户更新：无奖金入账或结算失败")
        except Exception as e:
            print(f"  ❌ 账户更新异常：{str(e)}")
            errors.append(f"账户更新异常: {str(e)}")
    
    # 步骤5：经验回流（预加载记忆）
    log_step(5, "经验回流（预加载记忆）")
    try:
        result = preload_memory.fn(date=datetime.now().strftime('%Y-%m-%d'))
        results['memory_preload'] = result
        if result.get('success') or result.get('data'):
            print(f"  ✅ 经验回流完成：经验已加载到下一次分析")
        else:
            print(f"  ⚠️  经验回流部分完成：{result.get('message', '未知状态')}")
    except Exception as e:
        print(f"  ❌ 经验回流异常：{str(e)}")
        errors.append(f"经验回流异常: {str(e)}")
    
    # 总结
    log_step(6, "闭环完成总结")
    print(f"  投注单ID: {bet_slip_id}")
    print(f"  成功步骤: {len(results) - len(errors)}/{5 if not skip_account else 4}")
    if errors:
        print(f"  错误数: {len(errors)}")
        for err in errors:
            print(f"    - {err}")
    else:
        print(f"  错误数: 0 ✅")
    print(f"\n  完整闭环流程已执行完毕！")
    
    return {
        'bet_slip_id': bet_slip_id,
        'completed_at': datetime.now().isoformat(),
        'results': results,
        'errors': errors,
        'success': len(errors) == 0,
    }


def main():
    parser = argparse.ArgumentParser(description='赛后一键闭环脚本')
    parser.add_argument('--date', help='结算指定日期的所有待结算投注单（YYYY-MM-DD）')
    parser.add_argument('--bet-slip-id', help='结算指定投注单ID')
    parser.add_argument('--match-results', help='赛果JSON文件路径（包含所有比赛的赛果）')
    parser.add_argument('--analysis-notes', default='', help='分析备注')
    parser.add_argument('--skip-account', action='store_true', help='跳过账户更新')
    parser.add_argument('--list-pending', action='store_true', help='只列出待结算投注单，不执行结算')
    args = parser.parse_args()
    
    # 列出待结算投注单
    if args.list_pending:
        pending = get_pending_bet_slips(date=args.date)
        print(f"\n待结算投注单（共{len(pending)}个）:")
        for p in pending:
            print(f"  - {p['bet_slip_id']} ({p['session_date']})，{p['ticket_count']}注，投入{p['total_stake']}元")
        return
    
    # 确定要结算的投注单
    if args.bet_slip_id:
        bet_slip_ids = [args.bet_slip_id]
    elif args.date:
        pending = get_pending_bet_slips(date=args.date)
        bet_slip_ids = [p['bet_slip_id'] for p in pending]
        if not bet_slip_ids:
            print(f"❌ {args.date}没有待结算的投注单")
            return
    else:
        print("❌ 请指定 --date 或 --bet-slip-id")
        parser.print_help()
        return
    
    # 加载赛果
    match_results = {}
    if args.match_results:
        with open(args.match_results, 'r', encoding='utf-8') as f:
            match_results = json.load(f)
        print(f"✅ 已加载赛果文件：{args.match_results}")
    else:
        print("⚠️  未提供赛果文件，将使用空赛果（实际使用时请通过--match-results提供赛果）")
        print("   赛果格式：{\"match_id\": {\"home_goals\": 2, \"away_goals\": 1, \"result\": \"主胜\"}}")
    
    # 执行闭环
    all_results = []
    for bet_slip_id in bet_slip_ids:
        print(f"\n\n{'#'*60}")
        print(f"# 处理投注单：{bet_slip_id}")
        print(f"{'#'*60}")
        
        result = run_full_settlement(
            bet_slip_id=bet_slip_id,
            match_results=match_results,
            analysis_notes=args.analysis_notes,
            skip_account=args.skip_account,
        )
        all_results.append(result)
    
    # 最终总结
    print(f"\n\n{'='*60}")
    print(f"全部处理完成！共处理{len(all_results)}个投注单")
    success_count = sum(1 for r in all_results if r['success'])
    print(f"成功：{success_count}/{len(all_results)}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
