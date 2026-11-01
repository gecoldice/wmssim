"""Four cards from completed-task samples. P95 is nearest-rank for every n>=1."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence


def mean(xs: Sequence[float]) -> Optional[float]:
    if not xs:
        return None
    return sum(xs) / len(xs)


def nearest_rank_p95(xs: Sequence[float]) -> Optional[float]:
    """1-based rank ceil(0.95*n). n=0 → null. n=1 still returns the only sample."""
    n = len(xs)
    if n == 0:
        return None
    ordered = sorted(float(x) for x in xs)
    rank = int(math.ceil(0.95 * n))
    rank = max(1, min(n, rank))
    return ordered[rank - 1]


def compute_cards(
    *,
    horizon_sec: float,
    completed: Sequence[Dict[str, Any]],
    resources: Sequence[Dict[str, Any]],
    entity_wait_sec: Dict[str, float],
    outbound_pallet_eq: float,
    incomplete_count: int,
) -> Dict[str, Any]:
    waits = [float(t["waitSec"]) for t in completed]
    horizon_h = horizon_sec / 3600.0 if horizon_sec > 0 else 0.0
    throughput = (outbound_pallet_eq / horizon_h) if horizon_h > 0 else None

    by_resource: List[Dict[str, Any]] = []
    grouped: Dict[str, Dict[str, float]] = {}
    for res in resources:
        rtype = str(res["resourceType"])
        busy = float(res.get("busySec") or 0)
        util = (busy / horizon_sec) if horizon_sec > 0 else None
        by_resource.append(
            {
                "resourceId": res["resourceId"],
                "resourceType": rtype,
                "busySec": busy,
                "utilization": util,
            }
        )
        bucket = grouped.setdefault(rtype, {"busySec": 0.0, "count": 0.0})
        bucket["busySec"] += busy
        bucket["count"] += 1.0
    by_type: List[Dict[str, Any]] = []
    for rtype in sorted(grouped):
        count = int(grouped[rtype]["count"])
        busy = grouped[rtype]["busySec"]
        denom = count * horizon_sec
        by_type.append(
            {
                "resourceType": rtype,
                "resourceCount": count,
                "busySec": busy,
                "utilization": (busy / denom) if denom > 0 else None,
            }
        )

    positive = [(ent, sec) for ent, sec in entity_wait_sec.items() if sec > 1e-9]
    positive.sort(key=lambda kv: (-kv[1], kv[0]))
    total_wait = sum(sec for _, sec in positive)
    top_n: List[Dict[str, Any]] = []
    if total_wait > 1e-9:
        for ent, sec in positive[:5]:
            top_n.append({"entityId": ent, "waitSec": sec, "share": sec / total_wait})

    done_n = len(completed)
    total_tasks = done_n + incomplete_count
    cards = {
        "throughput": {
            "value": throughput,
            "unit": "palletEq/h",
            "outboundPalletEq": outbound_pallet_eq,
            "horizonSec": horizon_sec,
            "definition": "外部发运托当量 / (horizonSec/3600)；无评价时长则为 null",
        },
        "wait": {
            "meanSec": mean(waits),
            "p95Sec": nearest_rank_p95(waits),
            "sampleCount": done_n,
            "unit": "s",
            "p95Rule": "nearest-rank ceil(0.95*n); n=0 → null; n>=1 always reports",
            "definition": "已完成任务的资源等待秒。无完成任务时均值与 P95 均为 null",
        },
        "utilization": {
            "byResourceType": by_type,
            "byResource": by_resource,
            "unit": "ratio",
            "definition": "资源占用秒 / 评价时长，按资源类型与资源 id 分列，不给无类型混合比",
        },
        "bottleneck": {
            "topN": top_n,
            "definition": "已结束的等待按实体汇总。无正等待样本时 topN 为空数组",
        },
    }
    return {
        "cards": cards,
        "secondary": {
            "completedTasks": done_n,
            "incompleteTasks": incomplete_count,
            "completionRate": (done_n / total_tasks) if total_tasks > 0 else None,
        },
    }
