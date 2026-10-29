"""M2 可选自动规划：场地确认门禁、基线规划器、锁定/局部重排、快速几何评估。

DEC-05 首期：常温、单层、轴对齐矩形场地/障碍、标准托盘存储。
evaluationLevel=quick 仅几何/路径估算，不宣称运营效率（待 M3 DES）。
"""

from __future__ import annotations

from .confirm import (
    FACILITY_CONFIRMED,
    assert_facility_usable_for_planning,
    facility_confirmation_status,
    scale_declared,
)
from .planner import PLANNER_VERSION, run_planning_job
from .locks import (
    assert_locks_preserved,
    element_pose_params,
    merge_region_layout,
    point_in_polygon,
)
from .adopt import adopt_candidate, build_diff

__all__ = [
    "FACILITY_CONFIRMED",
    "PLANNER_VERSION",
    "assert_facility_usable_for_planning",
    "assert_locks_preserved",
    "adopt_candidate",
    "build_diff",
    "element_pose_params",
    "facility_confirmation_status",
    "merge_region_layout",
    "point_in_polygon",
    "run_planning_job",
    "scale_declared",
]
