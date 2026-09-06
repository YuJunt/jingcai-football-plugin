#!/usr/bin/env python3
"""
竞彩足球插件核心功能单元测试
覆盖：泊松预测、EV计算、Dixon-Coles、半全场条件概率、串关奖金、错误处理、参数辅助
运行方式: pytest tests/test_core.py -v
"""
import os
import sys
import pytest

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'analyzer'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'portfolio'))

from error_handler import (
    safe_tool, make_error_response, make_success_response,
    validate_required, validate_type, validate_range
)
from param_helpers import (
    make_strategy_config, make_value_option, make_match_data,
    validate_strategy_config, validate_value_options
)


# ============================================================
# 测试1：错误处理模块
# ============================================================

class TestErrorHandler:
    """测试统一错误处理模块"""

    def test_make_error_response(self):
        """测试错误响应生成"""
        resp = make_error_response("测试错误", "validation", "请检查参数")
        assert resp["success"] is False
        assert resp["error"] == "测试错误"
        assert resp["error_type"] == "validation"
        assert resp["suggestion"] == "请检查参数"

    def test_make_success_response(self):
        """测试成功响应生成"""
        data = {"result": 42}
        resp = make_success_response(data, "操作成功")
        assert resp["success"] is True
        assert resp["data"] == data
        assert resp["message"] == "操作成功"

    def test_validate_required_pass(self):
        """测试必填参数验证（通过）"""
        params = {"a": 1, "b": 2}
        result = validate_required(params, ["a", "b"])
        assert result is None

    def test_validate_required_fail(self):
        """测试必填参数验证（失败）"""
        params = {"a": 1}
        result = validate_required(params, ["a", "b"])
        assert result is not None
        assert result["success"] is False
        assert "b" in result["error"]

    def test_validate_type_pass(self):
        """测试类型验证（通过）"""
        result = validate_type(42, int, "age")
        assert result is None

    def test_validate_type_fail(self):
        """测试类型验证（失败）"""
        result = validate_type("42", int, "age")
        assert result is not None
        assert result["error_type"] == "validation"

    def test_validate_range_pass(self):
        """测试范围验证（通过）"""
        result = validate_range(0.5, 0.0, 1.0, "prob")
        assert result is None

    def test_validate_range_fail(self):
        """测试范围验证（失败）"""
        result = validate_range(1.5, 0.0, 1.0, "prob")
        assert result is not None

    def test_safe_tool_normal(self):
        """测试安全装饰器（正常执行）"""
        @safe_tool
        def add(a, b):
            return a + b

        result = add(2, 3)
        assert result["success"] is True
        assert result["data"] == 5

    def test_safe_tool_value_error(self):
        """测试安全装饰器（ValueError）"""
        @safe_tool
        def bad_func():
            raise ValueError("无效值")

        result = bad_func()
        assert result["success"] is False
        assert result["error_type"] == "value_error"

    def test_safe_tool_type_error(self):
        """测试安全装饰器（TypeError）"""
        @safe_tool
        def bad_func():
            raise TypeError("类型错误")

        result = bad_func()
        assert result["success"] is False
        assert result["error_type"] == "type_error"

    def test_safe_tool_generic_exception(self):
        """测试安全装饰器（通用异常）"""
        @safe_tool
        def bad_func():
            raise RuntimeError("运行时错误")

        result = bad_func()
        assert result["success"] is False
        assert result["error_type"] == "runtime"


# ============================================================
# 测试2：参数辅助模块
# ============================================================

class TestParamHelpers:
    """测试参数辅助模块"""

    def test_make_strategy_config_default(self):
        """测试策略配置构造（默认值）"""
        config = make_strategy_config("测试策略")
        assert config["name"] == "测试策略"
        assert config["ev_threshold"] == 0.05
        assert len(config["plays"]) == 5
        assert config["max_parlay"] == 4

    def test_make_strategy_config_custom(self):
        """测试策略配置构造（自定义值）"""
        config = make_strategy_config(
            "激进策略",
            ev_threshold=0.03,
            plays=["胜平负"],
            max_parlay=6,
            kelly_fraction=0.5
        )
        assert config["ev_threshold"] == 0.03
        assert config["plays"] == ["胜平负"]
        assert config["max_parlay"] == 6
        assert config["kelly_fraction"] == 0.5

    def test_make_value_option(self):
        """测试价值选项构造"""
        option = make_value_option(
            "001", "胜平负", "主胜",
            1.85, 0.58, 0.073, "主队状态火热"
        )
        assert option["match_id"] == "001"
        assert option["play"] == "胜平负"
        assert option["option"] == "主胜"
        assert option["odds"] == 1.85
        assert option["model_prob"] == 0.58
        assert option["ev"] == 0.073
        assert option["reason"] == "主队状态火热"

    def test_make_match_data(self):
        """测试比赛数据构造"""
        match = make_match_data(
            "001", "英超", "利物浦", "阿森纳",
            [1.95, 3.40, 3.80], handicap="0"
        )
        assert match["match_id"] == "001"
        assert match["league"] == "英超"
        assert match["home"] == "利物浦"
        assert match["away"] == "阿森纳"
        assert "胜平负" in match["odds"]

    def test_validate_strategy_config_pass(self):
        """测试策略配置验证（通过）"""
        config = make_strategy_config("测试")
        result = validate_strategy_config(config)
        assert result is None

    def test_validate_strategy_config_fail(self):
        """测试策略配置验证（失败）"""
        config = {"name": "测试"}  # 缺少必填字段
        result = validate_strategy_config(config)
        assert result is not None

    def test_validate_value_options_pass(self):
        """测试价值选项验证（通过）"""
        options = [make_value_option("001", "胜平负", "主胜", 1.85, 0.5, 0.1)]
        result = validate_value_options(options)
        assert result is None

    def test_validate_value_options_empty(self):
        """测试价值选项验证（空列表）"""
        result = validate_value_options([])
        assert result is not None

    def test_validate_value_options_missing_field(self):
        """测试价值选项验证（缺少字段）"""
        options = [{"match_id": "001"}]  # 缺少必填字段
        result = validate_value_options(options)
        assert result is not None


# ============================================================
# 测试3：分析引擎核心函数
# ============================================================

class TestAnalyzerCore:
    """测试分析引擎核心数学函数"""

    def test_poisson_prob(self):
        """测试泊松分布概率计算"""
        # 导入泊松函数
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'analyzer'))
        import server as analyzer

        # λ=1.5, k=1的概率应该约为0.335
        prob = analyzer.poisson_prob(1.5, 1)
        assert 0.3 < prob < 0.4

        # λ=1.5, k=0的概率应该约为0.223
        prob0 = analyzer.poisson_prob(1.5, 0)
        assert 0.2 < prob0 < 0.3

    def test_remove_vig(self):
        """测试赔率去水"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'analyzer'))
        import server as analyzer

        # 标准赔率 [2.0, 3.0, 3.5]，去水后概率和应为1
        probs, payout = analyzer.remove_vig([2.0, 3.0, 3.5])
        assert abs(sum(probs) - 1.0) < 0.01
        assert 0.85 < payout < 0.95

    def test_calculate_ev_positive(self):
        """测试EV计算（正EV）"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'analyzer'))
        import server as analyzer

        # 模型概率0.6，赔率2.0，EV = 0.6*2.0 - 1 = 0.2
        result = analyzer.calculate_ev.fn(0.6, 2.0)
        assert result["success"] is True
        assert abs(result["data"]["ev"] - 0.2) < 0.01
        assert result["data"]["value"] == "有价值"

    def test_calculate_ev_negative(self):
        """测试EV计算（负EV）"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'analyzer'))
        import server as analyzer

        # 模型概率0.4，赔率2.0，EV = 0.4*2.0 - 1 = -0.2
        result = analyzer.calculate_ev.fn(0.4, 2.0)
        assert result["success"] is True
        assert result["data"]["ev"] < 0
        assert result["data"]["value"] == "无价值"

    def test_poisson_predict(self):
        """测试泊松比分预测"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'analyzer'))
        import server as analyzer

        # 主队λ=1.5，客队λ=1.0
        result = analyzer.poisson_predict.fn(1.5, 1.0)
        assert result["success"] is True
        data = result["data"]

        # 主胜概率应大于客胜概率（因为主队λ更高）
        assert data["home_win_prob"] > data["away_win_prob"]

        # 概率和应为1
        total_prob = data["home_win_prob"] + data["draw_prob"] + data["away_win_prob"]
        assert abs(total_prob - 1.0) < 0.05

    def test_dixon_coles(self):
        """测试Dixon-Coles模型"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'analyzer'))
        import server as analyzer

        result = analyzer.dixon_coles.fn(1.5, 1.0)
        assert result["success"] is True
        data = result["data"]

        # 应该包含主胜、平局、客胜概率
        assert "home_win" in data
        assert "draw" in data
        assert "away_win" in data

    def test_conditional_prob_half_full(self):
        """测试半全场条件概率"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'analyzer'))
        import server as analyzer

        result = analyzer.conditional_prob_half_full.fn(1.5, 1.0, "normal")
        assert result["success"] is True
        data = result["data"]

        # 应该包含9种半全场结果
        assert len(data["probabilities"]) == 9

        # 应该有Top3推荐
        assert len(data["top3"]) == 3


# ============================================================
# 测试4：投注组合核心函数
# ============================================================

class TestPortfolioCore:
    """测试投注组合核心函数"""

    def test_calculate_parlay_payout(self):
        """测试串关奖金计算"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'portfolio'))
        import server as portfolio

        # 2串1，赔率[2.0, 3.0]，投注100元
        bets = [
            {"match_id": "001", "odds": 2.0},
            {"match_id": "002", "odds": 3.0},
        ]
        result = portfolio.calculate_parlay_payout.fn(bets, 100)
        assert result["success"] is True
        data = result["data"]

        # 奖金 = 100 * 2.0 * 3.0 = 600
        assert abs(data["potential_payout"] - 600) < 1
        assert data["odds_product"] == 6.0

    def test_calculate_kelly(self):
        """测试Kelly公式计算"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servers', 'analyzer'))
        import server as analyzer

        # 模型概率0.6，赔率2.0，Kelly = (0.6*2.0 - 1) / (2.0 - 1) = 0.2
        result = analyzer.calculate_kelly.fn(0.6, 2.0, 0.25)
        assert result["success"] is True
        data = result["data"]

        # 分数Kelly = 0.2 * 0.25 = 0.05
        assert abs(data["fractional_kelly"] - 0.05) < 0.01


# ============================================================
# 测试5：数据资产完整性
# ============================================================

class TestDataAssets:
    """测试数据资产完整性"""

    def test_data_files_exist(self):
        """测试数据文件存在"""
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        required_files = [
            'team_ratings.json',
            'league_features.json',
            'calibration_by_league.json',
            'lessons.json',
            'case_library.json',
            'decision_log.json',
            'strategy_params.json',
            'score_calibration.json',
            'bankroll.json',
        ]

        for filename in required_files:
            filepath = os.path.join(data_dir, filename)
            assert os.path.exists(filepath), f"数据文件不存在: {filename}"

    def test_data_files_valid_json(self):
        """测试数据文件是有效JSON"""
        import json
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

        for filename in os.listdir(data_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(data_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                assert data is not None, f"JSON文件为空: {filename}"

    def test_team_ratings_structure(self):
        """测试球队强度库结构"""
        import json
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        filepath = os.path.join(data_dir, 'team_ratings.json')

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 应该包含多支球队
        assert len(data) > 100, f"球队数量过少: {len(data)}"

    def test_lessons_structure(self):
        """测试经验库结构"""
        import json
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        filepath = os.path.join(data_dir, 'lessons.json')

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 应该包含多条经验
        assert len(data) > 10, f"经验数量过少: {len(data)}"


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
