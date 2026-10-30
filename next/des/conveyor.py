"""Straight-line conveyor runtime for CV-STR-01, CV-ROL-01 and CV-BELT-01.

Formal speed is speed_mpm. The engine uses m/s = speed_mpm / 60.
speed_m_s is not a second primary field. Curves, merges, diverts and the
other CV types stay unsimulated. A refusal happens before the event loop,
so the caller does not receive cards.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .errors import DesError
from .scope import unsimulated_ids, unsimulated_message

LINEAR_TYPES = ("CV-STR-01", "CV-ROL-01", "CV-BELT-01")
LINK_MESSAGE = "输送还没接上：把端口对到邻段或月台后再推演"
MISSING_MESSAGE = "还差必填参数才能推演"

_FORMAL = re.compile(r"^[A-Z]+(?:-[A-Z0-9]+)+-\d{2}$")

_PARAM_LABELS = (
    ("length_m", "长度"),
    ("width_m", "宽度"),
    ("orientation_deg", "朝向"),
    ("speed_mpm", "速度"),
    ("throughput_uph", "吞吐"),
    ("max_load_kg", "载重"),
    ("direction", "方向"),
    ("allow_load_types", "允许货型"),
)


def loc_of(el: Dict[str, Any]) -> str:
    if el.get("instanceId"):
        return str(el["instanceId"])
    return str(el.get("elementId") or "")


def type_of(el: Dict[str, Any]) -> str:
    tid = el.get("typeElementId")
    if isinstance(tid, str) and tid:
        return tid
    eid = str(el.get("elementId") or "")
    if el.get("kind") == "node":
        return ""
    if _FORMAL.match(eid):
        return eid
    return ""


def is_linear(el: Dict[str, Any]) -> bool:
    return type_of(el) in LINEAR_TYPES


def _bag(el: Dict[str, Any]) -> Dict[str, Any]:
    params = el.get("params")
    return params if isinstance(params, dict) else {}


def param(el: Dict[str, Any], key: str) -> Any:
    params = _bag(el)
    if key in params and params[key] not in (None, ""):
        return params[key]
    if key in el and el[key] not in (None, "") and key not in {"elementId", "instanceId"}:
        return el[key]
    if key == "orientation_deg":
        pose = el.get("pose") or {}
        if isinstance(pose, dict):
            if pose.get("orientation_deg") not in (None, ""):
                return pose.get("orientation_deg")
            if pose.get("yawDeg") not in (None, ""):
                return pose.get("yawDeg")
    return None


def ports_of(el: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = el.get("ports")
    if not isinstance(raw, list):
        raw = _bag(el).get("ports")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def connector_ids_of(el: Dict[str, Any]) -> List[str]:
    raw = el.get("connector_ids")
    if not isinstance(raw, list):
        raw = _bag(el).get("connector_ids")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def collect_connections(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for raw in snapshot.get("connections") or []:
        if isinstance(raw, dict):
            found.append(raw)
    for el in snapshot.get("elements") or []:
        for raw in _bag(el).get("conveyorLinks") or []:
            if not isinstance(raw, dict):
                continue
            found.append(
                {
                    "from": {"instanceId": raw.get("fromInstanceId"), "portId": raw.get("fromPort")},
                    "to": {"instanceId": raw.get("toInstanceId"), "portId": raw.get("toPort")},
                }
            )
    return found


def _endpoint(ref: Any) -> Tuple[str, str]:
    if not isinstance(ref, dict):
        return "", ""
    return str(ref.get("instanceId") or ""), str(ref.get("portId") or "")


def missing_param_labels(el: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    for key, label in _PARAM_LABELS:
        value = param(el, key)
        if key == "allow_load_types":
            if not isinstance(value, list) or not value:
                labels.append(label)
            continue
        if key == "direction":
            if not isinstance(value, str) or not value.strip():
                labels.append(label)
            continue
        if value in (None, ""):
            labels.append(label)
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            labels.append(label)
            continue
        if not math.isfinite(number):
            labels.append(label)
            continue
        if key == "orientation_deg":
            continue
        if number <= 0:
            labels.append(label)
    return labels


def ports_linked(el: Dict[str, Any], connections: Sequence[Dict[str, Any]]) -> bool:
    inst = loc_of(el)
    ports = ports_of(el)
    cids = set(connector_ids_of(el))
    incoming = [p for p in ports if p.get("role") in {"in", "bidirectional"}]
    outgoing = [p for p in ports if p.get("role") in {"out", "bidirectional"}]
    if not incoming or not outgoing:
        return False
    for port in ports:
        if str(port.get("id") or "") not in cids:
            return False
    for port in incoming:
        pid = str(port.get("id") or "")
        if not any(_endpoint(row.get("to")) == (inst, pid) for row in connections):
            return False
    for port in outgoing:
        pid = str(port.get("id") or "")
        if not any(_endpoint(row.get("from")) == (inst, pid) for row in connections):
            return False
    return True


def _needed_load_types(demand: Optional[Dict[str, Any]], direct: Optional[Dict[str, Any]]) -> set:
    needed = set()
    tasks = (direct or {}).get("tasks") or []
    flows = (demand or {}).get("flows") or []
    kinds = [str(row.get("flowKind") or "") for row in list(tasks) + list(flows)]
    if any(kind in {"", "full_pallet", "break_bulk"} for kind in kinds):
        needed.add("pallet")
    return needed


def _allow(el: Dict[str, Any]) -> set:
    raw = param(el, "allow_load_types")
    if not isinstance(raw, list):
        return set()
    return {str(item).lower() for item in raw}


@dataclass
class ConveyorSeg:
    instance_id: str
    type_id: str
    length_m: float
    speed_mpm: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def speed_mps(self) -> float:
        return self.speed_mpm / 60.0

    @property
    def travel_sec(self) -> float:
        return self.length_m / self.speed_mps


class ConveyorGraph:
    def __init__(self, snapshot: Dict[str, Any]) -> None:
        self.elements = [el for el in (snapshot.get("elements") or []) if isinstance(el, dict)]
        self.by_loc = {loc_of(el): el for el in self.elements if loc_of(el)}
        self.connections = collect_connections(snapshot)
        self.adj: Dict[str, List[str]] = {}
        for row in self.connections:
            src, _ = _endpoint(row.get("from"))
            dst, _ = _endpoint(row.get("to"))
            if src and dst:
                self.adj.setdefault(src, []).append(dst)

    def linear_elements(self) -> List[Dict[str, Any]]:
        return [el for el in self.elements if is_linear(el)]

    def segment(self, loc: str) -> ConveyorSeg:
        el = self.by_loc[loc]
        length = float(param(el, "length_m"))
        speed = float(param(el, "speed_mpm"))
        yaw = math.radians(float(param(el, "orientation_deg") or 0))
        pose = el.get("pose") or {}
        cx = float(pose.get("x") or 0)
        cy = float(pose.get("y") or 0)
        dx = math.cos(yaw) * length / 2.0
        dy = math.sin(yaw) * length / 2.0
        return ConveyorSeg(
            instance_id=loc,
            type_id=type_of(el),
            length_m=length,
            speed_mpm=speed,
            x0=cx - dx,
            y0=cy - dy,
            x1=cx + dx,
            y1=cy + dy,
        )

    def chain(self, origin: str, dest: str) -> List[ConveyorSeg]:
        if not origin or not dest or origin == dest:
            return []
        queue: List[Tuple[str, Tuple[str, ...]]] = [(origin, tuple())]
        seen = {(origin, tuple())}
        while queue:
            node, cvs = queue.pop(0)
            if node == dest and cvs:
                return [self.segment(loc) for loc in cvs]
            for nxt in self.adj.get(node, []):
                next_cvs = cvs
                el = self.by_loc.get(node)
                if el is not None and is_linear(el) and node not in cvs:
                    next_cvs = cvs + (node,)
                key = (nxt, next_cvs)
                if key in seen:
                    continue
                seen.add(key)
                queue.append((nxt, next_cvs))
        return []


def _task_pairs(snapshot: Dict[str, Any], demand: Optional[Dict[str, Any]], direct: Optional[Dict[str, Any]]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for task in (direct or {}).get("tasks") or []:
        if str(task.get("pathMode") or "") in {"conveyor", "conveyor_then_access"}:
            pairs.append((str(task.get("originId") or ""), str(task.get("destId") or "")))
    if pairs:
        return pairs
    slots = []
    docks_ship = []
    docks_recv = []
    for el in snapshot.get("elements") or []:
        loc = loc_of(el)
        kind = el.get("kind")
        labels = el.get("labels") or []
        if kind == "slot":
            slots.append(loc)
        if kind == "dock" and "ship" in labels:
            docks_ship.append(loc)
        if kind == "dock" and "recv" in labels:
            docks_recv.append(loc)
    for slot in slots:
        for dock in docks_ship:
            pairs.append((slot, dock))
        for dock in docks_recv:
            pairs.append((dock, slot))
    return pairs


def _used_locations(graph: ConveyorGraph, pairs: Sequence[Tuple[str, str]]) -> set:
    used = set()
    for origin, dest in pairs:
        for seg in graph.chain(origin, dest):
            used.add(seg.instance_id)
    return used


def assess_snapshot(
    snapshot: Dict[str, Any],
    demand: Optional[Dict[str, Any]] = None,
    direct: Optional[Dict[str, Any]] = None,
) -> Optional[Tuple[str, str]]:
    """Return (code, message) when this snapshot must not enter the scheduler."""
    elements = [el for el in (snapshot.get("elements") or []) if isinstance(el, dict)]
    blocked = unsimulated_ids(type_of(el) for el in elements)
    if blocked:
        return "UNSUPPORTED_SCENARIO", unsimulated_message(blocked)
    linears = [el for el in elements if is_linear(el)]
    if not linears:
        return None
    for el in linears:
        missing = missing_param_labels(el)
        if missing:
            shown = type_of(el)
            return "INPUT_UNCONFIRMED", f"{MISSING_MESSAGE}：{'、'.join(missing)}（{shown}）"
    connections = collect_connections(snapshot)
    for el in linears:
        if not ports_linked(el, connections):
            shown = type_of(el)
            inst = loc_of(el)
            extra = shown if inst == shown else f"{inst} · {shown}"
            return "CONVEYOR_UNLINKED", f"{LINK_MESSAGE}（{extra}）"
    graph = ConveyorGraph(snapshot)
    needed = _needed_load_types(demand, direct)
    if not needed:
        return None
    used = _used_locations(graph, _task_pairs(snapshot, demand, direct))
    for el in linears:
        if loc_of(el) not in used:
            continue
        if not (_allow(el) & needed):
            return (
                "UNSUPPORTED_SCENARIO",
                f"本切片暂不仿真该类：{type_of(el)}。货型不符。",
            )
    return None


def raise_if_refused(
    snapshot: Dict[str, Any],
    demand: Optional[Dict[str, Any]] = None,
    direct: Optional[Dict[str, Any]] = None,
) -> None:
    found = assess_snapshot(snapshot, demand, direct)
    if found:
        raise DesError(found[0], found[1])


def direct_is_pure_conveyor(direct: Optional[Dict[str, Any]]) -> bool:
    tasks = (direct or {}).get("tasks") or []
    if not tasks:
        return False
    return all(str(task.get("pathMode") or "") == "conveyor" for task in tasks)
