"""基线规划器（DEV-08）：模板枚举 + 有限搜索 + 派生校验 + 快速几何评估。

输出真实可编辑 ST-PAL-01 / dock 布局，非示意位图。
quick 评估仅几何容量与路径长度估算，明确非运营效率证明。
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from simapp_derive import DERIVATION_VERSION, derive_layout_snapshot, input_fingerprint
from simapp_validate import is_simulation_ready, validate_layout

from .confirm import FacilityGateError, assert_facility_usable_for_planning, boundary_bbox
from .locks import LockConflictError, assert_locks_preserved, merge_region_layout
from .adopt import build_diff

PLANNER_VERSION = "m2-plan-baseline-0.1"
RACK_TYPE = "ST-PAL-01"
RACK_W, RACK_D = 2.7, 1.2
AISLE_WIDTH = 3.5
CLEAR = 0.4
LEVELS_DEFAULT = 4
PALLETS_PER_BAY = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fp(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _opening_mid(opening: Dict[str, Any]) -> Tuple[float, float]:
    seg = opening.get("segment") or []
    if len(seg) < 2:
        return (0.0, 0.0)
    return (
        (float(seg[0]["x"]) + float(seg[1]["x"])) / 2.0,
        (float(seg[0]["y"]) + float(seg[1]["y"])) / 2.0,
    )


def _place_docks(facility: Dict[str, Any]) -> List[Dict[str, Any]]:
    docks: List[Dict[str, Any]] = []
    min_x, _, max_x, _ = boundary_bbox(facility)
    mid_x = (min_x + max_x) / 2.0
    for op in facility.get("openings") or []:
        mx, my = _opening_mid(op)
        role = op.get("role") or "other"
        # 门内侧：靠场地中心一侧偏移 1.5m
        inward = 1.5 if mx <= mid_x else -1.5
        x = mx + inward
        if role == "recv":
            docks.append(
                {
                    "instanceId": f"dock-recv-{op.get('id', 'x')}",
                    "typeElementId": "IN-DOCK-01",
                    "pose": {"x": round(x, 3), "y": round(my, 3), "yawDeg": 0},
                    "params": {},
                    "assetDisposition": "new",
                }
            )
        elif role == "ship":
            docks.append(
                {
                    "instanceId": f"dock-ship-{op.get('id', 'x')}",
                    "typeElementId": "OUT-DOCK-01",
                    "pose": {"x": round(x, 3), "y": round(my, 3), "yawDeg": 180},
                    "params": {},
                    "assetDisposition": "new",
                }
            )
    if not docks:
        # 无门时默认左右
        min_x, min_y, max_x, max_y = boundary_bbox(facility)
        cy = (min_y + max_y) / 2.0
        docks = [
            {
                "instanceId": "dock-recv-default",
                "typeElementId": "IN-DOCK-01",
                "pose": {"x": min_x + 1.5, "y": round(cy, 3), "yawDeg": 0},
                "params": {},
                "assetDisposition": "new",
            },
            {
                "instanceId": "dock-ship-default",
                "typeElementId": "OUT-DOCK-01",
                "pose": {"x": max_x - 1.5, "y": round(cy, 3), "yawDeg": 180},
                "params": {},
                "assetDisposition": "new",
            },
        ]
    return docks


def _obstacle_aabbs(facility: Dict[str, Any]) -> List[Tuple[float, float, float, float]]:
    boxes: List[Tuple[float, float, float, float]] = []
    for obs in facility.get("obstacles") or []:
        outer = (obs.get("polygon") or {}).get("outer") or []
        if not outer:
            continue
        xs = [float(p["x"]) for p in outer]
        ys = [float(p["y"]) for p in outer]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    return boxes


def _overlaps_obstacle(
    cx: float, cy: float, w: float, d: float, obstacles: Sequence[Tuple[float, float, float, float]]
) -> bool:
    hw, hd = w / 2.0, d / 2.0
    a = (cx - hw, cy - hd, cx + hw, cy + hd)
    for o in obstacles:
        if not (a[2] <= o[0] or o[2] <= a[0] or a[3] <= o[1] or o[3] <= a[1]):
            return True
    return False


def _enumerate_rack_configs(
    facility: Dict[str, Any],
    *,
    yaw_deg: int,
    n_rows: int,
    bays_per_row: int,
    seed: int,
) -> Optional[Dict[str, Any]]:
    """在场地内按主通道 + 货架排摆放 ST-PAL-01。"""
    min_x, min_y, max_x, max_y = boundary_bbox(facility)
    obstacles = _obstacle_aabbs(facility)
    margin = 2.5  # 留出 dock/边通道
    # 主通道沿长边（x）居中
    aisle_y = round((min_y + max_y) / 2.0, 3)
    usable_x0, usable_x1 = min_x + margin, max_x - margin
    usable_y0, usable_y1 = min_y + margin, max_y - margin

    if yaw_deg % 180 == 0:
        rack_w, rack_d = RACK_W, RACK_D
    else:
        rack_w, rack_d = RACK_D, RACK_W  # 90° 交换 footprint 占用

    pitch_x = rack_w + CLEAR
    # 南北两侧各 n_rows 排；通道两侧各留 AISLE_WIDTH/2
    half_aisle = AISLE_WIDTH / 2.0
    elements: List[Dict[str, Any]] = []
    elements.extend(_place_docks(facility))

    row_offset = rack_d / 2.0 + half_aisle + CLEAR
    placed = 0
    for side, sign in (("N", 1.0), ("S", -1.0)):
        for r in range(n_rows):
            cy = aisle_y + sign * (row_offset + r * (rack_d + CLEAR))
            if cy - rack_d / 2 < usable_y0 or cy + rack_d / 2 > usable_y1:
                continue
            # 沿 X 摆 bays
            total_w = bays_per_row * pitch_x - CLEAR
            start_x = (usable_x0 + usable_x1) / 2.0 - total_w / 2.0 + rack_w / 2.0
            for b in range(bays_per_row):
                cx = start_x + b * pitch_x
                if cx - rack_w / 2 < usable_x0 or cx + rack_w / 2 > usable_x1:
                    continue
                if _overlaps_obstacle(cx, cy, rack_w, rack_d, obstacles):
                    continue
                placed += 1
                elements.append(
                    {
                        "instanceId": f"rack-{side}{r}-{b}-s{seed}",
                        "typeElementId": RACK_TYPE,
                        "pose": {
                            "x": round(cx, 3),
                            "y": round(cy, 3),
                            "yawDeg": float(yaw_deg),
                        },
                        "params": {
                            "levels": LEVELS_DEFAULT,
                            "bays": 1,
                            "palletsPerBay": PALLETS_PER_BAY,
                            "minClearWidthM": AISLE_WIDTH,
                            "footprintW": RACK_W,
                            "footprintD": RACK_D,
                        },
                        "assetDisposition": "new",
                    }
                )

    if placed == 0:
        return None

    aisle = {
        "id": "aisle-main",
        "centerline": [
            {"x": round(usable_x0, 3), "y": aisle_y},
            {"x": round(usable_x1, 3), "y": aisle_y},
        ],
        "widthM": AISLE_WIDTH,
    }
    return {"elements": elements, "aisles": [aisle], "rackCount": placed}


def _quick_metrics(snapshot: Dict[str, Any], demand: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """快速几何/路径估算 — 非运营 KPI，不宣称吞吐/等待/利用率。"""
    capacity = 0
    for e in snapshot.get("elements") or []:
        if e.get("kind") == "slot":
            capacity += int(e.get("capacityPallets") or 0)
    edge_len = sum(float(ed.get("lengthM") or 0.0) for ed in snapshot.get("edges") or [])
    target = None
    if demand:
        for inv in demand.get("inventoryTargets") or []:
            if inv.get("unit") == "pallet":
                target = (target or 0) + int(inv.get("quantity") or 0)
    gap = None if target is None else max(0, target - capacity)
    return {
        "evaluationLevel": "quick",
        "claimsOperationalEfficiency": False,
        "note": "几何容量与通道路径长度估算；运营效率需 M3 DES，不得据此宣称已验证",
        "metrics": {
            "geometricPalletCapacity": {
                "value": capacity,
                "unit": "pallet",
                "status": "estimated",
                "basis": "slot.capacityPallets from derive",
            },
            "aisleGraphLengthM": {
                "value": round(edge_len, 3),
                "unit": "m",
                "status": "estimated",
                "basis": "sum of derived aisle edge lengths",
            },
            "inventoryTargetGapPallets": {
                "value": gap,
                "unit": "pallet",
                "status": "estimated" if gap is not None else "unknown",
                "basis": "inventoryTargets − geometric capacity",
            },
        },
    }


def _empty_base_layout(facility: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "contractVersion": "0.3",
        "id": "layout-empty",
        "revision": "ld-empty",
        "facilityRef": {"id": facility["id"], "revision": facility["revision"]},
        "parentRef": None,
        "elements": [],
        "aisles": [],
        "locks": [],
        "catalogVersion": "catalog-mvp@c-r1",
    }


def run_planning_job(
    request: Dict[str, Any],
    *,
    facility: Dict[str, Any],
    base_layout: Optional[Dict[str, Any]] = None,
    demand: Optional[Dict[str, Any]] = None,
    drawing: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """同步执行规划任务；返回 job + candidates。"""
    job_id = job_id or f"pjob-{uuid4().hex[:10]}"
    created = _now()
    job: Dict[str, Any] = {
        "id": job_id,
        "kind": "planning",
        "state": "running",
        "phase": "input_validation",
        "outcome": None,
        "createdAt": created,
        "request": deepcopy(request),
        "counts": {"configurationsTried": 0, "candidates": 0, "rejected": 0},
        "partialResults": False,
        "terminationReason": None,
        "error": None,
        "resultRefs": None,
        "plannerVersion": PLANNER_VERSION,
        "derivationVersion": DERIVATION_VERSION,
    }

    try:
        support = assert_facility_usable_for_planning(facility, drawing=drawing, require_confirmed=True)
    except FacilityGateError as exc:
        job["state"] = "succeeded"
        job["phase"] = "input_validation"
        job["outcome"] = "invalid_input" if exc.code == "INPUT_UNCONFIRMED" else "unsupported"
        job["finishedAt"] = _now()
        job["error"] = {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "retryable": False,
            "traceId": None,
        }
        job["terminationReason"] = "completed"
        return {"job": job, "candidates": [], "support": None}

    # detailed 评价未实现 → unsupported（不静默降级宣称 DES）
    if request.get("evaluationLevel") == "detailed":
        job["state"] = "succeeded"
        job["outcome"] = "unsupported"
        job["phase"] = "input_validation"
        job["finishedAt"] = _now()
        job["terminationReason"] = "completed"
        job["error"] = {
            "code": "UNSUPPORTED_SCENARIO",
            "message": "M2 仅支持 evaluationLevel=quick（几何/路径估算）；detailed/DES 属 M3",
            "details": {"evaluationLevel": "detailed"},
            "retryable": False,
            "traceId": None,
        }
        return {"job": job, "candidates": [], "support": support}

    allowed = set((request.get("constraints") or {}).get("allowedTypeIds") or [RACK_TYPE])
    if RACK_TYPE not in allowed and allowed:
        job["state"] = "succeeded"
        job["outcome"] = "unsupported"
        job["finishedAt"] = _now()
        job["terminationReason"] = "completed"
        job["error"] = {
            "code": "UNSUPPORTED_SCENARIO",
            "message": "基线规划器需要 ST-PAL-01 在 allowedTypeIds 中（DEC-05）",
            "details": {"allowedTypeIds": sorted(allowed)},
            "retryable": False,
            "traceId": None,
        }
        return {"job": job, "candidates": [], "support": support}

    base_layout = deepcopy(base_layout) if base_layout else _empty_base_layout(facility)
    locks = list(request.get("locks") or []) + list(base_layout.get("locks") or [])
    # 去重 locks by instanceId（请求优先）
    lock_map = {lk["instanceId"]: lk for lk in locks}
    locks = list(lock_map.values())

    scope = request.get("scope") or {"mode": "whole"}
    budget = request.get("budget") or {}
    max_cfg = int(budget.get("maxConfigurations") or 50)
    seed = int(request.get("seed") or 0)

    job["phase"] = "generation"
    configs: List[Tuple[int, int, int]] = []
    # 有限模板：yaw × rows × bays
    for yaw in (0, 90):
        for rows in (1, 2):
            for bays in (2, 3, 4, 5):
                configs.append((yaw, rows, bays))
    # 确定性顺序；seed 仅作实例 ID 盐
    configs = configs[:max_cfg]

    candidates: List[Dict[str, Any]] = []
    seen_fp: set[str] = set()
    tried = 0
    rejected = 0

    for yaw, rows, bays in configs:
        if tried >= max_cfg:
            break
        tried += 1
        gen = _enumerate_rack_configs(facility, yaw_deg=yaw, n_rows=rows, bays_per_row=bays, seed=seed)
        if not gen:
            rejected += 1
            continue

        layout_doc = {
            "contractVersion": "0.3",
            "id": f"layout-cand-{job_id[-6:]}-{tried}",
            "revision": f"ld-c{tried}",
            "facilityRef": {"id": facility["id"], "revision": facility["revision"]},
            "parentRef": {"id": base_layout["id"], "revision": base_layout["revision"]},
            "elements": gen["elements"],
            "aisles": gen["aisles"],
            "locks": deepcopy(locks),
            "catalogVersion": base_layout.get("catalogVersion") or "catalog-mvp@c-r1",
        }

        # 局部重排：合并区域外冻结 + 锁定
        if scope.get("mode") == "region":
            polygon = (scope.get("polygon") or {}).get("outer") or scope.get("polygon")
            if not polygon:
                job["state"] = "succeeded"
                job["outcome"] = "invalid_input"
                job["finishedAt"] = _now()
                job["terminationReason"] = "completed"
                job["error"] = {
                    "code": "INPUT_UNCONFIRMED",
                    "message": "scope.mode=region 需要 polygon",
                    "details": {"scope": scope},
                    "retryable": False,
                    "traceId": None,
                }
                return {"job": job, "candidates": [], "support": support}
            if isinstance(polygon, dict):
                polygon = polygon.get("outer") or []
            try:
                layout_doc = merge_region_layout(base_layout, layout_doc, polygon, locks)
                layout_doc["id"] = f"layout-cand-{job_id[-6:]}-{tried}"
                layout_doc["revision"] = f"ld-c{tried}"
                layout_doc["facilityRef"] = {
                    "id": facility["id"],
                    "revision": facility["revision"],
                }
            except LockConflictError as exc:
                rejected += 1
                continue
        else:
            # whole：仍须保留锁定对象
            if locks:
                # 将锁定实例从 base 注入并覆盖生成同 id
                locked_ids = {lk["instanceId"] for lk in locks}
                base_by_id = {e["instanceId"]: deepcopy(e) for e in base_layout.get("elements") or []}
                gen_els = [e for e in layout_doc["elements"] if e["instanceId"] not in locked_ids]
                for lk in locks:
                    if lk["instanceId"] in base_by_id:
                        gen_els.append(base_by_id[lk["instanceId"]])
                layout_doc["elements"] = gen_els
                try:
                    assert_locks_preserved(
                        base_layout.get("elements") or [],
                        layout_doc["elements"],
                        locks,
                    )
                except LockConflictError:
                    rejected += 1
                    continue

        job["phase"] = "validation"
        try:
            snapshot = derive_layout_snapshot(
                layout_doc,
                facility,
                layout_id=layout_doc["id"],
                layout_revision=layout_doc["revision"],
            )
            report = validate_layout(
                snapshot,
                facility,
                layout_doc,
                rule_set_refs=list(request.get("ruleSetRefs") or []),
            )
        except Exception:  # noqa: BLE001
            rejected += 1
            continue

        if not is_simulation_ready(report):
            rejected += 1
            continue

        job["phase"] = "quick_evaluation"
        eval_payload = _quick_metrics(snapshot, demand)
        geo_cap = eval_payload["metrics"]["geometricPalletCapacity"]["value"]
        layout_fp = _fp(
            {
                "yaw": yaw,
                "rows": rows,
                "bays": bays,
                "rackCount": gen["rackCount"],
                "elements": [
                    {
                        "t": e["typeElementId"],
                        "x": e["pose"]["x"],
                        "y": e["pose"]["y"],
                        "yaw": e["pose"].get("yawDeg", 0),
                    }
                    for e in sorted(layout_doc["elements"], key=lambda z: z["instanceId"])
                ],
            }
        )
        if layout_fp in seen_fp:
            continue
        seen_fp.add(layout_fp)

        cand_id = f"cand-{uuid4().hex[:10]}"
        candidate = {
            "id": cand_id,
            "jobId": job_id,
            "baseVariantRef": request.get("baseVariantRef"),
            "facilityRef": {"id": facility["id"], "revision": facility["revision"]},
            "layoutDocumentRef": {"id": layout_doc["id"], "revision": layout_doc["revision"]},
            "layoutDocument": layout_doc,
            "operatingRef": None,
            "goalsMatched": list(request.get("goals") or []),
            "validationRef": {"id": report["id"], "revision": report.get("revision", "vr-1")},
            "validationReport": report,
            "feasibilityStatus": "validated",
            "evaluationLevel": "quick",
            "metrics": eval_payload["metrics"],
            "claimsOperationalEfficiency": False,
            "costEstimateRef": None,
            "explanation": {
                "reasons": [
                    {
                        "text": f"模板 yaw={yaw} rows={rows} bays={bays}；几何托盘容量={geo_cap}",
                        "evidenceRefs": [f"validation:{report['id']}"],
                    }
                ],
                "tradeoffs": [
                    "更多排/跨提高几何容量，但压缩通道机动余量（仅几何层）"
                ],
                "unknowns": [
                    "运营吞吐/等待/利用率未评估（需 M3 DES）",
                ],
            },
            "diff": build_diff(base_layout, layout_doc, locks),
            "assumptions": [
                "DEC-05：常温单层标准托盘",
                f"plannerVersion={PLANNER_VERSION}",
                "evaluationLevel=quick 非运营效率证明",
            ],
            "inputFingerprint": input_fingerprint(
                layout_doc, facility, list(request.get("ruleSetRefs") or [])
            ),
            "searchManifestRef": {
                "yaw": yaw,
                "nRows": rows,
                "baysPerRow": bays,
                "layoutFingerprint": layout_fp,
            },
            "derivedSnapshot": snapshot,
        }
        candidates.append(candidate)

    job["counts"] = {
        "configurationsTried": tried,
        "candidates": len(candidates),
        "rejected": rejected,
    }
    job["phase"] = "selection"
    job["finishedAt"] = _now()
    job["state"] = "succeeded"
    if candidates:
        job["outcome"] = "feasible"
        job["terminationReason"] = "completed" if tried < max_cfg or len(candidates) > 0 else "budget_exhausted"
        # 代表选择：容量优先、其次路径较短；不足 4 套不凑数
        candidates.sort(
            key=lambda c: (
                -int(c["metrics"]["geometricPalletCapacity"]["value"] or 0),
                float(c["metrics"]["aisleGraphLengthM"]["value"] or 0),
            )
        )
        # 多样性：同容量去重后最多 4
        picked: List[Dict[str, Any]] = []
        seen_cap: set[int] = set()
        for c in candidates:
            cap = int(c["metrics"]["geometricPalletCapacity"]["value"] or 0)
            if cap in seen_cap and len(picked) >= 1:
                # 仍可收不同模板
                if c["searchManifestRef"]["yaw"] in {p["searchManifestRef"]["yaw"] for p in picked} and len(
                    picked
                ) >= 2:
                    continue
            seen_cap.add(cap)
            picked.append(c)
            if len(picked) >= 4:
                break
        candidates = picked or candidates[:4]
        job["counts"]["candidates"] = len(candidates)
        job["resultRefs"] = {
            "candidateIds": [c["id"] for c in candidates],
            "plannerVersion": PLANNER_VERSION,
        }
        job["partialResults"] = tried >= max_cfg and len(candidates) > 0
        if tried >= max_cfg:
            job["terminationReason"] = "budget_exhausted"
    else:
        job["outcome"] = "no_feasible_found"
        job["terminationReason"] = "completed" if tried < max_cfg else "budget_exhausted"
        job["partialResults"] = False
        job["resultRefs"] = {"candidateIds": [], "plannerVersion": PLANNER_VERSION}

    job["support"] = support
    return {"job": job, "candidates": candidates, "support": support}
