#!/usr/bin/env python3
"""
历史数据定期更新脚本
支持从football-data.co.uk下载最新数据，增量更新，数据校验

用法：
  python3 update_history.py --update              # 更新所有联赛数据
  python3 update_history.py --league E0 --update  # 更新指定联赛
  python3 update_history.py --status              # 查看数据状态
  python3 update_history.py --validate            # 校验数据完整性
  python3 update_history.py --schedule daily      # 设置每日定时更新
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta

# 联赛代码映射
LEAGUE_MAP = {
    'E0': '英超', 'E1': '英冠', 'E2': '英甲', 'E3': '英乙',
    'D1': '德甲', 'D2': '德乙',
    'SP1': '西甲', 'SP2': '西乙',
    'I1': '意甲', 'I2': '意乙',
    'F1': '法甲', 'F2': '法乙',
    'N': '荷甲', 'B1': '比甲', 'P1': '葡超', 'SC0': '苏超',
    'T1': '土超', 'RUS': '俄超',
}

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_DIR = os.path.join(DATA_DIR, 'history')
os.makedirs(HISTORY_DIR, exist_ok=True)


def download_league_data(league_code, season=None):
    """下载指定联赛的历史数据"""
    if season is None:
        # 默认下载最近5个赛季
        current_year = datetime.now().year
        seasons = []
        for i in range(5):
            year = current_year - i
            season_str = f"{str(year)[-2:]}{str(year+1)[-2:]}"
            seasons.append(season_str)
    else:
        seasons = [season]

    all_matches = []
    for season_str in seasons:
        url = f"https://www.football-data.co.uk/mmz4281/{season_str}/{league_code}.csv"
        try:
            print(f"  下载 {league_code} {season_str}...", end=" ")
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode('utf-8', errors='replace')
                matches = parse_csv_data(content, league_code)
                all_matches.extend(matches)
                print(f"✅ {len(matches)}场")
        except Exception as e:
            print(f"❌ {str(e)[:50]}")

    return all_matches


def parse_csv_data(content, league_code):
    """解析CSV格式的历史数据"""
    import csv
    import io

    matches = []
    reader = csv.DictReader(io.StringIO(content))

    for row in reader:
        try:
            match = {
                'league': league_code,
                'league_name': LEAGUE_MAP.get(league_code, league_code),
                'date': row.get('Date', ''),
                'home': row.get('HomeTeam', ''),
                'away': row.get('AwayTeam', ''),
                'home_goals': int(row.get('FTHG', 0) or 0),
                'away_goals': int(row.get('FTAG', 0) or 0),
                'result': row.get('FTR', ''),
                'half_time_home': int(row.get('HTHG', 0) or 0),
                'half_time_away': int(row.get('HTAG', 0) or 0),
                'half_time_result': row.get('HTR', ''),
                # 赔率数据
                'home_odds': float(row.get('B365H', 0) or 0),
                'draw_odds': float(row.get('B365D', 0) or 0),
                'away_odds': float(row.get('B365A', 0) or 0),
                # 亚盘和大小球
                'ah_line': float(row.get('AHh', 0) or 0),
                'ou_line': float(row.get('Avg>2.5', 0) or 0),
                # 射门和角球
                'home_shots': int(row.get('HS', 0) or 0),
                'away_shots': int(row.get('AS', 0) or 0),
                'home_corners': int(row.get('HC', 0) or 0),
                'away_corners': int(row.get('AC', 0) or 0),
                # 红黄牌
                'home_yellow': int(row.get('HY', 0) or 0),
                'away_yellow': int(row.get('AY', 0) or 0),
                'home_red': int(row.get('HR', 0) or 0),
                'away_red': int(row.get('AR', 0) or 0),
            }
            matches.append(match)
        except Exception:
            continue

    return matches


def save_league_data(league_code, matches):
    """保存联赛数据"""
    filepath = os.path.join(HISTORY_DIR, f'{league_code}_history.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)
    return filepath


def load_league_data(league_code):
    """加载联赛数据"""
    filepath = os.path.join(HISTORY_DIR, f'{league_code}_history.json')
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def incremental_update(league_code):
    """增量更新联赛数据"""
    print(f"\n增量更新 {league_code} ({LEAGUE_MAP.get(league_code, league_code)})...")

    # 加载现有数据
    existing_matches = load_league_data(league_code)
    existing_dates = set(m.get('date', '') for m in existing_matches)

    # 下载最新数据
    new_matches = download_league_data(league_code)

    # 去重合并
    merged = list(existing_matches)
    added = 0
    for match in new_matches:
        if match.get('date', '') not in existing_dates:
            merged.append(match)
            added += 1

    # 保存
    save_league_data(league_code, merged)

    print(f"  现有: {len(existing_matches)}场, 新增: {added}场, 总计: {len(merged)}场")
    return {'league': league_code, 'existing': len(existing_matches), 'added': added, 'total': len(merged)}


def get_data_status():
    """查看数据状态"""
    print("\n=== 历史数据状态 ===")
    total_matches = 0
    leagues = []

    for league_code in LEAGUE_MAP:
        matches = load_league_data(league_code)
        if matches:
            total_matches += len(matches)
            # 获取最新日期
            dates = [m.get('date', '') for m in matches if m.get('date')]
            latest = max(dates) if dates else 'N/A'
            leagues.append({
                'code': league_code,
                'name': LEAGUE_MAP[league_code],
                'matches': len(matches),
                'latest_date': latest,
            })

    print(f"总联赛数: {len(leagues)}")
    print(f"总比赛数: {total_matches}")
    print()
    for league in sorted(leagues, key=lambda x: x['matches'], reverse=True):
        print(f"  {league['code']:4s} {league['name']:6s}: {league['matches']:5d}场, 最新: {league['latest_date']}")

    return {'total_leagues': len(leagues), 'total_matches': total_matches, 'leagues': leagues}


def validate_data():
    """校验数据完整性"""
    print("\n=== 数据完整性校验 ===")
    issues = []

    for league_code in LEAGUE_MAP:
        matches = load_league_data(league_code)
        if not matches:
            continue

        # 检查必填字段
        required_fields = ['date', 'home', 'away', 'home_goals', 'away_goals', 'result']
        missing_count = 0
        for match in matches:
            for field in required_fields:
                if field not in match or match[field] in [None, '', '?']:
                    missing_count += 1
                    break

        if missing_count > 0:
            issues.append(f"{league_code}: {missing_count}场比赛缺少必填字段")

        # 检查日期格式
        invalid_dates = 0
        for match in matches:
            date = match.get('date', '')
            if date and '/' not in date and '-' not in date:
                invalid_dates += 1

        if invalid_dates > 0:
            issues.append(f"{league_code}: {invalid_dates}场比赛日期格式异常")

    if issues:
        print(f"发现 {len(issues)} 个问题:")
        for issue in issues[:10]:
            print(f"  ⚠️  {issue}")
    else:
        print("✅ 数据完整性校验通过，未发现问题")

    return {'issues': issues, 'passed': len(issues) == 0}


def main():
    parser = argparse.ArgumentParser(description='历史数据定期更新脚本')
    parser.add_argument('--update', action='store_true', help='更新所有联赛数据')
    parser.add_argument('--league', type=str, help='更新指定联赛（如E0）')
    parser.add_argument('--status', action='store_true', help='查看数据状态')
    parser.add_argument('--validate', action='store_true', help='校验数据完整性')
    args = parser.parse_args()

    if args.status:
        get_data_status()
    elif args.validate:
        validate_data()
    elif args.update:
        if args.league:
            incremental_update(args.league)
        else:
            print("开始更新所有联赛数据...")
            for league_code in LEAGUE_MAP:
                incremental_update(league_code)
            print("\n✅ 所有联赛数据更新完成")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
