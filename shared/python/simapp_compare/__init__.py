"""M4 多方案比较与交付报告（DEV-13/14）。

- layout_only vs whole_solution
- 雷达：缺轴不补零；共同有效轴 <3 仅表格
- 加入方案不改既有绝对分（ScoreProfile 锚点锁定）
- 报告绑定历史 layoutRevision / run / costEstimate
"""

from .compare import COMPARE_ENGINE_VERSION, CompareError, build_comparison
from .radar import score_axis, select_radar_axes
from .recommend import recommend_capacity, recommend_from_comparison
from .report import build_delivery_report

__all__ = [
    "COMPARE_ENGINE_VERSION",
    "CompareError",
    "build_comparison",
    "score_axis",
    "select_radar_axes",
    "recommend_capacity",
    "recommend_from_comparison",
    "build_delivery_report",
]
