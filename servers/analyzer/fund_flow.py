#!/usr/bin/env python3
"""
竞彩资金流分析模块
来源：lottery-data项目 jc_fund_flow.py + jc_signal.py 整合
核心逻辑：多时段SP变化 → 资金流入方向信号

竞彩SP虽为"官方定价"，但销售期内会随投注量阶段性调整。
多时段SP变化 = 市场资金流向信号（SP下降=该选项资金流入）。

用法：
    from fund_flow import FundFlowAnalyzer
    analyzer = FundFlowAnalyzer()
    result = analyzer.analyze_timeline(snapshots)
"""
from typing import Dict, List, Optional


# 判定资金流入的SP下降阈值（竞彩SP调整幅度小，用0.5%敏感阈值）
DROP_THRESHOLD = 0.005

# 选项标签
LABELS = {"home": "主胜", "draw": "平局", "away": "客胜"}


class FundFlowAnalyzer:
    """竞彩资金流分析（多时段SP变化 → 信号）"""

    def analyze_timeline(self, snapshots: List[Dict]) -> Dict:
        """
        分析一场比赛的多时段SP资金流

        Args:
            snapshots: 多时段SP快照列表，按时间排序，每个元素格式：
                {
                    "captured_at": "2026-09-06T11:15:00",
                    "hda": {"home": 1.80, "draw": 3.20, "away": 3.50}
                }
                也支持直接 {"home":1.80,"draw":3.20,"away":3.50} 格式

        Returns:
            {
                "slots": 时段数,
                "first": 初盘SP,
                "latest": 最新SP,
                "changes": 各选项变化详情,
                "signal": 资金流信号描述,
                "direction": 资金流入方向(home/draw/away/none),
                "strength": 信号强度(0-3)
            }
        """
        if not snapshots or len(snapshots) < 2:
            return {"slots": len(snapshots) if snapshots else 0, "signal": "样本不足（需至少2个时段）", "direction": "none", "strength": 0}

        # 标准化提取hda
        timeline = []
        for snap in snapshots:
            hda = snap.get("hda", snap) if isinstance(snap, dict) else None
            if hda and hda.get("home"):
                timeline.append({
                    "captured_at": snap.get("captured_at", ""),
                    "home": float(hda["home"]),
                    "draw": float(hda["draw"]),
                    "away": float(hda["away"]),
                })

        if len(timeline) < 2:
            return {"slots": len(timeline), "signal": "样本不足（有效时段<2）", "direction": "none", "strength": 0}

        first, latest = timeline[0], timeline[-1]
        changes = {}
        for key in ("home", "draw", "away"):
            f, l = first[key], latest[key]
            drop = (f - l) / f if f else 0  # 正=下降=资金流入
            changes[key] = {
                "first": f, "latest": l,
                "change_pct": round((l - f) / f * 100, 2),
                "drop": round(drop, 4),
            }

        # 资金流入方向（下降最多的选项）
        direction = max(changes, key=lambda k: changes[k]["drop"])
        max_drop = changes[direction]["drop"]

        # 信号强度
        if max_drop >= 0.02:
            strength = 3
            signal = f"强资金流入：{LABELS[direction]}（SP {changes[direction]['first']}→{changes[direction]['latest']}，降幅{max_drop*100:.1f}%）"
        elif max_drop >= DROP_THRESHOLD:
            strength = 2
            signal = f"资金流入：{LABELS[direction]}（SP {changes[direction]['first']}→{changes[direction]['latest']}，降幅{max_drop*100:.1f}%）"
        elif max_drop >= 0.002:
            strength = 1
            signal = f"微弱资金流入：{LABELS[direction]}（降幅{max_drop*100:.1f}%，信号较弱）"
        else:
            strength = 0
            direction = "none"
            signal = "无明显资金流（SP变动<0.2%）"

        return {
            "slots": len(timeline),
            "first": {"home": first["home"], "draw": first["draw"], "away": first["away"]},
            "latest": {"home": latest["home"], "draw": latest["draw"], "away": latest["away"]},
            "changes": changes,
            "signal": signal,
            "direction": direction,
            "direction_label": LABELS.get(direction, "无"),
            "strength": strength,
            "interpretation": self._interpret(direction, strength, changes),
        }

    def _interpret(self, direction: str, strength: int, changes: Dict) -> str:
        """资金流信号解读"""
        if strength == 0:
            return "SP稳定，市场分歧不大，无明显资金偏向"
        if strength >= 2:
            label = LABELS.get(direction, "")
            other = [k for k in ("home", "draw", "away") if k != direction]
            other_changes = [changes[k]["change_pct"] for k in other]
            return f"{label}受资金追捧（SP下降），其他选项SP{'上升' if any(c > 0 for c in other_changes) else '变动不大'}。注意：资金流入≠必胜，需结合基本面判断是真实看好还是诱盘。"
        return "有轻微资金偏向，但信号不强，需结合其他维度综合判断"

    def batch_analyze(self, matches_timeline: Dict[str, List[Dict]], min_slots: int = 3) -> List[Dict]:
        """
        批量分析多场比赛的资金流

        Args:
            matches_timeline: {match_num: [snapshot1, snapshot2, ...]}
            min_slots: 最少时段数

        Returns:
            有信号的比赛列表，按信号强度降序
        """
        results = []
        for match_num, snapshots in matches_timeline.items():
            if len(snapshots) < min_slots:
                continue
            r = self.analyze_timeline(snapshots)
            r["match_num"] = match_num
            if r.get("strength", 0) >= 1:
                results.append(r)
        results.sort(key=lambda x: x.get("strength", 0), reverse=True)
        return results


def analyze_fund_flow(snapshots: List[Dict]) -> Dict:
    """便捷函数：单场资金流分析"""
    return FundFlowAnalyzer().analyze_timeline(snapshots)
