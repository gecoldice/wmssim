"""Pallet ledger. Conservation: initial + inbound = ending + in_transit + outbound."""

from __future__ import annotations

from typing import Any, Dict, List

from .errors import DesError


class InventoryLedger:
    def __init__(self, snapshot: Dict[str, Any], initial: List[Dict[str, Any]]) -> None:
        self.capacity: Dict[str, float] = {}
        self.on_hand: Dict[str, float] = {}
        for el in snapshot.get("elements") or []:
            if el.get("kind") == "slot":
                cap = float(el.get("capacityPallets") or 0)
                self.capacity[el["elementId"]] = cap
                self.on_hand[el["elementId"]] = 0.0
        self.reserved: Dict[str, float] = {loc: 0.0 for loc in self.on_hand}
        self.initial = 0.0
        self.inbound = 0.0
        self.outbound = 0.0
        self.in_transit = 0.0
        self.converted = 0.0
        self.cases_created = 0.0
        self.cases_on_hand: Dict[str, float] = {}
        for row in initial:
            loc = row.get("locationInstanceId")
            qty = float(row.get("quantity") or 0)
            if qty <= 0:
                continue
            if loc not in self.on_hand:
                raise DesError(
                    "INPUT_UNCONFIRMED",
                    f"初始库存位置不存在：{loc}",
                    {"locationInstanceId": loc},
                )
            if self.on_hand[loc] + qty > self.capacity[loc] + 1e-9:
                raise DesError(
                    "INPUT_UNCONFIRMED",
                    f"{loc} 初始库存超过货位容量",
                    {"locationInstanceId": loc},
                )
            self.on_hand[loc] += qty
            self.initial += qty

    def available(self, loc: str) -> float:
        return self.on_hand.get(loc, 0.0) - self.reserved.get(loc, 0.0)

    def pick_slot_with_stock(self, qty: float, preferred: str | None = None) -> str | None:
        if preferred and self.available(preferred) + 1e-9 >= qty:
            return preferred
        for loc in sorted(self.on_hand):
            if self.available(loc) + 1e-9 >= qty:
                return loc
        return None

    def reserve(self, loc: str, qty: float) -> None:
        if self.available(loc) + 1e-9 < qty:
            raise DesError("INPUT_UNCONFIRMED", f"{loc} 可预约库存不足", {"locationInstanceId": loc})
        self.reserved[loc] = self.reserved.get(loc, 0.0) + qty

    def release_reserve(self, loc: str, qty: float) -> None:
        self.reserved[loc] = max(0.0, self.reserved.get(loc, 0.0) - qty)

    def pick_slot_with_capacity(self, qty: float) -> str | None:
        for loc in sorted(self.capacity):
            free = self.capacity[loc] - self.on_hand[loc]
            if free + 1e-9 >= qty:
                return loc
        return None

    def remove(self, loc: str, qty: float) -> None:
        if self.on_hand.get(loc, 0) + 1e-9 < qty:
            raise DesError("INPUT_UNCONFIRMED", f"{loc} 库存不足", {"locationInstanceId": loc})
        self.on_hand[loc] -= qty
        self.reserved[loc] = max(0.0, self.reserved.get(loc, 0.0) - qty)
        self.in_transit += qty

    def add(self, loc: str, qty: float) -> None:
        if loc not in self.capacity:
            raise DesError("INPUT_UNCONFIRMED", f"货位不存在：{loc}", {"locationInstanceId": loc})
        if self.on_hand[loc] + qty > self.capacity[loc] + 1e-9:
            raise DesError("INPUT_UNCONFIRMED", f"{loc} 容量不足", {"locationInstanceId": loc})
        self.on_hand[loc] += qty
        self.inbound += qty

    def ship(self, qty: float) -> None:
        if self.in_transit + 1e-9 < qty:
            raise DesError("COMPUTATION_FAILED", "发运时没有在途托盘", {"qty": qty})
        self.in_transit -= qty
        self.outbound += qty

    def convert_to_cases(self, pallet_qty: float, cases: float, station_id: str) -> None:
        if self.in_transit + 1e-9 < pallet_qty:
            raise DesError("COMPUTATION_FAILED", "拆托时没有在途托盘", {"qty": pallet_qty})
        self.in_transit -= pallet_qty
        self.converted += pallet_qty
        self.cases_created += cases
        self.cases_on_hand[station_id] = self.cases_on_hand.get(station_id, 0.0) + cases

    def conservation(self) -> Dict[str, Any]:
        ending = sum(self.on_hand.values())
        residual = self.initial + self.inbound - (ending + self.in_transit + self.outbound + self.converted)
        return {
            "ok": abs(residual) <= 1e-6,
            "initial": self.initial,
            "inbound": self.inbound,
            "outbound": self.outbound,
            "ending": ending,
            "inTransit": self.in_transit,
            "converted": self.converted,
            "casesCreated": self.cases_created,
            "casesOnHand": dict(self.cases_on_hand),
            "onHand": dict(self.on_hand),
            "residual": residual,
        }
