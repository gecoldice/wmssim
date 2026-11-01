"""Shortest paths on a snapshot aisle graph."""

from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Optional


def build_adjacency(snapshot: Dict[str, Any], *, force_bidirectional: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    adj: Dict[str, List[Dict[str, Any]]] = {}
    for edge in snapshot.get("edges") or []:
        a, b = edge["from"], edge["to"]
        adj.setdefault(a, []).append(edge)
        if force_bidirectional or edge.get("bidirectional", True):
            rev = dict(edge)
            rev["from"], rev["to"] = b, a
            rev["edgeId"] = edge["edgeId"]
            adj.setdefault(b, []).append(rev)
        adj.setdefault(b, [])
        adj.setdefault(a, [])
    return adj


def shortest_path(
    adj: Dict[str, List[Dict[str, Any]]],
    origin: str,
    dest: str,
) -> Optional[Dict[str, Any]]:
    if origin == dest:
        return {"nodes": [origin], "edges": [], "lengthM": 0.0}
    dist = {origin: 0.0}
    prev: Dict[str, Optional[str]] = {origin: None}
    prev_edge: Dict[str, Optional[str]] = {origin: None}
    heap = [(0.0, origin)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist.get(node, math.inf) + 1e-12:
            continue
        if node == dest:
            break
        for edge in adj.get(node) or []:
            nxt = edge["to"]
            nd = d + float(edge.get("lengthM") or 0)
            if nd + 1e-12 < dist.get(nxt, math.inf):
                dist[nxt] = nd
                prev[nxt] = node
                prev_edge[nxt] = edge["edgeId"]
                heapq.heappush(heap, (nd, nxt))
    if dest not in dist:
        return None
    nodes: List[str] = []
    edges: List[str] = []
    cur: Optional[str] = dest
    while cur is not None:
        nodes.append(cur)
        eid = prev_edge.get(cur)
        if eid:
            edges.append(eid)
        cur = prev.get(cur)
    nodes.reverse()
    edges.reverse()
    return {"nodes": nodes, "edges": edges, "lengthM": dist[dest]}


def edge_lookup(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {e["edgeId"]: e for e in snapshot.get("edges") or []}


def travel_time_sec(length_m: float, speed_mps: float, speed_factor: float = 1.0) -> float:
    return float(length_m) / (float(speed_mps) * float(speed_factor))


def direction_is_the_block(snapshot: Dict[str, Any], origin: str, dest: str) -> bool:
    """True when the only missing link is a one-way edge against the trip."""
    if not origin or not dest:
        return False
    if shortest_path(build_adjacency(snapshot), origin, dest) is not None:
        return False
    opened = build_adjacency(snapshot, force_bidirectional=True)
    return shortest_path(opened, origin, dest) is not None


def tight_turn(
    poses: Dict[str, Any],
    nodes: List[str],
    edge_ids: List[str],
    edges: Dict[str, Dict[str, Any]],
    radius_m: Optional[float],
) -> Optional[Dict[str, Any]]:
    """A corner needs aisle width at least twice the turning radius.

    A heading change of 1° or less is straight and is not a turn.
    radius None or <= 0 does not judge. Missing width on a real corner is reported.
    """
    if radius_m is None or radius_m <= 0 or len(nodes) < 3:
        return None
    need = 2.0 * float(radius_m)
    for index in range(1, len(nodes) - 1):
        a = _xy(poses.get(nodes[index - 1]))
        b = _xy(poses.get(nodes[index]))
        c = _xy(poses.get(nodes[index + 1]))
        if a is None or b is None or c is None:
            continue
        incoming = (b[0] - a[0], b[1] - a[1])
        outgoing = (c[0] - b[0], c[1] - b[1])
        n1 = math.hypot(*incoming)
        n2 = math.hypot(*outgoing)
        if n1 <= 1e-9 or n2 <= 1e-9:
            continue
        cos = (incoming[0] * outgoing[0] + incoming[1] * outgoing[1]) / (n1 * n2)
        cos = max(-1.0, min(1.0, cos))
        if cos >= math.cos(math.radians(1.0)):
            continue
        left = edges.get(edge_ids[index - 1]) or {}
        right = edges.get(edge_ids[index]) or {}
        if left.get("widthM") in (None, "") or right.get("widthM") in (None, ""):
            return {"nodeId": nodes[index], "missingWidth": True, "radiusM": float(radius_m), "needM": need}
        width = min(float(left["widthM"]), float(right["widthM"]))
        if width + 1e-9 < need:
            return {
                "nodeId": nodes[index],
                "widthM": width,
                "needM": need,
                "radiusM": float(radius_m),
                "missingWidth": False,
            }
    return None


def _xy(pose: Any) -> Optional[tuple]:
    if not isinstance(pose, dict):
        return None
    point = pose.get("pose") if "pose" in pose else pose
    if not isinstance(point, dict) or point.get("x") is None or point.get("y") is None:
        return None
    return float(point["x"]), float(point["y"])
