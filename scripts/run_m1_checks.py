#!/usr/bin/env python3
"""M1 派生+权威校验夹具金样。

Usage (from simapp root):
  source .venv/bin/activate
  PYTHONPATH=shared/python python3 scripts/run_m1_checks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared" / "python"))

from simapp_derive import derive_layout_snapshot  # noqa: E402
from simapp_geometry import segment_blocked  # noqa: E402
from simapp_validate import is_simulation_ready, validate_layout  # noqa: E402

FIXTURES = ROOT / "fixtures"


def load(rel: str):
    with (FIXTURES / rel).open(encoding="utf-8") as f:
        return json.load(f)


def expect_ready(name: str, layout_rel: str, facility_rel: str) -> None:
    layout = load(layout_rel)
    facility = load(facility_rel)
    snap = derive_layout_snapshot(layout, facility)
    report = validate_layout(snap, facility, layout)
    if not is_simulation_ready(report):
        raise AssertionError(f"{name}: expected simulationReady, got {report['status']} {report['checks']}")
    # 每个 slot/dock 须有 accessNode
    for e in snap["elements"]:
        if e["kind"] in {"slot", "dock", "device", "station"} and not e.get("accessNodeId"):
            raise AssertionError(f"{name}: missing accessNode on {e['elementId']}")
    print(f"PASS {name} simulationReady layoutRevision={snap['layoutRevision']}")


def expect_fail(
    name: str,
    layout_rel: str,
    facility_rel: str,
    reason_code: str,
) -> None:
    layout = load(layout_rel)
    facility = load(facility_rel)
    snap = derive_layout_snapshot(layout, facility)
    report = validate_layout(snap, facility, layout)
    if report["status"] == "pass":
        raise AssertionError(f"{name}: expected fail({reason_code}), got pass")
    codes = {c["ruleId"] for c in report["checks"] if c["status"] == "fail"}
    if reason_code not in codes:
        raise AssertionError(f"{name}: expected rule {reason_code} in {codes}; checks={report['checks']}")
    if is_simulation_ready(report):
        raise AssertionError(f"{name}: simulationReady must be false")
    print(f"PASS {name} rejected by {reason_code}")


def expect_snapshot_fail(name: str, snap_rel: str, facility_rel: str, reason_code: str) -> None:
    snap = load(snap_rel)
    facility = load(facility_rel)
    report = validate_layout(snap, facility, layout_doc=None)
    codes = {c["ruleId"] for c in report["checks"] if c["status"] == "fail"}
    if reason_code not in codes and report["status"] == "pass":
        raise AssertionError(f"{name}: expected {reason_code}, got pass")
    if reason_code not in codes:
        raise AssertionError(f"{name}: expected rule {reason_code} in {codes}")
    print(f"PASS {name} snapshot rejected by {reason_code}")


def main() -> int:
    failures = 0
    cases = [
        ("FX-M1-OK", lambda: expect_ready(
            "FX-M1-OK",
            "valid/fx-m1-ok-layout.json",
            "valid/fx01-small-rect-facility.json",
        )),
        ("FX-M1-COLLISION", lambda: expect_fail(
            "FX-M1-COLLISION",
            "invalid/fx-m1-collision-layout.json",
            "valid/fx01-small-rect-facility.json",
            "GEOMETRY_INVALID",
        )),
        ("FX-M1-NARROW", lambda: expect_fail(
            "FX-M1-NARROW",
            "invalid/fx-m1-narrow-aisle-layout.json",
            "valid/fx01-small-rect-facility.json",
            "NARROW_AISLE",
        )),
        ("FX-M1-CROSS-WALL-DERIVE", lambda: expect_fail(
            "FX-M1-CROSS-WALL-DERIVE",
            "invalid/fx-m1-cross-wall-layout.json",
            "valid/fx01-facility-with-wall.json",
            "NO_ACCESS_NODE",
        )),
        ("FX-M1-CROSS-WALL-SNAP", lambda: expect_snapshot_fail(
            "FX-M1-CROSS-WALL-SNAP",
            "invalid/fx-m1-cross-wall-snapshot.json",
            "valid/fx01-facility-with-wall.json",
            "NO_ACCESS_NODE",
        )),
    ]
    for name, fn in cases:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}: {exc}")

    # 跨墙派生额外断言：不得生成穿墙边
    layout = load("invalid/fx-m1-cross-wall-layout.json")
    facility = load("valid/fx01-facility-with-wall.json")
    snap = derive_layout_snapshot(layout, facility)
    obstacles = []
    for obs in facility.get("obstacles") or []:
        outer = (obs.get("polygon") or {}).get("outer") or []
        if len(outer) >= 3:
            obstacles.append([(float(p["x"]), float(p["y"])) for p in outer])
    node_pose = {
        e["elementId"]: (float(e["pose"]["x"]), float(e["pose"]["y"]))
        for e in snap["elements"]
        if e.get("kind") == "node"
    }
    crossing = []
    for edge in snap["edges"]:
        a = node_pose.get(edge["from"])
        b = node_pose.get(edge["to"])
        if a and b and segment_blocked(a, b, obstacles):
            crossing.append(edge)
    if crossing:
        failures += 1
        print(f"FAIL FX-M1-NO-CROSS-EDGE: wall-crossing edges {crossing}")
    else:
        print("PASS FX-M1-NO-CROSS-EDGE (no wall-crossing aisle edges)")

    if failures:
        print(f"\n{failures} M1 check failure(s)")
        return 1
    print("\nAll M1 derive/validate checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
