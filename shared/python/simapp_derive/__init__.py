"""从 LayoutDocument + Facility 派生 LayoutSnapshot 0.2（货位/通道/accessNode）。

M1 手动路径：不依赖自动规划。禁止引入 UI 演示 KPI 公式。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from simapp_geometry import (
    Point,
    dist,
    segment_blocked,
)

DERIVATION_VERSION = "m1-derive-0.1"

# 目录缺省 footprint（盒子代理）；真实 equip 可覆盖
DEFAULT_FOOTPRINTS: Dict[str, Dict[str, float]] = {
    "ST-PAL-01": {"w": 2.7, "d": 1.2},
    "IN-DOCK-01": {"w": 3.0, "d": 4.0},
    "OUT-DOCK-01": {"w": 3.0, "d": 4.0},
    "MH-HAND-01": {"w": 1.2, "d": 2.0},
}

KIND_BY_PREFIX = {
    "ST-": "slot",
    "IN-": "dock",
    "OUT-": "dock",
    "PK-": "station",
    "MH-": "device",
}


def _kind_for(type_element_id: str) -> str:
    for prefix, kind in KIND_BY_PREFIX.items():
        if type_element_id.startswith(prefix):
            return kind
    return "device"


def _footprint_for(type_element_id: str, params: Dict[str, Any]) -> Dict[str, float]:
    if "footprintW" in params and "footprintD" in params:
        return {"w": float(params["footprintW"]), "d": float(params["footprintD"])}
    return dict(DEFAULT_FOOTPRINTS.get(type_element_id, {"w": 1.0, "d": 1.0}))


def _obstacle_rings(facility: Dict[str, Any]) -> List[List[Point]]:
    rings: List[List[Point]] = []
    for obs in facility.get("obstacles") or []:
        poly = obs.get("polygon") or {}
        outer = poly.get("outer") or []
        if len(outer) >= 3:
            rings.append([(float(p["x"]), float(p["y"])) for p in outer])
    return rings


def _node_key(x: float, y: float, quant: float = 0.05) -> Tuple[float, float]:
    return (round(x / quant) * quant, round(y / quant) * quant)


def _project_to_polyline(origin: Point, polyline: Sequence[Point]) -> Optional[Point]:
    """将点投影到折线最近段；无折线则 None。"""
    if len(polyline) < 2:
        return None
    best: Optional[Point] = None
    best_d = 1e18
    ox, oy = origin
    for i in range(len(polyline) - 1):
        ax, ay = polyline[i]
        bx, by = polyline[i + 1]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        if seg2 <= 1e-18:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((ox - ax) * dx + (oy - ay) * dy) / seg2))
        px, py = ax + t * dx, ay + t * dy
        d = dist(origin, (px, py))
        if d < best_d:
            best_d = d
            best = (px, py)
    return best


def derive_layout_snapshot(
    layout_doc: Dict[str, Any],
    facility: Dict[str, Any],
    *,
    layout_id: Optional[str] = None,
    layout_revision: Optional[str] = None,
    max_access_distance_m: float = 8.0,
) -> Dict[str, Any]:
    """权威派生：通道节点/边 + 设备绑定 accessNode（禁止跨障绑定）。"""
    obstacles = _obstacle_rings(facility)
    aisle_nodes: Dict[Tuple[float, float], str] = {}
    elements: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_seq = 0

    def ensure_node(x: float, y: float, preferred_id: Optional[str] = None) -> str:
        nonlocal node_seq
        key = _node_key(x, y)
        if key in aisle_nodes:
            return aisle_nodes[key]
        node_seq += 1
        nid = preferred_id or f"n-{node_seq}"
        aisle_nodes[key] = nid
        elements.append(
            {
                "elementId": nid,
                "kind": "node",
                "pose": {"x": key[0], "y": key[1]},
                "footprint": {"w": 0.1, "d": 0.1},
            }
        )
        return nid

    # 1) 通道中心线 → 节点与边（边不得穿过障碍）
    for aisle in layout_doc.get("aisles") or []:
        centerline = aisle.get("centerline") or []
        if len(centerline) < 2:
            continue
        pts = [(float(p["x"]), float(p["y"])) for p in centerline]
        ids: List[str] = []
        for i, (x, y) in enumerate(pts):
            preferred = None
            if i == 0 and aisle.get("id"):
                preferred = f"n-{aisle['id']}-a"
            elif i == len(pts) - 1 and aisle.get("id"):
                preferred = f"n-{aisle['id']}-b"
            ids.append(ensure_node(x, y, preferred))
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if segment_blocked(a, b, obstacles):
                continue  # 跨障边不生成；校验层可另报 ROUTE_UNREACHABLE
            length = dist(a, b)
            if length <= 0:
                continue
            edges.append(
                {
                    "edgeId": f"e-{ids[i]}-{ids[i + 1]}",
                    "from": ids[i],
                    "to": ids[i + 1],
                    "lengthM": round(length, 6),
                    "bidirectional": True,
                    "maxConcurrent": 2,
                    "speedFactor": 1,
                    "aisleId": aisle.get("id"),
                    "aisleWidthM": aisle.get("widthM"),
                }
            )

    node_by_id = {e["elementId"]: e for e in elements if e["kind"] == "node"}

    def bind_access(pose: Point, hint_id: Optional[str] = None) -> Optional[str]:
        """同可通行域：到候选节点的直线不被障碍切断；取最近可达。禁止跨墙欧氏最近。"""
        candidates: List[Tuple[float, str]] = []
        for nid, el in node_by_id.items():
            np = (float(el["pose"]["x"]), float(el["pose"]["y"]))
            if segment_blocked(pose, np, obstacles):
                continue
            d = dist(pose, np)
            if d <= max_access_distance_m:
                candidates.append((d, nid))
        if not candidates:
            return None
        candidates.sort(key=lambda t: (t[0], t[1]))
        if hint_id and any(c[1] == hint_id for c in candidates):
            return hint_id
        return candidates[0][1]

    # 2) 布局元素 → snapshot 元素 + accessNode
    for el in layout_doc.get("elements") or []:
        if el.get("assetDisposition") == "removed":
            continue
        tid = el["typeElementId"]
        kind = _kind_for(tid)
        pose = el.get("pose") or {}
        px, py = float(pose.get("x", 0)), float(pose.get("y", 0))
        yaw = float(pose.get("yawDeg", 0) or 0)
        fp = _footprint_for(tid, el.get("params") or {})
        access_pose: Point = (px, py)
        if kind in {"slot", "station", "dock", "device"}:
            # 投影到最近通道中心线并落节点（不仅端点）
            if layout_doc.get("aisles"):
                best: Optional[Point] = None
                best_d = 1e18
                for aisle in layout_doc["aisles"]:
                    cl = [(float(p["x"]), float(p["y"])) for p in (aisle.get("centerline") or [])]
                    proj = _project_to_polyline(access_pose, cl)
                    if proj is None:
                        continue
                    d = dist(access_pose, proj)
                    if d < best_d:
                        best_d = d
                        best = proj
                if best is not None and best_d <= max_access_distance_m:
                    ensure_node(best[0], best[1])
                    # 把投影点接到既有通道边上：与最近端点连边（若不穿障）
                    nearest_existing = None
                    nearest_d = 1e18
                    for nid, eln in list(node_by_id.items()):
                        np = (float(eln["pose"]["x"]), float(eln["pose"]["y"]))
                        d = dist(best, np)
                        if d < nearest_d:
                            nearest_d = d
                            nearest_existing = (nid, np)
                    new_id = aisle_nodes[_node_key(best[0], best[1])]
                    node_by_id = {e["elementId"]: e for e in elements if e["kind"] == "node"}
                    if nearest_existing and nearest_existing[0] != new_id and nearest_d > 1e-6:
                        a_id, a_pt = nearest_existing
                        if not segment_blocked(best, a_pt, obstacles):
                            edges.append(
                                {
                                    "edgeId": f"e-{a_id}-{new_id}",
                                    "from": a_id,
                                    "to": new_id,
                                    "lengthM": round(nearest_d, 6),
                                    "bidirectional": True,
                                    "maxConcurrent": 2,
                                    "speedFactor": 1,
                                }
                            )

            access = bind_access(access_pose)
        else:
            access = None

        params = el.get("params") or {}
        levels = int(params.get("levels") or 1)
        bays = int(params.get("bays") or 1)
        pallets_per_bay = int(params.get("palletsPerBay") or params.get("pallets_per_bay") or 2)

        out: Dict[str, Any] = {
            "elementId": el["instanceId"],
            "typeElementId": tid,
            "kind": kind,
            "pose": {"x": px, "y": py, "yawDeg": yaw},
            "footprint": {"w": fp["w"], "d": fp["d"]},
        }
        if access:
            out["accessNodeId"] = access
        if kind == "slot":
            out["capacityPallets"] = levels * bays * pallets_per_bay
            out["zone"] = params.get("zone", "storage")
            out["labels"] = params.get("labels") or ["bulk"]
            out["parentInstanceId"] = el["instanceId"]
        if kind == "dock":
            role = "recv" if tid.startswith("IN-") else "ship"
            out["labels"] = [role]
        if kind == "device":
            out["resourceHome"] = bool(params.get("resourceHome", True))

        elements.append(out)

    coord = facility.get("coord") or {
        "origin": "facility_sw_corner",
        "xAxis": "east",
        "yAxis": "north",
        "unit": "m",
    }
    snapshot = {
        "schemaVersion": "0.2",
        "layoutId": layout_id or layout_doc["id"],
        "layoutRevision": layout_revision or layout_doc["revision"],
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "coord": {
            "origin": coord.get("origin", "facility_sw_corner"),
            "xAxis": coord.get("xAxis", "east"),
            "yAxis": coord.get("yAxis", "north"),
            "unit": "m",
            "yawZero": "+X",
        },
        "elements": elements,
        "edges": edges,
        "defaults": {"travelSpeedMps": 1.2, "emptySpeedMps": 1.5},
        "validation": {
            "derivationVersion": DERIVATION_VERSION,
            "aisleCount": len(layout_doc.get("aisles") or []),
            "obstacleCount": len(obstacles),
        },
    }
    return snapshot


def derived_index(snapshot: Dict[str, Any], layout_doc: Dict[str, Any]) -> Dict[str, Any]:
    slots = [e for e in snapshot.get("elements") or [] if e.get("kind") == "slot"]
    return {
        "derivationVersion": DERIVATION_VERSION,
        "parentToSlots": {
            el["instanceId"]: [
                s["elementId"] for s in slots if s.get("parentInstanceId") == el["instanceId"] or s["elementId"] == el["instanceId"]
            ]
            for el in layout_doc.get("elements") or []
            if el.get("typeElementId", "").startswith("ST-")
        },
        "nodeCount": sum(1 for e in snapshot.get("elements") or [] if e.get("kind") == "node"),
        "edgeCount": len(snapshot.get("edges") or []),
        "totalAisleLengthM": sum(float(e.get("lengthM") or 0) for e in snapshot.get("edges") or []),
    }


def input_fingerprint(
    layout_doc: Dict[str, Any],
    facility: Dict[str, Any],
    rule_set_refs: Sequence[Dict[str, str]] | None = None,
) -> str:
    payload = {
        "layout": {
            "id": layout_doc.get("id"),
            "revision": layout_doc.get("revision"),
            "elements": layout_doc.get("elements"),
            "aisles": layout_doc.get("aisles"),
            "catalogVersion": layout_doc.get("catalogVersion"),
        },
        "facility": {
            "id": facility.get("id"),
            "revision": facility.get("revision"),
            "boundary": facility.get("boundary"),
            "obstacles": facility.get("obstacles"),
        },
        "ruleSetRefs": list(rule_set_refs or []),
        "derivationVersion": DERIVATION_VERSION,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
