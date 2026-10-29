"""Coordinate and unit helpers shared by API / worker / validators.

Plane: meters, origin = facility SW corner, +X east, +Y north.
3D world (Y-up): (X, Y, Z) = (x, height_m, -y).
Asset local 0° points +Z → world yaw about Y is 90° + yaw_deg.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import radians
from typing import Tuple

PLANE_ORIGIN = "facility_sw_corner"
PLANE_X_AXIS = "east"
PLANE_Y_AXIS = "north"
PLANE_UNIT = "m"


@dataclass(frozen=True)
class Pose2:
    x: float
    y: float
    yaw_deg: float = 0.0


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float


def plane_to_world3d(pose: Pose2, height_m: float = 0.0) -> Tuple[Vec3, float]:
    """Map 2D layout pose to 3D world position and yaw about +Y (degrees)."""
    position = Vec3(x=pose.x, y=height_m, z=-pose.y)
    yaw_y_deg = 90.0 + pose.yaw_deg
    return position, yaw_y_deg


def world3d_to_plane(position: Vec3) -> Pose2:
    """Inverse of plane_to_world3d for XY; yaw not recovered from position alone."""
    return Pose2(x=position.x, y=-position.z)


def yaw_deg_to_rad(yaw_deg: float) -> float:
    return radians(yaw_deg)


def assert_finite_numbers(*values: float) -> None:
    for v in values:
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("NaN/Infinity are not allowed in contract payloads")
