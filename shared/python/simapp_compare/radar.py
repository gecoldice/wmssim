"""雷达轴评分：缺失不补零；锚点锁定；超出截断。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def score_axis(
    value: Optional[float],
    *,
    direction: str,
    bad: float,
    good: float,
) -> Dict[str, Any]:
    """返回 score(0–100) 或 status=missing/invalid。缺值不绘为 0。"""
    if value is None:
        return {"status": "missing", "score": None, "value": None}

    if direction == "higher_better":
        if not (good > bad):
            return {
                "status": "invalid",
                "score": None,
                "value": value,
                "code": "SCORE_PROFILE_INVALID",
                "message": "higher_better 要求 good > bad",
            }
        span = good - bad
        raw = (float(value) - bad) / span
    elif direction == "lower_better":
        if not (bad > good):
            return {
                "status": "invalid",
                "score": None,
                "value": value,
                "code": "SCORE_PROFILE_INVALID",
                "message": "lower_better 要求 bad > good",
            }
        span = bad - good
        raw = (bad - float(value)) / span
    else:
        return {
            "status": "invalid",
            "score": None,
            "value": value,
            "code": "SCORE_PROFILE_INVALID",
            "message": f"未知 direction={direction}",
        }

    score = 100.0 * max(0.0, min(1.0, raw))
    return {
        "status": "available",
        "score": score,
        "value": float(value),
        "clamped": raw < 0.0 or raw > 1.0,
    }


def select_radar_axes(
    entry_axis_statuses: Sequence[Dict[str, str]],
    *,
    axis_order: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """共同对所有方案 available 的轴；不足 3 → radarEnabled=False。

    entry_axis_statuses: 每个 entry 一份 {axisId: status}
    """
    order = axis_order or [
        "storage",
        "efficiency",
        "investment",
        "lifecycle",
        "expansion",
        "operability",
    ]
    if not entry_axis_statuses:
        return {
            "radarEnabled": False,
            "commonAxes": [],
            "reason": "no_entries",
            "message": "无方案；不显示雷达",
        }

    common: List[str] = []
    for axis in order:
        if all(st.get(axis) == "available" for st in entry_axis_statuses):
            common.append(axis)

    if len(common) < 3:
        return {
            "radarEnabled": False,
            "commonAxes": common,
            "reason": "insufficient_common_axes",
            "message": "共同有效轴不足 3 个；仅显示表格，缺轴不补零",
        }
    return {
        "radarEnabled": True,
        "commonAxes": common,
        "reason": None,
        "message": f"当前轴集：{', '.join(common)}",
    }
