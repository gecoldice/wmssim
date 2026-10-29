"""DES 核心：只读 Snapshot；FIFO；确定性事件序；主四卡由事件派生。

事件排序：(simTime, phasePriority, sequenceNo)
同刻：释放占用 → 完成/产出 → 到达/生成 → 申请/派发
"""

from __future__ import annotations

import heapq
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .graph import build_adjacency, edge_lookup, shortest_path, travel_time_sec
from .inventory import InventoryError, InventoryLedger
from .kpi import compute_kpi, kpi_event_evidence

ENGINE_VERSION = "m3-des-0.1"
METRIC_DEFINITION_VERSION = "metrics-m3-v1"

PHASE_RELEASE = 10
PHASE_COMPLETE = 20
PHASE_ARRIVE = 30
PHASE_REQUEST = 40


class DesError(Exception):
    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(order=True)
class Event:
    t: float
    phase: int
    seq: int
    kind: str = field(compare=False)
    payload: Dict[str, Any] = field(compare=False, default_factory=dict)


@dataclass
class Resource:
    resource_id: str
    pool_id: str
    kind: str
    home_node: str
    last_busy_end: float = 0.0
    busy_sec: float = 0.0
    node_id: str = ""
    task_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = self.home_node


@dataclass
class Task:
    task_id: str
    flow_kind: str
    qty: float
    origin_node: str
    dest_node: str
    location_id: Optional[str]
    dock_id: Optional[str]
    direction: str  # inbound_putaway | outbound_ship
    status: str = "queued"
    wait_sec: float = 0.0
    busy_sec: float = 0.0
    enqueue_t: float = 0.0
    resource_id: Optional[str] = None
    path_nodes: List[str] = field(default_factory=list)
    path_edges: List[str] = field(default_factory=list)
    edge_i: int = 0
    picked: bool = False
    waiting_on: Optional[str] = None
    wait_start: Optional[float] = None
    flow_chain_id: Optional[str] = None
    phase: str = "to_pickup"  # to_pickup | to_dest


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
        scenario_id: Optional[str] = None,
        variant_ref: Optional[Dict[str, str]] = None,
        validation_ref: Optional[Dict[str, Any]] = None,
        faults: Optional[List[Dict[str, Any]]] = None,
        skill_tags_present: bool = False,
        shift_schedule_present: bool = False,
    ) -> None:
        self.snapshot = deepcopy(snapshot)
        self.demand = demand
        self.operating = operating
        self.run_control = run_control
        self.expected_layout_revision = expected_layout_revision
        self.run_id = run_id or f"run-{uuid4().hex[:10]}"
        self.scenario_id = scenario_id or "scenario-inline"
        self.variant_ref = variant_ref
        self.validation_ref = validation_ref
        self.faults = faults or []
        self.warnings: List[Dict[str, str]] = []
        self.skill_tags_present = skill_tags_present
        self.shift_schedule_present = shift_schedule_present

        self.horizon = float(run_control.get("horizonSec") or 0)
        self.seed_streams = dict(run_control.get("seedStreams") or {"demand": 42, "dispatch": 42})
        self.seq = 0
        self.t = 0.0
        self.pq: List[Event] = []
        self.events: List[Dict[str, Any]] = []
        self.segments: List[Dict[str, Any]] = []
        self.tasks: Dict[str, Task] = {}
        self.resources: List[Resource] = []
        self.pool_queue: Dict[str, List[str]] = {}
        self.edge_occ: Dict[str, int] = {}
        self.edge_wait: Dict[str, List[Tuple[str, str]]] = {}
        self.entity_wait: Dict[str, float] = {}
        self.outbound_pallet_eq = 0.0
        self.outbound_event_ids: List[str] = []
        self.event_counter = 0
        self.max_events = int(run_control.get("maxEvents") or 200_000)

        defaults = self.snapshot.get("defaults") or {}
        svc = self.operating.get("serviceParameters") or {}
        self.travel_speed = float(svc.get("travelSpeedMps") or defaults.get("travelSpeedMps") or 1.2)
        self.empty_speed = float(svc.get("emptySpeedMps") or defaults.get("emptySpeedMps") or 1.5)
        proc = svc.get("processSec") or {}
        self.process_putaway = float(proc.get("full_pallet") or proc.get("putaway") or 90)
        self.process_pick = float(proc.get("pick") or 60)
        self.process_ship = float(proc.get("ship") or 30)

        self.adj = build_adjacency(self.snapshot)
        self.edges = edge_lookup(self.snapshot)
        self._index_layout()
        self.inventory = InventoryLedger(
            self.snapshot, list(self.demand.get("initialInventory") or [])
        )

    def _index_layout(self) -> None:
        self.nodes = {
            e["elementId"]: e for e in self.snapshot.get("elements") or [] if e.get("kind") == "node"
        }
        self.slots = {
            e["elementId"]: e for e in self.snapshot.get("elements") or [] if e.get("kind") == "slot"
        }
        self.docks = {
            e["elementId"]: e for e in self.snapshot.get("elements") or [] if e.get("kind") == "dock"
        }
        self.recv_dock = next(
            (d for d in self.docks.values() if "recv" in (d.get("labels") or [])), None
        )
        self.ship_dock = next(
            (d for d in self.docks.values() if "ship" in (d.get("labels") or [])), None
        )
        homes = [
            e
            for e in self.snapshot.get("elements") or []
            if e.get("kind") == "device" and e.get("resourceHome")
        ]
        self.home_node = (
            (homes[0].get("accessNodeId") if homes else None)
            or (self.recv_dock.get("accessNodeId") if self.recv_dock else None)
            or next(iter(self.nodes), None)
        )

    def _warn(self, code: str, message: str) -> None:
        self.warnings.append({"code": code, "message": message})

    def _next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def _schedule(self, t: float, phase: int, kind: str, payload: Dict[str, Any]) -> None:
        if t > self.horizon + 1e-9:
            return
        heapq.heappush(
            self.pq, Event(t=t, phase=phase, seq=self._next_seq(), kind=kind, payload=payload)
        )

    def _emit(self, kind: str, payload: Dict[str, Any]) -> str:
        self.event_counter += 1
        eid = f"ev-{self.event_counter:06d}"
        self.events.append({"eventId": eid, "t": self.t, "kind": kind, **payload})
        return eid

    def validate_load(self) -> None:
        if self.snapshot.get("schemaVersion") != "0.2":
            raise DesError("CONTRACT_VERSION", "Snapshot schemaVersion must be 0.2")
        rev = self.snapshot.get("layoutRevision")
        if rev != self.expected_layout_revision:
            raise DesError(
                "LAYOUT_REVISION_MISMATCH",
                "expectedLayoutRevision 与快照 layoutRevision 字符串不相等",
                {"expected": self.expected_layout_revision, "actual": rev},
            )
        for el in self.snapshot.get("elements") or []:
            if el.get("kind") in {"slot", "dock", "station", "device"}:
                an = el.get("accessNodeId")
                if not an or an not in self.nodes:
                    raise DesError(
                        "NO_ACCESS_NODE",
                        f"{el.get('elementId')} 缺有效 accessNodeId",
                        {"elementId": el.get("elementId"), "accessNodeId": an},
                    )
        if not self.ship_dock and not self.recv_dock:
            raise DesError("INPUT_UNCONFIRMED", "快照缺少收货/发运月台")
        if self.horizon <= 0:
            raise DesError("INPUT_UNCONFIRMED", "horizonSec 必须 > 0")

        for f in self.faults:
            if f.get("enabled") is True:
                self._warn(
                    "FAULT_INJECT_IGNORED",
                    f"faultInject enabled 被忽略（MVP 不实现）：{f.get('faultType') or f}",
                )
        for pool in self.operating.get("resourcePools") or []:
            if pool.get("skillTags"):
                self.skill_tags_present = True
            for r in pool.get("resources") or []:
                if r.get("skillTags"):
                    self.skill_tags_present = True
        if self.skill_tags_present:
            self._warn(
                "SKILL_TAGS_IGNORED",
                "skillTags 已填写但本版本调度忽略（仍 FIFO+空闲最久）",
            )
        if self.shift_schedule_present or self.operating.get("shiftSchedule"):
            self._warn("SHIFT_SCHEDULE_IGNORED", "shiftSchedule 已填写但本版本忽略")

    def _build_resources(self) -> None:
        for pool in self.operating.get("resourcePools") or []:
            kind = pool.get("resourceType") or "forklift"
            if kind not in {"forklift", "picker"}:
                continue
            count = int(pool.get("count") or 0)
            pool_id = pool.get("id") or f"pool-{kind}"
            self.pool_queue[pool_id] = []
            home = self.home_node or ""
            homes = pool.get("homeInstanceIds") or []
            if homes:
                for el in self.snapshot.get("elements") or []:
                    if el.get("elementId") in homes and el.get("accessNodeId"):
                        home = el["accessNodeId"]
                        break
            for i in range(count):
                self.resources.append(
                    Resource(
                        resource_id=f"{kind}-{i+1}",
                        pool_id=pool_id,
                        kind=kind,
                        home_node=home,
                    )
                )
        if not self.resources:
            raise DesError("NO_RESOURCES", "资源数为 0，无法推演")

    def _add_task(self, task: Task, t_arr: float, spawn_kind: str) -> None:
        self.tasks[task.task_id] = task
        self._schedule(t_arr, PHASE_ARRIVE, spawn_kind, {"taskId": task.task_id})

    def _generate_tasks(self) -> None:
        # 种子写入 RunManifest；整数均匀到达，无随机抖动 → 同输入可复现
        _ = int(self.seed_streams.get("demand", 42))
        flows = list(self.demand.get("flows") or [])
        task_n = 0
        window = float(
            (self.demand.get("arrivalProfile") or {}).get("windowSec") or self.horizon
        )
        window = min(window, self.horizon)

        def arrival_times(n: int) -> List[float]:
            if n <= 0:
                return []
            if n == 1:
                return [0.0]
            return [window * i / n for i in range(n)]

        for flow in flows:
            fk = flow.get("flowKind")
            if fk != "full_pallet":
                self._warn("FLOW_KIND_STUB", f"flowKind={fk} 本切片未建模，已跳过")
                continue
            qty_total = float(flow.get("quantity") or 0)
            if qty_total <= 0:
                continue
            n = int(round(qty_total))
            intent = flow.get("intent") or flow.get("direction")
            source = flow.get("source") or "external"
            # intent 优先；否则 external + 无 downstream → inbound；storage/inventory → outbound
            if intent in {"outbound", "outbound_ship"} or source in {"storage", "inventory"}:
                direction = "outbound_ship"
            elif intent in {"inbound", "inbound_putaway"} or source == "external":
                direction = "inbound_putaway"
            else:
                direction = "outbound_ship"

            times = arrival_times(n)
            for i, t_arr in enumerate(times):
                task_n += 1
                if direction == "inbound_putaway":
                    if not self.recv_dock:
                        raise DesError("INPUT_UNCONFIRMED", "入库流需要收货月台")
                    slot = self.inventory.pick_slot_with_capacity(1.0)
                    if not slot:
                        self._warn("NO_SLOT_CAPACITY", f"无库位容量承接入库任务 #{i+1}")
                        continue
                    tid = f"T-in-{task_n:04d}"
                    self._add_task(
                        Task(
                            task_id=tid,
                            flow_kind="full_pallet",
                            qty=1.0,
                            origin_node=self.recv_dock["accessNodeId"],
                            dest_node=self.slots[slot]["accessNodeId"],
                            location_id=slot,
                            dock_id=self.recv_dock["elementId"],
                            direction="inbound_putaway",
                            enqueue_t=t_arr,
                            flow_chain_id=tid,
                        ),
                        t_arr,
                        "arrival",
                    )
                else:
                    if not self.ship_dock:
                        raise DesError("INPUT_UNCONFIRMED", "出库流需要发运月台")
                    preferred = next(iter(sorted(self.slots.keys())), None)
                    if preferred is None:
                        self._warn("NO_SLOT", "无货位可服务出库")
                        continue
                    tid = f"T-out-{task_n:04d}"
                    self._add_task(
                        Task(
                            task_id=tid,
                            flow_kind="full_pallet",
                            qty=1.0,
                            origin_node=self.slots[preferred]["accessNodeId"],
                            dest_node=self.ship_dock["accessNodeId"],
                            location_id=preferred,
                            dock_id=self.ship_dock["elementId"],
                            direction="outbound_ship",
                            enqueue_t=t_arr,
                            flow_chain_id=tid,
                        ),
                        t_arr,
                        "task_spawn",
                    )

        if not flows and self.inventory.initial_total > 0 and self.ship_dock:
            n = int(round(self.inventory.initial_total))
            for i, t_arr in enumerate(arrival_times(n)):
                task_n += 1
                preferred = next(iter(sorted(self.slots.keys())))
                tid = f"T-out-{task_n:04d}"
                self._add_task(
                    Task(
                        task_id=tid,
                        flow_kind="full_pallet",
                        qty=1.0,
                        origin_node=self.slots[preferred]["accessNodeId"],
                        dest_node=self.ship_dock["accessNodeId"],
                        location_id=preferred,
                        dock_id=self.ship_dock["elementId"],
                        direction="outbound_ship",
                        enqueue_t=t_arr,
                        flow_chain_id=tid,
                    ),
                    t_arr,
                    "task_spawn",
                )

    def _resource(self, rid: str) -> Resource:
        return next(r for r in self.resources if r.resource_id == rid)

    def _pick_longest_idle(self, pool_id: str) -> Optional[Resource]:
        idle = [r for r in self.resources if r.pool_id == pool_id and r.task_id is None]
        if not idle:
            return None
        idle.sort(key=lambda r: (r.last_busy_end, r.resource_id))
        return idle[0]

    def _pool_for_task(self, _task: Task) -> str:
        for p in self.operating.get("resourcePools") or []:
            if (p.get("resourceType") or "forklift") == "forklift":
                return p.get("id") or "pool-forklift"
        return self.resources[0].pool_id

    def _clear_wait(self, task: Task) -> None:
        if task.wait_start is not None and task.waiting_on:
            waited = self.t - task.wait_start
            task.wait_sec += waited
            self.entity_wait[task.waiting_on] = self.entity_wait.get(task.waiting_on, 0.0) + waited
        task.wait_start = None
        task.waiting_on = None

    def _request_dispatch(self, task_id: str) -> None:
        task = self.tasks[task_id]
        if task.status not in {"queued", "waiting_resource"}:
            return
        pool = self._pool_for_task(task)
        res = self._pick_longest_idle(pool)
        if not res:
            if task_id not in self.pool_queue[pool]:
                self.pool_queue[pool].append(task_id)
                task.status = "waiting_resource"
                task.waiting_on = pool
                task.wait_start = self.t
                self._emit("occupy_request", {"taskId": task_id, "poolId": pool, "queued": True})
            return
        self._assign(res, task)

    def _assign(self, res: Resource, task: Task) -> None:
        self._clear_wait(task)
        task.status = "dispatched"
        task.resource_id = res.resource_id
        res.task_id = task.task_id

        if task.direction == "outbound_ship":
            slot = self.inventory.pick_slot_with_stock(task.qty, preferred=task.location_id)
            if not slot:
                # 仍派发到偏好位，取货时 STOCKOUT → failed
                slot = task.location_id or next(iter(sorted(self.slots.keys())))
            task.location_id = slot
            pick_node = self.slots[slot]["accessNodeId"]
            task.origin_node = pick_node
            path1 = shortest_path(self.adj, res.node_id, pick_node)
            path2 = shortest_path(self.adj, pick_node, task.dest_node)
        else:
            path1 = shortest_path(self.adj, res.node_id, task.origin_node)
            path2 = shortest_path(self.adj, task.origin_node, task.dest_node)

        if path1 is None or path2 is None:
            self._warn("NO_PATH", f"任务 {task.task_id} 无可达最短路")
            task.status = "failed"
            res.task_id = None
            res.last_busy_end = self.t
            return

        nodes = list(path1["nodes"])
        edges = list(path1["edges"])
        # 记录取货点在合并路径中的下标
        pickup_idx = len(nodes) - 1
        if path2["nodes"]:
            nodes.extend(path2["nodes"][1:])
            edges.extend(path2["edges"])
        task.path_nodes = nodes
        task.path_edges = edges
        task.edge_i = 0
        task.picked = False
        task.phase = "to_pickup"
        self._emit(
            "dispatch",
            {
                "taskId": task.task_id,
                "resourceId": res.resource_id,
                "path": nodes,
                "edges": edges,
                "pickupIndex": pickup_idx,
            },
        )
        self._emit(
            "haul_start",
            {"taskId": task.task_id, "resourceId": res.resource_id, "path": nodes, "t0": self.t},
        )
        if not edges:
            # 已在点上
            self._schedule(
                self.t,
                PHASE_COMPLETE,
                "at_node",
                {"taskId": task.task_id, "nodeId": res.node_id},
            )
        else:
            self._try_enter_edge(task, res)

    def _speed_for(self, task: Task) -> float:
        if task.direction == "outbound_ship":
            return self.travel_speed if task.picked else self.empty_speed
        # inbound：离开收货口后载货
        return self.travel_speed if task.phase == "to_dest" else self.empty_speed

    def _try_enter_edge(self, task: Task, res: Resource) -> None:
        if task.edge_i >= len(task.path_edges):
            self._schedule(
                self.t, PHASE_COMPLETE, "at_node", {"taskId": task.task_id, "nodeId": res.node_id}
            )
            return
        eid = task.path_edges[task.edge_i]
        edge = self.edges[eid]
        mc = int(edge.get("maxConcurrent") or 1)
        occ = self.edge_occ.get(eid, 0)
        if occ >= mc:
            self.edge_wait.setdefault(eid, []).append((task.task_id, res.resource_id))
            task.status = "waiting_edge"
            task.waiting_on = eid
            task.wait_start = self.t
            self._emit(
                "occupy_request",
                {
                    "taskId": task.task_id,
                    "resourceId": res.resource_id,
                    "edgeId": eid,
                    "queued": True,
                },
            )
            return

        self.edge_occ[eid] = occ + 1
        self._emit(
            "occupy_grant",
            {"taskId": task.task_id, "resourceId": res.resource_id, "edgeId": eid},
        )
        length = float(edge.get("lengthM") or 0)
        sf = float(edge.get("speedFactor") or 1.0)
        dt = travel_time_sec(length, self._speed_for(task), sf)
        frm = task.path_nodes[task.edge_i]
        to = task.path_nodes[task.edge_i + 1]
        t0, t1 = self.t, self.t + dt
        self.segments.append(
            {
                "t0": t0,
                "t1": t1,
                "from": frm,
                "to": to,
                "resourceId": res.resource_id,
                "taskId": task.task_id,
                "edgeId": eid,
            }
        )
        task.status = "hauling"
        self._schedule(
            t1,
            PHASE_ARRIVE,
            "haul_arrive",
            {
                "taskId": task.task_id,
                "resourceId": res.resource_id,
                "edgeId": eid,
                "nodeId": to,
            },
        )

    def _release_edge(self, edge_id: str) -> None:
        self.edge_occ[edge_id] = max(0, self.edge_occ.get(edge_id, 0) - 1)
        self._emit("occupy_release", {"edgeId": edge_id})
        q = self.edge_wait.get(edge_id) or []
        if not q:
            return
        tid, rid = q.pop(0)
        task = self.tasks.get(tid)
        if not task or task.resource_id != rid or task.status != "waiting_edge":
            return
        res = self._resource(rid)
        self._clear_wait(task)
        self._try_enter_edge(task, res)

    def _finish_resource(self, res: Resource) -> None:
        res.task_id = None
        res.last_busy_end = self.t
        q = self.pool_queue.get(res.pool_id) or []
        while q:
            nxt = q.pop(0)
            nt = self.tasks.get(nxt)
            if nt and nt.status in {"queued", "waiting_resource"}:
                self._assign(res, nt)
                return

    def _fail_task(self, task: Task, res: Resource, code: str, message: str) -> None:
        self._warn(code, message)
        task.status = "failed"
        res.task_id = None
        res.last_busy_end = self.t
        self._emit("task_complete", {"taskId": task.task_id, "status": "failed"})
        self._finish_resource(res)

    def _on_at_node(self, task: Task, res: Resource, node_id: str) -> None:
        """到达某节点后的业务动作 / 继续下一段。"""
        res.node_id = node_id

        # 出库：到取货点且未取货
        if (
            task.direction == "outbound_ship"
            and not task.picked
            and node_id == task.origin_node
        ):
            try:
                self.inventory.remove(
                    task.location_id, task.qty, t=self.t, task_id=task.task_id
                )
            except InventoryError as exc:
                self._fail_task(task, res, exc.code, exc.message)
                return
            task.picked = True
            task.phase = "to_dest"
            task.status = "picking"
            self._emit(
                "pick",
                {
                    "taskId": task.task_id,
                    "locationId": task.location_id,
                    "qty": task.qty,
                },
            )
            dt = self.process_pick
            task.busy_sec += dt
            res.busy_sec += dt
            self._schedule(
                self.t + dt,
                PHASE_COMPLETE,
                "process_done",
                {"taskId": task.task_id, "next": "continue"},
            )
            return

        # 入库：到收货口
        if (
            task.direction == "inbound_putaway"
            and task.phase == "to_pickup"
            and node_id == task.origin_node
        ):
            task.phase = "to_dest"
            self._emit("arrival_loaded", {"taskId": task.task_id, "dockId": task.dock_id})

        # 还有边 → 继续
        if task.edge_i < len(task.path_edges):
            self._try_enter_edge(task, res)
            return

        # 路径结束
        if task.direction == "inbound_putaway":
            try:
                self.inventory.add(
                    task.location_id, task.qty, t=self.t, task_id=task.task_id
                )
            except InventoryError as exc:
                self._fail_task(task, res, exc.code, exc.message)
                return
            dt = self.process_putaway
            task.busy_sec += dt
            res.busy_sec += dt
            self._emit(
                "putaway",
                {
                    "taskId": task.task_id,
                    "locationId": task.location_id,
                    "qty": task.qty,
                },
            )
            self._schedule(
                self.t + dt,
                PHASE_COMPLETE,
                "task_complete",
                {"taskId": task.task_id, "outbound": False},
            )
            return

        # outbound 发运
        dt = self.process_ship
        task.busy_sec += dt
        res.busy_sec += dt
        self._emit(
            "outbound",
            {"taskId": task.task_id, "dockId": task.dock_id, "palletEq": task.qty},
        )
        self._schedule(
            self.t + dt,
            PHASE_COMPLETE,
            "task_complete",
            {"taskId": task.task_id, "outbound": True, "palletEq": task.qty},
        )

    def _on_haul_arrive(self, payload: Dict[str, Any]) -> None:
        task = self.tasks[payload["taskId"]]
        res = self._resource(payload["resourceId"])
        edge_id = payload["edgeId"]
        node_id = payload["nodeId"]
        self._emit(
            "haul_arrive",
            {
                "taskId": task.task_id,
                "resourceId": res.resource_id,
                "nodeId": node_id,
                "edgeId": edge_id,
            },
        )
        task.edge_i += 1
        # 先释放边（同刻优先），再处理节点业务
        self._schedule(self.t, PHASE_RELEASE, "release_edge", {"edgeId": edge_id})
        self._schedule(
            self.t,
            PHASE_COMPLETE,
            "at_node",
            {"taskId": task.task_id, "nodeId": node_id},
        )

    def _on_task_complete(self, payload: Dict[str, Any]) -> None:
        task = self.tasks[payload["taskId"]]
        res = self._resource(task.resource_id)  # type: ignore[arg-type]
        if payload.get("outbound"):
            peq = float(payload.get("palletEq") or task.qty)
            self.outbound_pallet_eq += peq
            eid = self._emit(
                "outbound_complete",
                {"taskId": task.task_id, "palletEq": peq, "dockId": task.dock_id},
            )
            self.outbound_event_ids.append(eid)
        task.status = "done"
        self._emit(
            "task_complete",
            {
                "taskId": task.task_id,
                "status": "done",
                "waitSec": task.wait_sec,
                "busySec": task.busy_sec,
                "direction": task.direction,
            },
        )
        self._finish_resource(res)

    def run(self) -> Dict[str, Any]:
        started = datetime.now(timezone.utc).isoformat()
        self.validate_load()
        self._build_resources()
        self._generate_tasks()

        steps = 0
        while self.pq:
            if steps >= self.max_events:
                self._warn("MAX_EVENTS", f"达到最大事件数 {self.max_events}")
                break
            ev = heapq.heappop(self.pq)
            if ev.t > self.horizon + 1e-9:
                break
            self.t = ev.t
            steps += 1
            kind, p = ev.kind, ev.payload
            if kind in {"arrival", "task_spawn"}:
                self._emit(kind, {"taskId": p["taskId"]})
                self.tasks[p["taskId"]].status = "queued"
                self._schedule(
                    self.t, PHASE_REQUEST, "dispatch_request", {"taskId": p["taskId"]}
                )
            elif kind == "dispatch_request":
                self._request_dispatch(p["taskId"])
            elif kind == "haul_arrive":
                self._on_haul_arrive(p)
            elif kind == "release_edge":
                self._release_edge(p["edgeId"])
            elif kind == "at_node":
                task = self.tasks[p["taskId"]]
                res = self._resource(task.resource_id)  # type: ignore[arg-type]
                self._on_at_node(task, res, p["nodeId"])
            elif kind == "process_done":
                task = self.tasks[p["taskId"]]
                res = self._resource(task.resource_id)  # type: ignore[arg-type]
                if p.get("next") == "continue":
                    if task.edge_i < len(task.path_edges):
                        self._try_enter_edge(task, res)
                    else:
                        self._on_at_node(task, res, res.node_id)
            elif kind == "task_complete":
                self._on_task_complete(p)
            else:
                self._warn("UNKNOWN_EVENT", f"未知事件 {kind}")

        self.inventory.assert_non_negative()
        conservation = self.inventory.conservation_check()
        if not conservation["ok"]:
            self._warn("INVENTORY_CONSERVATION", f"守恒残差={conservation['residual']}")

        completed = [t for t in self.tasks.values() if t.status == "done"]
        incomplete = [t for t in self.tasks.values() if t.status != "done"]
        for t in incomplete:
            if t.wait_start is not None:
                t.wait_sec += max(0.0, self.horizon - t.wait_start)

        kpi = compute_kpi(
            horizon_sec=self.horizon,
            completed_tasks=[
                {"taskId": t.task_id, "waitSec": t.wait_sec, "busySec": t.busy_sec}
                for t in completed
            ],
            resources=[
                {
                    "resourceId": r.resource_id,
                    "busySec": r.busy_sec,
                    "poolId": r.pool_id,
                }
                for r in self.resources
            ],
            entity_wait_sec=dict(self.entity_wait),
            outbound_pallet_eq=self.outbound_pallet_eq,
            incomplete_count=len(incomplete),
        )
        evidence = kpi_event_evidence(
            self.events,
            outbound_event_ids=self.outbound_event_ids,
            completed_task_ids=[t.task_id for t in completed],
        )
        finished = datetime.now(timezone.utc).isoformat()
        layout_revision = self.snapshot["layoutRevision"]

        trajectory = {
            "runId": self.run_id,
            "layoutRevision": layout_revision,
            "horizonSec": self.horizon,
            "tasks": [
                {
                    "taskId": t.task_id,
                    "flowKind": t.flow_kind,
                    "status": t.status,
                    "direction": t.direction,
                    "waitSec": t.wait_sec,
                    "busySec": t.busy_sec,
                    "locationId": t.location_id,
                }
                for t in self.tasks.values()
            ],
            "resources": [
                {
                    "resourceId": r.resource_id,
                    "kind": r.kind,
                    "poolId": r.pool_id,
                    "busySec": r.busy_sec,
                }
                for r in self.resources
            ],
            "segments": self.segments,
        }

        manifest = {
            "runId": self.run_id,
            "variantRef": self.variant_ref,
            "layoutRef": {
                "id": self.snapshot.get("layoutId"),
                "revision": layout_revision,
            },
            "scenarioId": self.scenario_id,
            "demandRef": {
                "id": self.demand.get("id"),
                "revision": self.demand.get("revision"),
            },
            "operatingRef": {
                "id": self.operating.get("id"),
                "revision": self.operating.get("revision"),
            },
            "seedStreams": self.seed_streams,
            "engineVersion": ENGINE_VERSION,
            "metricDefinitionVersion": self.run_control.get("metricDefinitionVersion")
            or METRIC_DEFINITION_VERSION,
            "validationRef": self.validation_ref,
            "startedAt": started,
            "finishedAt": finished,
            "state": "succeeded",
            "warnings": self.warnings,
            "horizonSec": self.horizon,
            "resultRefs": {
                "kpi": True,
                "events": True,
                "trajectory": True,
                "inventoryConservation": True,
            },
        }

        return {
            "runId": self.run_id,
            "runManifest": manifest,
            "kpi": kpi,
            "kpiEvidence": evidence,
            "events": self.events,
            "trajectory": trajectory,
            "inventoryConservation": conservation,
            "layoutSnapshotBound": {
                "layoutId": self.snapshot.get("layoutId"),
                "layoutRevision": layout_revision,
                "schemaVersion": self.snapshot.get("schemaVersion"),
                "elementCount": len(self.snapshot.get("elements") or []),
                "edgeCount": len(self.snapshot.get("edges") or []),
                "layoutSnapshot": self.snapshot,
            },
            "engineVersion": ENGINE_VERSION,
            "kpiFromUiDemo": False,
            "claimsOperationalEfficiency": True,
        }


def run_des(**kwargs: Any) -> Dict[str, Any]:
    return DesEngine(**kwargs).run()
