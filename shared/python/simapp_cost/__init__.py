"""M4 BOM / 成本估算（DEV-12）。

- 数量与布局/编制一致
- 缺价列入 missingItems；可给 knownSubtotal，不给完整 total
- 缺价方案不得参与「最低成本」排序
- 新购 / 搬移 / 安装分列，不重复计费
"""

from .bom import build_bom_lines
from .estimate import COST_ENGINE_VERSION, CostError, estimate_cost
from .rank import recommend_lowest_capex

__all__ = [
    "COST_ENGINE_VERSION",
    "CostError",
    "build_bom_lines",
    "estimate_cost",
    "recommend_lowest_capex",
]
