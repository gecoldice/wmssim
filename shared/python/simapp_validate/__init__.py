"""权威校验：碰撞 / 窄通道 / 跨墙 accessNode / 连通性。产出 ValidationReport。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from simapp_geometry import Aabb, Point, footprint_aabb, segment_blocked
from simapp_derive import DERIVATION_VERSION, input_fingerprint

ACCESS_KINDS = {"slot", "station", "dock", "device"}

# M1 规则包：阈值来自设备声明/夹具声明，不编消防规范数值
RULE_SET_M1 = {"id": "ruleset.m1.geometry", "revision": "0.1"}


def _obstacle_rings(facility: Dict[str, Any]) -> List[List[Point]]:
    rings: List[List[Point]] = []
    for obs in facility.get("obstacles") or []:
        poly = obs.get("polygon") or {}
        outer = poly.get("outer") or []
        if len(outer) >= 3:
            rings.append([(float(p["x"]), float(p["y"])) for p in outer])
    return rings


def _check(
    check_id: str,
    rule_id: str,
    status: str,
    *,
    object_ids: Optional[List[str]] = None,
    message: str = "",
    evidence: Optional[Dict[str, Any]] = None,
    fix_hint: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "checkId": check_id,
        "ruleId": rule_id,
        "status": status,
        "objectIds": object_ids or [],
        "message": message,
        "evidence": evidence or {},
        "fixHint": fix_hint,
    }


def validate_layout(
    snapshot: Dict[str, Any],
    facility: Dict[str, Any],
    layout_doc: Optional[Dict[str, Any]] = None,
    *,
    rule_set_refs: Optional[Sequence[Dict[str, str]]] = None,
    min_aisle_width_by_type: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """对派生快照做权威校验。status=pass|warn|fail。"""
    checks: List[Dict[str, Any]] = []
    obstacles = _obstacle_rings(facility)
    elements = snapshot.get("elements") or []
    edges = snapshot.get("edges") or []
    node_ids = {e["elementId"] for e in elements if e.get("kind") == "node"}
    node_pose = {
        e["elementId"]: (float(e["pose"]["x"]), float(e["pose"]["y"]))
        for e in elements
        if e.get("kind") == "node"
    }

    # --- accessNode 存在性 ---
    for e in elements:
        kind = e.get("kind")
        if kind not in ACCESS_KINDS:
            continue
        an = e.get("accessNodeId")
        eid = e.get("elementId")
        if not an:
            checks.append(
                _check(
                    f"access-missing-{eid}",
                    "NO_ACCESS_NODE",
                    "fail",
                    object_ids=[eid],
                    message=f"{eid} 缺少 accessNodeId",
                    fix_hint="将设备移近通道中心线并重新派生",
                )
            )
        elif an not in node_ids:
            checks.append(
                _check(
                    f"access-dangling-{eid}",
                    "NO_ACCESS_NODE",
                    "fail",
                    object_ids=[eid, str(an)],
                    message=f"{eid} 的 accessNodeId={an} 不存在",
                    fix_hint="重新派生通道图",
                )
            )

    # --- 跨墙：元素中心 → accessNode 直线不得穿障 ---
    for e in elements:
        if e.get("kind") not in ACCESS_KINDS:
            continue
        an = e.get("accessNodeId")
        if not an or an not in node_pose:
            continue
        origin = (float(e["pose"]["x"]), float(e["pose"]["y"]))
        target = node_pose[an]
        if segment_blocked(origin, target, obstacles):
            checks.append(
                _check(
                    f"cross-wall-{e['elementId']}",
                    "NO_ACCESS_NODE",
                    "fail",
                    object_ids=[e["elementId"], an],
                    message=f"{e['elementId']} 到 {an} 的绑定穿越障碍（禁止跨墙最近节点）",
                    evidence={"from": origin, "to": target},
                    fix_hint="改绑同侧通道节点或调整障碍/设备位置",
                )
            )

    # --- 通道边不得穿障 ---
    for edge in edges:
        a = node_pose.get(edge.get("from"))
        b = node_pose.get(edge.get("to"))
        if not a or not b:
            continue
        if segment_blocked(a, b, obstacles):
            checks.append(
                _check(
                    f"edge-through-wall-{edge.get('edgeId')}",
                    "ROUTE_UNREACHABLE",
                    "fail",
                    object_ids=[edge.get("edgeId"), edge.get("from"), edge.get("to")],
                    message=f"边 {edge.get('edgeId')} 穿越障碍",
                    fix_hint="断开跨墙边或重布通道",
                )
            )

    # --- 碰撞：实体 footprint AABB 相交 ---
    solid = [e for e in elements if e.get("kind") in {"slot", "station", "dock", "device"}]
    boxes: List[Tuple[str, Aabb]] = []
    for e in solid:
        fp = e.get("footprint") or {}
        if "w" not in fp or "d" not in fp:
            continue
        yaw = float((e.get("pose") or {}).get("yawDeg") or 0)
        box = footprint_aabb(
            float(e["pose"]["x"]),
            float(e["pose"]["y"]),
            float(fp["w"]),
            float(fp["d"]),
            yaw,
        )
        boxes.append((e["elementId"], box))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            id_a, box_a = boxes[i]
            id_b, box_b = boxes[j]
            if box_a.intersects(box_b):
                checks.append(
                    _check(
                        f"collision-{id_a}-{id_b}",
                        "GEOMETRY_INVALID",
                        "fail",
                        object_ids=[id_a, id_b],
                        message=f"{id_a} 与 {id_b} 占地碰撞",
                        evidence={"rule": "aabb_overlap"},
                        fix_hint="移动或缩小冲突设备",
                    )
                )

    # --- 窄通道：aisle.widthM < 设备声明最小净宽 ---
    required = dict(min_aisle_width_by_type or {"ST-PAL-01": 3.0})
    # 也可从 layout_doc.aisles + 相邻设备 params 读取
    aisles = (layout_doc or {}).get("aisles") or []
    if not aisles:
        # 从边注解恢复
        seen = set()
        for edge in edges:
            aid = edge.get("aisleId")
            w = edge.get("aisleWidthM")
            if aid and w is not None and aid not in seen:
                seen.add(aid)
                aisles.append({"id": aid, "widthM": w})

    max_required = 0.0
    for e in solid:
        tid = e.get("typeElementId") or ""
        if tid in required:
            max_required = max(max_required, float(required[tid]))
        params_req = None
        if layout_doc:
            for le in layout_doc.get("elements") or []:
                if le.get("instanceId") == e.get("elementId"):
                    params_req = (le.get("params") or {}).get("minClearWidthM")
                    break
        if params_req is not None:
            max_required = max(max_required, float(params_req))

    for aisle in aisles:
        width = aisle.get("widthM")
        if width is None:
            checks.append(
                _check(
                    f"aisle-width-unknown-{aisle.get('id')}",
                    "NARROW_AISLE",
                    "unknown",
                    object_ids=[str(aisle.get("id"))],
                    message="通道宽度未知，窄通道规则未评估",
                )
            )
            continue
        if max_required > 0 and float(width) + 1e-9 < max_required:
            checks.append(
                _check(
                    f"narrow-aisle-{aisle.get('id')}",
                    "NARROW_AISLE",
                    "fail",
                    object_ids=[str(aisle.get("id"))],
                    message=(
                        f"通道 {aisle.get('id')} 宽度 {width}m "
                        f"小于设备声明最小净宽 {max_required}m"
                    ),
                    evidence={
                        "aisleWidthM": width,
                        "requiredMinWidthM": max_required,
                        "source": "equipment_declared",
                    },
                    fix_hint="加宽通道或更换净宽需求更小的设备",
                )
            )

    # 汇总
    statuses = [c["status"] for c in checks]
    if any(s == "fail" for s in statuses):
        overall = "fail"
    elif any(s == "unknown" for s in statuses):
        overall = "unknown"
    elif any(s == "warn" for s in statuses):
        overall = "warn"
    else:
        overall = "pass"
        if not checks:
            checks.append(
                _check(
                    "geometry-ok",
                    "GEOMETRY_OK",
                    "pass",
                    message="碰撞/窄通道/跨墙检查通过",
                )
            )

    refs = list(rule_set_refs) if rule_set_refs else [RULE_SET_M1]
    fp = None
    if layout_doc is not None:
        fp = input_fingerprint(layout_doc, facility, refs)

    return {
        "contractVersion": "0.3",
        "id": f"vr-{uuid4().hex[:10]}",
        "inputFingerprint": fp,
        "status": overall,
        "checks": checks,
        "ruleSetRefs": refs,
        "computedAt": datetime.now(timezone.utc).isoformat(),
        "derivationVersion": DERIVATION_VERSION,
        "layoutRef": {
            "id": snapshot.get("layoutId"),
            "revision": snapshot.get("layoutRevision"),
        },
        "facilityRef": {
            "id": facility.get("id"),
            "revision": facility.get("revision"),
        },
    }


def is_simulation_ready(report: Dict[str, Any]) -> bool:
    return report.get("status") == "pass"
