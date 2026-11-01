"""锁定语义与局部重排区域合并（DEV-09 / AC-05）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Sequence, Tuple, Union


Point = Tuple[float, float]


def point_in_polygon(point: Point, polygon: Sequence[Dict[str, Any]], eps: float = 1e-9) -> bool:
    """射线法；polygon 为 [{x,y},...]，允许闭合重复点。"""
    pts = [(float(p["x"]), float(p["y"])) for p in polygon]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return False
    x, y = point
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if abs(yi - yj) <= eps and abs(yi - y) <= eps:
            if min(xi, xj) - eps <= x <= max(xi, xj) + eps:
                return True
        intersect = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 0.0) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def element_pose_params(el: Dict[str, Any]) -> Dict[str, Any]:
    pose = el.get("pose") or {}
    return {
        "pose": {
            "x": round(float(pose.get("x", 0.0)), 4),
            "y": round(float(pose.get("y", 0.0)), 4),
            "yawDeg": round(float(pose.get("yawDeg", 0.0)), 4),
        },
        "params": deepcopy(el.get("params") or {}),
        "typeElementId": el.get("typeElementId"),
    }


def _lock_fields(lock: Dict[str, Any]) -> Union[str, List[str]]:
    return lock.get("fields", "all")


def assert_locks_preserved(
    base_elements: Sequence[Dict[str, Any]],
    candidate_elements: Sequence[Dict[str, Any]],
    locks: Sequence[Dict[str, Any]],
) -> None:
    """锁定实例：fields=all → 位姿/尺寸/型号不变；字段列表 → 对应字段不变。"""
    base_by_id = {e["instanceId"]: e for e in base_elements}
    cand_by_id = {e["instanceId"]: e for e in candidate_elements}
    for lock in locks:
        iid = lock["instanceId"]
        if iid not in base_by_id:
            continue
        if iid not in cand_by_id:
            raise LockConflictError(
                f"锁定实例 {iid} 在候选中缺失",
                details={"instanceId": iid},
            )
        base = base_by_id[iid]
        cand = cand_by_id[iid]
        fields = _lock_fields(lock)
        if fields == "all":
            if element_pose_params(base) != element_pose_params(cand):
                raise LockConflictError(
                    f"锁定实例 {iid} 被修改",
                    details={"instanceId": iid, "fields": "all"},
                )
        else:
            for f in fields:
                if f in {"pose", "x", "y", "yawDeg"}:
                    bp, cp = element_pose_params(base)["pose"], element_pose_params(cand)["pose"]
                    if bp != cp:
                        raise LockConflictError(
                            f"锁定实例 {iid} 位姿被修改",
                            details={"instanceId": iid, "fields": fields},
                        )
                elif f == "params":
                    if (base.get("params") or {}) != (cand.get("params") or {}):
                        raise LockConflictError(
                            f"锁定实例 {iid} params 被修改",
                            details={"instanceId": iid, "fields": fields},
                        )
                elif f == "typeElementId":
                    if base.get("typeElementId") != cand.get("typeElementId"):
                        raise LockConflictError(
                            f"锁定实例 {iid} 型号被修改",
                            details={"instanceId": iid, "fields": fields},
                        )


class LockConflictError(Exception):
    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.code = "LOCK_CONFLICT"
        self.message = message
        self.details = details


def merge_region_layout(
    base_layout: Dict[str, Any],
    generated_region_layout: Dict[str, Any],
    polygon: Sequence[Dict[str, Any]],
    locks: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """局部重排：区域外对象冻结；区域内用生成结果；锁定优先。

    跨边界设备默认全部冻结（中心点在区域外或边上）。
    """
    locked_ids = {lk["instanceId"] for lk in locks}
    base_els = list(base_layout.get("elements") or [])
    gen_els = list(generated_region_layout.get("elements") or [])

    frozen: List[Dict[str, Any]] = []
    for el in base_els:
        pose = el.get("pose") or {}
        cx, cy = float(pose.get("x", 0.0)), float(pose.get("y", 0.0))
        inside = point_in_polygon((cx, cy), polygon)
        if el["instanceId"] in locked_ids or not inside:
            frozen.append(deepcopy(el))

    frozen_ids = {e["instanceId"] for e in frozen}
    merged_els: List[Dict[str, Any]] = list(frozen)
    for el in gen_els:
        if el["instanceId"] in frozen_ids:
            continue
        pose = el.get("pose") or {}
        if point_in_polygon((float(pose.get("x", 0.0)), float(pose.get("y", 0.0))), polygon):
            merged_els.append(deepcopy(el))

    # 通道：区域外保留 base；区域内用生成（简化：若生成有通道则替换同 id，否则追加）
    base_aisles = {a["id"]: deepcopy(a) for a in (base_layout.get("aisles") or [])}
    gen_aisles = {a["id"]: deepcopy(a) for a in (generated_region_layout.get("aisles") or [])}
    # 保守：局部重排保留 base 通道，并并入生成通道（新 id）
    aisles = list(base_aisles.values())
    for aid, aisle in gen_aisles.items():
        if aid not in base_aisles:
            aisles.append(aisle)

    out = deepcopy(base_layout)
    out["elements"] = merged_els
    out["aisles"] = aisles
    # 合并 locks
    existing_locks = {lk["instanceId"]: deepcopy(lk) for lk in (base_layout.get("locks") or [])}
    for lk in locks:
        existing_locks[lk["instanceId"]] = deepcopy(lk)
    out["locks"] = list(existing_locks.values())
    assert_locks_preserved(base_els, merged_els, locks)
    return out
