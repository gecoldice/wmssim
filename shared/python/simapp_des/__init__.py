"""M3 真实运营推演 DES（DEV-10/11）。

- 只读 LayoutSnapshot 0.2；不反写几何
- 确定性：同快照/场景/种子/引擎版本 → 同结果
- 路径 = 通道图最短路；拥堵只等待不改路
- FIFO + 空闲最久；主四卡由事件派生
- faultInject / skillTags：契约占位，忽略并告警
"""

from .engine import ENGINE_VERSION, METRIC_DEFINITION_VERSION, DesEngine, DesError, run_des
from .graph import shortest_path, build_adjacency
from .inventory import InventoryError, InventoryLedger
from .kpi import compute_kpi

__all__ = [
    "ENGINE_VERSION",
    "METRIC_DEFINITION_VERSION",
    "DesEngine",
    "DesError",
    "run_des",
    "shortest_path",
    "build_adjacency",
    "InventoryError",
    "InventoryLedger",
    "compute_kpi",
]
