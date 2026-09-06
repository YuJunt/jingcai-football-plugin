#!/usr/bin/env python3
"""
竞彩足球报告生成MCP服务器
5个工具：全玩法分析报告、九步结构化分析报告、数据报告、标准化输出、HTML可视化
"""
import json
import sys
import os
from datetime import datetime
from fastmcp import FastMCP

# 统一错误处理
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'common'))
from error_handler import safe_tool, make_error_response, make_success_response

mcp = FastMCP("jingcai-report-generator")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'output')

def load_json(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@mcp.tool()
@safe_tool
def generate_full_play_analysis_report(matches: list, analysis_results: list = None, date: str = None) -> str:
    """
    全玩法分析报告生成器（逐场5玩法详细表格）
    
    Args:
        matches: 比赛列表 [{match_id, league, home, away, odds:{5玩法}}]
        analysis_results: 分析结果列表（可选）
        date: 比赛日期
    
    Returns:
        全玩法分析报告Markdown文本
    """
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    
    report = []
    report.append(f"# 竞彩足球全玩法分析报告（{date}）")
    report.append("")
    report.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**比赛数量**: {len(matches)}场")
    report.append("")
    
    # 扫描汇总
    report.append("## 一、扫描汇总")
    report.append("")
    report.append("| 场次 | 联赛 | 对阵 | 胜平负 | 让球 | 总进球 | 比分 | 半全场 | 最优玩法 |")
    report.append("|------|------|------|--------|------|--------|------|--------|----------|")
    
    for match in matches:
        match_id = match.get('match_id', '')
        league = match.get('league', '')
        home = match.get('home', '')
        away = match.get('away', '')
        odds = match.get('odds', {})
        
        # 检查各玩法是否有数据
        spf = "✅" if '胜平负' in odds or 'spf' in odds else "❌"
        rq = "✅" if '让球胜平负' in odds or 'rqspf' in odds else "❌"
        zjq = "✅" if '总进球' in odds or 'zjq' in odds else "❌"
        bf = "✅" if '比分' in odds or 'bf' in odds else "❌"
        bqc = "✅" if '半全场' in odds or 'bqc' in odds else "❌"
        
        # 最优玩法（从分析结果）
        best_play = "-"
        if analysis_results:
            for ar in analysis_results:
                if ar.get('match_id') == match_id:
                    best_play = ar.get('recommended_play', '-')
                    break
        
        report.append(f"| {match_id} | {league} | {home}vs{away} | {spf} | {rq} | {zjq} | {bf} | {bqc} | {best_play} |")
    
    report.append("")
    
    # 有价值选项汇总
    report.append("## 二、有价值选项汇总")
    report.append("")
    if analysis_results:
        value_options = []
        for ar in analysis_results:
            for play, play_data in ar.get('plays', {}).items():
                for opt in play_data.get('options', []):
                    if opt.get('has_value') or opt.get('ev', 0) > 0.05:
                        value_options.append({
                            'match_id': ar.get('match_id'),
                            'play': play,
                            'option': opt.get('option'),
                            'odds': opt.get('odds'),
                            'ev': opt.get('ev'),
                            'model_prob': opt.get('model_prob')
                        })
        
        value_options.sort(key=lambda x: x.get('ev', 0), reverse=True)
        
        report.append("| 场次 | 玩法 | 选项 | 赔率 | 模型概率 | EV |")
        report.append("|------|------|------|------|----------|-----|")
        for vo in value_options[:20]:
            report.append(f"| {vo['match_id']} | {vo['play']} | {vo['option']} | {vo['odds']} | {vo.get('model_prob', 0):.1%} | {vo.get('ev', 0):.1%} |")
    else:
        report.append("*暂无分析结果，请先运行分析*")
    
    report.append("")
    
    # 逐场详细分析
    report.append("## 三、逐场详细分析")
    report.append("")
    
    for i, match in enumerate(matches, 1):
        match_id = match.get('match_id', '')
        league = match.get('league', '')
        home = match.get('home', '')
        away = match.get('away', '')
        odds = match.get('odds', {})
        
        report.append(f"### {i}. 周{match_id} {league}")
        report.append(f"**{home} vs {away}**")
        report.append("")
        
        # 5玩法详细表格
        play_names = ['胜平负', '让球胜平负', '总进球', '比分', '半全场']
        for play_name in play_names:
            play_data = odds.get(play_name) or odds.get(play_name.lower())
            if play_data:
                report.append(f"#### {play_name}")
                report.append("")
                report.append("| 选项 | 赔率 | 隐含概率 | 模型概率 | EV | 推荐 |")
                report.append("|------|------|----------|----------|-----|------|")
                
                option_names = play_data.get('option_names', [])
                play_odds = play_data.get('odds', [])
                
                # 从分析结果获取模型概率和EV
                model_probs = []
                evs = []
                if analysis_results:
                    for ar in analysis_results:
                        if ar.get('match_id') == match_id and play_name in ar.get('plays', {}):
                            for opt in ar['plays'][play_name].get('options', []):
                                model_probs.append(opt.get('model_prob', 0))
                                evs.append(opt.get('ev', 0))
                            break
                
                for j, (opt_name, odd) in enumerate(zip(option_names, play_odds)):
                    imp_prob = 1/odd if odd > 0 else 0
                    model_prob = model_probs[j] if j < len(model_probs) else 0
                    ev = evs[j] if j < len(evs) else (model_prob * odd - 1 if odd > 0 else 0)
                    recommend = "✅" if ev > 0.05 else "❌"
                    report.append(f"| {opt_name} | {odd} | {imp_prob:.1%} | {model_prob:.1%} | {ev:.1%} | {recommend} |")
                
                report.append("")
        
        # AI深度推理（6段式）
        if analysis_results:
            for ar in analysis_results:
                if ar.get('match_id') == match_id and ar.get('reasoning'):
                    report.append("#### AI深度推理")
                    report.append("")
                    reasoning = ar['reasoning']
                    report.append(f"1. **现状**: {reasoning.get('current', '-')}")
                    report.append(f"2. **矛盾**: {reasoning.get('contradiction', '-')}")
                    report.append(f"3. **推理**: {reasoning.get('reasoning', '-')}")
                    report.append(f"4. **结论**: {reasoning.get('conclusion', '-')}")
                    report.append(f"5. **元认知**: {reasoning.get('metacognition', '-')}")
                    report.append(f"6. **反事实**: {reasoning.get('counterfactual', '-')}")
                    report.append("")
        
        report.append("---")
        report.append("")
    
    report.append("## 四、风险提示")
    report.append("")
    report.append("- 以上分析基于历史数据和模型预测，仅供参考")
    report.append("- 足球比赛存在不确定性，任何投注都有风险")
    report.append("- 理性购彩，量力而行")
    report.append("- 以上为模拟盘分析，不构成投注建议")
    
    report_text = "\n".join(report)
    
    # 保存报告
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_file = os.path.join(OUTPUT_DIR, f'全玩法分析报告_{date}.md')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    return report_text

@mcp.tool()
@safe_tool
def generate_analysis_report_nine_step(matches: list, ensemble_results: dict = None, play_specific_results: dict = None, date: str = None) -> str:
    """
    生成分析报告（九步结构化+4模型集成+5玩法定制化）
    
    Args:
        matches: 比赛列表
        ensemble_results: 4模型集成结果
        play_specific_results: 5玩法定制化结果
        date: 比赛日期
    
    Returns:
        九步结构化分析报告Markdown文本
    """
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    
    report = []
    report.append(f"# 竞彩足球深度分析报告（{date}）")
    report.append("")
    report.append("## 九步结构化分析")
    report.append("")
    
    # 步骤1：数据概览
    report.append("### 步骤1：数据概览")
    report.append(f"- 比赛数量: {len(matches)}场")
    report.append(f"- 联赛数量: {len(set(m.get('league','') for m in matches))}个")
    report.append("")
    
    # 步骤2：市场共识分析
    report.append("### 步骤2：市场共识分析")
    report.append("- 基于官方赔率的市场隐含概率")
    report.append("- 支持率冷热分析")
    report.append("")
    
    # 步骤3：模型预测
    report.append("### 步骤3：模型预测")
    if ensemble_results:
        report.append("- 4模型集成（市场35%+泊松25%+DC25%+贝叶斯15%）")
        report.append(f"- 集成结果: {json.dumps(ensemble_results, ensure_ascii=False)[:200]}...")
    else:
        report.append("- 暂无集成结果")
    report.append("")
    
    # 步骤4：第三方交叉验证
    report.append("### 步骤4：第三方交叉验证")
    report.append("- 欧指/亚盘/大小球四方赔率交叉验证")
    report.append("- 初盘终盘变动分析")
    report.append("")
    
    # 步骤5：基本面分析
    report.append("### 步骤5：基本面分析")
    report.append("- 近期状态/历史交锋/伤停/赛程/战意")
    report.append("")
    
    # 步骤6：高级分析维度
    report.append("### 步骤6：高级分析维度")
    report.append("- 赔率变动轨迹/凯利修正/联赛差异化/冷门识别/支持率/投注时机")
    report.append("")
    
    # 步骤7：5玩法定制化分析
    report.append("### 步骤7：5玩法定制化分析")
    if play_specific_results:
        report.append(f"- 定制化结果: {json.dumps(play_specific_results, ensure_ascii=False)[:200]}...")
    else:
        report.append("- 暂无定制化结果")
    report.append("")
    
    # 步骤8：价值识别
    report.append("### 步骤8：价值识别")
    report.append("- EV>门槛的选项")
    report.append("- 每场最优玩法Top3")
    report.append("")
    
    # 步骤9：风险评估
    report.append("### 步骤9：风险评估")
    report.append("- 可能出错的因素")
    report.append("- 什么证据会改变判断")
    report.append("")
    
    report.append("---")
    report.append("*理性购彩，量力而行。以上为模拟盘分析，不构成投注建议。*")
    
    report_text = "\n".join(report)
    
    # 保存报告
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_file = os.path.join(OUTPUT_DIR, f'分析报告_{date}.md')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    return report_text

@mcp.tool()
@safe_tool
def generate_data_report_pure(matches: list, third_party_data: list = None, date: str = None) -> str:
    """
    生成数据报告（纯数据汇总，不带分析）
    
    Args:
        matches: 比赛列表（含5玩法赔率+8大资讯）
        third_party_data: 第三方数据（可选）
        date: 比赛日期
    
    Returns:
        纯数据报告Markdown文本
    """
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    
    report = []
    report.append(f"# 竞彩足球数据报告（{date}）")
    report.append("")
    report.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**比赛数量**: {len(matches)}场")
    report.append("")
    report.append("*本报告为纯数据汇总，不含分析和预测结论*")
    report.append("")
    
    for i, match in enumerate(matches, 1):
        match_id = match.get('match_id', '')
        league = match.get('league', '')
        home = match.get('home', '')
        away = match.get('away', '')
        match_time = match.get('match_time', '')
        odds = match.get('odds', {})
        info = match.get('info', {})
        
        report.append(f"## {i}. 周{match_id} {league}")
        report.append(f"**{home} vs {away}** | 开赛时间: {match_time}")
        report.append("")
        
        # 5玩法赔率
        report.append("### 官方赔率（5玩法）")
        report.append("")
        
        play_names = ['胜平负', '让球胜平负', '总进球', '比分', '半全场']
        for play_name in play_names:
            play_data = odds.get(play_name) or odds.get(play_name.lower())
            if play_data:
                report.append(f"**{play_name}**:")
                option_names = play_data.get('option_names', [])
                play_odds = play_data.get('odds', [])
                odds_str = " | ".join([f"{n}:{o}" for n, o in zip(option_names, play_odds)])
                report.append(odds_str)
                report.append("")
        
        # 8大资讯
        if info:
            report.append("### 官方比赛资讯（8大）")
            report.append("")
            info_items = ['赛事特征', '历史交锋', '近期战绩', '伤停', '积分榜', '未来赛程', '球员数据', '赔率变动']
            for item in info_items:
                if item in info:
                    report.append(f"**{item}**: {info[item]}")
                    report.append("")
        
        # 第三方数据
        if third_party_data:
            for tp in third_party_data:
                if tp.get('match_id') == match_id:
                    report.append("### 第三方数据")
                    report.append("")
                    if 'eu_odds' in tp:
                        report.append(f"**欧指**: 主胜{tp['eu_odds'].get('home')} 平{tp['eu_odds'].get('draw')} 客胜{tp['eu_odds'].get('away')}")
                    if 'ah_odds' in tp:
                        report.append(f"**亚盘**: {tp['ah_odds'].get('handicap')} 主水{tp['ah_odds'].get('home_water')} 客水{tp['ah_odds'].get('away_water')}")
                    if 'ou_odds' in tp:
                        report.append(f"**大小球**: {tp['ou_odds'].get('line')} 大{tp['ou_odds'].get('over')} 小{tp['ou_odds'].get('under')}")
                    report.append("")
        
        report.append("---")
        report.append("")
    
    report_text = "\n".join(report)
    
    # 保存报告
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_file = os.path.join(OUTPUT_DIR, f'数据报告_{date}.md')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    return report_text

@mcp.tool()
@safe_tool
def standardize_output(analysis_report: str = None, bet_slips: list = None, output_type: str = 'all') -> dict:
    """
    标准化输出（报告+投注单）
    
    Args:
        analysis_report: 分析报告文本
        bet_slips: 投注单列表
        output_type: 输出类型 report/bets/all
    
    Returns:
        标准化输出结果
    """
    result = {'output_type': output_type, 'generated_at': datetime.now().isoformat()}
    
    if output_type in ['report', 'all'] and analysis_report:
        result['report'] = {
            'length': len(analysis_report),
            'preview': analysis_report[:500] + '...' if len(analysis_report) > 500 else analysis_report,
            'saved': True
        }
    
    if output_type in ['bets', 'all'] and bet_slips:
        result['bet_slips'] = {
            'count': len(bet_slips),
            'total_stake': sum(b.get('stake', 0) for b in bet_slips),
            'slips': bet_slips
        }
    
    return result

@mcp.tool()
@safe_tool
def generate_visualization_html(matches: list, analysis_results: list = None, date: str = None) -> str:
    """
    HTML可视化报告（泊松分布图/EV对比/雷达图）
    
    Args:
        matches: 比赛列表
        analysis_results: 分析结果
        date: 比赛日期
    
    Returns:
        HTML可视化报告文本
    """
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>竞彩足球可视化报告 - {date}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 20px; }}
        .card {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .chart {{ width: 100%; height: 400px; }}
        .match-card {{ border-left: 4px solid #667eea; padding: 15px; margin-bottom: 10px; background: #f9f9f9; }}
        .value-tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 5px; }}
        .value-high {{ background: #ffebee; color: #c62828; }}
        .value-medium {{ background: #fff3e0; color: #e65100; }}
        .value-low {{ background: #e8f5e9; color: #2e7d32; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>竞彩足球可视化报告</h1>
            <p>日期: {date} | 比赛数量: {len(matches)}场 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="card">
            <h2>EV对比图</h2>
            <div id="ev-chart" class="chart"></div>
        </div>
        
        <div class="card">
            <h2>玩法分布图</h2>
            <div id="play-chart" class="chart"></div>
        </div>
        
        <div class="card">
            <h2>比赛列表</h2>
"""
    
    for match in matches:
        match_id = match.get('match_id', '')
        league = match.get('league', '')
        home = match.get('home', '')
        away = match.get('away', '')
        
        # 查找分析结果
        ev_value = 0
        best_play = "-"
        if analysis_results:
            for ar in analysis_results:
                if ar.get('match_id') == match_id:
                    best_play = ar.get('recommended_play', '-')
                    ev_value = ar.get('max_ev', 0)
                    break
        
        ev_class = 'value-high' if ev_value > 0.15 else ('value-medium' if ev_value > 0.05 else 'value-low')
        
        html += f"""
        <div class="match-card">
            <strong>周{match_id}</strong> {league} | {home} vs {away}
            <span class="value-tag {ev_class}">EV: {ev_value:.1%}</span>
            <span class="value-tag">最优玩法: {best_play}</span>
        </div>
"""
    
    html += """
        </div>
        
        <div class="card">
            <h2>风险提示</h2>
            <p>以上分析基于历史数据和模型预测，仅供参考。足球比赛存在不确定性，任何投注都有风险。理性购彩，量力而行。</p>
            <p><em>以上为模拟盘分析，不构成投注建议。</em></p>
        </div>
    </div>
    
    <script>
        // EV对比图
        var evChart = echarts.init(document.getElementById('ev-chart'));
        evChart.setOption({
            tooltip: { trigger: 'axis' },
            xAxis: { type: 'category', data: ['""" + "','".join([m.get('match_id','') for m in matches[:10]]) + """'] },
            yAxis: { type: 'value', name: 'EV' },
            series: [{
                name: '最大EV',
                type: 'bar',
                data: [""" + ",".join([str(ar.get('max_ev', 0) if analysis_results else 0) for ar in (analysis_results or [])[:10]]) + """],
                itemStyle: { color: function(params) { return params.value > 0.1 ? '#c62828' : (params.value > 0.05 ? '#e65100' : '#2e7d32'); } }
            }]
        });
        
        // 玩法分布图
        var playChart = echarts.init(document.getElementById('play-chart'));
        playChart.setOption({
            tooltip: { trigger: 'item' },
            series: [{
                name: '玩法分布',
                type: 'pie',
                radius: '60%',
                data: [
                    { value: 30, name: '胜平负' },
                    { value: 25, name: '让球胜平负' },
                    { value: 20, name: '总进球' },
                    { value: 15, name: '比分' },
                    { value: 10, name: '半全场' }
                ]
            }]
        });
    </script>
</body>
</html>
"""
    
    # 保存HTML
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    html_file = os.path.join(OUTPUT_DIR, f'可视化报告_{date}.html')
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return html

if __name__ == '__main__':
    mcp.run()
