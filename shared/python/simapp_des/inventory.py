"""运行态库存：不反写 Snapshot；守恒与容量门禁。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


class InventoryError(Exception):
    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class InventoryLedger:
    """货位托盘库存账本。Snapshot 只读；本对象持有运行态副本。"""

    def __init__(self, snapshot: Dict[str, Any], initial: List[Dict[str, Any]]) -> None:
        self.capacity: Dict[str, int] = {}
        self.stock: Dict[str, float] = {}
        self.goods_at: Dict[str, str] = {}  # location -> goodsGroupId
        for el in snapshot.get("elements") or []:
            if el.get("kind") == "slot":
                lid = el["elementId"]
                self.capacity[lid] = int(el.get("capacityPallets") or 0)
                self.stock[lid] = 0.0
        for row in initial or []:
            loc = row.get("locationInstanceId") or row.get("locationId")
            qty = float(row.get("quantity") or 0)
            if not loc:
                if qty:
                    raise InventoryError(
                        "INPUT_UNCONFIRMED",
                        "初始库存缺 locationInstanceId",
                        {"quantity": qty},
                    )
                continue
            if loc not in self.capacity:
                raise InventoryError(
                    "INPUT_UNCONFIRMED",
                    f"初始库存位置不存在于快照: {loc}",
                    {"locationInstanceId": loc},
                )
            if qty < 0:
                raise InventoryError("INPUT_UNCONFIRMED", "初始库存不可为负", {"location": loc})
            if qty > self.capacity[loc]:
                raise InventoryError(
                    "CAPACITY_EXCEEDED",
                    f"初始库存超过容量 {loc}",
                    {"qty": qty, "capacity": self.capacity[loc]},
                )
            self.stock[loc] = qty
            if row.get("goodsGroupId"):
                self.goods_at[loc] = row["goodsGroupId"]

        self.initial_total = sum(self.stock.values())
        self.inbound_total = 0.0
        self.outbound_total = 0.0
        self.loss_total = 0.0
        self._events: List[Dict[str, Any]] = []

    def snapshot_stock(self) -> Dict[str, float]:
        return deepcopy(self.stock)

    def total(self) -> float:
        return sum(self.stock.values())

    def add(self, location_id: str, qty: float, *, t: float, task_id: str, kind: str = "putaway") -> None:
        if location_id not in self.capacity:
            raise InventoryError("NO_LOCATION", f"未知货位 {location_id}")
        if qty < 0:
            raise InventoryError("INVENTORY_NEGATIVE", "入库量不可为负")
        new = self.stock[location_id] + qty
        if new > self.capacity[location_id] + 1e-9:
            raise InventoryError(
                "CAPACITY_EXCEEDED",
                f"货位 {location_id} 超容量",
                {"stock": self.stock[location_id], "qty": qty, "capacity": self.capacity[location_id]},
            )
        self.stock[location_id] = new
        self.inbound_total += qty
        self._events.append(
            {
                "t": t,
                "kind": kind,
                "locationId": location_id,
                "delta": qty,
                "taskId": task_id,
                "stockAfter": new,
            }
        )

    def remove(self, location_id: str, qty: float, *, t: float, task_id: str, kind: str = "pick") -> None:
        if location_id not in self.capacity:
            raise InventoryError("NO_LOCATION", f"未知货位 {location_id}")
        if qty < 0:
            raise InventoryError("INVENTORY_NEGATIVE", "出库量不可为负")
        if self.stock[location_id] + 1e-9 < qty:
            raise InventoryError(
                "STOCKOUT",
                f"货位 {location_id} 库存不足",
                {"stock": self.stock[location_id], "qty": qty},
            )
        new = self.stock[location_id] - qty
        self.stock[location_id] = new
        self.outbound_total += qty
        self._events.append(
            {
                "t": t,
                "kind": kind,
                "locationId": location_id,
                "delta": -qty,
                "taskId": task_id,
                "stockAfter": new,
            }
        )

    def assert_non_negative(self) -> None:
        for lid, q in self.stock.items():
            if q < -1e-9:
                raise InventoryError("INVENTORY_NEGATIVE", f"负库存 {lid}={q}")

    def conservation_check(self) -> Dict[str, Any]:
        """初始 + 入库 − 出库 − 期末 − 损耗 = 0。"""
        end = self.total()
        residual = self.initial_total + self.inbound_total - self.outbound_total - end - self.loss_total
        ok = abs(residual) < 1e-6
        return {
            "ok": ok,
            "initial": self.initial_total,
            "inbound": self.inbound_total,
            "outbound": self.outbound_total,
            "ending": end,
            "loss": self.loss_total,
            "residual": residual,
            "formula": "initial + inbound - outbound - ending - loss = 0",
            "stockByLocation": self.snapshot_stock(),
            "mutations": list(self._events),
        }

    def pick_slot_with_stock(
        self, qty: float = 1.0, preferred: Optional[str] = None
    ) -> Optional[str]:
        if preferred and self.stock.get(preferred, 0) + 1e-9 >= qty:
            return preferred
        for lid, q in sorted(self.stock.items()):
            if q + 1e-9 >= qty:
                return lid
        return None

    def pick_slot_with_capacity(self, qty: float = 1.0, preferred: Optional[str] = None) -> Optional[str]:
        if preferred and preferred in self.capacity:
            if self.stock[preferred] + qty <= self.capacity[preferred] + 1e-9:
                return preferred
        for lid in sorted(self.capacity.keys()):
            if self.stock[lid] + qty <= self.capacity[lid] + 1e-9:
                return lid
        return None
