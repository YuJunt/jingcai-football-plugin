#!/usr/bin/env python3
"""
模拟数据生成器
为端到端测试和实战验证生成逼真的模拟数据

用法：
  python3 mock_data_generator.py --matches 10 --output mock_matches.json
  python3 mock_data_generator.py --matches 27 --realistic --output realistic_matches.json
"""
import argparse
import json
import os
import random
from datetime import datetime, timedelta


# 真实联赛和球队数据
LEAGUES = [
    {'code': 'E0', 'name': '英格兰超级联赛', 'teams': ['利物浦', '曼城', '阿森纳', '切尔西', '曼联', '热刺', '纽卡斯尔联', '阿斯顿维拉', '布莱顿', '西汉姆联']},
    {'code': 'D1', 'name': '德国甲级联赛', 'teams': ['拜仁慕尼黑', '多特蒙德', '莱比锡红牛', '勒沃库森', '门兴格拉德巴赫', '法兰克福', '沃尔夫斯堡', '弗赖堡']},
    {'code': 'SP1', 'name': '西班牙甲级联赛', 'teams': ['皇家马德里', '巴塞罗那', '马德里竞技', '塞维利亚', '皇家社会', '毕尔巴鄂竞技', '比利亚雷亚尔', '贝蒂斯']},
    {'code': 'I1', 'name': '意大利甲级联赛', 'teams': ['国际米兰', 'AC米兰', '尤文图斯', '那不勒斯', '罗马', '拉齐奥', '亚特兰大', '佛罗伦萨']},
    {'code': 'F1', 'name': '法国甲级联赛', 'teams': ['巴黎圣日耳曼', '马赛', '摩纳哥', '里昂', '里尔', '雷恩', '尼斯', '南特']},
]

# 玩法选项
SPF_OPTIONS = ['主胜', '平局', '客胜']
RQ_OPTIONS = ['让胜', '让平', '让负']
TTG_OPTIONS = ['0球', '1球', '2球', '3球', '4球', '5球', '6球', '7+球']
SCORE_OPTIONS = ['1:0', '2:0', '2:1', '3:0', '3:1', '3:2', '0:0', '1:1', '2:2', '0:1', '0:2', '1:2']
BQC_OPTIONS = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']


def generate_odds(option_count, favorite_index=0, min_odds=1.2, max_odds=8.0):
    """生成逼真的赔率"""
    odds = []
    for i in range(option_count):
        if i == favorite_index:
            # 热门选项赔率较低
            odd = round(random.uniform(min_odds, 2.5), 2)
        else:
            # 冷门选项赔率较高
            odd = round(random.uniform(2.5, max_odds), 2)
        odds.append(odd)
    return odds


def generate_match(match_id, league_info, realistic=True):
    """生成单场比赛的模拟数据"""
    home, away = random.sample(league_info['teams'], 2)

    # 生成胜平负赔率
    spf_odds = generate_odds(3, favorite_index=0)

    # 生成让球数（通常-1到+1）
    handicap = random.choice([-1, 0, 0, 0, 1])

    # 生成让球胜平负赔率
    rq_odds = generate_odds(3, favorite_index=0)

    # 生成总进球赔率
    ttg_odds = generate_odds(8, favorite_index=2)  # 2球最常见

    # 生成比分赔率（高赔）
    score_odds = [round(random.uniform(5.0, 25.0), 2) for _ in range(12)]

    # 生成半全场赔率
    bqc_odds = generate_odds(9, favorite_index=0)

    # 生成比赛资讯
    info = {
        '赛事特征': f"{league_info['name']}，{home}主场作战",
        '历史交锋': f"近10次交锋{home}{random.randint(3,6)}胜{random.randint(2,4)}平{random.randint(1,3)}负",
        '近期战绩': f"{home}近5场{random.randint(2,4)}胜{random.randint(0,2)}平{random.randint(0,2)}负，{away}近5场{random.randint(1,3)}胜{random.randint(1,3)}平{random.randint(1,3)}负",
        '伤停': f"{home}有{random.randint(0,3)}名球员伤停，{away}有{random.randint(0,3)}名球员伤停",
        '积分榜': f"{home}排名第{random.randint(1,10)}，{away}排名第{random.randint(1,10)}",
        '未来赛程': f"{home}下周中有杯赛，{away}赛程宽松",
        '球员数据': f"{home}头号射手本赛季{random.randint(5,15)}球，{away}头号射手本赛季{random.randint(3,12)}球",
        '赔率变动': f"主胜赔率从{round(spf_odds[0]+0.1, 2)}下降到{spf_odds[0]}，资金流向主胜",
    }

    # 第三方数据
    third_party = {
        'eu_odds': {'home': round(spf_odds[0] * random.uniform(0.95, 1.05), 2),
                     'draw': round(spf_odds[1] * random.uniform(0.95, 1.05), 2),
                     'away': round(spf_odds[2] * random.uniform(0.95, 1.05), 2)},
        'ah_odds': {'line': handicap, 'home': round(random.uniform(0.85, 1.05), 2), 'away': round(random.uniform(0.85, 1.05), 2)},
        'ou_odds': {'line': round(random.uniform(2.0, 3.0), 1), 'over': round(random.uniform(0.85, 1.05), 2), 'under': round(random.uniform(0.85, 1.05), 2)},
        'news': [f"{home}主帅赛前表示信心十足", f"{away}主力前锋状态火热"],
    }

    match = {
        'match_id': match_id,
        'mid': f"2026{random.randint(100000, 999999)}",
        'league': league_info['name'],
        'league_code': league_info['code'],
        'home': home,
        'away': away,
        'match_time': (datetime.now() + timedelta(days=random.randint(0, 2), hours=random.randint(18, 22))).strftime('%Y-%m-%d %H:%M'),
        'handicap': str(handicap),
        'odds': {
            '胜平负': {'odds': spf_odds, 'option_names': SPF_OPTIONS},
            '让球胜平负': {'odds': rq_odds, 'option_names': RQ_OPTIONS},
            '总进球': {'odds': ttg_odds, 'option_names': TTG_OPTIONS},
            '比分': {'odds': score_odds, 'option_names': SCORE_OPTIONS},
            '半全场': {'odds': bqc_odds, 'option_names': BQC_OPTIONS},
        },
        'info': info,
        'third_party': third_party,
    }

    return match


def generate_matches(count=10, realistic=True, output_file=None):
    """生成多场比赛的模拟数据"""
    matches = []
    for i in range(count):
        match_id = f"{i+1:03d}"
        league_info = random.choice(LEAGUES)
        match = generate_match(match_id, league_info, realistic)
        matches.append(match)

    result = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'generated_at': datetime.now().isoformat(),
        'total_matches': len(matches),
        'matches': matches,
        'note': '模拟数据，仅用于测试和验证'
    }

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ 已生成 {len(matches)} 场模拟比赛，保存到 {output_file}")

    return result


def main():
    parser = argparse.ArgumentParser(description='模拟数据生成器')
    parser.add_argument('--matches', type=int, default=10, help='生成比赛数量（默认10）')
    parser.add_argument('--output', type=str, default='mock_matches.json', help='输出文件路径')
    parser.add_argument('--realistic', action='store_true', help='生成更逼真的数据')
    args = parser.parse_args()

    generate_matches(args.matches, args.realistic, args.output)


if __name__ == '__main__':
    main()
