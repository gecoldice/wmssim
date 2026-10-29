"""通道图最短路（只读拓扑；拥堵不改路）。"""

from __future__ import annotations

import heapq
from typing import Any, Dict, List, Optional, Sequence, Tuple


def build_adjacency(snapshot: Dict[str, Any]) -> Dict[str, List[Tuple[str, str, float, float, int]]]:
    """node -> list of (neighbor, edgeId, lengthM, speedFactor, maxConcurrent)."""
    adj: Dict[str, List[Tuple[str, str, float, float, int]]] = {}
    for e in snapshot.get("edges") or []:
        a = e["from"]
        b = e["to"]
        eid = e["edgeId"]
        length = float(e.get("lengthM") or 0)
        sf = float(e.get("speedFactor") or 1.0) or 1.0
        mc = int(e.get("maxConcurrent") or 1)
        adj.setdefault(a, []).append((b, eid, length, sf, mc))
        if e.get("bidirectional", True):
            adj.setdefault(b, []).append((a, eid, length, sf, mc))
        else:
            adj.setdefault(b, [])
    for el in snapshot.get("elements") or []:
        if el.get("kind") == "node":
            adj.setdefault(el["elementId"], [])
    return adj


def shortest_path(
    adj: Dict[str, List[Tuple[str, str, float, float, int]]],
    origin: str,
    dest: str,
) -> Optional[Dict[str, Any]]:
    """Dijkstra by lengthM；返回 node 序列与 edge 序列。不可达 → None。"""
    if origin == dest:
        return {"nodes": [origin], "edges": [], "lengthM": 0.0}
    if origin not in adj or dest not in adj:
        return None
    dist: Dict[str, float] = {origin: 0.0}
    prev: Dict[str, Tuple[str, str]] = {}  # node -> (prev_node, edgeId)
    pq: List[Tuple[float, str]] = [(0.0, origin)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        if u == dest:
            break
        for v, eid, length, _sf, _mc in adj.get(u, []):
            nd = d + length
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                prev[v] = (u, eid)
                heapq.heappush(pq, (nd, v))
    if dest not in dist:
        return None
    nodes: List[str] = [dest]
    edges: List[str] = []
    cur = dest
    while cur != origin:
        p, eid = prev[cur]
        edges.append(eid)
        nodes.append(p)
        cur = p
    nodes.reverse()
    edges.reverse()
    return {"nodes": nodes, "edges": edges, "lengthM": dist[dest]}


def edge_lookup(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {e["edgeId"]: e for e in snapshot.get("edges") or []}


def travel_time_sec(length_m: float, speed_mps: float, speed_factor: float = 1.0) -> float:
    spd = max(1e-9, float(speed_mps) * max(1e-9, float(speed_factor)))
    return float(length_m) / spd
