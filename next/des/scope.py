"""Types this manual slice will place but will not pretend to simulate."""

from __future__ import annotations

from typing import Iterable, List

# Conveyors, AGV, cranes, and the P1 auto decant cell have no runtime here.
_EXACT = {
    "MH-AGV-01",
    "MH-CHG-01",
    "MH-WAIT-01",
    "MH-CRANE-01",
    "MH-HOIST-01",
    "MH-XFER-01",
    "ST-ASRS-01",
    "PK-DEPAL-AUTO-01",
}


def is_unsimulated(type_id: str) -> bool:
    return type_id.startswith("CV-") or type_id in _EXACT


def unsimulated_ids(type_ids: Iterable[str]) -> List[str]:
    found = []
    seen = set()
    for type_id in type_ids:
        if type_id and is_unsimulated(type_id) and type_id not in seen:
            seen.add(type_id)
            found.append(type_id)
    return found


def unsimulated_message(type_ids: Iterable[str]) -> str:
    shown = "、".join(unsimulated_ids(type_ids))
    return f"本切片暂不仿真该类：{shown}。可以保存落位，但不会为这些类型编造四卡。"
