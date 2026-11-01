"""Derive a Snapshot 0.2 from a layout document and a facility. No simapp import."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .geometry import Point, dist, segment_blocked

DERIVATION_VERSION = "slice-derive-0.1"
MAX_ACCESS_M = 8.0

FOOTPRINTS: Dict[str, Dict[str, float]] = {
    "ST-PAL-01": {"w": 2.7, "d": 1.2},
    "ST-FLOOR-01": {"w": 4.8, "d": 2.4},
    "IN-DOCK-01": {"w": 3.0, "d": 4.0},
    "OUT-DOCK-01": {"w": 3.0, "d": 4.0},
    "PK-DEPAL-01": {"w": 3.2, "d": 2.0},
    "PK-PUT-EACH-01": {"w": 4.2, "d": 1.0},
    "OUT-PACK-01": {"w": 2.4, "d": 1.4},
    "MH-HAND-01": {"w": 6.0, "d": 1.2},
    "MH-FORK-01": {"w": 4.0, "d": 2.2},
    "AUX-FIRE-01": {"w": 6.0, "d": 1.5},
    "AUX-WALL-01": {"w": 8.0, "d": 0.3},
}


def kind_for(type_element_id: str) -> str:
    """Docks are only the dock types. OUT-PACK is a station, not a second ship door."""
    if type_element_id.startswith("ST-"):
        return "slot"
    if type_element_id.startswith("IN-DOCK") or type_element_id.startswith("OUT-DOCK"):
        return "dock"
    if type_element_id.startswith("PK-") or type_element_id.startswith("OUT-PACK"):
        return "station"
    return "device"


def _footprint_for(type_element_id: str, params: Dict[str, Any]) -> Dict[str, float]:
    geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}
    length = params.get("length_m", geom.get("length_m") if isinstance(geom, dict) else None)
    width = params.get("width_m", geom.get("width_m") if isinstance(geom, dict) else None)
    if length is not None and width is not None:
        return {"w": float(length), "d": float(width)}
    if "footprintW" in params and "footprintD" in params:
        return {"w": float(params["footprintW"]), "d": float(params["footprintD"])}
    return dict(FOOTPRINTS.get(type_element_id, {"w": 1.0, "d": 1.0}))


def _preset_access(
    params: Dict[str, Any],
    pose: Point,
    obstacles: List[List[Point]],
) -> Optional[Tuple[float, float, str]]:
    point = params.get("accessPoint")
    preset_id = params.get("accessNodeId")
    if not isinstance(point, dict) or not isinstance(preset_id, str) or not preset_id:
        return None
    try:
        ax = float(point["x"])
        ay = float(point["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if dist(pose, (ax, ay)) > MAX_ACCESS_M + 1e-6:
        return None
    if segment_blocked(pose, (ax, ay), obstacles):
        return None
    return ax, ay, preset_id


def obstacle_rings(facility: Dict[str, Any]) -> List[List[Point]]:
    rings: List[List[Point]] = []
    for obs in facility.get("obstacles") or []:
        outer = ((obs.get("polygon") or {}).get("outer")) or []
        if len(outer) >= 3:
            rings.append([(float(p["x"]), float(p["y"])) for p in outer])
    return rings


def _node_key(x: float, y: float, quant: float = 0.05) -> Tuple[float, float]:
    return (round(x / quant) * quant, round(y / quant) * quant)


def _project(origin: Point, polyline: Sequence[Point]) -> Optional[Point]:
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
        t = 0.0 if seg2 <= 1e-18 else max(0.0, min(1.0, ((ox - ax) * dx + (oy - ay) * dy) / seg2))
        px, py = ax + t * dx, ay + t * dy
        d = dist(origin, (px, py))
        if d < best_d:
            best_d = d
            best = (px, py)
    return best


def _split_edge_at(
    edges: List[Dict[str, Any]],
    poses: Dict[str, Point],
    point: Point,
    new_id: str,
    obstacles: List[List[Point]],
) -> None:
    """Insert a node that lies on an aisle edge so both directions stay connected."""
    for index, edge in enumerate(list(edges)):
        a_id, b_id = edge["from"], edge["to"]
        if new_id in {a_id, b_id}:
            continue
        a, b = poses.get(a_id), poses.get(b_id)
        if a is None or b is None:
            continue
        span = dist(a, b)
        if span <= 1e-6:
            continue
        if abs(dist(a, point) + dist(point, b) - span) > 1e-3:
            continue
        if dist(a, point) <= 1e-4 or dist(b, point) <= 1e-4:
            continue
        if segment_blocked(a, point, obstacles) or segment_blocked(point, b, obstacles):
            continue
        edges.remove(edge)
        for src, dst, length in (
            (a_id, new_id, dist(a, point)),
            (new_id, b_id, dist(point, b)),
        ):
            edges.append(
                {
                    "edgeId": f"e-{src}-{dst}",
                    "from": src,
                    "to": dst,
                    "lengthM": round(length, 6),
                    "bidirectional": True,
                    "maxConcurrent": int(edge.get("maxConcurrent") or 2),
                    "speedFactor": float(edge.get("speedFactor") or 1),
                }
            )
        return


def derive_snapshot(
    layout_doc: Dict[str, Any],
    facility: Dict[str, Any],
    *,
    layout_revision: str,
) -> Dict[str, Any]:
    obstacles = obstacle_rings(facility)
    aisle_nodes: Dict[Tuple[float, float], str] = {}
    elements: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_seq = 0

    def ensure_node(x: float, y: float, preferred: Optional[str] = None) -> str:
        nonlocal node_seq
        key = _node_key(x, y)
        if key in aisle_nodes:
            return aisle_nodes[key]
        node_seq += 1
        nid = preferred or f"n-{node_seq}"
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

    for aisle in layout_doc.get("aisles") or []:
        center = [(float(p["x"]), float(p["y"])) for p in (aisle.get("centerline") or [])]
        if len(center) < 2:
            continue
        ids: List[str] = []
        for i, (x, y) in enumerate(center):
            preferred = None
            if aisle.get("id") and i == 0:
                preferred = f"n-{aisle['id']}-a"
            elif aisle.get("id") and i == len(center) - 1:
                preferred = f"n-{aisle['id']}-b"
            ids.append(ensure_node(x, y, preferred))
        for i in range(len(center) - 1):
            a, b = center[i], center[i + 1]
            if segment_blocked(a, b, obstacles):
                continue
            length = dist(a, b)
            if length <= 1e-9:
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
                }
            )

    def node_pose() -> Dict[str, Point]:
        return {
            e["elementId"]: (float(e["pose"]["x"]), float(e["pose"]["y"]))
            for e in elements
            if e["kind"] == "node"
        }

    def bind_access(pose: Point) -> Tuple[Optional[str], bool]:
        candidates: List[Tuple[float, str]] = []
        blocked_near = False
        for nid, np in node_pose().items():
            d = dist(pose, np)
            if d > MAX_ACCESS_M:
                continue
            if segment_blocked(pose, np, obstacles):
                blocked_near = True
                continue
            candidates.append((d, nid))
        if not candidates:
            return None, blocked_near
        candidates.sort()
        return candidates[0][1], blocked_near

    for el in layout_doc.get("elements") or []:
        if el.get("assetDisposition") == "removed":
            continue
        tid = el["typeElementId"]
        kind = kind_for(tid)
        pose = el.get("pose") or {}
        px, py = float(pose.get("x", 0)), float(pose.get("y", 0))
        yaw = float(pose.get("yawDeg") or 0)
        params = el.get("params") or {}
        fp = _footprint_for(tid, params)
        access = None
        blocked_near = False
        preset = _preset_access(params, (px, py), obstacles) if kind in {"slot", "dock", "device", "station"} else None
        if preset is not None:
            ax, ay, preset_id = preset
            new_id = ensure_node(ax, ay, preset_id)
            _split_edge_at(edges, node_pose(), (ax, ay), new_id, obstacles)
            access = new_id
        elif kind in {"slot", "dock", "device", "station"}:
            best: Optional[Point] = None
            best_d = 1e18
            for aisle in layout_doc.get("aisles") or []:
                cl = [(float(p["x"]), float(p["y"])) for p in (aisle.get("centerline") or [])]
                proj = _project((px, py), cl)
                if proj is None:
                    continue
                d = dist((px, py), proj)
                if d < best_d:
                    best_d = d
                    best = proj
            if best is not None and best_d <= MAX_ACCESS_M and not segment_blocked((px, py), best, obstacles):
                new_id = ensure_node(best[0], best[1])
                _split_edge_at(edges, node_pose(), best, new_id, obstacles)
            access, blocked_near = bind_access((px, py))
        out: Dict[str, Any] = {
            "elementId": el["instanceId"],
            "typeElementId": tid,
            "kind": kind,
            "pose": {"x": px, "y": py, "yawDeg": yaw},
            "footprint": fp,
        }
        if access:
            out["accessNodeId"] = access
        elif blocked_near:
            out["accessBlocked"] = True
        if kind == "slot":
            levels = int(params.get("levels") or 1)
            bays = int(params.get("bays") or 1)
            per_bay = int(params.get("palletsPerBay") or 2)
            out["capacityPallets"] = levels * bays * per_bay
            out["zone"] = params.get("zone") or "storage"
            out["labels"] = ["bulk"]
        if kind == "dock":
            out["labels"] = ["recv" if tid.startswith("IN-") else "ship"]
        if kind == "station" and tid == "PK-DEPAL-01":
            out["labels"] = ["break_bulk"]
            out["capacitySlots"] = 1
        if params:
            out["params"] = dict(params)
        if isinstance(params.get("ports"), list):
            out["ports"] = params["ports"]
        if isinstance(params.get("connector_ids"), list):
            out["connector_ids"] = params["connector_ids"]
        elements.append(out)

    coord = facility.get("coord") or {}
    return {
        "schemaVersion": "0.2",
        "layoutId": layout_doc["id"],
        "layoutRevision": layout_revision,
        "exportedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "coord": {
            "origin": coord.get("origin", "facility_sw_corner"),
            "xAxis": coord.get("xAxis", "east"),
            "yAxis": coord.get("yAxis", "north"),
            "unit": "m",
            "yawZero": "+X",
        },
        "elements": elements,
        "edges": edges,
        "defaults": {},
        "validation": {"derivationVersion": DERIVATION_VERSION},
    }
