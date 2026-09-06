#!/usr/bin/env python3
"""
批量8大资讯采集器
为每场比赛生成搜索关键词，供LLM用general_search获取官方8大资讯的替代内容
8大资讯：赛事特征/历史交锋/近期战绩/伤停/积分榜/未来赛程/球员数据/赔率变动
用法：
  python3 batch_news_collector.py --matches matches.json --output news_keywords.json
"""
import argparse
import json

NEWS_CATEGORIES = [
    ("赛事特征", "联赛特点 主客场 风格"),
    ("历史交锋", "历史交锋 对战记录"),
    ("近期战绩", "近期战绩 近5场 状态"),
    ("伤停", "伤停 伤病 缺阵 首发"),
    ("积分榜", "积分榜 排名 积分"),
    ("未来赛程", "未来赛程 赛程密集 疲劳"),
    ("球员数据", "球员数据 射手榜 助攻"),
    ("赔率变动", "赔率变动 盘口变化 资金流向"),
]

def generate_keywords(match):
    """为单场比赛生成8大资讯搜索关键词"""
    home = match.get('home', '')
    away = match.get('away', '')
    league = match.get('league', '')
    match_id = match.get('matchNumStr', '')
    
    keywords = {}
    for category, suffix in NEWS_CATEGORIES:
        keywords[category] = f"{league} {home} {away} {suffix}"
    
    # 合并搜索（减少搜索次数）
    combined = [
        f"{home} {away} 伤停 首发 阵容 预测",
        f"{home} {away} 历史交锋 近期战绩 积分榜",
        f"{league} {home} {away} 赔率变动 盘口 分析",
    ]
    
    return {
        'match_id': match_id,
        'home': home, 'away': away, 'league': league,
        'detailed_keywords': keywords,  # 8个详细关键词
        'combined_keywords': combined,   # 3个合并关键词（推荐使用）
        'status': 'pending',
    }

def main():
    parser = argparse.ArgumentParser(description='批量8大资讯采集器')
    parser.add_argument('--matches', required=True, help='比赛列表JSON文件')
    parser.add_argument('--output', default='news_keywords.json', help='输出文件')
    args = parser.parse_args()
    
    with open(args.matches, 'r', encoding='utf-8') as f:
        matches = json.load(f)
    
    results = {}
    for m in matches:
        kw = generate_keywords(m)
        results[kw['match_id']] = kw
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已为{len(matches)}场比赛生成8大资讯搜索关键词")
    print(f"   保存到: {args.output}")
    print(f"\n使用方法：")
    print(f"  对每场比赛用general_search搜索combined_keywords中的3个关键词")
    print(f"  然后用parse_news_response解析搜索结果")

if __name__ == '__main__':
    main()
