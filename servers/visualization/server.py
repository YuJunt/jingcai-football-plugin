#!/usr/bin/env python3
"""
竞彩足球可视化服务器
生成赔率走势图、概率雷达图、收益矩阵、HTML交互式报告
使用纯HTML+ECharts，无需额外依赖
"""
import json
import os
from datetime import datetime

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PLUGIN_ROOT, 'output')

try:
    from fastmcp import FastMCP
    mcp = FastMCP("jingcai-visualization")
except ImportError:
    class FakeMCP:
        def tool(self, fn):
            return fn
    mcp = FakeMCP()


def _ensure_output():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


@mcp.tool()
def generate_odds_trend_chart(match_id: str, home_team: str, away_team: str,
                               odds_history: list = None, date: str = "") -> dict:
    """
    生成赔率走势图（HTML+ECharts）
    odds_history: [{'time': '2026-09-06 10:00', 'home': 1.5, 'draw': 3.8, 'away': 5.0}, ...]
    """
    _ensure_output()
    if not odds_history:
        odds_history = [
            {'time': '初盘', 'home': 1.55, 'draw': 3.80, 'away': 5.20},
            {'time': '即时', 'home': 1.48, 'draw': 3.90, 'away': 5.50},
        ]
    
    times = [h['time'] for h in odds_history]
    home_odds = [h['home'] for h in odds_history]
    draw_odds = [h['draw'] for h in odds_history]
    away_odds = [h['away'] for h in odds_history]
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>赔率走势 - {home_team} vs {away_team}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
</head><body>
<div id="chart" style="width:100%;height:400px;"></div>
<script>
var chart = echarts.init(document.getElementById('chart'));
chart.setOption({{
    title: {{text: '{home_team} vs {away_team} 赔率走势', left: 'center'}},
    tooltip: {{trigger: 'axis'}},
    legend: {{data: ['主胜', '平局', '客胜'], bottom: 0}},
    xAxis: {{type: 'category', data: {json.dumps(times)}}},
    yAxis: {{type: 'value', name: '赔率'}},
    series: [
        {{name: '主胜', type: 'line', data: {json.dumps(home_odds)}, smooth: true}},
        {{name: '平局', type: 'line', data: {json.dumps(draw_odds)}, smooth: true}},
        {{name: '客胜', type: 'line', data: {json.dumps(away_odds)}, smooth: true}}
    ]
}});
</script></body></html>"""
    
    filename = f"odds_trend_{match_id}_{date}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {'success': True, 'data': {'file': filepath, 'filename': filename, 'note': '用浏览器打开查看赔率走势图'}}


@mcp.tool()
def generate_probability_radar(match_id: str, home_team: str, away_team: str,
                                probabilities: dict, date: str = "") -> dict:
    """
    生成概率分布雷达图
    probabilities: {'胜平负': {'主胜': 0.6, '平局': 0.25, '客胜': 0.15}, '总进球': {...}, ...}
    """
    _ensure_output()
    
    indicators = []
    values = []
    for play, opts in probabilities.items():
        if isinstance(opts, dict):
            for opt, prob in opts.items():
                indicators.append({'name': f"{play}-{opt}", 'max': 1.0})
                values.append(round(prob, 3))
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>概率雷达 - {home_team} vs {away_team}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
</head><body>
<div id="chart" style="width:100%;height:500px;"></div>
<script>
var chart = echarts.init(document.getElementById('chart'));
chart.setOption({{
    title: {{text: '{home_team} vs {away_team} 概率分布', left: 'center'}},
    tooltip: {{}},
    radar: {{indicator: {json.dumps(indicators)}}},
    series: [{{type: 'radar', data: [{{value: {json.dumps(values)}, name: '模型概率'}}]}}]
}});
</script></body></html>"""
    
    filename = f"prob_radar_{match_id}_{date}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {'success': True, 'data': {'file': filepath, 'filename': filename}}


@mcp.tool()
def generate_payout_matrix(bet_slips: list, date: str = "") -> dict:
    """
    生成投注组合收益矩阵图
    bet_slips: [{'name': '稳单', 'cost': 100, 'scenarios': [{'name': '全中', 'payout': 500}, ...]}, ...]
    """
    _ensure_output()
    
    slip_names = [s['name'] for s in bet_slips]
    scenario_names = [s['name'] for s in bet_slips[0].get('scenarios', [])] if bet_slips else []
    
    heatmap_data = []
    for i, slip in enumerate(bet_slips):
        for j, sc in enumerate(slip.get('scenarios', [])):
            profit = sc.get('payout', 0) - slip.get('cost', 0)
            heatmap_data.append([j, i, round(profit, 0)])
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>投注收益矩阵</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
</head><body>
<div id="chart" style="width:100%;height:400px;"></div>
<script>
var chart = echarts.init(document.getElementById('chart'));
chart.setOption({{
    title: {{text: '投注组合收益矩阵（元）', left: 'center'}},
    tooltip: {{position: 'top'}},
    grid: {{height: '50%', top: '10%'}},
    xAxis: {{type: 'category', data: {json.dumps(scenario_names)}, splitArea: {{show: true}}}},
    yAxis: {{type: 'category', data: {json.dumps(slip_names)}, splitArea: {{show: true}}}},
    visualMap: {{min: -200, max: 500, calculable: true, orient: 'horizontal', left: 'center', bottom: '5%'}},
    series: [{{type: 'heatmap', data: {json.dumps(heatmap_data)}, label: {{show: true}}}}]
}});
</script></body></html>"""
    
    filename = f"payout_matrix_{date}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {'success': True, 'data': {'file': filepath, 'filename': filename}}


@mcp.tool()
def generate_hit_rate_trend(history: list, date: str = "") -> dict:
    """
    生成历史命中率趋势图
    history: [{'date': '2026-09-01', 'play': '胜平负', 'hit_rate': 0.6, 'roi': 0.1}, ...]
    """
    _ensure_output()
    
    dates = sorted(set(h['date'] for h in history))
    plays = sorted(set(h['play'] for h in history))
    
    series = []
    for play in plays:
        play_data = [h['hit_rate'] for h in history if h['play'] == play]
        series.append({'name': play, 'type': 'line', 'data': play_data, 'smooth': True})
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>命中率趋势</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
</head><body>
<div id="chart" style="width:100%;height:400px;"></div>
<script>
var chart = echarts.init(document.getElementById('chart'));
chart.setOption({{
    title: {{text: '各玩法命中率趋势', left: 'center'}},
    tooltip: {{trigger: 'axis'}},
    legend: {{data: {json.dumps(plays)}, bottom: 0}},
    xAxis: {{type: 'category', data: {json.dumps(dates)}}},
    yAxis: {{type: 'value', name: '命中率', max: 1.0}},
    series: {json.dumps(series)}
}});
</script></body></html>"""
    
    filename = f"hit_rate_trend_{date}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {'success': True, 'data': {'file': filepath, 'filename': filename}}


@mcp.tool()
def generate_interactive_report(matches: list, analysis_results: list,
                                 bet_slips: list = None, date: str = "") -> dict:
    """
    生成完整的HTML交互式分析报告
    整合：比赛概览+概率分析+投注方案+可视化图表
    """
    _ensure_output()
    
    # 比赛概览表格
    match_rows = ""
    for m in matches[:10]:
        match_rows += f"<tr><td>{m.get('match_id','')}</td><td>{m.get('league','')}</td><td>{m.get('home','')} vs {m.get('away','')}</td><td>{m.get('match_time','')}</td></tr>\n"
    
    # 分析结果摘要
    analysis_summary = ""
    for a in analysis_results[:5]:
        top_plays = a.get('top_plays', [])
        top_str = ", ".join([p.get('play','') if isinstance(p, dict) else str(p) for p in top_plays[:3]])
        analysis_summary += f"<div class='card'><h4>{a.get('home','')} vs {a.get('away','')}</h4><p>Top玩法: {top_str}</p></div>\n"
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>竞彩足球分析报告 - {date}</title>
<style>
body {{font-family: -apple-system, sans-serif; margin: 20px; background: #f5f5f5;}}
h1 {{color: #1a1a2e;}}
.card {{background: white; padding: 15px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);}}
table {{width: 100%; border-collapse: collapse; background: white;}}
th, td {{padding: 8px 12px; border: 1px solid #ddd; text-align: left;}}
th {{background: #1a1a2e; color: white;}}
.tag {{display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin: 2px;}}
.tag-value {{background: #d4edda; color: #155724;}}
.tag-risk {{background: #f8d7da; color: #721c24;}}
</style></head><body>
<h1>竞彩足球全量分析报告 - {date}</h1>
<div class="card">
<h3>比赛概览（共{len(matches)}场）</h3>
<table><tr><th>编号</th><th>联赛</th><th>对阵</th><th>时间</th></tr>
{match_rows}
</table>
</div>
<div class="card">
<h3>重点比赛分析</h3>
{analysis_summary}
</div>
<div class="card">
<h3>投注方案</h3>
<p>共{len(bet_slips) if bet_slips else 0}张投注单</p>
</div>
<div class="card">
<h3>风险提示</h3>
<p>本报告由AI辅助生成，仅供参考，不构成投注建议。理性购彩，量力而行。</p>
</div>
</body></html>"""
    
    filename = f"interactive_report_{date}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {
        'success': True,
        'data': {
            'file': filepath,
            'filename': filename,
            'matches_count': len(matches),
            'analysis_count': len(analysis_results),
            'bet_slips_count': len(bet_slips) if bet_slips else 0,
            'note': '用浏览器打开查看完整交互式报告',
        }
    }


@mcp.tool()
def generate_ev_distribution_chart(value_options: list, date: str = "") -> dict:
    """
    生成EV分布柱状图
    value_options: [{'match': '001', 'play': '胜平负', 'option': '主胜', 'ev': 0.15, 'odds': 1.8}, ...]
    """
    _ensure_output()
    
    labels = [f"{v.get('match','')}-{v.get('play','')}-{v.get('option','')}" for v in value_options[:20]]
    evs = [round(v.get('ev', 0) * 100, 1) for v in value_options[:20]]
    colors = ['#52c41a' if e > 0 else '#ff4d4f' for e in evs]
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>EV分布图</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
</head><body>
<div id="chart" style="width:100%;height:500px;"></div>
<script>
var chart = echarts.init(document.getElementById('chart'));
chart.setOption({{
    title: {{text: '价值选项EV分布（%）', left: 'center'}},
    tooltip: {{trigger: 'axis'}},
    xAxis: {{type: 'category', data: {json.dumps(labels)}, axisLabel: {{rotate: 45}}}},
    yAxis: {{type: 'value', name: 'EV(%)'}},
    series: [{{type: 'bar', data: {json.dumps(evs)}, itemStyle: {{color: function(params){{return params.value > 0 ? '#52c41a' : '#ff4d4f';}}}}}}]
}});
</script></body></html>"""
    
    filename = f"ev_distribution_{date}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {'success': True, 'data': {'file': filepath, 'filename': filename}}


if __name__ == '__main__':
    mcp.run()
