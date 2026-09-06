#!/usr/bin/env python3
"""
赔率快照自动采集脚本
用于定时任务触发，在开售时/午间/临场自动采集全部比赛的赔率快照。

用法：
  python3 odds_snapshot_collector.py --label 初盘    # 采集初盘快照
  python3 odds_snapshot_collector.py --label 午间    # 采集午间快照
  python3 odds_snapshot_collector.py --label 临场    # 采集临场快照
  python3 odds_snapshot_collector.py --compare       # 对比全部比赛的赔率走势

注意：服务器端urllib直连竞彩API返回403，本脚本仅生成采集任务清单，
实际采集由LLM通过web.fetch+parse_odds_response完成。
"""
import argparse
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PLUGIN_DIR, 'data')

# 竞彩官方API
MATCH_LIST_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchListV1.qry?clientCode=3001"
FIXED_BONUS_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getFixedBonusV1.qry?clientCode=3001&matchId={mid}"


def get_today_matches():
    """获取今天在售比赛的matchId列表（从本地缓存或生成采集任务）"""
    # 尝试从本地缓存读取
    cache_file = os.path.join(DATA_DIR, 'matches_today.json')
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        matches = data.get('matches', data) if isinstance(data, dict) else data
        return [m.get('matchId', m.get('match_id', '')) for m in matches if m.get('matchId') or m.get('match_id')]
    
    # 无缓存时，返回需要LLM先采集赛程的提示
    return None


def collect_snapshot(label):
    """生成赔率快照采集任务"""
    print("=" * 60)
    print(f"赔率快照采集任务 - {label}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    match_ids = get_today_matches()
    
    if not match_ids:
        print("\n⚠️  未找到本地比赛缓存")
        print("请先执行以下步骤：")
        print("  1. 调用data-collector的get_match_list获取赛程")
        print("  2. 调用collect_all_matches采集全部比赛数据")
        print("  3. 然后再运行本脚本采集赔率快照")
        print("\n或者直接调用MCP工具：")
        print(f'  batch_record_odds_snapshot(match_ids="全部比赛ID", label="{label}")')
        return
    
    print(f"\n找到{len(match_ids)}场比赛")
    print(f"\n采集任务：")
    print(f'  batch_record_odds_snapshot(match_ids="{",".join(match_ids)}", label="{label}")')
    print(f"\n直连失败时，请用web.fetch获取以下URL：")
    for mid in match_ids[:5]:
        print(f"  {FIXED_BONUS_URL.format(mid=mid)}")
    if len(match_ids) > 5:
        print(f"  ... 共{len(match_ids)}场")
    
    print(f"\n采集完成后，可调用compare_odds_movement对比赔率走势")
    print(f"或调用fund_flow_analysis做资金流分析")
    print("=" * 60)


def compare_all():
    """对比全部比赛的赔率走势"""
    print("=" * 60)
    print("全部比赛赔率走势对比")
    print("=" * 60)
    
    snapshot_base = os.path.join(DATA_DIR, 'odds_snapshots')
    if not os.path.exists(snapshot_base):
        print("❌ 无赔率快照数据，请先采集初盘和临场快照")
        return
    
    matches = [d for d in os.listdir(snapshot_base) if os.path.isdir(os.path.join(snapshot_base, d))]
    print(f"\n找到{len(matches)}场比赛的快照数据")
    
    for mid in sorted(matches):
        match_dir = os.path.join(snapshot_base, mid)
        snapshots = [f for f in os.listdir(match_dir) if f.startswith('snapshot_')]
        if len(snapshots) >= 2:
            print(f"  ✅ 比赛{mid}: {len(snapshots)}个快照，可对比")
        else:
            print(f"  ⚠️  比赛{mid}: {len(snapshots)}个快照，需至少2个")
    
    print(f"\n对比单场：compare_odds_movement(match_id='{matches[0] if matches else ''}')")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='赔率快照自动采集')
    parser.add_argument('--label', type=str, default='', help='快照标签（初盘/午间/临场）')
    parser.add_argument('--compare', action='store_true', help='对比全部比赛赔率走势')
    args = parser.parse_args()
    
    if args.compare:
        compare_all()
    else:
        label = args.label or datetime.now().strftime('%H:%M')
        collect_snapshot(label)


if __name__ == '__main__':
    main()
