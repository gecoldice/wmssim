#!/usr/bin/env python3
"""M2 规划/采用/锁定/并发夹具检查。

Usage:
  source .venv/bin/activate
  PYTHONPATH=shared/python python3 scripts/run_m2_checks.py
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared" / "python"))
sys.path.insert(0, str(ROOT / "services" / "api"))

from fastapi.testclient import TestClient  # noqa: E402

from simapp_plan import run_planning_job  # noqa: E402
from simapp_plan.confirm import FacilityGateError, assert_facility_usable_for_planning  # noqa: E402
from simapp_plan.locks import assert_locks_preserved, element_pose_params  # noqa: E402
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


def test_unconfirmed_facility() -> None:
    facility = load("invalid/fx-m2-unconfirmed-facility.json")
    try:
        assert_facility_usable_for_planning(facility, require_confirmed=True)
        raise AssertionError("expected FacilityGateError")
    except FacilityGateError as exc:
        assert exc.code == "INPUT_UNCONFIRMED", exc.code

    req = load("valid/fx01-planning-request.json")
    result = run_planning_job(req, facility=facility)
    assert result["job"]["outcome"] == "invalid_input"
    assert result["job"]["error"]["code"] == "INPUT_UNCONFIRMED"
    assert result["candidates"] == []
    print("PASS FX-M2-UNCONFIRMED (pending ≠ validated planning)")


def test_baseline_candidates() -> None:
    facility = load("valid/fx01-small-rect-facility.json")
    demand = load("valid/fx01-demand-revision.json")
    req = load("valid/fx01-planning-request.json")
    result = run_planning_job(req, facility=facility, demand=demand)
    job = result["job"]
    cands = result["candidates"]
    assert job["outcome"] == "feasible", job
    assert len(cands) >= 1
    assert len(cands) <= 4  # 不足 4 不凑数；最多 4
    for c in cands:
        assert c["feasibilityStatus"] == "validated"
        assert c["claimsOperationalEfficiency"] is False
        els = c["layoutDocument"]["elements"]
        racks = [e for e in els if e["typeElementId"] == "ST-PAL-01"]
        assert racks, "must emit real ST-PAL-01 editable devices"
        assert all("instanceId" in e and "pose" in e and "params" in e for e in racks)
        # 可编辑参数存在
        assert "levels" in racks[0]["params"]
    print(f"PASS FX-M2-BASELINE feasible candidates={len(cands)} real ST-PAL-01")


def test_locks_and_region() -> None:
    facility = load("valid/fx01-small-rect-facility.json")
    base = load("valid/fx-m2-base-layout-locked.json")
    demand = load("valid/fx01-demand-revision.json")
    req = load("valid/fx01-planning-request.json")
    req = deepcopy(req)
    req["locks"] = [
        {"instanceId": "dock-recv-locked", "fields": "all"},
        {"instanceId": "dock-ship-locked", "fields": "all"},
    ]
    req["scope"] = {
        "mode": "region",
        "polygon": {
            "outer": [
                {"x": 5, "y": 8},
                {"x": 35, "y": 8},
                {"x": 35, "y": 20},
                {"x": 5, "y": 20},
                {"x": 5, "y": 8},
            ]
        },
    }
    result = run_planning_job(req, facility=facility, base_layout=base, demand=demand)
    assert result["job"]["outcome"] == "feasible", result["job"]
    for c in result["candidates"]:
        assert_locks_preserved(base["elements"], c["layoutDocument"]["elements"], req["locks"])
        # 区域外 rack-keep-outside 必须仍在
        ids = {e["instanceId"] for e in c["layoutDocument"]["elements"]}
        assert "rack-keep-outside" in ids
        outside = next(e for e in c["layoutDocument"]["elements"] if e["instanceId"] == "rack-keep-outside")
        assert element_pose_params(outside) == element_pose_params(
            next(e for e in base["elements"] if e["instanceId"] == "rack-keep-outside")
        )
        docks = {
            e["instanceId"]: e
            for e in c["layoutDocument"]["elements"]
            if e["instanceId"] in {"dock-recv-locked", "dock-ship-locked"}
        }
        assert docks["dock-recv-locked"]["pose"] == {"x": 1.5, "y": 12, "yawDeg": 0}
    print("PASS FX-M2-LOCKS region replan preserves locks + outside")


def test_api_adopt_and_conflict() -> None:
    reset_store()
    client = TestClient(app)
    health = client.get("/api/v1/health").json()
    # M3 起 milestone 前进；规划路径仍独立，且 quick 候选不得宣称运营效率
    assert health["milestone"] in {"M2", "M3"}
    assert health["capabilities"]["planning"] is True
    assert health["capabilities"]["manualLayout"] is True
    assert health["capabilities"]["kpiFromUiDemo"] is False

    project = client.post(
        "/api/v1/projects", json={"name": "M2 demo", "unitSystem": "metric"}
    ).json()
    pid = project["id"]

    facility = load("valid/fx01-small-rect-facility.json")
    fr = client.post(
        f"/api/v1/projects/{pid}/facility-revisions",
        json={"facility": facility},
    ).json()
    assert fr["gate"]["usableForValidatedPlanning"] is True

    # 未确认场地登记：门禁不可用
    pending = load("invalid/fx-m2-unconfirmed-facility.json")
    pending["id"] = "facility-pending-api"
    pending["revision"] = "f-pending-api"
    gate = client.post(
        f"/api/v1/projects/{pid}/facility-revisions",
        json={"facility": pending},
    ).json()["gate"]
    assert gate["usableForValidatedPlanning"] is False

    # 底图未标定
    drawing = client.post(
        f"/api/v1/projects/{pid}/drawings",
        json={"filename": "plan.png", "meta": {}, "status": "uploaded"},
    ).json()
    assert drawing["status"] == "uploaded"

    demand = load("valid/fx01-demand-revision.json")
    client.post("/api/v1/demands", json={"projectId": pid, "demand": demand})

    # 空 base variant
    empty_layout = {
        "contractVersion": "0.3",
        "id": "layout-empty-m2",
        "revision": "ld-e1",
        "facilityRef": {"id": "facility-fx01", "revision": "f-r1"},
        "parentRef": None,
        "elements": [],
        "aisles": [],
        "locks": [],
        "catalogVersion": "catalog-mvp@c-r1",
    }
    # 恢复确认场地为 head（上面写了 pending）
    client.post(
        f"/api/v1/projects/{pid}/facility-revisions",
        json={"facility": facility},
    )
    client.post(
        "/api/v1/layouts/layout-empty-m2/revisions",
        json={"projectId": pid, "baseRevision": None, "document": empty_layout},
    )
    variant = client.post(
        f"/api/v1/projects/{pid}/variants",
        json={
            "name": "空底稿",
            "source": "manual",
            "layoutRef": {"id": "layout-empty-m2", "revision": "ld-e1"},
        },
    ).json()

    req = load("valid/fx01-planning-request.json")
    req["projectId"] = pid
    req["facilityRef"] = {"id": "facility-fx01", "revision": "f-r1"}
    req["baseVariantRef"] = {"id": variant["id"], "revision": variant["revision"]}
    req["demandRef"] = {"id": "demand-fx01", "revision": "d-r1"}

    plan = client.post("/api/v1/planning-jobs", json=req).json()
    assert plan["outcome"] == "feasible", plan
    assert plan["candidates"], plan
    assert all(c.get("claimsOperationalEfficiency") is False for c in plan["candidates"])

    cand_id = plan["candidates"][0]["id"]
    detail = client.get(f"/api/v1/candidates/{cand_id}").json()
    assert detail["layoutDocument"]["elements"]

    # 采用
    adopted = client.post(
        f"/api/v1/candidates/{cand_id}/adoptions",
        json={
            "projectId": pid,
            "currentVariantRef": {"id": variant["id"], "revision": variant["revision"]},
            "newName": "生成方案 A",
            "expectedVariantRevision": variant["revision"],
        },
    )
    assert adopted.status_code == 201, adopted.text
    body = adopted.json()
    assert body["variant"]["source"] == "generated"
    assert body["variant"]["id"] != variant["id"]
    assert body["layoutRef"]["id"] != "layout-empty-m2"
    # 原 variant 未改
    still = client.get(f"/api/v1/projects/{pid}/variants").json()["items"]
    orig = next(v for v in still if v["id"] == variant["id"])
    assert orig["revision"] == variant["revision"]
    assert orig["layoutRef"]["id"] == "layout-empty-m2"

    # 并发：陈旧 revision → 409
    conflict = client.post(
        f"/api/v1/candidates/{cand_id}/adoptions",
        json={
            "projectId": pid,
            "currentVariantRef": {"id": variant["id"], "revision": "vr-stale"},
            "newName": "应失败",
            "expectedVariantRevision": "vr-stale",
        },
    )
    assert conflict.status_code == 409, conflict.text
    detail_err = conflict.json()["detail"]
    assert detail_err["code"] == "REVISION_CONFLICT"

    # 手动路径仍可用
    manual = load("valid/fx-m1-ok-layout.json")
    client.post(
        f"/api/v1/layouts/{manual['id']}/revisions",
        json={"projectId": pid, "baseRevision": None, "document": manual},
    )
    prep = client.post(
        f"/api/v1/layouts/{manual['id']}/prepare-jobs",
        json={
            "projectId": pid,
            "layoutRef": {"id": manual["id"], "revision": manual["revision"]},
            "facilityRef": {"id": "facility-fx01", "revision": "f-r1"},
            "ruleSetRefs": [],
            "sync": True,
        },
    ).json()
    assert prep["simulationReady"] is True

    print("PASS FX-M2-API adopt branch + REVISION_CONFLICT + manual intact")


def test_no_ops_efficiency_claim() -> None:
    facility = load("valid/fx01-small-rect-facility.json")
    req = load("valid/fx01-planning-request.json")
    req = deepcopy(req)
    req["evaluationLevel"] = "detailed"
    result = run_planning_job(req, facility=facility)
    assert result["job"]["outcome"] == "unsupported"
    assert result["job"]["error"]["code"] == "UNSUPPORTED_SCENARIO"
    # 规划器 detailed 仍非 DES 入口；真实效率走 /simulation-jobs（见 test:m3）
    print("PASS FX-M2-NO-DES planning detailed unsupported (DES is /simulation-jobs)")


def main() -> int:
    failures = 0
    cases = [
        ("FX-M2-UNCONFIRMED", test_unconfirmed_facility),
        ("FX-M2-BASELINE", test_baseline_candidates),
        ("FX-M2-LOCKS", test_locks_and_region),
        ("FX-M2-API", test_api_adopt_and_conflict),
        ("FX-M2-NO-DES", test_no_ops_efficiency_claim),
    ]
    for name, fn in cases:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}: {exc}")
    if failures:
        print(f"\n{failures} M2 check failure(s)")
        return 1
    print("\nAll M2 planning/adopt checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
