"""M5 扩展切片：复杂识图与高级优化的明确失败/不支持路径。

本包不实现 DXF/OCR/多边形分区、NSGA-II、长期成本、扩容或运维量表。
每项能力只返回失败、待确认或不支持，以及校正动作；不产出已验证几何或分数。
"""

from .advanced import ADVANCED_CAPABILITIES, EXTEND_VERSION, assess_advanced
from .recognition import RECOGNITION_CAPABILITIES, assess_recognition

__all__ = [
    "ADVANCED_CAPABILITIES",
    "EXTEND_VERSION",
    "RECOGNITION_CAPABILITIES",
    "assess_advanced",
    "assess_recognition",
]
