"""ComparisonSet：layout_only / whole_solution + 容量/成本/雷达表格。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .radar import score_axis, select_radar_axes

COMPARE_ENGINE_VERSION = "m4-compare-0.1"

# M4 可用轴；lifecycle/expansion/operability 默认 unsupported（M5）
M4_AXIS_DEFS = {
    "storage": {
        "metricId": "effective_capacity",
        "direction": "higher_better",
        "milestone": "M2+",
    },
    "efficiency": {
        "metricId": "completed_cycle_mean",
        "direction": "lower_better",
        "milestone": "M4",
    },
    "investment": {
        "metricId": "capex",
        "direction": "lower_better",
        "milestone": "M4",
    },
    "lifecycle": {
        "metricId": "horizon_cost",
        "direction": "lower_better",
        "milestone": "M5",
        "defaultStatus": "unsupported",
    },
    "expansion": {
        "metricId": "expansion_rubric",
        "direction": "higher_better",
        "milestone": "M5",
        "defaultStatus": "unsupported",
    },
    "operability": {
        "metricId": "operability_rubric",
        "direction": "higher_better",
        "milestone": "M5",
        "defaultStatus": "unsupported",
    },
}


class CompareError(Exception):
    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resource_fingerprint(operating: Optional[Dict[str, Any]]) -> Dict[str, float]:
    if not operating:
        return {}
    out: Dict[str, float] = {}
    for pool in operating.get("resourcePools") or []:
        key = pool.get("resourceType") or pool.get("id") or "resource"
        out[str(key)] = float(pool.get("count") or 0)
    return out


def _check_mode_consistency(
    mode: str,
    entries_meta: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """layout_only：资源型号/数量须一致；否则标不可比。"""
    issues: List[Dict[str, Any]] = []
    if mode == "layout_only":
        fps = [e.get("resourceFingerprint") or {} for e in entries_meta]
        base = fps[0] if fps else {}
        for i, fp in enumerate(fps[1:], start=1):
            if fp != base:
                issues.append(
                    {
                        "code": "INCOMPARABLE_RESULTS",
                        "entryIndex": i,
                        "message": "layout_only 下资源数量/型号不一致；不强行补齐",
                        "expected": base,
                        "actual": fp,
                    }
                )
    elif mode == "whole_solution":
        # 允许资源差异，但必须披露
        fps = [e.get("resourceFingerprint") or {} for e in entries_meta]
        if len({tuple(sorted(fp.items())) for fp in fps}) > 1:
            issues.append(
                {
                    "code": "RESOURCE_DIFF_DISCLOSED",
                    "message": "whole_solution：资源差异已展示并应计费；收益不可全部归因布局",
                    "fingerprints": fps,
                }
            )
    else:
        raise CompareError("INPUT_UNCONFIRMED", f"未知 comparison mode={mode}")

    comparable = not any(i.get("code") == "INCOMPARABLE_RESULTS" for i in issues)
    return {"comparable": comparable, "issues": issues}


def _metric_bundle(entry: Dict[str, Any]) -> Dict[str, Any]:
    """从 entry 载荷抽取原始指标（不伪造）。"""
    capacity = entry.get("effectiveCapacity")
    run = entry.get("run") or {}
    kpi = (run.get("kpi") or {}).get("secondary") or {}
    cards = (run.get("kpi") or {}).get("cards") or {}
    cycle = kpi.get("completedCycleMeanSec")
    if cycle is None:
        # 兼容：若仅有 wait mean，不偷梁换柱为 cycle；保持 null
        cycle = entry.get("completedCycleMeanSec")
    cost = entry.get("costEstimate") or {}
    totals = cost.get("totals") or {}
    capex = totals.get("capex") if cost.get("status") == "complete" else None
    return {
        "effective_capacity": capacity,
        "completed_cycle_mean": cycle,
        "capex": capex,
        "outbound_throughput": (cards.get("throughput") or {}).get("value"),
        "wait_mean": (cards.get("wait") or {}).get("meanSec"),
        "costStatus": cost.get("status"),
        "costKnownSubtotal": totals.get("knownSubtotal"),
        "eligibleForLowestCostRanking": cost.get("eligibleForLowestCostRanking"),
    }


def build_comparison(
    *,
    mode: str,
    entries: List[Dict[str, Any]],
    common_basis: Dict[str, Any],
    score_profile: Optional[Dict[str, Any]] = None,
    comparison_id: Optional[str] = None,
    revision: Optional[str] = None,
) -> Dict[str, Any]:
    """构建 ComparisonSet + 可比性 + 表格 + 条件雷达。

    entries[] 期望字段：
      variantRef, layoutRef, runRef?, run?, costEstimateRef?, costEstimate?,
      operating?, effectiveCapacity?, label?
    """
    if mode not in {"layout_only", "whole_solution"}:
        raise CompareError("INPUT_UNCONFIRMED", "mode 须为 layout_only | whole_solution")
    if len(entries) < 2:
        raise CompareError("INPUT_UNCONFIRMED", "至少两个方案才能比较")

    enriched: List[Dict[str, Any]] = []
    for i, raw in enumerate(entries):
        op = raw.get("operating")
        fp = _resource_fingerprint(op)
        metrics = _metric_bundle(raw)
        axis_scores: Dict[str, Any] = {}
        axis_status: Dict[str, str] = {}

        profile_axes = (score_profile or {}).get("axes") or {}
        for axis_id, axis_def in M4_AXIS_DEFS.items():
            if axis_def.get("defaultStatus") == "unsupported":
                axis_status[axis_id] = "unsupported"
                axis_scores[axis_id] = {
                    "status": "unsupported",
                    "score": None,
                    "metricId": axis_def["metricId"],
                }
                continue

            metric_id = axis_def["metricId"]
            value = metrics.get(metric_id)
            # investment：缺价 → missing，不补 0
            if axis_id == "investment" and (raw.get("costEstimate") or {}).get("status") != "complete":
                axis_status[axis_id] = "missing"
                axis_scores[axis_id] = {
                    "status": "missing",
                    "score": None,
                    "metricId": metric_id,
                    "value": None,
                    "note": "缺价不补零，不参与投资轴",
                }
                continue

            anchors = profile_axes.get(axis_id)
            if value is None:
                axis_status[axis_id] = "missing"
                axis_scores[axis_id] = {
                    "status": "missing",
                    "score": None,
                    "metricId": metric_id,
                    "value": None,
                }
                continue
            if not anchors:
                # 有原始值但无锚点 → 只显示原始，不算分
                axis_status[axis_id] = "raw_only"
                axis_scores[axis_id] = {
                    "status": "raw_only",
                    "score": None,
                    "metricId": metric_id,
                    "value": value,
                    "note": "锚点未确认；只显示原始指标",
                }
                continue

            scored = score_axis(
                float(value),
                direction=anchors.get("direction") or axis_def["direction"],
                bad=float(anchors["bad"]),
                good=float(anchors["good"]),
            )
            if scored["status"] == "available":
                axis_status[axis_id] = "available"
            else:
                axis_status[axis_id] = scored["status"]
            axis_scores[axis_id] = {**scored, "metricId": metric_id}

        # raw_only 对雷达不算 available
        radar_status = {
            k: ("available" if v == "available" else v) for k, v in axis_status.items()
        }

        enriched.append(
            {
                "entryId": raw.get("entryId") or f"entry-{i+1}",
                "label": raw.get("label") or (raw.get("variantRef") or {}).get("id"),
                "variantRef": raw.get("variantRef"),
                "layoutRef": raw.get("layoutRef"),
                "runRef": raw.get("runRef")
                or ({"runId": (raw.get("run") or {}).get("runId")} if raw.get("run") else None),
                "costEstimateRef": raw.get("costEstimateRef")
                or (
                    {"id": (raw.get("costEstimate") or {}).get("id")}
                    if raw.get("costEstimate")
                    else None
                ),
                "resourceFingerprint": fp,
                "metrics": metrics,
                "axisScores": axis_scores,
                "axisStatus": radar_status,
                "hardGatePass": raw.get("hardGatePass", True),
            }
        )

    mode_check = _check_mode_consistency(mode, enriched)
    radar = select_radar_axes([e["axisStatus"] for e in enriched])

    # 雷达多边形：仅 commonAxes；缺轴不闭合伪完整图
    radar_series: List[Dict[str, Any]] = []
    if radar["radarEnabled"]:
        for e in enriched:
            points = []
            for ax in radar["commonAxes"]:
                sc = e["axisScores"].get(ax) or {}
                points.append({"axisId": ax, "score": sc.get("score")})
            radar_series.append(
                {
                    "entryId": e["entryId"],
                    "label": e["label"],
                    "points": points,
                }
            )

    table_rows = []
    for e in enriched:
        m = e["metrics"]
        table_rows.append(
            {
                "entryId": e["entryId"],
                "label": e["label"],
                "effectiveCapacity": m.get("effective_capacity"),
                "completedCycleMeanSec": m.get("completed_cycle_mean"),
                "outboundThroughput": m.get("outbound_throughput"),
                "waitMeanSec": m.get("wait_mean"),
                "capex": m.get("capex"),
                "costStatus": m.get("costStatus"),
                "costKnownSubtotal": m.get("costKnownSubtotal"),
                "resourceFingerprint": e["resourceFingerprint"],
                "layoutRevision": (e.get("layoutRef") or {}).get("revision"),
                "runId": (e.get("runRef") or {}).get("runId"),
            }
        )

    return {
        "contractVersion": "0.3",
        "id": comparison_id or f"cmp-{uuid4().hex[:10]}",
        "revision": revision or f"cr-{uuid4().hex[:6]}",
        "compareEngineVersion": COMPARE_ENGINE_VERSION,
        "mode": mode,
        "commonBasis": common_basis,
        "scoreProfileRef": (
            {"id": score_profile.get("id"), "revision": score_profile.get("revision")}
            if score_profile
            else None
        ),
        "scoreProfileLocked": bool(score_profile),
        "entries": [
            {
                "entryId": e["entryId"],
                "label": e["label"],
                "variantRef": e["variantRef"],
                "layoutRef": e["layoutRef"],
                "runRef": e["runRef"],
                "costEstimateRef": e["costEstimateRef"],
                "resourceFingerprint": e["resourceFingerprint"],
                "metrics": e["metrics"],
                "axisScores": e["axisScores"],
                "hardGatePass": e["hardGatePass"],
            }
            for e in enriched
        ],
        "comparability": mode_check,
        "radar": {
            **radar,
            "series": radar_series,
            "note": "缺失值不绘为 0；不以雷达面积求总分",
        },
        "table": {"rows": table_rows},
        "computedAt": _now(),
        "kpiFromUiDemo": False,
    }
