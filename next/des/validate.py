"""Authoritative geometry checks for the manual slice."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .derive import DERIVATION_VERSION, obstacle_rings
from .geometry import Aabb, Point, footprint_aabb, ring_aabb, segment_blocked
from .graph import build_adjacency, shortest_path

ACCESS_KINDS = {"slot", "dock", "station", "device"}
RULE_SET = {"id": "ruleset.slice.geometry", "revision": "0.1"}


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


def _facility_box(facility: Dict[str, Any]) -> Optional[Aabb]:
    outer = ((facility.get("boundary") or {}).get("outer")) or []
    pts = [(float(p["x"]), float(p["y"])) for p in outer]
    return ring_aabb(pts)


def validate_layout(
    snapshot: Dict[str, Any],
    facility: Dict[str, Any],
    layout_doc: Dict[str, Any],
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    obstacles = obstacle_rings(facility)
    elements = snapshot.get("elements") or []
    edges = snapshot.get("edges") or []
    node_ids = {e["elementId"] for e in elements if e.get("kind") == "node"}
    node_pose = {
        e["elementId"]: (float(e["pose"]["x"]), float(e["pose"]["y"]))
        for e in elements
        if e.get("kind") == "node"
    }
    box = _facility_box(facility)

    for e in elements:
        if e.get("kind") not in ACCESS_KINDS:
            continue
        eid = e["elementId"]
        an = e.get("accessNodeId")
        if not an or an not in node_ids:
            blocked = bool(e.get("accessBlocked"))
            checks.append(
                _check(
                    f"access-missing-{eid}",
                    "NO_ACCESS_NODE",
                    "fail",
                    object_ids=[eid],
                    message=(
                        f"{eid} 到通道接入点的直线被障碍挡住（跨墙）"
                        if blocked
                        else f"{eid} 没有可达的 accessNodeId"
                    ),
                    fix_hint="把设备移到通道同侧，距离中心线 8 米以内",
                )
            )
            continue
        origin = (float(e["pose"]["x"]), float(e["pose"]["y"]))
        target = node_pose[an]
        if segment_blocked(origin, target, obstacles):
            checks.append(
                _check(
                    f"cross-wall-{eid}",
                    "NO_ACCESS_NODE",
                    "fail",
                    object_ids=[eid, an],
                    message=f"{eid} 到接入点 {an} 的连线穿过障碍",
                    evidence={"from": {"x": origin[0], "y": origin[1]}, "accessNodeId": an},
                    fix_hint="不要把货架接到墙另一侧的通道",
                )
            )

    for edge in edges:
        a = node_pose.get(edge.get("from"))
        b = node_pose.get(edge.get("to"))
        if a and b and segment_blocked(a, b, obstacles):
            checks.append(
                _check(
                    f"edge-wall-{edge.get('edgeId')}",
                    "ROUTE_UNREACHABLE",
                    "fail",
                    object_ids=[str(edge.get("edgeId"))],
                    message=f"通道边 {edge.get('edgeId')} 穿过障碍",
                )
            )

    solids = [e for e in elements if e.get("kind") in ACCESS_KINDS]
    boxes: List[Tuple[str, Aabb]] = []
    for e in solids:
        fp = e.get("footprint") or {}
        if "w" not in fp or "d" not in fp:
            continue
        yaw = float((e.get("pose") or {}).get("yawDeg") or 0)
        abb = footprint_aabb(
            float(e["pose"]["x"]),
            float(e["pose"]["y"]),
            float(fp["w"]),
            float(fp["d"]),
            yaw,
        )
        boxes.append((e["elementId"], abb))
        if box and not abb.inside(box):
            checks.append(
                _check(
                    f"outside-{e['elementId']}",
                    "GEOMETRY_INVALID",
                    "fail",
                    object_ids=[e["elementId"]],
                    message=f"{e['elementId']} 的占地超出场地边界",
                    fix_hint="把设备移回场地矩形内",
                )
            )
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
                        message=f"{id_a} 与 {id_b} 占地重叠",
                        fix_hint="拉开重叠的设备",
                    )
                )

    required = 0.0
    declaring: List[str] = []
    for el in layout_doc.get("elements") or []:
        raw = (el.get("params") or {}).get("minClearWidthM")
        if raw is None:
            continue
        width_need = float(raw)
        if width_need > required:
            required = width_need
        declaring.append(el["instanceId"])
    for aisle in layout_doc.get("aisles") or []:
        width = aisle.get("widthM")
        aid = str(aisle.get("id"))
        if width is None:
            checks.append(
                _check(
                    f"aisle-unknown-{aid}",
                    "NARROW_AISLE",
                    "unknown",
                    object_ids=[aid],
                    message=f"通道 {aid} 宽度未填写",
                )
            )
            continue
        if required > 0 and float(width) + 1e-9 < required:
            checks.append(
                _check(
                    f"narrow-{aid}",
                    "NARROW_AISLE",
                    "fail",
                    object_ids=[aid, *declaring],
                    message=f"通道 {aid} 宽 {width} m，窄于设备要求的 {required} m",
                    evidence={"aisleWidthM": width, "requiredMinWidthM": required},
                    fix_hint="加宽通道，或减小设备声明的最小净宽",
                )
            )

    adj = build_adjacency(snapshot)
    docks = [e for e in elements if e.get("kind") == "dock" and e.get("accessNodeId") in node_ids]
    ship = next((d for d in docks if "ship" in (d.get("labels") or [])), None)
    slots = [e for e in elements if e.get("kind") == "slot" and e.get("accessNodeId") in node_ids]
    if ship:
        for slot in slots:
            path = shortest_path(adj, slot["accessNodeId"], ship["accessNodeId"])
            if path is None:
                checks.append(
                    _check(
                        f"route-{slot['elementId']}",
                        "ROUTE_UNREACHABLE",
                        "fail",
                        object_ids=[slot["elementId"], ship["elementId"]],
                        message=f"{slot['elementId']} 到发货月台没有通路",
                    )
                )

    statuses = [c["status"] for c in checks]
    if any(s == "fail" for s in statuses):
        overall = "fail"
    elif any(s == "unknown" for s in statuses):
        overall = "unknown"
    else:
        overall = "pass"
        if not checks:
            checks.append(
                _check("geometry-ok", "GEOMETRY_OK", "pass", message="碰撞、窄通道、跨墙检查通过")
            )
    return {
        "contractVersion": "0.3",
        "id": f"vr-{uuid4().hex[:12]}",
        "status": overall,
        "checks": checks,
        "ruleSetRefs": [RULE_SET],
        "computedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "derivationVersion": DERIVATION_VERSION,
        "layoutRef": {"id": snapshot.get("layoutId"), "revision": snapshot.get("layoutRevision")},
        "facilityRef": {"id": facility.get("id"), "revision": facility.get("revision")},
    }
