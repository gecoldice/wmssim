"""Event engine for the manual slice.

full_pallet: arrival, resource wait, empty travel, pick, loaded travel, ship.
break_bulk: deliver a pallet to a break_bulk station slot, process, convert
1 pallet into casesPerPallet cases. Edge and station slots use the same
occupy_request / grant / release rule. Waiting lengthens the later segment;
the node sequence stays the shortest path.

Speeds and process seconds are required inputs on the flow API. A direct
gold scenario may omit pick/ship; those durations stay 0 instead of being invented.
A workload whose access nodes are not connected raises ROUTE_UNREACHABLE
before the event loop, so a rejected load does not emit cards.
"""

from __future__ import annotations

import heapq
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .errors import DesError
from .graph import build_adjacency, edge_lookup, shortest_path, travel_time_sec
from .inventory import InventoryLedger
from .kpi import compute_cards

ENGINE_VERSION = "slice-des-0.1"
METRIC_DEFINITION_VERSION = "metrics-slice-manual-v1"

PHASE_COMPLETE = 10
PHASE_TRAVEL = 20
PHASE_ARRIVE = 30
PHASE_DISPATCH = 40


@dataclass(order=True)
class _Ev:
    t: float
    phase: int
    seq: int
    kind: str = field(compare=False)
    payload: Dict[str, Any] = field(compare=False, default_factory=dict)


@dataclass
class _Task:
    task_id: str
    direction: str
    qty: float
    arrival_t: float
    location_id: Optional[str] = None
    origin_node: str = ""
    dest_node: str = ""
    dock_id: Optional[str] = None
    status: str = "pending"
    wait_sec: float = 0.0
    resource_id: Optional[str] = None
    path_nodes: List[str] = field(default_factory=list)
    path_edges: List[str] = field(default_factory=list)
    edge_i: int = 0
    pickup_after: int = 0
    picked: bool = False
    flow_kind: str = "full_pallet"
    station_id: Optional[str] = None
    station_wait_sec: float = 0.0
    cases_created: float = 0.0


@dataclass
class _Res:
    resource_id: str
    resource_type: str
    pool_id: str
    node_id: str
    task_id: Optional[str] = None
    busy_sec: float = 0.0
    assign_t: float = 0.0
    last_busy_end: float = 0.0
    travel_mps: Optional[float] = None
    empty_mps: Optional[float] = None


@dataclass
class _Gate:
    cap: int
    holders: List[str] = field(default_factory=list)
    queue: List[Dict[str, Any]] = field(default_factory=list)


class DesEngine:
    def __init__(
        self,
        snapshot: Dict[str, Any],
        *,
        demand: Dict[str, Any],
        operating: Dict[str, Any],
        run_control: Dict[str, Any],
        expected_layout_revision: str,
        run_id: Optional[str] = None,
        direct: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.snapshot_in = snapshot
        self.snapshot = deepcopy(snapshot)
        self.demand = demand
        self.operating = operating
        self.run_control = run_control
        self.expected_layout_revision = expected_layout_revision
        self.direct = direct
        self.run_id = run_id or f"run-{uuid4().hex[:12]}"
        self.warnings: List[Dict[str, str]] = []
        self.seq = 0
        self.t = 0.0
        self.pq: List[_Ev] = []
        self.events: List[Dict[str, Any]] = []
        self.segments: List[Dict[str, Any]] = []
        self.tasks: Dict[str, _Task] = {}
        self.resources: List[_Res] = []
        self.queues: Dict[str, List[str]] = {}
        self.entity_wait: Dict[str, float] = {}
        self.outbound_pallet_eq = 0.0
        self.ship_event_ids: List[str] = []
        self.event_counter = 0
        self.forklift_pool = ""
        self.edge_gates: Dict[str, _Gate] = {}
        self.station_gates: Dict[str, _Gate] = {}
        self.edge_waits: List[Dict[str, Any]] = []
        self.station_windows: List[Dict[str, Any]] = []
        self.piece_tasks: List[Dict[str, Any]] = []
        self.break_sec: Optional[float] = None
        self.cases_per_pallet: Optional[float] = None
        self.downstream_piece = False
        self.stations: Dict[str, Dict[str, Any]] = {}
        self.break_stations: List[Dict[str, Any]] = []

    def _require_number(self, bag: Dict[str, Any], key: str, label: str) -> float:
        if key not in bag or bag[key] is None or bag[key] == "":
            raise DesError("INPUT_UNCONFIRMED", f"{label}未填写", {"field": key})
        value = float(bag[key])
        if value <= 0:
            raise DesError("INPUT_UNCONFIRMED", f"{label}必须大于 0", {"field": key})
        return value

    def _prepare_inputs(self) -> None:
        if self.snapshot.get("schemaVersion") != "0.2":
            raise DesError("CONTRACT_VERSION", "Snapshot schemaVersion 必须是 0.2")
        rev = self.snapshot.get("layoutRevision")
        if rev != self.expected_layout_revision:
            raise DesError(
                "LAYOUT_REVISION_MISMATCH",
                "expectedLayoutRevision 与快照 layoutRevision 不相等",
                {"expected": self.expected_layout_revision, "actual": rev},
            )
        self.horizon = self._require_number(self.run_control, "horizonSec", "评价时长")
        svc = self.operating.get("serviceParameters") or {}
        self.travel = self._require_number(svc, "travelSpeedMps", "载货速度")
        self.empty = self._require_number(svc, "emptySpeedMps", "空驶速度")
        proc = svc.get("processSec") or {}
        if not isinstance(proc, dict):
            raise DesError("INPUT_UNCONFIRMED", "处理时间未填写", {"field": "processSec"})
        defaults = ((self.snapshot.get("defaults") or {}).get("processSec") or {})
        if self.direct is not None:
            self.pick_sec = float(proc["pick"]) if proc.get("pick") not in (None, "") else 0.0
            self.ship_sec = float(proc["ship"]) if proc.get("ship") not in (None, "") else 0.0
        else:
            self.pick_sec = self._require_number(proc, "pick", "取货时间")
            self.ship_sec = self._require_number(proc, "ship", "发运时间")
        self.putaway_sec = float(proc["putaway"]) if proc.get("putaway") not in (None, "") else None
        break_raw = proc.get("break_bulk")
        if break_raw in (None, "") and isinstance(defaults, dict):
            break_raw = defaults.get("break_bulk")
        self.break_sec = float(break_raw) if break_raw not in (None, "") else None
        cases = None
        if self.direct is not None and self.direct.get("casesPerPallet") not in (None, ""):
            cases = self.direct.get("casesPerPallet")
        elif self.demand.get("casesPerPallet") not in (None, ""):
            cases = self.demand.get("casesPerPallet")
        elif svc.get("casesPerPallet") not in (None, ""):
            cases = svc.get("casesPerPallet")
        self.cases_per_pallet = float(cases) if cases not in (None, "") else None
        if self.direct is not None and self.direct.get("downstream"):
            self.downstream_piece = True
        self.nodes = {
            e["elementId"]: e for e in self.snapshot.get("elements") or [] if e.get("kind") == "node"
        }
        self.slots = {
            e["elementId"]: e for e in self.snapshot.get("elements") or [] if e.get("kind") == "slot"
        }
        self.docks = {
            e["elementId"]: e for e in self.snapshot.get("elements") or [] if e.get("kind") == "dock"
        }
        self.stations = {
            e["elementId"]: e for e in self.snapshot.get("elements") or [] if e.get("kind") == "station"
        }
        self.break_stations = [
            s for s in self.stations.values() if "break_bulk" in (s.get("labels") or [])
        ]
        self.recv = next((d for d in self.docks.values() if "recv" in (d.get("labels") or [])), None)
        self.ship_dock = next((d for d in self.docks.values() if "ship" in (d.get("labels") or [])), None)
        for el in list(self.slots.values()) + list(self.docks.values()):
            an = el.get("accessNodeId")
            if not an or an not in self.nodes:
                raise DesError(
                    "NO_ACCESS_NODE",
                    f"{el.get('elementId')} 缺有效 accessNodeId",
                    {"elementId": el.get("elementId")},
                )
        self.adj = build_adjacency(self.snapshot)
        self.edges = edge_lookup(self.snapshot)
        for eid, edge in self.edges.items():
            cap = int(edge.get("maxConcurrent") or 1)
            self.edge_gates[eid] = _Gate(cap=max(1, cap))
        for sid, station in self.stations.items():
            cap = int(station.get("capacitySlots") or 1)
            self.station_gates[sid] = _Gate(cap=max(1, cap))
        self.inventory = InventoryLedger(self.snapshot, list(self.demand.get("initialInventory") or []))
        self._build_resources()
        self._check_flows()

    def _flow_kinds(self) -> List[str]:
        if self.direct is not None:
            return [str(task.get("flowKind") or "") for task in self.direct.get("tasks") or []]
        return [str(flow.get("flowKind") or "") for flow in self.demand.get("flows") or []]

    def _check_flows(self) -> None:
        kinds = self._flow_kinds()
        for flow in self.demand.get("flows") or []:
            if flow.get("downstream"):
                self.downstream_piece = True
        if "piece_pick" in kinds and "break_bulk" in kinds:
            self.downstream_piece = True
        for kind in kinds:
            if kind in {"full_pallet", ""}:
                continue
            if kind == "break_bulk":
                if not self.break_stations:
                    raise DesError(
                        "FLOWKIND_STATION_MISSING",
                        "场景含 break_bulk，但布局没有 labels 含 break_bulk 的工位",
                        {"flowKind": kind},
                    )
                continue
            if kind == "piece_pick":
                if "break_bulk" in kinds:
                    continue
                raise DesError(
                    "UNSUPPORTED_SCENARIO",
                    "piece_pick 不单独跑人路径；只在 break_bulk downstream 时生成箱任务骨架",
                    {"flowKind": kind},
                )
            raise DesError(
                "UNSUPPORTED_SCENARIO",
                f"本切片不支持 flowKind={kind}",
                {"flowKind": kind},
            )
        if "break_bulk" in kinds:
            if self.break_sec is None or self.break_sec <= 0:
                raise DesError("INPUT_UNCONFIRMED", "拆托处理时间未填写", {"field": "processSec.break_bulk"})
            if self.cases_per_pallet is None or self.cases_per_pallet <= 0:
                raise DesError("INPUT_UNCONFIRMED", "casesPerPallet 未填写", {"field": "casesPerPallet"})
            for station in self.break_stations:
                if not station.get("accessNodeId"):
                    raise DesError(
                        "NO_ACCESS_NODE",
                        f"{station.get('elementId')} 缺有效 accessNodeId",
                        {"elementId": station.get("elementId")},
                    )

    def _build_resources(self) -> None:
        if self.direct is not None:
            pool_id = "pool-forklift"
            self.queues[pool_id] = []
            self.forklift_pool = pool_id
            for spec in self.direct.get("resources") or []:
                home = spec.get("homeNodeId")
                if home not in self.nodes:
                    raise DesError("INPUT_UNCONFIRMED", f"资源停靠节点不存在：{home}", {"nodeId": home})
                kind = spec.get("kind") or spec.get("resourceType") or "forklift"
                if kind not in {"forklift", "picker"}:
                    raise DesError("UNSUPPORTED_SCENARIO", f"本切片不支持资源类型 {kind}", {"resourceType": kind})
                self.resources.append(
                    _Res(
                        resource_id=str(spec.get("resourceId")),
                        resource_type=kind,
                        pool_id=pool_id,
                        node_id=home,
                        travel_mps=float(spec["travelSpeedMps"]) if spec.get("travelSpeedMps") else None,
                        empty_mps=float(spec["emptySpeedMps"]) if spec.get("emptySpeedMps") else None,
                    )
                )
            if not any(r.resource_type == "forklift" for r in self.resources):
                raise DesError("NO_RESOURCES", "至少需要 1 台叉车", {"resourceType": "forklift"})
            return
        home = None
        if self.recv and self.recv.get("accessNodeId"):
            home = self.recv["accessNodeId"]
        elif self.nodes:
            home = next(iter(self.nodes))
        if not home:
            raise DesError("INPUT_UNCONFIRMED", "快照没有资源可以停靠的节点")
        for pool in self.operating.get("resourcePools") or []:
            rtype = pool.get("resourceType") or ""
            if rtype not in {"forklift", "picker"}:
                raise DesError(
                    "UNSUPPORTED_SCENARIO",
                    f"本切片不支持资源类型 {rtype}",
                    {"resourceType": rtype},
                )
            count = int(pool.get("count") or 0)
            pool_id = pool.get("id") or f"pool-{rtype}"
            self.queues[pool_id] = []
            if rtype == "forklift":
                self.forklift_pool = pool_id
            for i in range(count):
                self.resources.append(
                    _Res(
                        resource_id=f"{rtype}-{i + 1}",
                        resource_type=rtype,
                        pool_id=pool_id,
                        node_id=home,
                    )
                )
        if not any(r.resource_type == "forklift" for r in self.resources):
            raise DesError("NO_RESOURCES", "至少需要 1 台叉车才能推演整托", {"resourceType": "forklift"})

    def _next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def _schedule(self, t: float, phase: int, kind: str, payload: Dict[str, Any]) -> None:
        if t > self.horizon + 1e-9:
            return
        heapq.heappush(self.pq, _Ev(t=t, phase=phase, seq=self._next_seq(), kind=kind, payload=payload))

    def _emit(self, kind: str, payload: Dict[str, Any]) -> str:
        self.event_counter += 1
        eid = f"ev-{self.event_counter:06d}"
        body = {"eventId": eid, "t": self.t, "kind": kind}
        body.update(payload)
        self.events.append(body)
        return eid

    def _arrival_times(self, n: int) -> List[float]:
        profile = self.demand.get("arrivalProfile") or {}
        if "windowSec" not in profile:
            raise DesError("INPUT_UNCONFIRMED", "到达窗口未填写", {"field": "windowSec"})
        window = float(profile["windowSec"])
        if window <= 0:
            raise DesError("INPUT_UNCONFIRMED", "到达窗口必须大于 0")
        window = min(window, self.horizon)
        if n <= 0:
            return []
        if n == 1:
            return [0.0]
        return [window * i / n for i in range(n)]

    def _add(self, task: _Task) -> None:
        self.tasks[task.task_id] = task
        self._schedule(task.arrival_t, PHASE_ARRIVE, "arrival", {"taskId": task.task_id})

    def _element(self, element_id: str) -> Dict[str, Any]:
        el = self.slots.get(element_id) or self.docks.get(element_id) or self.stations.get(element_id)
        if not el:
            raise DesError("INPUT_UNCONFIRMED", f"找不到元素 {element_id}", {"elementId": element_id})
        if not el.get("accessNodeId"):
            raise DesError("NO_ACCESS_NODE", f"{element_id} 缺有效 accessNodeId", {"elementId": element_id})
        return el

    def _generate(self) -> None:
        if self.direct is not None:
            self._generate_direct()
            return
        task_n = 0
        for flow in self.demand.get("flows") or []:
            kind = flow.get("flowKind")
            if kind == "piece_pick":
                continue
            if kind == "break_bulk":
                task_n = self._generate_break_flow(flow, task_n)
                continue
            qty = float(flow.get("quantity") or 0)
            if qty <= 0:
                continue
            if abs(qty - round(qty)) > 1e-6:
                raise DesError("INPUT_UNCONFIRMED", "整托数量必须是整数托", {"quantity": qty})
            n = int(round(qty))
            intent = flow.get("intent") or ""
            source = flow.get("source") or ""
            outbound = intent in {"outbound", "outbound_ship"} or source in {"storage", "inventory"}
            times = self._arrival_times(n)
            for t_arr in times:
                task_n += 1
                if outbound:
                    if not self.ship_dock:
                        raise DesError("INPUT_UNCONFIRMED", "出库需要发货月台")
                    self._add(
                        _Task(
                            task_id=f"T-out-{task_n:04d}",
                            direction="outbound_ship",
                            qty=1.0,
                            arrival_t=t_arr,
                            dock_id=self.ship_dock["elementId"],
                            dest_node=self.ship_dock["accessNodeId"],
                        )
                    )
                else:
                    if not self.recv:
                        raise DesError("INPUT_UNCONFIRMED", "入库需要收货月台")
                    if self.putaway_sec is None:
                        raise DesError("INPUT_UNCONFIRMED", "上架时间未填写", {"field": "putaway"})
                    slot = self.inventory.pick_slot_with_capacity(1.0)
                    if not slot:
                        raise DesError("INPUT_UNCONFIRMED", "没有货位容量承接入库")
                    self._add(
                        _Task(
                            task_id=f"T-in-{task_n:04d}",
                            direction="inbound_putaway",
                            qty=1.0,
                            arrival_t=t_arr,
                            location_id=slot,
                            origin_node=self.recv["accessNodeId"],
                            dest_node=self.slots[slot]["accessNodeId"],
                            dock_id=self.recv["elementId"],
                        )
                    )

    def _generate_break_flow(self, flow: Dict[str, Any], task_n: int) -> int:
        qty = float(flow.get("quantity") or 0)
        if qty <= 0:
            return task_n
        if abs(qty - round(qty)) > 1e-6:
            raise DesError("INPUT_UNCONFIRMED", "拆托数量必须是整数托", {"quantity": qty})
        station = self.break_stations[0]
        times = self._arrival_times(int(round(qty)))
        for t_arr in times:
            task_n += 1
            self._add(
                _Task(
                    task_id=f"T-break-{task_n:04d}",
                    direction="break_bulk",
                    qty=1.0,
                    arrival_t=t_arr,
                    station_id=station["elementId"],
                    dest_node=station["accessNodeId"],
                    flow_kind="break_bulk",
                )
            )
        return task_n

    def _generate_direct(self) -> None:
        for spec in self.direct.get("tasks") or []:
            kind = spec.get("flowKind")
            origin = self._element(spec["originId"])
            dest = self._element(spec["destId"])
            qty = float(spec.get("qtyPallets") or 1)
            ready = float(spec.get("readyAt") or 0)
            if kind == "break_bulk":
                if "break_bulk" not in (dest.get("labels") or []):
                    raise DesError(
                        "FLOWKIND_STATION_MISSING",
                        f"{spec['destId']} 不是拆托工位",
                        {"elementId": spec["destId"]},
                    )
                self._add(
                    _Task(
                        task_id=str(spec["taskId"]),
                        direction="break_bulk",
                        qty=qty,
                        arrival_t=ready,
                        location_id=spec["originId"],
                        origin_node=origin["accessNodeId"],
                        dest_node=dest["accessNodeId"],
                        station_id=dest["elementId"],
                        flow_kind="break_bulk",
                    )
                )
                continue
            if kind != "full_pallet":
                raise DesError("UNSUPPORTED_SCENARIO", f"直接任务不支持 {kind}", {"flowKind": kind})
            self._add(
                _Task(
                    task_id=str(spec["taskId"]),
                    direction="outbound_ship",
                    qty=qty,
                    arrival_t=ready,
                    location_id=spec["originId"],
                    origin_node=origin["accessNodeId"],
                    dest_node=dest["accessNodeId"],
                    dock_id=dest["elementId"] if dest.get("kind") == "dock" else None,
                    flow_kind="full_pallet",
                )
            )

    def _idle(self, pool_id: str) -> Optional[_Res]:
        idle = [r for r in self.resources if r.pool_id == pool_id and r.task_id is None]
        if not idle:
            return None
        idle.sort(key=lambda r: (r.last_busy_end, r.resource_id))
        return idle[0]

    def _pump(self, pool_id: str) -> None:
        queue = self.queues[pool_id]
        while queue:
            res = self._idle(pool_id)
            if res is None:
                head = self.tasks[queue[0]]
                if head.status != "waiting_resource":
                    head.status = "waiting_resource"
                    self._emit(
                        "resource_wait",
                        {"taskId": head.task_id, "entityId": pool_id, "queued": True},
                    )
                return
            self._assign(res, self.tasks[queue.pop(0)])

    def _fail(self, task: _Task, code: str, message: str) -> None:
        task.status = "failed"
        self.warnings.append({"code": code, "message": message})
        self._emit("task_complete", {"taskId": task.task_id, "status": "failed", "waitSec": task.wait_sec})

    def _assign(self, res: _Res, task: _Task) -> None:
        waited = self.t - task.arrival_t
        task.wait_sec = waited
        if waited > 1e-9:
            self.entity_wait[res.pool_id] = self.entity_wait.get(res.pool_id, 0.0) + waited
        if task.direction in {"outbound_ship", "break_bulk"}:
            slot = self.inventory.pick_slot_with_stock(task.qty, preferred=task.location_id)
            if not slot:
                self._fail(task, "STOCKOUT", f"{task.task_id} 没有可取库存")
                return
            self.inventory.reserve(slot, task.qty)
            task.location_id = slot
            task.origin_node = self.slots[slot]["accessNodeId"]
            path_a = shortest_path(self.adj, res.node_id, task.origin_node)
            path_b = shortest_path(self.adj, task.origin_node, task.dest_node)
            if path_a is None or path_b is None:
                self.inventory.release_reserve(slot, task.qty)
                self._fail(task, "ROUTE_UNREACHABLE", f"{task.task_id} 没有通路")
                return
        else:
            path_a = shortest_path(self.adj, res.node_id, task.origin_node)
            path_b = shortest_path(self.adj, task.origin_node, task.dest_node)
            if path_a is None or path_b is None:
                self._fail(task, "ROUTE_UNREACHABLE", f"{task.task_id} 没有通路")
                return
        nodes = list(path_a["nodes"])
        edges = list(path_a["edges"])
        task.pickup_after = len(edges)
        if path_b["nodes"]:
            nodes.extend(path_b["nodes"][1:])
            edges.extend(path_b["edges"])
        task.path_nodes = nodes
        task.path_edges = edges
        task.edge_i = 0
        task.picked = False
        task.status = "dispatched"
        task.resource_id = res.resource_id
        res.task_id = task.task_id
        res.assign_t = self.t
        self._emit(
            "dispatch",
            {
                "taskId": task.task_id,
                "resourceId": res.resource_id,
                "resourceType": res.resource_type,
                "path": nodes,
                "edges": edges,
            },
        )
        self._advance(task, res)

    def _speed(self, task: _Task, res: _Res) -> float:
        if task.picked:
            return res.travel_mps if res.travel_mps else self.travel
        return res.empty_mps if res.empty_mps else self.empty

    def _advance(self, task: _Task, res: _Res) -> None:
        if (
            task.direction in {"outbound_ship", "break_bulk"}
            and not task.picked
            and task.edge_i == task.pickup_after
        ):
            self._begin_pick(task, res)
            return
        if task.direction == "inbound_putaway" and not task.picked and task.edge_i == task.pickup_after:
            task.picked = True
            self._emit("load", {"taskId": task.task_id, "dockId": task.dock_id})
        if task.edge_i >= len(task.path_edges):
            self._at_destination(task, res)
            return
        self._request_edge(task, res, task.path_edges[task.edge_i])

    def _begin_pick(self, task: _Task, res: _Res) -> None:
        assert task.location_id
        self.inventory.remove(task.location_id, task.qty)
        task.picked = True
        self._emit("pick", {"taskId": task.task_id, "locationId": task.location_id, "qty": task.qty})
        self._schedule(
            self.t + self.pick_sec,
            PHASE_COMPLETE,
            "process_done",
            {"taskId": task.task_id, "resourceId": res.resource_id, "process": "pick"},
        )

    def _at_destination(self, task: _Task, res: _Res) -> None:
        if task.direction == "inbound_putaway":
            assert task.location_id
            self.inventory.add(task.location_id, task.qty)
            self._emit("putaway", {"taskId": task.task_id, "locationId": task.location_id, "qty": task.qty})
            self._schedule(
                self.t + float(self.putaway_sec or 0),
                PHASE_COMPLETE,
                "task_complete",
                {"taskId": task.task_id, "outbound": False},
            )
            return
        if task.direction == "break_bulk":
            self._request_station(task, res)
            return
        self._emit("ship_start", {"taskId": task.task_id, "dockId": task.dock_id, "qty": task.qty})
        self._schedule(
            self.t + self.ship_sec,
            PHASE_COMPLETE,
            "task_complete",
            {"taskId": task.task_id, "outbound": True, "palletEq": task.qty},
        )

    def _request_edge(self, task: _Task, res: _Res, edge_id: str) -> None:
        requested_at = self.t
        self._emit(
            "occupy_request",
            {"taskId": task.task_id, "resourceId": res.resource_id, "edgeId": edge_id},
        )
        gate = self.edge_gates[edge_id]
        if len(gate.holders) < gate.cap:
            self._grant_edge(task, res, edge_id, requested_at)
            return
        gate.queue.append(
            {
                "taskId": task.task_id,
                "resourceId": res.resource_id,
                "requestedAt": requested_at,
            }
        )
        task.status = "waiting_edge"

    def _grant_edge(self, task: _Task, res: _Res, edge_id: str, requested_at: float) -> None:
        gate = self.edge_gates[edge_id]
        gate.holders.append(res.resource_id)
        wait = self.t - requested_at
        if wait < 0:
            wait = 0.0
        self.edge_waits.append(
            {
                "taskId": task.task_id,
                "resourceId": res.resource_id,
                "edgeId": edge_id,
                "edgeWaitSec": wait,
                "requestedAt": requested_at,
                "grantedAt": self.t,
            }
        )
        if wait > 1e-9:
            self.entity_wait[edge_id] = self.entity_wait.get(edge_id, 0.0) + wait
        self._emit(
            "occupy_grant",
            {
                "taskId": task.task_id,
                "resourceId": res.resource_id,
                "edgeId": edge_id,
                "grantedAt": self.t,
            },
        )
        edge = self.edges[edge_id]
        frm = task.path_nodes[task.edge_i]
        to = task.path_nodes[task.edge_i + 1]
        dt = travel_time_sec(float(edge["lengthM"]), self._speed(task, res), float(edge.get("speedFactor") or 1))
        t1 = self.t + dt
        task.status = "traveling"
        self.segments.append(
            {
                "t0": self.t,
                "t1": t1,
                "from": frm,
                "to": to,
                "fromPose": {"x": self.nodes[frm]["pose"]["x"], "y": self.nodes[frm]["pose"]["y"]},
                "toPose": {"x": self.nodes[to]["pose"]["x"], "y": self.nodes[to]["pose"]["y"]},
                "resourceId": res.resource_id,
                "taskId": task.task_id,
                "edgeId": edge_id,
            }
        )
        self._emit(
            "travel_start",
            {"taskId": task.task_id, "resourceId": res.resource_id, "edgeId": edge_id, "from": frm, "to": to},
        )
        self._schedule(
            t1,
            PHASE_TRAVEL,
            "travel_arrive",
            {"taskId": task.task_id, "resourceId": res.resource_id, "edgeId": edge_id, "nodeId": to},
        )

    def _release_edge(self, edge_id: str, res: _Res, task: _Task) -> None:
        gate = self.edge_gates[edge_id]
        if res.resource_id in gate.holders:
            gate.holders.remove(res.resource_id)
        self._emit(
            "occupy_release",
            {"taskId": task.task_id, "resourceId": res.resource_id, "edgeId": edge_id},
        )
        if not gate.queue:
            return
        head = gate.queue.pop(0)
        waiter = self.tasks[head["taskId"]]
        waiter_res = next(r for r in self.resources if r.resource_id == head["resourceId"])
        self._grant_edge(waiter, waiter_res, edge_id, float(head["requestedAt"]))

    def _request_station(self, task: _Task, res: _Res) -> None:
        station_id = task.station_id or ""
        requested_at = self.t
        self._emit(
            "occupy_request",
            {"taskId": task.task_id, "resourceId": res.resource_id, "stationId": station_id},
        )
        gate = self.station_gates[station_id]
        if len(gate.holders) < gate.cap:
            self._grant_station(task, res, station_id, requested_at)
            return
        gate.queue.append(
            {"taskId": task.task_id, "resourceId": res.resource_id, "requestedAt": requested_at}
        )
        task.status = "waiting_station"

    def _grant_station(self, task: _Task, res: _Res, station_id: str, requested_at: float) -> None:
        gate = self.station_gates[station_id]
        gate.holders.append(res.resource_id)
        wait = max(0.0, self.t - requested_at)
        task.station_wait_sec = wait
        if wait > 1e-9:
            self.entity_wait[station_id] = self.entity_wait.get(station_id, 0.0) + wait
        self._emit(
            "occupy_grant",
            {
                "taskId": task.task_id,
                "resourceId": res.resource_id,
                "stationId": station_id,
                "grantedAt": self.t,
            },
        )
        task.status = "breaking"
        self._schedule(
            self.t + float(self.break_sec or 0),
            PHASE_COMPLETE,
            "process_done",
            {"taskId": task.task_id, "resourceId": res.resource_id, "process": "break_bulk", "t0": self.t},
        )

    def _release_station(self, station_id: str, res: _Res, task: _Task) -> None:
        gate = self.station_gates[station_id]
        if res.resource_id in gate.holders:
            gate.holders.remove(res.resource_id)
        self._emit(
            "occupy_release",
            {"taskId": task.task_id, "resourceId": res.resource_id, "stationId": station_id},
        )
        if not gate.queue:
            return
        head = gate.queue.pop(0)
        waiter = self.tasks[head["taskId"]]
        waiter_res = next(r for r in self.resources if r.resource_id == head["resourceId"])
        self._grant_station(waiter, waiter_res, station_id, float(head["requestedAt"]))

    def _finish_break(self, task: _Task, res: _Res) -> None:
        cases = float(task.qty) * float(self.cases_per_pallet or 0)
        self.inventory.convert_to_cases(task.qty, cases, task.station_id or "")
        task.cases_created = cases
        t0 = None
        for ev in reversed(self.events):
            if ev.get("kind") == "occupy_grant" and ev.get("taskId") == task.task_id and ev.get("stationId") == task.station_id:
                t0 = float(ev["t"])
                break
        self.station_windows.append(
            {
                "stationId": task.station_id,
                "taskId": task.task_id,
                "resourceId": res.resource_id,
                "t0": t0 if t0 is not None else self.t,
                "t1": self.t,
                "waitSec": task.station_wait_sec,
            }
        )
        self._release_station(task.station_id or "", res, task)
        if self.downstream_piece:
            self._spawn_piece(task, cases)
        task.status = "done"
        self._emit(
            "task_complete",
            {
                "taskId": task.task_id,
                "status": "done",
                "waitSec": task.wait_sec,
                "direction": task.direction,
                "casesCreated": cases,
            },
        )
        self._release(res)

    def _spawn_piece(self, parent: _Task, cases: float) -> None:
        child_id = f"{parent.task_id}-piece"
        body = {
            "taskId": child_id,
            "flowKind": "piece_pick",
            "status": "generated",
            "qtyCases": cases,
            "parentTaskId": parent.task_id,
            "originId": parent.station_id,
            "direction": "piece_pick",
        }
        self.piece_tasks.append(body)
        self._emit(
            "piece_pick_generated",
            {"taskId": child_id, "parentTaskId": parent.task_id, "qtyCases": cases, "flowKind": "piece_pick"},
        )

    def _release(self, res: _Res) -> None:
        res.busy_sec += self.t - res.assign_t
        res.last_busy_end = self.t
        res.task_id = None
        self._pump(res.pool_id)

    def _on_arrival(self, task_id: str) -> None:
        task = self.tasks[task_id]
        task.status = "queued"
        self._emit("arrival", {"taskId": task_id, "direction": task.direction})
        self.queues[self.forklift_pool].append(task_id)
        self._pump(self.forklift_pool)

    def _on_travel_arrive(self, payload: Dict[str, Any]) -> None:
        task = self.tasks[payload["taskId"]]
        res = next(r for r in self.resources if r.resource_id == payload["resourceId"])
        self._release_edge(payload["edgeId"], res, task)
        task.edge_i += 1
        res.node_id = payload["nodeId"]
        self._emit(
            "travel_arrive",
            {
                "taskId": task.task_id,
                "resourceId": res.resource_id,
                "nodeId": payload["nodeId"],
                "edgeId": payload["edgeId"],
            },
        )
        self._advance(task, res)

    def _on_process_done(self, payload: Dict[str, Any]) -> None:
        task = self.tasks[payload["taskId"]]
        res = next(r for r in self.resources if r.resource_id == payload["resourceId"])
        if payload.get("process") == "break_bulk":
            self._finish_break(task, res)
            return
        self._emit("pick_done", {"taskId": task.task_id, "resourceId": res.resource_id})
        self._advance(task, res)

    def _on_task_complete(self, payload: Dict[str, Any]) -> None:
        task = self.tasks[payload["taskId"]]
        res = next(r for r in self.resources if r.resource_id == task.resource_id)
        if payload.get("outbound"):
            peq = float(payload.get("palletEq") or task.qty)
            self.inventory.ship(peq)
            self.outbound_pallet_eq += peq
            eid = self._emit(
                "ship",
                {"taskId": task.task_id, "dockId": task.dock_id, "palletEq": peq},
            )
            self.ship_event_ids.append(eid)
        task.status = "done"
        self._emit(
            "task_complete",
            {"taskId": task.task_id, "status": "done", "waitSec": task.wait_sec, "direction": task.direction},
        )
        self._release(res)

    def _path_ok(self, origin: str, dest: str) -> bool:
        if not origin or not dest:
            return False
        return shortest_path(self.adj, origin, dest) is not None

    def _reject_if_unlinked(self) -> None:
        """Stop at load when this workload has no aisle path. No events, no cards."""
        homes = [res.node_id for res in self.resources if res.resource_type == "forklift" and res.node_id]
        if not homes:
            return
        for task in self.tasks.values():
            dest = task.dest_node
            if task.direction in {"outbound_ship", "break_bulk"} and not task.origin_node:
                origins = [
                    str(slot.get("accessNodeId"))
                    for slot in self.slots.values()
                    if slot.get("accessNodeId")
                    and self.inventory.available(slot["elementId"]) + 1e-9 >= task.qty
                ]
                if not dest or not origins:
                    continue
                linked = any(
                    self._path_ok(home, origin) and self._path_ok(origin, dest)
                    for home in homes
                    for origin in origins
                )
                if not linked:
                    raise DesError(
                        "ROUTE_UNREACHABLE",
                        "通道图不连通，加载失败，未进入调度",
                        {"taskId": task.task_id, "destNode": dest},
                    )
                continue
            if task.origin_node and dest:
                linked = any(
                    self._path_ok(home, task.origin_node) and self._path_ok(task.origin_node, dest)
                    for home in homes
                )
                if not linked:
                    raise DesError(
                        "ROUTE_UNREACHABLE",
                        "通道图不连通，加载失败，未进入调度",
                        {"taskId": task.task_id, "originNode": task.origin_node, "destNode": dest},
                    )

    def run(self) -> Dict[str, Any]:
        started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        before = deepcopy(self.snapshot_in)
        self._prepare_inputs()
        self._generate()
        self._reject_if_unlinked()
        while self.pq:
            ev = heapq.heappop(self.pq)
            if ev.t > self.horizon + 1e-9:
                break
            self.t = ev.t
            if ev.kind == "arrival":
                self._on_arrival(ev.payload["taskId"])
            elif ev.kind == "travel_arrive":
                self._on_travel_arrive(ev.payload)
            elif ev.kind == "process_done":
                self._on_process_done(ev.payload)
            elif ev.kind == "task_complete":
                self._on_task_complete(ev.payload)
            else:
                raise DesError("COMPUTATION_FAILED", f"未知事件 {ev.kind}")
        if before != self.snapshot_in:
            raise DesError("COMPUTATION_FAILED", "推演改写了输入快照")
        conservation = self.inventory.conservation()
        if not conservation["ok"]:
            self.warnings.append({"code": "INVENTORY_CONSERVATION", "message": "库存守恒不成立"})
        completed = [t for t in self.tasks.values() if t.status == "done"]
        incomplete = [t for t in self.tasks.values() if t.status != "done"]
        kpi = compute_cards(
            horizon_sec=self.horizon,
            completed=[{"taskId": t.task_id, "waitSec": t.wait_sec} for t in completed],
            resources=[
                {
                    "resourceId": r.resource_id,
                    "resourceType": r.resource_type,
                    "busySec": r.busy_sec,
                }
                for r in self.resources
            ],
            entity_wait_sec=dict(self.entity_wait),
            outbound_pallet_eq=self.outbound_pallet_eq,
            incomplete_count=len(incomplete),
        )
        finished = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        revision = self.snapshot["layoutRevision"]
        ship_evidence = [
            {"eventId": e["eventId"], "t": e["t"], "taskId": e.get("taskId"), "palletEq": e.get("palletEq")}
            for e in self.events
            if e["eventId"] in set(self.ship_event_ids)
        ]
        return {
            "contractVersion": "0.3",
            "engineVersion": ENGINE_VERSION,
            "metricDefinitionVersion": self.run_control.get("metricDefinitionVersion")
            or METRIC_DEFINITION_VERSION,
            "kpiFromUiDemo": False,
            "runId": self.run_id,
            "layoutId": self.snapshot.get("layoutId"),
            "layoutRevision": revision,
            "cards": kpi["cards"],
            "secondary": kpi["secondary"],
            "runManifest": {
                "runId": self.run_id,
                "layoutRef": {"id": self.snapshot.get("layoutId"), "revision": revision},
                "seedStreams": dict(self.run_control.get("seedStreams") or {}),
                "engineVersion": ENGINE_VERSION,
                "metricDefinitionVersion": self.run_control.get("metricDefinitionVersion")
                or METRIC_DEFINITION_VERSION,
                "startedAt": started,
                "finishedAt": finished,
                "state": "succeeded",
                "warnings": self.warnings,
                "horizonSec": self.horizon,
                "kpiFromUiDemo": False,
            },
            "events": self.events,
            "shipEvidence": ship_evidence,
            "trajectory": {
                "runId": self.run_id,
                "layoutRevision": revision,
                "horizonSec": self.horizon,
                "segments": self.segments,
                "tasks": [
                    {
                        "taskId": t.task_id,
                        "status": t.status,
                        "direction": t.direction,
                        "flowKind": t.flow_kind,
                        "waitSec": t.wait_sec,
                        "stationWaitSec": t.station_wait_sec,
                        "casesCreated": t.cases_created,
                        "locationId": t.location_id,
                        "stationId": t.station_id,
                        "resourceId": t.resource_id,
                    }
                    for t in self.tasks.values()
                ]
                + self.piece_tasks,
            },
            "resources": [
                {
                    "resourceId": r.resource_id,
                    "resourceType": r.resource_type,
                    "busySec": r.busy_sec,
                }
                for r in self.resources
            ],
            "inventoryConservation": conservation,
            "edgeWaits": self.edge_waits,
            "stationWindows": self.station_windows,
            "piecePickTasks": self.piece_tasks,
        }


def run_des(**kwargs: Any) -> Dict[str, Any]:
    return DesEngine(**kwargs).run()
