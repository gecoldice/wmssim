#!/usr/bin/env python3
"""Validate fixture catalog against JSON Schema + light semantic checks.

Usage (from simapp root):
  PYTHONPATH=shared/python python3 scripts/validate_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
    from jsonschema import Draft7Validator
except ImportError:
    print("Missing dependency: pip install -r services/api/requirements.txt", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contracts" / "schemas"
FIXTURES = ROOT / "fixtures"
CATALOG = FIXTURES / "meta" / "catalog.json"

# kinds that need accessNode on non-node elements
ACCESS_KINDS = {"slot", "station", "dock", "device"}


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def semantic_layout_snapshot(data: dict) -> list[str]:
    errors: list[str] = []
    if data.get("schemaVersion") != "0.2":
        errors.append("SCHEMA_VERSION")
    elements = data.get("elements") or []
    ids = [e.get("elementId") for e in elements]
    if len(ids) != len(set(ids)):
        errors.append("DUPLICATE_ELEMENT_ID")
    node_ids = {e["elementId"] for e in elements if e.get("kind") == "node"}
    for e in elements:
        kind = e.get("kind")
        if kind in ACCESS_KINDS:
            an = e.get("accessNodeId")
            if not an:
                errors.append(f"NO_ACCESS_NODE:{e.get('elementId')}")
            elif an not in node_ids:
                errors.append(f"DANGLING_ACCESS_NODE:{e.get('elementId')}->{an}")
        if kind == "slot" and e.get("capacityPallets") is not None and e["capacityPallets"] < 1:
            errors.append(f"CAPACITY:{e.get('elementId')}")
        if kind == "station" and e.get("capacitySlots") is not None and e["capacitySlots"] < 1:
            errors.append(f"CAPACITY:{e.get('elementId')}")
    edge_ids = []
    for edge in data.get("edges") or []:
        edge_ids.append(edge.get("edgeId"))
        if edge.get("lengthM", 0) <= 0:
            errors.append(f"EDGE_LENGTH:{edge.get('edgeId')}")
        for end in ("from", "to"):
            if edge.get(end) not in {e.get("elementId") for e in elements}:
                errors.append(f"EDGE_ENDPOINT:{edge.get('edgeId')}:{end}")
    if len(edge_ids) != len(set(edge_ids)):
        errors.append("DUPLICATE_EDGE_ID")
    return errors


def main() -> int:
    catalog = load_json(CATALOG)
    failures = 0
    for entry in catalog["entries"]:
        rel = entry["path"]
        schema_rel = entry["schema"]
        expect = entry["expect"]
        path = FIXTURES / rel
        schema = load_json(SCHEMAS / schema_rel)
        data = load_json(path)
        validator = Draft7Validator(schema)
        schema_errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        semantic_errors: list[str] = []
        if entry["kind"] == "layoutSnapshot":
            semantic_errors = semantic_layout_snapshot(data)

        schema_ok = len(schema_errors) == 0
        semantic_ok = len(semantic_errors) == 0

        if expect == "pass":
            ok = schema_ok and semantic_ok
            if not ok:
                failures += 1
                print(f"FAIL {entry['id']} expected pass")
                for err in schema_errors[:5]:
                    print(f"  schema: {list(err.path)}: {err.message}")
                for err in semantic_errors:
                    print(f"  semantic: {err}")
            else:
                print(f"PASS {entry['id']}")
        elif expect == "fail":
            ok = not schema_ok
            if not ok:
                failures += 1
                print(f"FAIL {entry['id']} expected schema fail but passed")
            else:
                print(f"PASS {entry['id']} (schema rejected as expected)")
        elif expect == "semantic_fail":
            ok = schema_ok and (not semantic_ok)
            if not ok:
                failures += 1
                print(
                    f"FAIL {entry['id']} expected schema pass + semantic fail "
                    f"(schema_ok={schema_ok}, semantic={semantic_errors})"
                )
            else:
                print(f"PASS {entry['id']} (semantic reject: {semantic_errors})")
        else:
            failures += 1
            print(f"FAIL {entry['id']} unknown expect={expect}")

    # unit transform smoke
    sys.path.insert(0, str(ROOT / "shared" / "python"))
    from simapp_units import Pose2, plane_to_world3d, world3d_to_plane

    pos, yaw = plane_to_world3d(Pose2(x=12, y=14, yaw_deg=30), height_m=1.5)
    assert abs(pos.x - 12) < 1e-9 and abs(pos.y - 1.5) < 1e-9 and abs(pos.z - (-14)) < 1e-9
    assert abs(yaw - 120) < 1e-9
    back = world3d_to_plane(pos)
    assert abs(back.x - 12) < 1e-9 and abs(back.y - 14) < 1e-9
    print("PASS unit transform (X,Y,Z)=(x,h,-y)")

    if failures:
        print(f"\n{failures} failure(s)")
        return 1
    print("\nAll fixture checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
