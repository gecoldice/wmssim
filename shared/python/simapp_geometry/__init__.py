"""平面几何原语（米制）：AABB / 线段 / 障碍相交。不依赖 Shapely。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple


Point = Tuple[float, float]


@dataclass(frozen=True)
class Aabb:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def intersects(self, other: "Aabb") -> bool:
        return not (
            self.max_x <= other.min_x
            or other.max_x <= self.min_x
            or self.max_y <= other.min_y
            or other.max_y <= self.min_y
        )

    def contains_point(self, p: Point, eps: float = 1e-9) -> bool:
        x, y = p
        return (
            self.min_x - eps <= x <= self.max_x + eps
            and self.min_y - eps <= y <= self.max_y + eps
        )


def footprint_aabb(
    cx: float,
    cy: float,
    w: float,
    d: float,
    yaw_deg: float = 0.0,
) -> Aabb:
    """轴对齐外包：yaw 取 0/90/180/270 时精确；其它角度用旋转矩形外包盒。"""
    yaw = math.radians(yaw_deg % 360.0)
    hw, hd = w / 2.0, d / 2.0
    corners = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
    cos_a, sin_a = math.cos(yaw), math.sin(yaw)
    xs: List[float] = []
    ys: List[float] = []
    for lx, ly in corners:
        xs.append(cx + lx * cos_a - ly * sin_a)
        ys.append(cy + lx * sin_a + ly * cos_a)
    return Aabb(min(xs), min(ys), max(xs), max(ys))


def orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(a: Point, b: Point, p: Point, eps: float = 1e-9) -> bool:
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    )


def segments_intersect(a: Point, b: Point, c: Point, d: Point, eps: float = 1e-9) -> bool:
    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    if (o1 * o2 < -eps) and (o3 * o4 < -eps):
        return True
    if abs(o1) <= eps and on_segment(a, b, c, eps):
        return True
    if abs(o2) <= eps and on_segment(a, b, d, eps):
        return True
    if abs(o3) <= eps and on_segment(c, d, a, eps):
        return True
    if abs(o4) <= eps and on_segment(c, d, b, eps):
        return True
    return False


def point_in_ring(point: Point, ring: Sequence[Point], eps: float = 1e-9) -> bool:
    """射线法；ring 可首尾闭合。边界点视为在内。"""
    if len(ring) < 3:
        return False
    pts = list(ring)
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    x, y = point
    for i in range(len(pts) - 1):
        if on_segment(pts[i], pts[i + 1], point, eps):
            return True
    inside = False
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        if ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-30) + x1
        ):
            inside = not inside
    return inside


def segment_hits_polygon(a: Point, b: Point, ring: Sequence[Point]) -> bool:
    pts = list(ring)
    if not pts:
        return False
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    if point_in_ring(a, pts) or point_in_ring(b, pts) or point_in_ring(mid, pts):
        return True
    for i in range(len(pts) - 1):
        if segments_intersect(a, b, pts[i], pts[i + 1]):
            return True
    return False


def segment_blocked(
    a: Point,
    b: Point,
    obstacles: Iterable[Sequence[Point]],
) -> bool:
    for ring in obstacles:
        if segment_hits_polygon(a, b, ring):
            return True
    return False


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def polyline_length(points: Sequence[Point]) -> float:
    total = 0.0
    for i in range(len(points) - 1):
        total += dist(points[i], points[i + 1])
    return total


def nearest_point_index(origin: Point, candidates: Sequence[Point]) -> Optional[int]:
    if not candidates:
        return None
    best_i = 0
    best_d = dist(origin, candidates[0])
    for i in range(1, len(candidates)):
        d = dist(origin, candidates[i])
        if d < best_d:
            best_d = d
            best_i = i
    return best_i
