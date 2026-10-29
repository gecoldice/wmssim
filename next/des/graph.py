"""Shortest paths on a snapshot aisle graph."""

from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Optional


def build_adjacency(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    adj: Dict[str, List[Dict[str, Any]]] = {}
    for edge in snapshot.get("edges") or []:
        a, b = edge["from"], edge["to"]
        adj.setdefault(a, []).append(edge)
        if edge.get("bidirectional", True):
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
