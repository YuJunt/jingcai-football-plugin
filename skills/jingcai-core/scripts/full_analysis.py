#!/usr/bin/env python3
"""
竞彩足球核心协调脚本（full_analysis.py）
自动调用5个玩法技能的分析脚本，整合结果，识别每场比赛的最佳玩法
实现技能间协作：jingcai-core → 5个玩法技能 → 整合结果

用法：
  python3 full_analysis.py --input matches.json
  python3 full_analysis.py --input matches.json --json
  python3 full_analysis.py --match-id 2041310 --home 莫尔德 --away 奥斯陆KFUM --league 挪威超
"""
import argparse
import json
import os
import subprocess
import sys

# 脚本路径: jingcai-football-plugin/skills/jingcai-core/scripts/full_analysis.py
# 4层dirname = jingcai-football-plugin/
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SKILLS_DIR = os.path.join(PLUGIN_ROOT, 'skills')

# 5个玩法技能的分析脚本路径
PLAY_SCRIPTS = {
    '胜平负': os.path.join(SKILLS_DIR, 'jingcai-spf', 'scripts', 'analyze_spf.py'),
    '让球胜平负': os.path.join(SKILLS_DIR, 'jingcai-rangqiu', 'scripts', 'analyze_rangqiu.py'),
    '总进球': os.path.join(SKILLS_DIR, 'jingcai-zongjinqiu', 'scripts', 'analyze_zongjinqiu.py'),
    '比分': os.path.join(SKILLS_DIR, 'jingcai-bifen', 'scripts', 'analyze_bifen.py'),
    '半全场': os.path.join(SKILLS_DIR, 'jingcai-banquanchang', 'scripts', 'analyze_banquanchang.py'),
}

def run_play_analysis(play_name, match_id, home, away, league=''):
    """
    调用单个玩法的分析脚本
    Returns: dict - 该玩法的分析结果
    """
    script_path = PLAY_SCRIPTS.get(play_name)
    if not script_path or not os.path.exists(script_path):
        return {'play': play_name, 'error': '脚本不存在', 'success': False}
    
    try:
        # 输入验证：防止命令注入（虽然使用列表形式已较安全，但仍需验证）
        import re
        def _safe_str(s, max_len=100):
            """安全字符串验证：只允许字母、数字、中文、常见符号，限制长度"""
            if not isinstance(s, str):
                s = str(s)
            # 移除潜在危险字符（只保留安全字符）
            s = re.sub(r'[;<>|&$`\\]', '', s)
            return s[:max_len]
        
        match_id = _safe_str(match_id, 50)
        home = _safe_str(home, 50)
        away = _safe_str(away, 50)
        league = _safe_str(league, 50)
        
        # 验证脚本路径存在且在预期目录内（防止路径遍历）
        if not os.path.exists(script_path):
            return {'play': play_name, 'success': False, 'error': f'脚本不存在: {script_path}'}
        
        # 确保脚本路径在skills目录内（防止任意代码执行）
        script_real_path = os.path.realpath(script_path)
        skills_dir = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
        if not script_real_path.startswith(skills_dir):
            return {'play': play_name, 'success': False, 'error': '脚本路径不在允许的目录内'}
        
        cmd = [
            sys.executable, script_real_path,
            '--match-id', match_id,
            '--home', home,
            '--away', away,
            '--league', league,
            '--json'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=False)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {'play': play_name, 'success': True, 'data': data}
        else:
            return {'play': play_name, 'success': False, 'error': result.stderr[:200]}
    except Exception as e:
        return {'play': play_name, 'success': False, 'error': str(e)}

def analyze_single_match(match_id, home, away, league=''):
    """
    对单场比赛进行全玩法分析
    Returns: dict - 包含5个玩法的分析结果和最佳玩法识别
    """
    result = {
        'match_id': match_id,
        'match': f'{home} vs {away}',
        'league': league,
        'plays': {},
        'best_play': None,
        'top_plays': [],
    }
    
    # 调用5个玩法的分析脚本
    play_evs = []
    for play_name in PLAY_SCRIPTS.keys():
        play_result = run_play_analysis(play_name, match_id, home, away, league)
        result['plays'][play_name] = play_result
        
        if play_result.get('success'):
            data = play_result.get('data', {})
            rec = data.get('recommendation', {})
            ev = rec.get('ev', 0)
            option = rec.get('option', '')
            confidence = rec.get('confidence', '低')
            # 获取玩法适配度和模型置信度（各玩法脚本输出，缺失时用默认值）
            play_fitness = rec.get('play_fitness_score', 0.5)
            model_confidence = rec.get('model_confidence', 0.5)
            odds = rec.get('odds', 0) or 0
            # 赔率合理性：赔率在1.5-8.0之间为合理，过高或过低都扣分
            if odds and 1.5 <= odds <= 8.0:
                odds_reasonableness = 1.0
            elif odds and odds > 0:
                odds_reasonableness = max(0.3, 1.0 - abs(odds - 4.0) / 10.0)
            else:
                odds_reasonableness = 0.5
            
            # EV标准化：将EV映射到0-1范围（-50%以下=0，+50%以上=1）
            ev_normalized = max(0, min(1, (ev + 0.5) / 1.0))
            
            # 多维度综合评分：EV40% + 玩法适配度30% + 模型置信度20% + 赔率合理性10%
            composite_score = (ev_normalized * 0.4 + 
                             play_fitness * 0.3 + 
                             model_confidence * 0.2 + 
                             odds_reasonableness * 0.1)
            
            play_evs.append({
                'play': play_name,
                'option': option,
                'ev': ev,
                'confidence': confidence,
                'play_fitness_score': play_fitness,
                'model_confidence': model_confidence,
                'odds_reasonableness': odds_reasonableness,
                'composite_score': round(composite_score, 4),
            })
    
    # 按综合评分排序（不再只按EV排序），识别最佳玩法和Top3玩法
    play_evs.sort(key=lambda x: x['composite_score'], reverse=True)
    result['top_plays'] = play_evs[:3]
    result['best_play'] = play_evs[0] if play_evs else None
    
    return result

def load_matches(input_file):
    """加载比赛列表"""
    if not os.path.exists(input_file):
        print(f"❌ 比赛文件不存在: {input_file}")
        return []
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and 'matches' in data:
        return data['matches']
    return []

def print_result(result):
    """打印格式化结果"""
    print("\n" + "=" * 70)
    print("竞彩足球全玩法分析结果（核心协调）")
    print("=" * 70)
    
    if isinstance(result, list):
        # 多场比赛
        print(f"比赛场数: {len(result)}")
        for i, match in enumerate(result, 1):
            print(f"\n--- 比赛 {i}: {match.get('match', '')} ---")
            best = match.get('best_play', {})
            if best:
                print(f"  最佳玩法: {best.get('play', '')} - {best.get('option', '')} (综合评分={best.get('composite_score', 0):.3f}, EV={best.get('ev', 0):.1%}, 信心度={best.get('confidence', '')})")
            print(f"  Top3玩法:")
            for j, p in enumerate(match.get('top_plays', []), 1):
                print(f"    {j}. {p.get('play', '')} - {p.get('option', '')} (综合评分={p.get('composite_score', 0):.3f}, EV={p.get('ev', 0):.1%})")
    else:
        # 单场比赛
        print(f"比赛: {result.get('match', '')}")
        print(f"联赛: {result.get('league', '')}")
        print("-" * 70)
        
        best = result.get('best_play', {})
        if best:
            print(f"最佳玩法: {best.get('play', '')} - {best.get('option', '')}")
            print(f"  综合评分: {best.get('composite_score', 0):.3f} (EV40%+适配度30%+置信度20%+赔率合理性10%)")
            print(f"  EV: {best.get('ev', 0):.1%}")
            print(f"  玩法适配度: {best.get('play_fitness_score', 0):.1%}")
            print(f"  模型置信度: {best.get('model_confidence', 0):.1%}")
            print(f"  信心度: {best.get('confidence', '')}")
        
        print(f"\nTop3玩法:")
        for i, p in enumerate(result.get('top_plays', []), 1):
            print(f"  {i}. {p.get('play', '')} - {p.get('option', '')} (综合评分={p.get('composite_score', 0):.3f}, EV={p.get('ev', 0):.1%}, 适配度={p.get('play_fitness_score', 0):.0%})")
        
        print(f"\n5个玩法分析状态:")
        for play_name, play_result in result.get('plays', {}).items():
            status = '✅' if play_result.get('success') else '❌'
            print(f"  {status} {play_name}")
            if not play_result.get('success'):
                print(f"     错误: {play_result.get('error', '')[:100]}")
    
    print("\n" + "=" * 70)

def main():
    parser = argparse.ArgumentParser(description='竞彩足球核心协调脚本 - 全玩法分析')
    parser.add_argument('--input', help='比赛列表JSON文件（多场比赛）')
    parser.add_argument('--match-id', help='单场比赛ID')
    parser.add_argument('--home', help='主队名称')
    parser.add_argument('--away', help='客队名称')
    parser.add_argument('--league', default='', help='联赛名称（可选）')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    args = parser.parse_args()
    
    if args.input:
        # 多场比赛
        matches = load_matches(args.input)
        results = []
        for match in matches:
            result = analyze_single_match(
                match.get('match_id', ''),
                match.get('home', ''),
                match.get('away', ''),
                match.get('league', '')
            )
            results.append(result)
        
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        else:
            print_result(results)
    elif args.match_id and args.home and args.away:
        # 单场比赛
        result = analyze_single_match(args.match_id, args.home, args.away, args.league)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print_result(result)
    else:
        print("❌ 请提供 --input 比赛列表文件，或 --match-id/--home/--away 单场比赛参数")
        parser.print_help()

if __name__ == '__main__':
    main()
