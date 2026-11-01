"""从 LayoutDocument + OperatingProfile 派生 BOM 行（数量口径）。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional


def build_bom_lines(
    layout: Dict[str, Any],
    *,
    operating: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """按 typeElementId × assetDisposition 聚合设备；另加资源池人头/台数。

    返回行：
      lineId, category (equipment|labor|install|relocate),
      skuKey, qty, unit, disposition, sourceRefs
    """
    lines: List[Dict[str, Any]] = []
    buckets: Dict[tuple, List[str]] = defaultdict(list)

    for el in layout.get("elements") or []:
        type_id = el.get("typeElementId") or "UNKNOWN"
        disposition = el.get("assetDisposition") or "new"
        # 契约枚举：existing | new | relocated | removed
        if disposition not in {"new", "existing", "relocated", "removed"}:
            disposition = "new"
        if disposition == "removed":
            continue
        key = (type_id, disposition)
        buckets[key].append(el.get("instanceId") or "")

    seq = 0
    for (type_id, disposition), instance_ids in sorted(buckets.items()):
        seq += 1
        category = "equipment"
        if disposition == "relocated":
            category = "relocate"
        lines.append(
            {
                "lineId": f"bom-{seq:03d}",
                "category": category,
                "skuKey": type_id,
                "qty": float(len(instance_ids)),
                "unit": "ea",
                "disposition": disposition,
                "sourceRefs": {
                    "instanceIds": [i for i in instance_ids if i],
                    "layoutId": layout.get("id"),
                    "layoutRevision": layout.get("revision"),
                },
            }
        )

    if operating:
        for pool in operating.get("resourcePools") or []:
            seq += 1
            rtype = pool.get("resourceType") or pool.get("id") or "resource"
            count = float(pool.get("count") or 0)
            lines.append(
                {
                    "lineId": f"bom-{seq:03d}",
                    "category": "labor" if rtype in {"operator", "picker", "labor"} else "resource",
                    "skuKey": f"resource:{rtype}",
                    "qty": count,
                    "unit": "ea",
                    "disposition": "operating",
                    "sourceRefs": {
                        "poolId": pool.get("id"),
                        "operatingId": operating.get("id"),
                        "operatingRevision": operating.get("revision"),
                    },
                }
            )

    return lines
