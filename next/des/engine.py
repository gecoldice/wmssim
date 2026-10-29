"""Event engine for full_pallet only.

Stages per outbound task: arrival, resource wait, empty travel, pick,
loaded travel, ship. Busy time is the whole assignment, including travel.
Speeds and process seconds are required inputs — this module does not invent them.
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
    ) -> None:
        self.snapshot_in = snapshot
        self.snapshot = deepcopy(snapshot)
        self.demand = demand
        self.operating = operating
        self.run_control = run_control
        self.expected_layout_revision = expected_layout_revision
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
        self.pick_sec = self._require_number(proc, "pick", "取货时间")
        self.ship_sec = self._require_number(proc, "ship", "发运时间")
        self.putaway_sec = float(proc["putaway"]) if proc.get("putaway") not in (None, "") else None
        self.nodes = {
            e["elementId"]: e for e in self.snapshot.get("elements") or [] if e.get("kind") == "node"
        }
        self.slots = {
            e["elementId"]: e for e in self.snapshot.get("elements") or [] if e.get("kind") == "slot"
        }
        self.docks = {
            e["elementId"]: e for e in self.snapshot.get("elements") or [] if e.get("kind") == "dock"
        }
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
        self.inventory = InventoryLedger(self.snapshot, list(self.demand.get("initialInventory") or []))
        self._build_resources()
        self._check_flows()

    def _check_flows(self) -> None:
        for flow in self.demand.get("flows") or []:
            kind = flow.get("flowKind")
            if kind != "full_pallet":
                raise DesError(
                    "UNSUPPORTED_SCENARIO",
                    f"本切片只接受 flowKind=full_pallet，收到 {kind}",
                    {"flowKind": kind},
                )

    def _build_resources(self) -> None:
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

    def _generate(self) -> None:
        task_n = 0
        for flow in self.demand.get("flows") or []:
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
        if task.direction == "outbound_ship":
            slot = self.inventory.pick_slot_with_stock(task.qty)
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

    def _speed(self, task: _Task) -> float:
        return self.travel if task.picked else self.empty

    def _advance(self, task: _Task, res: _Res) -> None:
        if (
            task.direction == "outbound_ship"
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
        eid = task.path_edges[task.edge_i]
        edge = self.edges[eid]
        frm = task.path_nodes[task.edge_i]
        to = task.path_nodes[task.edge_i + 1]
        dt = travel_time_sec(float(edge["lengthM"]), self._speed(task), float(edge.get("speedFactor") or 1))
        t1 = self.t + dt
        self.segments.append(
            {
                "t0": self.t,
                "t1": t1,
                "from": frm,
                "to": to,
                "fromPose": {
                    "x": self.nodes[frm]["pose"]["x"],
                    "y": self.nodes[frm]["pose"]["y"],
                },
                "toPose": {"x": self.nodes[to]["pose"]["x"], "y": self.nodes[to]["pose"]["y"]},
                "resourceId": res.resource_id,
                "taskId": task.task_id,
                "edgeId": eid,
            }
        )
        self._emit(
            "travel_start",
            {"taskId": task.task_id, "resourceId": res.resource_id, "edgeId": eid, "from": frm, "to": to},
        )
        self._schedule(
            t1,
            PHASE_TRAVEL,
            "travel_arrive",
            {"taskId": task.task_id, "resourceId": res.resource_id, "edgeId": eid, "nodeId": to},
        )

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
        self._emit("ship_start", {"taskId": task.task_id, "dockId": task.dock_id, "qty": task.qty})
        self._schedule(
            self.t + self.ship_sec,
            PHASE_COMPLETE,
            "task_complete",
            {"taskId": task.task_id, "outbound": True, "palletEq": task.qty},
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

    def run(self) -> Dict[str, Any]:
        started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        before = deepcopy(self.snapshot_in)
        self._prepare_inputs()
        self._generate()
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
                        "waitSec": t.wait_sec,
                        "locationId": t.location_id,
                        "resourceId": t.resource_id,
                    }
                    for t in self.tasks.values()
                ],
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
        }


def run_des(**kwargs: Any) -> Dict[str, Any]:
    return DesEngine(**kwargs).run()
