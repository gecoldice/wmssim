"""主四卡：吞吐 / 等待 / 利用率 / 瓶颈 — 仅从事件与任务样本计算，无 UI 演示公式。"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence


def _mean(xs: Sequence[float]) -> Optional[float]:
    if not xs:
        return None
    return sum(xs) / len(xs)


def _p95_order_stat(xs: Sequence[float]) -> Dict[str, Any]:
    """ceil(0.95*n) 1-based；n<20 不报 P95。"""
    n = len(xs)
    if n < 20:
        return {"value": None, "sampleInsufficient": True, "n": n, "rule": "n<20 → 不报 P95"}
    ordered = sorted(xs)
    idx = int(math.ceil(0.95 * n)) - 1  # 0-based
    idx = max(0, min(n - 1, idx))
    return {
        "value": ordered[idx],
        "sampleInsufficient": False,
        "n": n,
        "orderIndex1Based": idx + 1,
        "rule": "ceil(0.95*n) order statistic",
    }


def compute_kpi(
    *,
    horizon_sec: float,
    completed_tasks: Sequence[Dict[str, Any]],
    resources: Sequence[Dict[str, Any]],
    entity_wait_sec: Dict[str, float],
    outbound_pallet_eq: float,
    incomplete_count: int,
) -> Dict[str, Any]:
    horizon_h = horizon_sec / 3600.0 if horizon_sec > 0 else 0.0
    wait_samples = [float(t.get("waitSec") or 0) for t in completed_tasks]
    wait_mean = _mean(wait_samples)
    p95 = _p95_order_stat(wait_samples)

    n_res = len(resources)
    busy_sum = sum(float(r.get("busySec") or 0) for r in resources)
    if n_res == 0 or horizon_sec <= 0:
        util = None
        util_note = "0 资源或不适用；不除零"
    else:
        util = busy_sum / (n_res * horizon_sec)
        util_note = "busySec合计 / (资源数 × horizonSec)"

    total_entity_wait = sum(entity_wait_sec.values())
    bottleneck: Optional[Dict[str, Any]] = None
    top_n: List[Dict[str, Any]] = []
    if total_entity_wait > 1e-9:
        ranked = sorted(entity_wait_sec.items(), key=lambda kv: (-kv[1], kv[0]))
        for ent, contrib in ranked[:5]:
            top_n.append(
                {
                    "entityId": ent,
                    "waitSec": contrib,
                    "share": contrib / total_entity_wait,
                }
            )
        if top_n:
            bottleneck = {
                "entityId": top_n[0]["entityId"],
                "waitSec": top_n[0]["waitSec"],
                "share": top_n[0]["share"],
            }
    else:
        bottleneck = {
            "entityId": None,
            "waitSec": 0.0,
            "share": 0.0,
            "note": "无显著等待",
        }

    throughput = (outbound_pallet_eq / horizon_h) if horizon_h > 0 else None

    cards = {
        "throughput": {
            "value": throughput,
            "unit": "palletEq/h",
            "definition": "外部发运完成托盘当量 / (horizonSec/3600)；拆托中间产出不计",
            "outboundPalletEq": outbound_pallet_eq,
            "horizonSec": horizon_sec,
            "evidenceEventKinds": ["outbound", "task_complete"],
        },
        "wait": {
            "meanSec": wait_mean,
            "p95Sec": p95["value"],
            "p95Meta": p95,
            "sampleCount": len(wait_samples),
            "definition": "已完成任务生命周期等待秒均值；仅完成任务",
            "unit": "s",
        },
        "utilization": {
            "value": util,
            "unit": "ratio",
            "busySecTotal": busy_sum,
            "resourceCount": n_res,
            "note": util_note,
            "definition": "各资源 busySec 之和 / (资源数 × horizonSec)",
        },
        "bottleneck": {
            "top1": bottleneck,
            "topN": top_n,
            "definition": "实体累计等待秒贡献 TopN（边/工位/资源池）",
        },
    }

    return {
        "cards": cards,
        "secondary": {
            "completedTasks": len(completed_tasks),
            "incompleteTasks": incomplete_count,
            "completionRate": (
                len(completed_tasks) / (len(completed_tasks) + incomplete_count)
                if (len(completed_tasks) + incomplete_count) > 0
                else None
            ),
        },
        "kpiFromUiDemo": False,
    }


def kpi_event_evidence(
    events: Sequence[Dict[str, Any]],
    *,
    outbound_event_ids: Sequence[str],
    completed_task_ids: Sequence[str],
) -> Dict[str, Any]:
    """把四卡数值追到事件/任务 ID，供 UI 证据链。"""
    by_id = {e["eventId"]: e for e in events if "eventId" in e}
    outbound_ev = [by_id[i] for i in outbound_event_ids if i in by_id]
    return {
        "outboundEvents": [
            {
                "eventId": e["eventId"],
                "t": e.get("t"),
                "taskId": e.get("taskId"),
                "palletEq": e.get("palletEq"),
            }
            for e in outbound_ev
        ],
        "completedTaskIds": list(completed_task_ids),
        "note": "吞吐由 outbound 事件求和；等待由已完成任务 waitSec 样本；利用率由资源 busySec",
    }
