#!/usr/bin/env python3
"""M5 复杂识图与高级优化：每项必须是失败/不支持，不宣称未实现能力。

Usage:
  source .venv/bin/activate
  PYTHONPATH=shared/python:services/api python3 scripts/run_m5_checks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared" / "python"))
sys.path.insert(0, str(ROOT / "services" / "api"))

from fastapi.testclient import TestClient  # noqa: E402

from simapp_extend import assess_advanced, assess_recognition  # noqa: E402
from app.main import app  # noqa: E402
from app.store import STORE  # noqa: E402


def reset_store() -> None:
    STORE.projects.clear()
    STORE._orphan_jobs.clear()
    STORE._global_candidates.clear()
    STORE._global_runs.clear()
    STORE._global_estimates.clear()
    STORE._global_comparisons.clear()
    STORE._global_reports.clear()


def _assert_no_geometry(result: dict) -> None:
    assert result["implemented"] is False
    assert result["claimsValidatedGeometry"] is False
    assert result["producedGeometry"] is None
    assert result["producedFacility"] is None
    assert result["preciseRackLayout"] is None
    assert result["confirmationStatus"] == "pending"
    assert result["correction"]["dropsSource"] is False
    assert result["failure"]["code"]
    assert result["failure"]["message"]


def test_unknown_recognition() -> None:
    result = assess_recognition(capability="lidar_scan", source={"filename": "a.dxf"})
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "UNKNOWN_RECOGNITION_CAPABILITY"
    _assert_no_geometry(result)
    print("OK recognition: unknown capability fails")


def test_dxf_paths() -> None:
    missing = assess_recognition(capability="dxf_vector_extract", source={})
    assert missing["status"] == "failed"
    assert missing["failure"]["code"] == "MISSING_SOURCE"
    _assert_no_geometry(missing)

    wrong = assess_recognition(
        capability="dxf_vector_extract",
        source={"filename": "plan.png", "mediaType": "image/png"},
        drawing={"id": "d1", "filename": "plan.png", "status": "uploaded"},
    )
    assert wrong["status"] == "failed"
    assert wrong["failure"]["code"] == "SOURCE_TYPE_MISMATCH"
    assert wrong["drawingRetained"] is True
    _assert_no_geometry(wrong)

    dxf = assess_recognition(
        capability="dxf_vector_extract",
        source={
            "filename": "hall.dxf",
            "mediaType": "application/dxf",
            "polygons": [{"outer": [{"x": 0, "y": 0}, {"x": 10, "y": 0}]}],
            "extractedGeometry": {"boundary": "rect"},
        },
        drawing={"id": "d2", "filename": "hall.dxf", "status": "uploaded"},
    )
    assert dxf["status"] == "unsupported"
    assert dxf["failure"]["code"] == "DXF_EXTRACT_UNSUPPORTED"
    assert dxf["correction"]["action"] == "manual_trace"
    _assert_no_geometry(dxf)
    assert "polygons" not in dxf
    print("OK recognition: DXF missing / wrong type / unsupported extract")


def test_ocr_not_verified() -> None:
    missing = assess_recognition(capability="ocr_assist", source={})
    assert missing["failure"]["code"] == "MISSING_SOURCE"

    high = assess_recognition(
        capability="ocr_assist",
        source={"filename": "scan.png", "mediaType": "image/png", "ocrConfidence": 0.99},
        drawing={"id": "d3", "filename": "scan.png", "status": "uploaded"},
    )
    assert high["status"] == "needs_confirmation"
    assert high["failure"]["code"] == "OCR_NOT_VERIFIED"
    assert high["ocrConfidenceEcho"] == 0.99
    assert high["confirmationStatus"] == "pending"
    _assert_no_geometry(high)
    print("OK recognition: OCR high confidence stays unconfirmed")


def test_polygon_paths() -> None:
    missing_scale = assess_recognition(
        capability="polygon_height_partition",
        source={"filename": "plan.pdf", "concave": False, "floors": 1},
    )
    assert missing_scale["status"] == "failed"
    assert missing_scale["failure"]["code"] == "SCALE_MISSING"
    _assert_no_geometry(missing_scale)

    complex_site = assess_recognition(
        capability="polygon_height_partition",
        source={
            "filename": "plan.pdf",
            "scaleDeclared": True,
            "concave": True,
            "floors": 2,
            "heightZones": 3,
            "coldStorage": True,
        },
    )
    assert complex_site["status"] == "unsupported"
    assert complex_site["failure"]["code"] == "SITE_COMPLEXITY_UNSUPPORTED"
    assert complex_site["correction"]["action"] == "manual_trace"
    _assert_no_geometry(complex_site)

    simple = assess_recognition(
        capability="polygon_height_partition",
        source={
            "filename": "plan.pdf",
            "scaleDeclared": True,
            "metersPerPixel": 0.02,
            "floors": 1,
            "heightZones": 1,
            "polygons": [{"outer": [{"x": 0, "y": 0}]}],
        },
    )
    assert simple["status"] == "unsupported"
    assert simple["failure"]["code"] == "POLYGON_PARTITION_UNSUPPORTED"
    assert simple["correction"]["action"] == "manual_facility"
    _assert_no_geometry(simple)
    print("OK recognition: scale / complex site / simple rect all refuse geometry")


def _assert_no_benefit(result: dict) -> None:
    assert result["implemented"] is False
    assert result["claimsBetterThanBaseline"] is False
    assert result["benefitProven"] is False
    assert result["claimsSavings"] is False
    assert result["claimsThroughput"] is False
    assert result["searchRan"] is False
    assert result["candidates"] == []
    assert result["score"] is None
    assert result["horizonCost"] is None
    assert result["npv"] is None
    assert result["payback"] is None
    assert result["savingsRate"] is None
    assert result["supportedInConclusion"] is False
    assert result["failure"]["code"]


def test_nsga2_and_multi_objective() -> None:
    nsga = assess_advanced(
        capability="nsga2",
        inputs={"population": 80, "claimedImprovementPct": 15, "candidates": [{"id": "fake"}]},
    )
    assert nsga["status"] == "unsupported"
    assert nsga["failure"]["code"] == "NSGA2_NOT_ADOPTED"
    assert nsga["baselinePlanner"] == "m2-plan-baseline-0.1"
    assert nsga["correction"]["action"] == "use_baseline_planner"
    _assert_no_benefit(nsga)

    multi = assess_advanced(
        capability="multi_objective",
        inputs={
            "goals": ["capacity", "lifecycle_cost", "easy_automation", "expandable", "magic"],
            "score": 88,
        },
    )
    assert multi["status"] == "unsupported"
    assert multi["failure"]["code"] == "MULTI_OBJECTIVE_UNSUPPORTED"
    assert multi["acceptedGoals"] == []
    goals = {item["goal"] for item in multi["disabledGoals"]}
    assert {"lifecycle_cost", "easy_automation", "expandable", "magic"} <= goals
    _assert_no_benefit(multi)
    print("OK advanced: NSGA-II and multi-objective produce no candidates")


def test_lifecycle_cost_unsupported() -> None:
    incomplete = assess_advanced(
        capability="lifecycle_cost",
        inputs={"horizonYears": 5, "feeComplete": False, "capex": 1000},
    )
    assert incomplete["failure"]["code"] == "HORIZON_INCOMPLETE"
    _assert_no_benefit(incomplete)

    no_rate = assess_advanced(
        capability="lifecycle_cost",
        inputs={"horizonYears": 5, "feeComplete": True, "discountRequested": True, "capex": 1000},
    )
    assert no_rate["failure"]["code"] == "DISCOUNT_RATE_MISSING"
    assert no_rate["npv"] is None
    _assert_no_benefit(no_rate)

    complete = assess_advanced(
        capability="lifecycle_cost",
        inputs={
            "horizonYears": 5,
            "feeComplete": True,
            "capex": 100000,
            "annualOpex": 20000,
            "discountRequested": True,
            "discountRate": 0.08,
            "baselineCapex": 120000,
            "horizonCost": 999,
            "npv": 1,
            "savingsRate": 0.2,
        },
    )
    assert complete["status"] == "unsupported"
    assert complete["failure"]["code"] == "LIFECYCLE_NOT_IMPLEMENTED"
    assert complete["correction"]["action"] == "use_m4_capex"
    _assert_no_benefit(complete)
    print("OK advanced: lifecycle stays null even when inputs look complete")


def test_scales_and_automation() -> None:
    expansion = assess_advanced(
        capability="expansion_scale",
        inputs={"growthPct": 20, "score": 0},
    )
    assert expansion["failure"]["code"] == "EXPANSION_SCALE_UNCONFIRMED"
    assert expansion["axisId"] == "expansion"
    assert expansion["axisStatus"] == "unavailable"
    assert expansion["score"] is None
    _assert_no_benefit(expansion)

    expansion_named = assess_advanced(
        capability="expansion_scale",
        inputs={"growthScenarioId": "g1", "scaleVersion": "s1", "score": 70},
    )
    assert expansion_named["failure"]["code"] == "EXPANSION_SCALE_NOT_IMPLEMENTED"
    assert expansion_named["score"] is None

    oper = assess_advanced(
        capability="operability_scale",
        inputs={"skillTags": ["certified"], "faultInject": True, "score": 0},
    )
    assert oper["failure"]["code"] == "OPERABILITY_EVIDENCE_MISSING"
    assert oper["axisStatus"] == "unavailable"
    assert oper["score"] is None

    oper_named = assess_advanced(
        capability="operability_scale",
        inputs={"evidenceRefs": ["doc-1"], "scaleVersion": "op-1", "score": 50},
    )
    assert oper_named["failure"]["code"] == "OPERABILITY_SCALE_NOT_IMPLEMENTED"
    assert oper_named["score"] is None

    auto = assess_advanced(
        capability="calibrated_automation",
        inputs={"equipment": ["AGV", "ASRS"], "calibrated": False},
    )
    assert auto["failure"]["code"] == "AUTOMATION_UNCALIBRATED"
    assert auto["claimsThroughput"] is False
    _assert_no_benefit(auto)

    auto_flag = assess_advanced(
        capability="calibrated_automation",
        inputs={"equipment": ["AGV"], "calibrated": True, "calibrationEvidenceRefs": ["cal-1"]},
    )
    assert auto_flag["failure"]["code"] == "AUTOMATION_MODEL_NOT_IMPLEMENTED"
    assert auto_flag["claimsThroughput"] is False
    assert auto_flag["supportedInConclusion"] is False
    print("OK advanced: expansion/operability/automation do not score or claim throughput")


def test_unknown_advanced() -> None:
    result = assess_advanced(capability="rl_policy", inputs={"score": 100})
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "UNKNOWN_ADVANCED_CAPABILITY"
    _assert_no_benefit(result)
    print("OK advanced: unknown capability fails")


def test_api_recognition_retains_drawing() -> None:
    reset_store()
    client = TestClient(app)
    health = client.get("/api/v1/health").json()
    assert health["milestone"] == "M5"
    assert health["capabilities"]["recognitionImplemented"] is False
    assert health["capabilities"]["claimsUnimplementedM5"] is False
    assert health["capabilities"]["bomCost"] is True
    assert health["capabilities"]["des"] is True

    project = client.post("/api/v1/projects", json={"name": "m5", "unitSystem": "metric"}).json()
    pid = project["id"]
    drawing = client.post(
        f"/api/v1/projects/{pid}/drawings",
        json={"filename": "hall.dxf", "status": "uploaded", "meta": {}},
    ).json()
    before = client.get(f"/api/v1/projects/{pid}").json()
    assert before["facilityHead"] is None

    res = client.post(
        "/api/v1/recognition-jobs",
        json={
            "projectId": pid,
            "capability": "dxf_vector_extract",
            "drawingId": drawing["id"],
            "source": {
                "filename": "hall.dxf",
                "mediaType": "application/dxf",
                "writeFacility": True,
                "polygons": [{"outer": [{"x": 0, "y": 0}]}],
            },
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "unsupported"
    assert body["failure"]["code"] == "DXF_EXTRACT_UNSUPPORTED"
    assert body["producedGeometry"] is None
    assert body["facilityWritten"] is False
    assert body["facilityHeadUnchanged"] is True
    assert body["drawingRetained"] is True
    assert body["drawingStatus"] == "uploaded"

    still = client.get(f"/api/v1/projects/{pid}/drawings/{drawing['id']}")
    assert still.status_code == 200
    assert still.json()["status"] == "uploaded"
    after = client.get(f"/api/v1/projects/{pid}").json()
    assert after["facilityHead"] is None

    missing = client.post(
        "/api/v1/recognition-jobs",
        json={"projectId": pid, "capability": "ocr_assist", "drawingId": "missing"},
    )
    assert missing.status_code == 404
    print("OK API: recognition keeps drawing and does not write facility")


def test_api_advanced_evaluations() -> None:
    reset_store()
    client = TestClient(app)
    project = client.post("/api/v1/projects", json={"name": "m5-adv", "unitSystem": "metric"}).json()
    pid = project["id"]
    res = client.post(
        "/api/v1/advanced-evaluations",
        json={
            "projectId": pid,
            "capability": "lifecycle_cost",
            "inputs": {
                "horizonYears": 8,
                "feeComplete": True,
                "discountRequested": False,
                "capex": 50000,
                "annualOpex": 8000,
                "horizonCost": 1,
                "savingsRate": 0.5,
            },
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["failure"]["code"] == "LIFECYCLE_NOT_IMPLEMENTED"
    assert body["horizonCost"] is None
    assert body["savingsRate"] is None
    assert body["candidates"] == []

    nsga = client.post(
        "/api/v1/advanced-evaluations",
        json={"projectId": pid, "capability": "nsga2", "inputs": {"claimedImprovementPct": 30}},
    ).json()
    assert nsga["claimsBetterThanBaseline"] is False
    assert nsga["benefitProven"] is False
    assert nsga["candidates"] == []

    missing_project = client.post(
        "/api/v1/advanced-evaluations",
        json={"projectId": "nope", "capability": "nsga2", "inputs": {}},
    )
    assert missing_project.status_code == 404
    print("OK API: advanced evaluations stay unsupported")


def main() -> int:
    tests = [
        test_unknown_recognition,
        test_dxf_paths,
        test_ocr_not_verified,
        test_polygon_paths,
        test_nsga2_and_multi_objective,
        test_lifecycle_cost_unsupported,
        test_scales_and_automation,
        test_unknown_advanced,
        test_api_recognition_retains_drawing,
        test_api_advanced_evaluations,
    ]
    for test in tests:
        test()
    print(f"\nAll {len(tests)} M5 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
