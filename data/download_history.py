#!/usr/bin/env python3
"""
竞彩足球历史数据下载脚本
从football-data.co.uk下载36个联赛的历史比赛数据
数据来源：https://www.football-data.co.uk/
"""
import os
import json
import urllib.request
import csv
import io
from datetime import datetime

# 36个联赛代码映射（football-data.co.uk的代码）
LEAGUE_MAP = {
    # 英格兰
    'E0': ('英超', 'https://www.football-data.co.uk/mmz4281/{season}/E0.csv'),
    'E1': ('英冠', 'https://www.football-data.co.uk/mmz4281/{season}/E1.csv'),
    'E2': ('英甲', 'https://www.football-data.co.uk/mmz4281/{season}/E2.csv'),
    'E3': ('英乙', 'https://www.football-data.co.uk/mmz4281/{season}/E3.csv'),
    'EC': ('英非联', 'https://www.football-data.co.uk/mmz4281/{season}/EC.csv'),
    # 德国
    'D1': ('德甲', 'https://www.football-data.co.uk/mmz4281/{season}/D1.csv'),
    'D2': ('德乙', 'https://www.football-data.co.uk/mmz4281/{season}/D2.csv'),
    # 西班牙
    'SP1': ('西甲', 'https://www.football-data.co.uk/mmz4281/{season}/SP1.csv'),
    'SP2': ('西乙', 'https://www.football-data.co.uk/mmz4281/{season}/SP2.csv'),
    # 意大利
    'I1': ('意甲', 'https://www.football-data.co.uk/mmz4281/{season}/I1.csv'),
    'I2': ('意乙', 'https://www.football-data.co.uk/mmz4281/{season}/I2.csv'),
    # 法国
    'F1': ('法甲', 'https://www.football-data.co.uk/mmz4281/{season}/F1.csv'),
    'F2': ('法乙', 'https://www.football-data.co.uk/mmz4281/{season}/F2.csv'),
    # 荷兰
    'N1': ('荷甲', 'https://www.football-data.co.uk/mmz4281/{season}/N1.csv'),
    # 比利时
    'B1': ('比甲', 'https://www.football-data.co.uk/mmz4281/{season}/B1.csv'),
    # 葡萄牙
    'P1': ('葡超', 'https://www.football-data.co.uk/mmz4281/{season}/P1.csv'),
    # 苏格兰
    'SC0': ('苏超', 'https://www.football-data.co.uk/mmz4281/{season}/SC0.csv'),
    'SC1': ('苏冠', 'https://www.football-data.co.uk/mmz4281/{season}/SC1.csv'),
    'SC2': ('苏甲', 'https://www.football-data.co.uk/mmz4281/{season}/SC2.csv'),
    'SC3': ('苏乙', 'https://www.football-data.co.uk/mmz4281/{season}/SC3.csv'),
    # 土耳其
    'T1': ('土超', 'https://www.football-data.co.uk/mmz4281/{season}/T1.csv'),
    # 希腊
    'G1': ('希超', 'https://www.football-data.co.uk/mmz4281/{season}/G1.csv'),
    # 其他
    'ARG': ('阿甲', None),  # football-data.co.uk不提供
    'AUT': ('奥甲', None),
    'BRA': ('巴甲', None),
    'CHN': ('中超', None),
    'FIN': ('芬超', None),
    'IRL': ('爱超', None),
    'JPN': ('日职', None),
    'MEX': ('墨超', None),
    'NOR': ('挪超', None),
    'PL': ('波超', None),
    'ROU': ('罗甲', None),
    'RUS': ('俄超', None),
    'SWE': ('瑞超', None),
    'USA': ('美职', None),
}

HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'history')

def get_seasons(n_years=5):
    """获取最近n个赛季的代码（如2526, 2425）"""
    current_year = datetime.now().year
    seasons = []
    for i in range(n_years):
        start = current_year - i - 1
        end = current_year - i
        season_code = f"{str(start)[-2:]}{str(end)[-2:]}"
        seasons.append(season_code)
    return seasons

def download_league(league_code, seasons=None):
    """下载单个联赛的历史数据"""
    if seasons is None:
        seasons = get_seasons(5)
    
    league_name, url_template = LEAGUE_MAP.get(league_code, (None, None))
    if url_template is None:
        print(f"  ⚠️  {league_code} ({league_name})：football-data.co.uk不提供，跳过")
        return None
    
    all_matches = []
    
    for season in seasons:
        url = url_template.format(season=season)
        try:
            print(f"  下载 {league_code} {season}赛季...", end=" ")
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode('utf-8', errors='ignore')
            
            # 解析CSV
            reader = csv.DictReader(io.StringIO(content))
            count = 0
            for row in reader:
                try:
                    match = {
                        'date': row.get('Date', ''),
                        'home': row.get('HomeTeam', ''),
                        'away': row.get('AwayTeam', ''),
                        'home_goals': int(row.get('FTHG', 0) or 0),
                        'away_goals': int(row.get('FTAG', 0) or 0),
                        'result': row.get('FTR', ''),
                        'league': league_code,
                        'season': season,
                        # 赔率
                        'home_odds': float(row.get('B365H', 0) or 0),
                        'draw_odds': float(row.get('B365D', 0) or 0),
                        'away_odds': float(row.get('B365A', 0) or 0),
                        # 半场
                        'hthg': int(row.get('HTHG', 0) or 0),
                        'htag': int(row.get('HTAG', 0) or 0),
                        'htr': row.get('HTR', ''),
                        # 统计
                        'hs': int(row.get('HS', 0) or 0),  # 主队射门
                        'as': int(row.get('AS', 0) or 0),  # 客队射门
                        'hst': int(row.get('HST', 0) or 0),  # 主队射正
                        'ast': int(row.get('AST', 0) or 0),  # 客队射正
                        'hc': int(row.get('HC', 0) or 0),  # 主队角球
                        'ac': int(row.get('AC', 0) or 0),  # 客队角球
                        'hy': int(row.get('HY', 0) or 0),  # 主队黄牌
                        'ay': int(row.get('AY', 0) or 0),  # 客队黄牌
                        'hr': int(row.get('HR', 0) or 0),  # 主队红牌
                        'ar': int(row.get('AR', 0) or 0),  # 客队红牌
                        # 裁判
                        'referee': row.get('Referee', ''),
                    }
                    all_matches.append(match)
                    count += 1
                except (ValueError, KeyError):
                    continue
            print(f"✅ {count}场")
        except Exception as e:
            print(f"❌ 失败: {e}")
            continue
    
    if all_matches:
        # 保存
        os.makedirs(HISTORY_DIR, exist_ok=True)
        output_file = os.path.join(HISTORY_DIR, f'{league_code}_history.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_matches, f, ensure_ascii=False, indent=2)
        print(f"  ✅ {league_code} ({league_name})：共{len(all_matches)}场，已保存到{output_file}")
        return all_matches
    
    return None

def main():
    print("=" * 60)
    print("竞彩足球历史数据下载脚本")
    print("=" * 60)
    print()
    
    # 创建历史数据目录
    os.makedirs(HISTORY_DIR, exist_ok=True)
    
    # 下载所有可用联赛
    available_leagues = [code for code, (name, url) in LEAGUE_MAP.items() if url is not None]
    print(f"可下载联赛：{len(available_leagues)}个")
    print(f"下载赛季：最近5个赛季")
    print()
    
    total_matches = 0
    success_count = 0
    
    for league_code in available_leagues:
        matches = download_league(league_code)
        if matches:
            total_matches += len(matches)
            success_count += 1
    
    print()
    print("=" * 60)
    print("下载完成")
    print("=" * 60)
    print(f"成功下载：{success_count}/{len(available_leagues)}个联赛")
    print(f"总比赛数：{total_matches}场")
    print(f"保存目录：{HISTORY_DIR}")
    print()
    print("注意：部分联赛（巴甲/阿甲/中超/日职等）football-data.co.uk不提供，")
    print("需要从其他数据源获取或手动导入。")
    print("=" * 60)

if __name__ == '__main__':
    main()
