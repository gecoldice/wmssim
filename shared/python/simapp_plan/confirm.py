"""场地确认与比例门禁（DEV-06）。未确认几何不得作为正式 validated 规划输入。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


FACILITY_CONFIRMED = "confirmed"


class FacilityGateError(Exception):
    def __init__(self, code: str, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def facility_confirmation_status(facility: Dict[str, Any]) -> str:
    evidence = facility.get("evidence") or {}
    status = evidence.get("confirmationStatus")
    if isinstance(status, str) and status:
        return status
    return "pending"


def scale_declared(facility: Dict[str, Any], drawing: Optional[Dict[str, Any]] = None) -> bool:
    """比例已声明：米制 coord.unit=m，且（无图纸）或图纸含 metersPerPixel/scale。"""
    coord = facility.get("coord") or {}
    if coord.get("unit") != "m":
        return False
    evidence = facility.get("evidence") or {}
    if evidence.get("metersPerPixel") or evidence.get("scaleDeclared") is True:
        return True
    if drawing:
        meta = drawing.get("meta") or {}
        if meta.get("metersPerPixel") or meta.get("scaleDeclared") is True:
            return True
        if drawing.get("status") == "calibrated":
            return True
    # 纯手动录入的米制场地（无底图）视为比例已明确
    source = evidence.get("sourceKind")
    if source in {"manual", "demo", "measured"} and evidence.get("confirmationStatus") == FACILITY_CONFIRMED:
        return True
    return False


def _is_axis_aligned_rect(outer: List[Dict[str, Any]], eps: float = 1e-6) -> bool:
    """闭合外轮廓是否为轴对齐矩形（允许首尾重复点）。"""
    pts = [(float(p["x"]), float(p["y"])) for p in outer]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) != 4:
        return False
    xs = {round(p[0], 6) for p in pts}
    ys = {round(p[1], 6) for p in pts}
    if len(xs) != 2 or len(ys) != 2:
        return False
    # 边须水平或竖直
    for i in range(4):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % 4]
        if abs(ax - bx) > eps and abs(ay - by) > eps:
            return False
    return True


def boundary_bbox(facility: Dict[str, Any]) -> Tuple[float, float, float, float]:
    outer = (facility.get("boundary") or {}).get("outer") or []
    xs = [float(p["x"]) for p in outer]
    ys = [float(p["y"]) for p in outer]
    if not xs:
        raise FacilityGateError("GEOMETRY_INVALID", "facility boundary empty")
    return min(xs), min(ys), max(xs), max(ys)


def assert_facility_usable_for_planning(
    facility: Dict[str, Any],
    *,
    drawing: Optional[Dict[str, Any]] = None,
    require_confirmed: bool = True,
) -> Dict[str, Any]:
    """规划入口门禁。返回支持范围摘要；失败抛 FacilityGateError。"""
    status = facility_confirmation_status(facility)
    if require_confirmed and status != FACILITY_CONFIRMED:
        raise FacilityGateError(
            "INPUT_UNCONFIRMED",
            "场地关键几何尚未确认，不能产出正式 validated 候选",
            details={"confirmationStatus": status, "fieldPaths": ["evidence.confirmationStatus"]},
        )
    if not scale_declared(facility, drawing):
        raise FacilityGateError(
            "INPUT_UNCONFIRMED",
            "底图比例未标定或单位不明，不得输出精确 validated 布局",
            details={"fieldPaths": ["evidence.metersPerPixel", "coord.unit"]},
        )

    height = facility.get("heightProfile") or {}
    if height.get("kind") not in {None, "uniform"}:
        # zoned 为首期 unsupported
        raise FacilityGateError(
            "UNSUPPORTED_SCENARIO",
            "首期自动规划仅支持均匀净高单层场地（DEC-05）",
            details={"heightProfile.kind": height.get("kind")},
        )

    outer = (facility.get("boundary") or {}).get("outer") or []
    if not _is_axis_aligned_rect(outer):
        raise FacilityGateError(
            "UNSUPPORTED_SCENARIO",
            "首期自动规划仅支持轴对齐矩形场地外轮廓（DEC-05）",
            details={"boundary.outer": "non_axis_aligned_or_non_rect"},
        )

    holes = (facility.get("boundary") or {}).get("holes") or []
    if holes:
        raise FacilityGateError(
            "UNSUPPORTED_SCENARIO",
            "首期自动规划不支持带洞场地",
            details={"boundary.holes": len(holes)},
        )

    for obs in facility.get("obstacles") or []:
        poly = (obs.get("polygon") or {}).get("outer") or []
        if poly and not _is_axis_aligned_rect(poly):
            raise FacilityGateError(
                "UNSUPPORTED_SCENARIO",
                "首期自动规划仅支持轴对齐矩形障碍",
                details={"obstacleId": obs.get("id")},
            )

    min_x, min_y, max_x, max_y = boundary_bbox(facility)
    return {
        "supportScope": "DEC-05 ambient single-floor axis-aligned rect + ST-PAL-01",
        "confirmationStatus": status,
        "scaleDeclared": True,
        "bbox": {"minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y},
        "unit": "m",
    }
