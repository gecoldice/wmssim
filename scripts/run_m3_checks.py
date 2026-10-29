#!/usr/bin/env python3
"""M3 DES 核心 / 四卡 / 回放绑定 / 可复现性检查。

Usage:
  source .venv/bin/activate
  PYTHONPATH=shared/python:services/api python3 scripts/run_m3_checks.py
"""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["SIMAPP_DB"] = "off"
sys.path.insert(0, str(ROOT / "shared" / "python"))
sys.path.insert(0, str(ROOT / "services" / "api"))

from fastapi.testclient import TestClient  # noqa: E402

from simapp_derive import derive_layout_snapshot  # noqa: E402
from simapp_des import DesError, run_des  # noqa: E402
from simapp_des.graph import build_adjacency, shortest_path  # noqa: E402
from app.main import app  # noqa: E402
from app.store import STORE  # noqa: E402

FIXTURES = ROOT / "fixtures"


def load(rel: str):
    with (FIXTURES / rel).open(encoding="utf-8") as f:
        return json.load(f)


def reset_store() -> None:
    STORE.projects.clear()
    STORE._orphan_jobs.clear()
    STORE._global_candidates.clear()
    STORE._global_runs.clear()


def _strip_run(result: dict) -> dict:
    return {
        "cards": result["kpi"]["cards"],
        "secondary": result["kpi"]["secondary"],
        "cons": {
            k: result["inventoryConservation"][k]
            for k in ("ok", "initial", "inbound", "outbound", "ending", "residual")
        },
        "task_status": sorted(
            (t["taskId"], t["status"]) for t in result["trajectory"]["tasks"]
        ),
        "seg_n": len(result["trajectory"]["segments"]),
        "event_kinds": [e["kind"] for e in result["events"]],
        "warn_codes": sorted(w["code"] for w in result["runManifest"]["warnings"]),
        "outbound_ids": [e["eventId"] for e in result["kpiEvidence"]["outboundEvents"]],
        "layoutRevision": result["layoutSnapshotBound"]["layoutRevision"],
    }


def test_engine_core() -> None:
    layout = load("valid/fx-m1-ok-layout.json")
    facility = load("valid/fx01-small-rect-facility.json")
    demand = load("valid/fx-m3-demand-outbound.json")
    operating = load("valid/fx-m3-operating.json")
    snap = derive_layout_snapshot(layout, facility)
    snap_before = json.dumps(snap, sort_keys=True)

    adj = build_adjacency(snap)
    docks = {e["elementId"]: e for e in snap["elements"] if e["kind"] == "dock"}
    slots = {e["elementId"]: e for e in snap["elements"] if e["kind"] == "slot"}
    ship = next(d for d in docks.values() if "ship" in (d.get("labels") or []))
    rack = next(iter(slots.values()))
    path = shortest_path(adj, rack["accessNodeId"], ship["accessNodeId"])
    assert path is not None and path["lengthM"] > 0, path

    common = dict(
        snapshot=snap,
        demand=demand,
        operating=operating,
        run_control={
            "horizonSec": 3600,
            "seedStreams": {"demand": 42, "dispatch": 42},
            "metricDefinitionVersion": "metrics-m3-v1",
        },
        expected_layout_revision=snap["layoutRevision"],
        faults=operating.get("faults"),
        skill_tags_present=True,
    )
    r1 = run_des(**common, run_id="run-a")
    r2 = run_des(**common, run_id="run-b")
    assert json.dumps(snap, sort_keys=True) == snap_before, "Snapshot must stay read-only"
    assert _strip_run(r1) == _strip_run(r2), "fixed scenario must be reproducible"

    assert r1["inventoryConservation"]["ok"] is True
    assert r1["inventoryConservation"]["outbound"] == 4.0
    assert r1["kpi"]["secondary"]["completedTasks"] == 4
    assert r1["kpi"]["cards"]["throughput"]["outboundPalletEq"] == 4.0
    assert r1["kpiFromUiDemo"] is False

    # KPI 可追事件
    evidence = r1["kpiEvidence"]["outboundEvents"]
    assert len(evidence) == 4
    assert all(e.get("palletEq") == 1.0 for e in evidence)
    event_ids = {e["eventId"] for e in r1["events"]}
    assert all(e["eventId"] in event_ids for e in evidence)

    # 回放绑历史布局
    assert r1["trajectory"]["layoutRevision"] == snap["layoutRevision"]
    assert r1["layoutSnapshotBound"]["layoutSnapshot"]["layoutRevision"] == snap["layoutRevision"]

    # faultInject / skillTags 告警
    codes = {w["code"] for w in r1["runManifest"]["warnings"]}
    assert "FAULT_INJECT_IGNORED" in codes
    assert "SKILL_TAGS_IGNORED" in codes

    # revision mismatch
    try:
        run_des(**{**common, "expected_layout_revision": "nope"})
        raise AssertionError("expected LAYOUT_REVISION_MISMATCH")
    except DesError as exc:
        assert exc.code == "LAYOUT_REVISION_MISMATCH"

    print("PASS FX-M3-ENGINE reproducible + conservation + evidence + readonly snapshot")


def test_zero_demand_no_divzero() -> None:
    layout = load("valid/fx-m1-ok-layout.json")
    facility = load("valid/fx01-small-rect-facility.json")
    demand = load("valid/fx07-zero-demand.json")
    operating = load("valid/fx-m3-operating.json")
    # 去掉 faults/skill 干扰
    operating = deepcopy(operating)
    operating["faults"] = []
    for p in operating["resourcePools"]:
        p.pop("skillTags", None)
    snap = derive_layout_snapshot(layout, facility)
    result = run_des(
        snapshot=snap,
        demand=demand,
        operating=operating,
        run_control={
            "horizonSec": 3600,
            "seedStreams": {"demand": 1},
            "metricDefinitionVersion": "metrics-m3-v1",
        },
        expected_layout_revision=snap["layoutRevision"],
    )
    cards = result["kpi"]["cards"]
    assert cards["throughput"]["outboundPalletEq"] == 0
    assert cards["wait"]["meanSec"] is None  # 无完成样本，不伪造 0 等待
    assert cards["wait"]["sampleCount"] == 0
    assert result["kpi"]["secondary"]["completedTasks"] == 0
    print("PASS FX-M3-ZERO-DEMAND no forged wait / no div-zero")


def test_api_simulation_job() -> None:
    reset_store()
    client = TestClient(app)

    h = client.get("/api/v1/health").json()
    assert h["milestone"] in {"M3", "M4", "M5"}
    assert h["capabilities"]["des"] is True
    assert h["capabilities"]["des"] is True
    assert h["capabilities"]["kpiFromUiDemo"] is False

    project = client.post(
        "/api/v1/projects", json={"name": "M3", "unitSystem": "metric"}
    ).json()
    pid = project["id"]

    facility = load("valid/fx01-small-rect-facility.json")
    assert (
        client.post(
            f"/api/v1/projects/{pid}/facility-revisions",
            json={"facility": facility},
        ).status_code
        == 201
    )

    layout = load("valid/fx-m1-ok-layout.json")
    saved = client.post(
        f"/api/v1/layouts/{layout['id']}/revisions",
        json={"projectId": pid, "baseRevision": None, "document": layout},
    ).json()
    layout_ref = saved["layoutRef"]

    variant = client.post(
        f"/api/v1/projects/{pid}/variants",
        json={"name": "M3-A", "source": "manual", "layoutRef": layout_ref},
    ).json()

    prep = client.post(
        f"/api/v1/layouts/{layout_ref['id']}/prepare-jobs",
        json={
            "projectId": pid,
            "layoutRef": layout_ref,
            "facilityRef": {"id": facility["id"], "revision": facility["revision"]},
            "ruleSetRefs": [{"id": "ruleset.m1.geometry", "revision": "0.1"}],
            "sync": True,
        },
    ).json()
    assert prep["simulationReady"] is True, prep

    demand = load("valid/fx-m3-demand-outbound.json")
    operating = load("valid/fx-m3-operating.json")
    client.post("/api/v1/demands", json={"projectId": pid, "demand": demand})
    client.post(
        "/api/v1/operating-profiles", json={"projectId": pid, "operating": operating}
    )

    scenario = load("valid/fx-m3-scenario-package.json")
    scenario["expectedLayoutRevision"] = layout_ref["revision"]

    # 未 ready 的假 revision 应拒绝 —— 用错误 expected
    bad = client.post(
        "/api/v1/simulation-jobs",
        json={
            "projectId": pid,
            "variantRef": {"id": variant["id"], "revision": variant["revision"]},
            "scenarioPackage": {**scenario, "expectedLayoutRevision": "stale-rev"},
        },
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "LAYOUT_REVISION_MISMATCH"

    ok = client.post(
        "/api/v1/simulation-jobs",
        json={
            "projectId": pid,
            "variantRef": {"id": variant["id"], "revision": variant["revision"]},
            "scenarioPackage": scenario,
        },
    )
    assert ok.status_code == 202, ok.text
    body = ok.json()
    assert body["state"] == "succeeded"
    assert body["kpiFromUiDemo"] is False
    assert body["kpi"]["cards"]["throughput"]["outboundPalletEq"] == 4.0
    assert body["inventoryConservation"]["ok"] is True
    assert body["replayBinding"]["layoutRevision"] == layout_ref["revision"]
    assert body["trajectorySummary"]["layoutRevision"] == layout_ref["revision"]
    assert any(w["code"] == "FAULT_INJECT_IGNORED" for w in body["warnings"])

    run = client.get(f"/api/v1/runs/{body['runId']}").json()
    assert run["runId"] == body["runId"]
    assert run["trajectory"]["layoutRevision"] == layout_ref["revision"]
    assert len(run["kpiEvidence"]["outboundEvents"]) == 4
    # 历史快照绑定
    assert (
        run["layoutSnapshotBound"]["layoutSnapshot"]["layoutRevision"]
        == layout_ref["revision"]
    )

    # 第二次同输入可复现 KPI
    ok2 = client.post(
        "/api/v1/simulation-jobs",
        json={
            "projectId": pid,
            "variantRef": {"id": variant["id"], "revision": variant["revision"]},
            "scenarioPackage": scenario,
        },
    ).json()
    assert ok2["kpi"]["cards"] == body["kpi"]["cards"]
    assert ok2["trajectorySummary"]["segmentCount"] == body["trajectorySummary"]["segmentCount"]

    print(
        f"PASS FX-M3-API runId={body['runId']} throughputEq={body['kpi']['cards']['throughput']['outboundPalletEq']}"
    )


def test_not_ready_blocks_des() -> None:
    reset_store()
    client = TestClient(app)
    project = client.post(
        "/api/v1/projects", json={"name": "M3-block", "unitSystem": "metric"}
    ).json()
    pid = project["id"]
    facility = load("valid/fx01-small-rect-facility.json")
    client.post(
        f"/api/v1/projects/{pid}/facility-revisions", json={"facility": facility}
    )
    layout = load("valid/fx-m1-ok-layout.json")
    saved = client.post(
        f"/api/v1/layouts/{layout['id']}/revisions",
        json={"projectId": pid, "document": layout},
    ).json()
    variant = client.post(
        f"/api/v1/projects/{pid}/variants",
        json={
            "name": "draft",
            "source": "manual",
            "layoutRef": saved["layoutRef"],
        },
    ).json()
    scenario = load("valid/fx-m3-scenario-package.json")
    demand = load("valid/fx-m3-demand-outbound.json")
    operating = load("valid/fx-m3-operating.json")
    res = client.post(
        "/api/v1/simulation-jobs",
        json={
            "projectId": pid,
            "variantRef": {"id": variant["id"], "revision": variant["revision"]},
            "scenarioPackage": scenario,
            "demand": demand,
            "operating": operating,
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "NOT_SIMULATION_READY"
    print("PASS FX-M3-GATE prepare required before DES")


def _ops_common(demand: dict, snap: dict, operating: dict) -> dict:
    return dict(
        snapshot=snap,
        demand=demand,
        operating=operating,
        run_control={
            "horizonSec": 3600,
            "seedStreams": {"demand": 42, "dispatch": 42},
            "metricDefinitionVersion": "metrics-m3-v1",
        },
        expected_layout_revision=snap["layoutRevision"],
        faults=operating.get("faults"),
        skill_tags_present=True,
    )


def test_break_bulk_and_piece_pick() -> None:
    layout = load("valid/fx-m1-ok-layout.json")
    facility = load("valid/fx01-small-rect-facility.json")
    operating = load("valid/fx-m3-operating.json")
    snap = derive_layout_snapshot(layout, facility)
    before_ids = sorted(el["elementId"] for el in snap["elements"])
    break_demand = load("valid/fx-ops-demand-break-bulk.json")
    piece_demand = load("valid/fx-ops-demand-piece-pick.json")

    common_break = _ops_common(break_demand, snap, operating)
    b1 = run_des(**common_break, run_id="run-break-a")
    b2 = run_des(**common_break, run_id="run-break-b")
    assert _strip_run(b1) == _strip_run(b2)
    assert sorted(el["elementId"] for el in snap["elements"]) == before_ids
    assert b1["inventoryConservation"]["ok"] is True
    assert b1["inventoryConservation"]["initial"] == 2.0
    assert b1["inventoryConservation"]["outbound"] == 2.0
    assert b1["inventoryConservation"]["ending"] == 0.0
    assert min(b1["inventoryConservation"]["stockByLocation"].values()) >= 0
    assert b1["kpi"]["cards"]["throughput"]["outboundPalletEq"] == 2.0
    assert b1["kpiFromUiDemo"] is False
    breaks = [e for e in b1["events"] if e["kind"] == "break_bulk"]
    ships = [e for e in b1["events"] if e["kind"] == "outbound_complete"]
    assert len(breaks) == 2
    assert all(e["countsAsExternalThroughput"] is False for e in breaks)
    assert all(e["cases"] == 4 for e in breaks)
    assert len(ships) == 2
    assert all(e["countsAsExternalThroughput"] is True for e in ships)
    assert all(e["source"] == "derived" and e["parentTaskId"] for e in ships)
    assert abs(sum(e["palletEq"] for e in ships) - 2.0) < 1e-9
    assert "FLOW_KIND_STUB" not in {w["code"] for w in b1["runManifest"]["warnings"]}
    derived = [e for e in b1["events"] if e["kind"] == "derived_ship"]
    assert len(derived) == 2
    assert {e["flowChainId"] for e in derived} == {"flow-break-1"}

    common_piece = _ops_common(piece_demand, snap, operating)
    p1 = run_des(**common_piece, run_id="run-piece-a")
    p2 = run_des(**common_piece, run_id="run-piece-b")
    assert _strip_run(p1) == _strip_run(p2)
    assert p1["inventoryConservation"]["ok"] is True
    assert p1["inventoryConservation"]["ending"] == 1.0
    assert p1["kpi"]["cards"]["throughput"]["outboundPalletEq"] == 1.0
    piece_ships = [e for e in p1["events"] if e["kind"] == "outbound_complete"]
    assert len(piece_ships) == 4
    assert all(e["source"] == "external" and e["parentTaskId"] is None for e in piece_ships)
    assert abs(sum(e["palletEq"] for e in piece_ships) - 1.0) < 1e-9
    assert not any(e["kind"] == "break_bulk" for e in p1["events"])

    mixed = deepcopy(break_demand)
    mixed["initialInventory"][0]["quantity"] = 3
    mixed["flows"] = [
        break_demand["flows"][0],
        piece_demand["flows"][0],
    ]
    mixed["flows"][0] = deepcopy(mixed["flows"][0])
    mixed["flows"][0]["quantity"] = 1
    m1 = run_des(**_ops_common(mixed, snap, operating), run_id="run-mix-a")
    m2 = run_des(**_ops_common(mixed, snap, operating), run_id="run-mix-b")
    assert _strip_run(m1) == _strip_run(m2)
    assert m1["kpi"]["cards"]["throughput"]["outboundPalletEq"] == 2.0
    assert m1["inventoryConservation"]["ok"] is True
    assert m1["inventoryConservation"]["ending"] == 1.0
    mix_ships = [e for e in m1["events"] if e["kind"] == "outbound_complete"]
    assert abs(sum(e["palletEq"] for e in mix_ships) - 2.0) < 1e-9
    assert len([e for e in m1["events"] if e["kind"] == "break_bulk"]) == 1

    missing = deepcopy(piece_demand)
    missing["flows"][0]["casesPerPallet"] = None
    try:
        run_des(**_ops_common(missing, snap, operating), run_id="run-missing-cpp")
        raise AssertionError("expected missing casesPerPallet")
    except DesError as exc:
        assert exc.code == "INPUT_UNCONFIRMED"
        assert "casesPerPallet" in exc.message

    print(
        "PASS FX-OPS break outboundEq=2 piece outboundEq=1 mixed=2 "
        "no extra zone, reproducible"
    )


def main() -> int:
    failures = 0
    for name, fn in [
        ("ENGINE", test_engine_core),
        ("ZERO", test_zero_demand_no_divzero),
        ("OPS", test_break_bulk_and_piece_pick),
        ("API", test_api_simulation_job),
        ("GATE", test_not_ready_blocks_des),
    ]:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}: {exc}")
    if failures:
        print(f"{failures} M3 check(s) failed")
        return 1
    print("All M3 checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
