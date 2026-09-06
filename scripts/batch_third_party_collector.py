#!/usr/bin/env python3
"""
批量第三方数据采集器
一次性获取多场比赛的第三方赔率（欧指/亚盘/大小球）和比赛资讯
用法：
  python3 batch_third_party_collector.py --matches matches.json --output third_party.json
"""
import argparse
import json
import re
import sys
import time
from urllib.parse import quote

def extract_odds_from_text(text, home, away):
    """从搜索结果文本中提取第三方赔率"""
    result = {'eu_odds': {}, 'ah_odds': {}, 'ou_odds': {}, 'news': '', 'confidence': 0}
    
    # 提取欧指（常见格式：主胜X.XX 平X.XX 客胜X.XX）
    eu_patterns = [
        r'主胜\s*(\d+\.?\d*).*?平\s*(\d+\.?\d*).*?客胜\s*(\d+\.?\d*)',
        r'(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+).*?欧赔',
        r'欧赔.*?(\d+\.\d+).*?(\d+\.\d+).*?(\d+\.\d+)',
    ]
    for pat in eu_patterns:
        m = re.search(pat, text)
        if m:
            result['eu_odds'] = {'home': float(m.group(1)), 'draw': float(m.group(2)), 'away': float(m.group(3))}
            result['confidence'] += 1
            break
    
    # 提取亚盘
    ah_patterns = [
        r'让球\s*([+-]?\d+\.?\d*).*?主水\s*(\d+\.?\d*).*?客水\s*(\d+\.?\d*)',
        r'亚盘.*?([+-]?\d+\.?\d*).*?(\d+\.\d+).*?(\d+\.\d+)',
        r'([+-]?\d+\.?\d*)\s*球.*?(\d+\.\d+).*?(\d+\.\d+)',
    ]
    for pat in ah_patterns:
        m = re.search(pat, text)
        if m:
            result['ah_odds'] = {'handicap': float(m.group(1)), 'home': float(m.group(2)), 'away': float(m.group(3))}
            result['confidence'] += 1
            break
    
    # 提取大小球
    ou_patterns = [
        r'大小球\s*(\d+\.?\d*).*?大球\s*(\d+\.?\d*).*?小球\s*(\d+\.?\d*)',
        r'(\d+\.?\d*)\s*球.*?大\s*(\d+\.\d+).*?小\s*(\d+\.\d+)',
    ]
    for pat in ou_patterns:
        m = re.search(pat, text)
        if m:
            result['ou_odds'] = {'line': float(m.group(1)), 'over': float(m.group(2)), 'under': float(m.group(3))}
            result['confidence'] += 1
            break
    
    # 提取资讯关键词
    news_keywords = ['伤停', '首发', '阵容', '状态', '交锋', '战意', '天气', '裁判']
    for kw in news_keywords:
        if kw in text:
            # 提取关键词附近的文本
            idx = text.find(kw)
            snippet = text[max(0,idx-20):idx+100]
            result['news'] += f"[{kw}]{snippet}... "
    if result['news']:
        result['confidence'] += 1
    
    return result

def collect_batch(matches, output_file=None):
    """批量采集第三方数据"""
    results = {}
    print(f"开始批量采集{len(matches)}场比赛的第三方数据...")
    print("提示：请在LLM中对每场比赛执行general_search，搜索关键词：")
    print("  '主队 客队 欧赔 亚盘 大小球 伤停 预测'")
    print("然后将搜索结果文本传入parse_third_party_text工具解析")
    print()
    
    for i, m in enumerate(matches):
        match_id = m.get('matchNumStr', m.get('match_id', f'match_{i}'))
        home = m.get('home', '')
        away = m.get('away', '')
        league = m.get('league', '')
        
        # 生成搜索关键词（供LLM用general_search搜索）
        search_keywords = [
            f"{home} {away} 欧赔 亚盘 大小球",
            f"{home} {away} 伤停 首发 预测",
            f"{league} {home} {away} 赛前分析",
        ]
        
        results[match_id] = {
            'home': home, 'away': away, 'league': league,
            'search_keywords': search_keywords,
            'status': 'pending_llm_search',
            'note': '请用general_search搜索search_keywords，然后用parse_third_party_text解析结果'
        }
        print(f"  [{i+1}/{len(matches)}] {match_id} {home}vs{away}")
        print(f"    搜索关键词: {search_keywords[0]}")
    
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 采集任务已保存到 {output_file}")
    
    return results

def main():
    parser = argparse.ArgumentParser(description='批量第三方数据采集器')
    parser.add_argument('--matches', required=True, help='比赛列表JSON文件')
    parser.add_argument('--output', default='third_party.json', help='输出文件')
    args = parser.parse_args()
    
    with open(args.matches, 'r', encoding='utf-8') as f:
        matches = json.load(f)
    
    collect_batch(matches, args.output)

if __name__ == '__main__':
    main()
