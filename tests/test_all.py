#!/usr/bin/env python3
"""
竞彩足球插件自动化测试套件
覆盖：服务器导入/工具列表/核心功能/端到端workflow/规范验证
用法：python3 tests/test_all.py
"""
import json
import os
import sys
import importlib.util
import traceback

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, 'common'))

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def test(self, name, func):
        try:
            func()
            self.passed += 1
            print(f"  ✅ {name}")
        except Exception as e:
            self.failed += 1
            self.errors.append((name, str(e), traceback.format_exc()))
            print(f"  ❌ {name}: {e}")
    
    def summary(self):
        print(f"\n{'='*60}")
        print(f"测试完成: 通过{self.passed}, 失败{self.failed}")
        if self.errors:
            print(f"\n失败详情:")
            for name, err, tb in self.errors:
                print(f"\n--- {name} ---")
                print(err[:200])
        print(f"{'='*60}")
        return self.failed == 0


def load_server(name):
    """加载MCP服务器模块"""
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(PLUGIN_ROOT, 'servers', name, 'server.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_server_imports(runner):
    """测试1: 所有服务器能正常导入"""
    servers = ['data-collector', 'analyzer', 'portfolio', 'quality-control',
               'self-evolution', 'report-generator', 'workflow', 'news-intelligence', 'visualization']
    for s in servers:
        def _test(s=s):
            mod = load_server(s)
            assert hasattr(mod, 'mcp'), f"{s}缺少mcp对象"
        runner.test(f"服务器导入: {s}", _test)


def test_tool_counts(runner):
    """测试2: 各服务器工具数量"""
    expected = {
        'data-collector': 29,
        'analyzer': 52,
        'portfolio': 19,
        'quality-control': 4,
        'self-evolution': 19,  # 17+2用户偏好
        'report-generator': 5,
        'workflow': 1,
        'news-intelligence': 7,
        'visualization': 6,
    }
    for server, expected_count in expected.items():
        def _test(s=server, exp=expected_count):
            import re
            filepath = os.path.join(PLUGIN_ROOT, 'servers', s, 'server.py')
            with open(filepath, 'r', encoding='utf-8') as f:
                code = f.read()
            # 统计@mcp.tool()装饰器数量
            tool_count = len(re.findall(r'@mcp\.tool\(\)', code))
            assert tool_count >= exp, f"{s}工具数{tool_count} < 预期{exp}"
        runner.test(f"工具数量: {server} (>={expected_count})", _test)


def test_data_collector(runner):
    """测试3: 数据采集核心工具"""
    dc = load_server('data-collector')
    
    def test_get_match_list():
        r = dc.get_match_list.fn('2026-09-06')
        assert isinstance(r, dict), "返回不是字典"
        assert 'success' in r or 'data' in r, "返回格式错误"
    runner.test("get_match_list", test_get_match_list)
    
    def test_parse_odds():
        sample = {'value': {'oddsHistory': {'hadList': [{'odds': '1.50,3.80,5.00'}]}}}
        r = dc.parse_odds_response.fn(sample)
        assert isinstance(r, dict), "解析结果不是字典"
    runner.test("parse_odds_response", test_parse_odds)


def test_analyzer(runner):
    """测试4: 分析核心工具"""
    an = load_server('analyzer')
    
    def test_poisson():
        r = an.poisson_predict.fn(1.5, 1.2)
        assert isinstance(r, dict), "泊松返回不是字典"
        assert 'score_matrix' in r or 'probabilities' in r or 'data' in r, "泊松结果缺少关键字段"
    runner.test("poisson_predict", test_poisson)
    
    def test_ev():
        r = an.calculate_ev.fn(0.6, 1.8)
        assert isinstance(r, (int, float, dict)), "EV返回类型错误"
    runner.test("calculate_ev", test_ev)
    
    def test_ensemble():
        r = an.ensemble_predict.fn(1.5, 1.2, [1.8, 3.5, 4.0])
        assert isinstance(r, dict), "集成预测返回不是字典"
    runner.test("ensemble_predict", test_ensemble)


def test_portfolio(runner):
    """测试5: 投注组合核心工具"""
    pf = load_server('portfolio')
    
    def test_parlay_payout():
        r = pf.calc_parlay_payout.fn([1.8, 2.0, 3.0], 2, 1)
        assert isinstance(r, (int, float, dict)), "串关奖金返回类型错误"
    runner.test("calc_parlay_payout", test_parlay_payout)
    
    def test_bankroll():
        r = pf.bankroll_management.fn(1000, 0.05, 'balanced')
        assert isinstance(r, dict), "资金管理返回不是字典"
    runner.test("bankroll_management", test_bankroll)


def test_quality_control(runner):
    """测试6: 质量控制工具"""
    qc = load_server('quality-control')
    
    def test_preflight():
        r = qc.preflight_check.fn({'matches': [], 'date': '2026-09-06'})
        assert isinstance(r, dict), "预检返回不是字典"
    runner.test("preflight_check", test_preflight)
    
    def test_rules():
        r = qc.check_official_rules.fn([], '2串1', 100)
        assert isinstance(r, dict), "规则检查返回不是字典"
    runner.test("check_official_rules", test_rules)


def test_self_evolution(runner):
    """测试7: 自进化工具"""
    se = load_server('self-evolution')
    
    def test_get_stats():
        r = se.get_stats.fn()
        assert isinstance(r, dict), "统计返回不是字典"
    runner.test("get_stats", test_get_stats)
    
    def test_user_prefs():
        r = se.get_user_preferences.fn()
        assert isinstance(r, dict), "用户偏好返回不是字典"
        assert 'success' in r, "缺少success字段"
    runner.test("get_user_preferences", test_user_prefs)


def test_news_intelligence(runner):
    """测试8: 资讯智能工具"""
    ni = load_server('news-intelligence')
    
    def test_keywords():
        r = ni.generate_news_search_keywords.fn('利物浦', '阿森纳', '英超')
        assert isinstance(r, dict), "关键词返回不是字典"
        assert 'keywords' in r.get('data', {}), "缺少keywords"
    runner.test("generate_news_search_keywords", test_keywords)
    
    def test_injury():
        r = ni.quantify_injury_impact.fn({'home': ['主力前锋伤停'], 'away': []}, '利物浦', '阿森纳')
        assert isinstance(r, dict), "伤停量化返回不是字典"
    runner.test("quantify_injury_impact", test_injury)


def test_visualization(runner):
    """测试9: 可视化工具"""
    viz = load_server('visualization')
    
    def test_odds_chart():
        r = viz.generate_odds_trend_chart.fn('001', '利物浦', '阿森纳', [], '2026-09-06')
        assert isinstance(r, dict), "赔率图返回不是字典"
        assert 'file' in r.get('data', {}), "缺少file路径"
    runner.test("generate_odds_trend_chart", test_odds_chart)
    
    def test_interactive_report():
        r = viz.generate_interactive_report.fn([], [], [], '2026-09-06')
        assert isinstance(r, dict), "交互报告返回不是字典"
    runner.test("generate_interactive_report", test_interactive_report)


def test_common_module(runner):
    """测试10: 公共模块"""
    def test_tool_response():
        from tool_response import ok, fail, parse_response
        r = ok('test', {'a': 1})
        assert r['tool'] == 'test'
        assert r['success'] == True
        r2 = fail('test', 'error')
        assert r2['success'] == False
        parsed = parse_response({'success': True, 'data': {'x': 1}})
        assert parsed['success'] == True
    runner.test("tool_response公共模块", test_tool_response)


def test_workflow_e2e(runner):
    """测试11: 端到端workflow（核心）"""
    def test_run():
        wf = load_server('workflow')
        r = wf.run_full_workflow.fn(date='2026-09-06', total_budget=500, risk_preference='balanced')
        assert isinstance(r, dict), "workflow返回不是字典"
        assert 'success' in r, "缺少success字段"
        assert r['success'] == True, "workflow执行失败"
        data = r.get('data', {})
        assert 'tools_called' in data, "缺少tools_called"
        assert 'tools_success' in data, "缺少tools_success"
        assert data['tools_success'] > 100, f"成功工具数{data['tools_success']} < 100"
        assert 'observability' in data, "缺少可观测性指标"
    runner.test("run_full_workflow端到端", test_run)


def test_plugin_structure(runner):
    """测试12: 插件结构规范"""
    def test_plugin_json():
        with open(os.path.join(PLUGIN_ROOT, 'plugin.json'), 'r') as f:
            p = json.load(f)
        assert 'name' in p, "缺少name"
        assert 'version' in p, "缺少version"
        assert 'extensions' in p, "缺少extensions"
        assert 'mcpServers' in p['extensions'], "缺少mcpServers"
        assert len(p['extensions']['mcpServers']) == 9, f"MCP服务器数{len(p['extensions']['mcpServers'])} != 9"
    runner.test("plugin.json结构", test_plugin_json)
    
    def test_mcp_json():
        with open(os.path.join(PLUGIN_ROOT, 'mcp.json'), 'r') as f:
            m = json.load(f)
        assert 'mcpServers' in m, "缺少mcpServers"
        assert len(m['mcpServers']) == 9, f"MCP服务器数{len(m['mcpServers'])} != 9"
    runner.test("mcp.json结构", test_mcp_json)
    
    def test_skills():
        skills_dir = os.path.join(PLUGIN_ROOT, 'skills')
        skills = os.listdir(skills_dir)
        assert len(skills) >= 6, f"技能数{len(skills)} < 6"
        for s in skills:
            assert os.path.exists(os.path.join(skills_dir, s, 'SKILL.md')), f"{s}缺少SKILL.md"
    runner.test("技能目录结构", test_skills)


def main():
    print("=" * 60)
    print("竞彩足球插件自动化测试套件")
    print("=" * 60)
    
    runner = TestRunner()
    
    print("\n【1/12】服务器导入测试")
    test_server_imports(runner)
    
    print("\n【2/12】工具数量测试")
    test_tool_counts(runner)
    
    print("\n【3/12】数据采集测试")
    test_data_collector(runner)
    
    print("\n【4/12】分析工具测试")
    test_analyzer(runner)
    
    print("\n【5/12】投注组合测试")
    test_portfolio(runner)
    
    print("\n【6/12】质量控制测试")
    test_quality_control(runner)
    
    print("\n【7/12】自进化测试")
    test_self_evolution(runner)
    
    print("\n【8/12】资讯智能测试")
    test_news_intelligence(runner)
    
    print("\n【9/12】可视化测试")
    test_visualization(runner)
    
    print("\n【10/12】公共模块测试")
    test_common_module(runner)
    
    print("\n【11/12】端到端workflow测试")
    test_workflow_e2e(runner)
    
    print("\n【12/12】插件结构测试")
    test_plugin_structure(runner)
    
    success = runner.summary()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
