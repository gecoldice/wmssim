#!/usr/bin/env python3
"""M4 BOM/成本 / 多方案比较 / 交付报告检查。

Usage:
  source .venv/bin/activate
  PYTHONPATH=shared/python:services/api python3 scripts/run_m4_checks.py
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

from simapp_compare import (  # noqa: E402
    build_comparison,
    build_delivery_report,
    recommend_from_comparison,
    score_axis,
    select_radar_axes,
)
from simapp_cost import estimate_cost, recommend_lowest_capex  # noqa: E402
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
    STORE._global_estimates.clear()
    STORE._global_comparisons.clear()
    STORE._global_reports.clear()


def test_cost_missing_price_blocks_ranking() -> None:
    """DEV-12 / AC：缺价不排最低成本；可给 knownSubtotal。"""
    layout = load("valid/fx-m1-ok-layout.json")
    operating = load("valid/fx-m3-operating.json")
    basis = load("valid/fx-m4-cost-basis.json")
    pb_ok = load("valid/fx-m4-price-book-complete.json")
    pb_miss = load("valid/fx-m4-price-book-missing.json")

    complete = estimate_cost(
        layout=layout,
        price_book=pb_ok,
        cost_basis=basis,
        operating=operating,
        estimate_id="est-complete",
        variant_ref={"id": "v-a", "revision": "vr1"},
    )
    incomplete = estimate_cost(
        layout=layout,
        price_book=pb_miss,
        cost_basis=basis,
        operating=operating,
        estimate_id="est-incomplete",
        variant_ref={"id": "v-b", "revision": "vr1"},
    )

    assert complete["status"] == "complete"
    assert complete["eligibleForLowestCostRanking"] is True
    assert complete["totals"]["total"] is not None
    assert complete["totals"]["capex"] is not None
    assert complete["totals"]["capex"] > 0

    assert incomplete["status"] == "incomplete"
    assert incomplete["eligibleForLowestCostRanking"] is False
    assert incomplete["totals"]["total"] is None
    assert incomplete["totals"]["capex"] is None
    assert incomplete["totals"]["knownSubtotal"] > 0
    assert any(m["skuKey"] == "ST-PAL-01" for m in incomplete["missingItems"])

    # 缺价方案 knownSubtotal 可能更小，但不得因此成为「最低成本」赢家
    ranking = recommend_lowest_capex([incomplete, complete])
    assert ranking["rankingUnavailable"] is False
    assert ranking["winner"]["estimateId"] == "est-complete"
    assert any(x["estimateId"] == "est-incomplete" for x in ranking["excluded"])

    only_miss = recommend_lowest_capex([incomplete])
    assert only_miss["rankingUnavailable"] is True
    assert only_miss["code"] == "PRICE_INCOMPLETE"
    assert only_miss["winner"] is None
    print("OK cost: missing price blocks lowest-cost ranking")


def test_reuse_vs_purchase_no_double_count() -> None:
    """AC-14：复用零采购；搬移分列；安装不与单价重复。"""
    layout_new = load("valid/fx-m1-ok-layout.json")
    layout_reuse = load("valid/fx-m4-layout-reuse.json")
    basis = load("valid/fx-m4-cost-basis.json")
    pb = load("valid/fx-m4-price-book-complete.json")

    est_new = estimate_cost(layout=layout_new, price_book=pb, cost_basis=basis)
    est_reuse = estimate_cost(layout=layout_reuse, price_book=pb, cost_basis=basis)

    assert est_new["status"] == "complete"
    assert est_reuse["status"] == "complete"
    # 复用货架：无 ST-PAL-01 purchase，可有 relocate
    reuse_fees = {i["feeKind"] for i in est_reuse["items"] if i["skuKey"] == "ST-PAL-01"}
    assert "purchase" not in reuse_fees
    assert "existing_zero_purchase" in reuse_fees or "relocate" in reuse_fees
    assert est_reuse["totals"]["capex"] < est_new["totals"]["capex"]

    # purchaseIncludesInstall 时不加安装行
    basis_bundled = deepcopy(basis)
    basis_bundled["purchaseIncludesInstall"] = True
    est_bundled = estimate_cost(layout=layout_new, price_book=pb, cost_basis=basis_bundled)
    assert not any(i.get("feeKind") == "install" for i in est_bundled["items"])
    print("OK cost: reuse/relocate/install separation")


def test_radar_missing_axis_no_zero() -> None:
    """AC-12：缺轴不补零；共同轴 <3 仅表格。"""
    miss = score_axis(None, direction="higher_better", bad=0, good=10)
    assert miss["status"] == "missing"
    assert miss["score"] is None

    # 两方案：投资轴一方缺价
    profile = load("valid/fx-m4-score-profile.json")
    entries = [
        {
            "entryId": "a",
            "label": "A",
            "variantRef": {"id": "va", "revision": "1"},
            "layoutRef": {"id": "la", "revision": "r1"},
            "effectiveCapacity": 40,
            "completedCycleMeanSec": 120,
            "costEstimate": {
                "id": "c1",
                "status": "complete",
                "eligibleForLowestCostRanking": True,
                "totals": {"capex": 40000, "knownSubtotal": 40000, "currency": "CNY"},
            },
            "operating": {
                "resourcePools": [{"id": "f", "resourceType": "forklift", "count": 1}]
            },
        },
        {
            "entryId": "b",
            "label": "B",
            "variantRef": {"id": "vb", "revision": "1"},
            "layoutRef": {"id": "lb", "revision": "r1"},
            "effectiveCapacity": 50,
            "completedCycleMeanSec": 100,
            "costEstimate": {
                "id": "c2",
                "status": "incomplete",
                "eligibleForLowestCostRanking": False,
                "totals": {"capex": None, "knownSubtotal": 10000, "currency": "CNY"},
                "missingItems": [{"skuKey": "ST-PAL-01"}],
            },
            "operating": {
                "resourcePools": [{"id": "f", "resourceType": "forklift", "count": 1}]
            },
        },
    ]
    cmp = build_comparison(
        mode="layout_only",
        entries=entries,
        common_basis={"demandRevision": "d-r1", "engineVersion": "m3-des-0.1"},
        score_profile=profile,
    )
    # investment 对 B missing → 共同 available 轴只有 storage+efficiency <3
    assert cmp["radar"]["radarEnabled"] is False
    assert "investment" not in cmp["radar"]["commonAxes"]
    b_inv = cmp["entries"][1]["axisScores"]["investment"]
    assert b_inv["status"] == "missing"
    assert b_inv["score"] is None  # 不补零

    # 三轴齐全 → 雷达开启
    entries2 = deepcopy(entries)
    entries2[1]["costEstimate"] = {
        "id": "c2b",
        "status": "complete",
        "eligibleForLowestCostRanking": True,
        "totals": {"capex": 55000, "knownSubtotal": 55000, "currency": "CNY"},
    }
    cmp2 = build_comparison(
        mode="layout_only",
        entries=entries2,
        common_basis={"demandRevision": "d-r1"},
        score_profile=profile,
    )
    assert cmp2["radar"]["radarEnabled"] is True
    assert set(cmp2["radar"]["commonAxes"]) >= {"storage", "efficiency", "investment"}

    # 加入第四方案不改既有绝对分（锚点锁定）
    scores_before = {
        e["entryId"]: {k: v.get("score") for k, v in e["axisScores"].items()}
        for e in cmp2["entries"]
    }
    entries3 = entries2 + [
        {
            "entryId": "d",
            "label": "D",
            "variantRef": {"id": "vd", "revision": "1"},
            "layoutRef": {"id": "ld", "revision": "r1"},
            "effectiveCapacity": 90,
            "completedCycleMeanSec": 50,
            "costEstimate": {
                "id": "c4",
                "status": "complete",
                "eligibleForLowestCostRanking": True,
                "totals": {"capex": 90000, "knownSubtotal": 90000, "currency": "CNY"},
            },
            "operating": {
                "resourcePools": [{"id": "f", "resourceType": "forklift", "count": 1}]
            },
        }
    ]
    cmp3 = build_comparison(
        mode="layout_only",
        entries=entries3,
        common_basis={"demandRevision": "d-r1"},
        score_profile=profile,
    )
    for e in cmp3["entries"]:
        if e["entryId"] in scores_before:
            for ax, sc in scores_before[e["entryId"]].items():
                assert e["axisScores"][ax].get("score") == sc, (e["entryId"], ax)
    print("OK radar: no zero-fill; add entry keeps absolute scores")


def test_layout_only_vs_whole_solution() -> None:
    """AC-10：layout_only 资源不一致 → 不可比；whole_solution 披露人数差异。"""
    profile = load("valid/fx-m4-score-profile.json")
    base_op = {"resourcePools": [{"id": "f", "resourceType": "forklift", "count": 1}]}
    extra_op = load("valid/fx-m4-operating-extra-labor.json")

    def mk(eid, cap, op):
        return {
            "entryId": eid,
            "label": eid,
            "variantRef": {"id": eid, "revision": "1"},
            "layoutRef": {"id": f"l-{eid}", "revision": "r1"},
            "effectiveCapacity": cap,
            "completedCycleMeanSec": 100,
            "costEstimate": {
                "id": f"c-{eid}",
                "status": "complete",
                "eligibleForLowestCostRanking": True,
                "totals": {"capex": 30000, "knownSubtotal": 30000, "currency": "CNY"},
            },
            "operating": op,
        }

    cmp_lo = build_comparison(
        mode="layout_only",
        entries=[mk("a", 40, base_op), mk("b", 45, extra_op)],
        common_basis={},
        score_profile=profile,
    )
    assert cmp_lo["comparability"]["comparable"] is False
    assert any(
        i["code"] == "INCOMPARABLE_RESULTS" for i in cmp_lo["comparability"]["issues"]
    )

    cmp_ws = build_comparison(
        mode="whole_solution",
        entries=[mk("a", 40, base_op), mk("b", 45, extra_op)],
        common_basis={},
        score_profile=profile,
    )
    assert cmp_ws["comparability"]["comparable"] is True
    assert any(
        i["code"] == "RESOURCE_DIFF_DISCLOSED" for i in cmp_ws["comparability"]["issues"]
    )
    # 表格保留资源指纹
    fps = [r["resourceFingerprint"] for r in cmp_ws["table"]["rows"]]
    assert fps[0] != fps[1]
    print("OK compare: layout_only vs whole_solution")


def test_report_version_consistency() -> None:
    """DEV-14：报告与 layoutRevision/run 一致。"""
    project = {"id": "p1", "name": "demo"}
    variant = {"id": "v1", "revision": "vr1"}
    layout_ref = {"id": "layout-doc-fx01", "revision": "ld-r1"}
    run = {
        "runId": "run-1",
        "engineVersion": "m3-des-0.1",
        "kpiFromUiDemo": False,
        "trajectory": {"layoutRevision": "ld-r1"},
        "replayBinding": {"layoutRevision": "ld-r1"},
        "kpi": {"cards": {"throughput": {"outboundPalletEq": 4}, "wait": {"meanSec": 12}}},
        "runManifest": {"metricDefinitionVersion": "metrics-m3-v1"},
    }
    cost = {
        "id": "est-1",
        "costEngineVersion": "m4-cost-0.1",
        "status": "complete",
        "layoutRef": dict(layout_ref),
        "totals": {"capex": 1000, "total": 1000, "knownSubtotal": 1000, "currency": "CNY"},
        "missingItems": [],
    }
    report = build_delivery_report(
        project=project,
        variant=variant,
        layout_ref=layout_ref,
        run=run,
        cost_estimate=cost,
    )
    assert report["versionConsistent"] is True
    assert "ld-r1" in report["html"]
    assert "run-1" in report["html"]

    bad_run = deepcopy(run)
    bad_run["trajectory"]["layoutRevision"] = "OTHER"
    bad_run["replayBinding"]["layoutRevision"] = "OTHER"
    bad = build_delivery_report(
        project=project,
        variant=variant,
        layout_ref=layout_ref,
        run=bad_run,
        cost_estimate=cost,
    )
    assert bad["versionConsistent"] is False
    print("OK report: version binding")


def test_api_e2e() -> None:
    """API：成本 → 排序 → 比较 → 报告；绑历史布局。"""
    reset_store()
    client = TestClient(app)

    h = client.get("/api/v1/health").json()
    assert h["milestone"] in {"M4", "M5"}
    assert h["capabilities"]["missingPriceBlocksLowestCost"] is True

    project = client.post(
        "/api/v1/projects", json={"name": "m4-e2e", "unitSystem": "metric"}
    ).json()
    pid = project["id"]

    facility = load("valid/fx01-small-rect-facility.json")
    client.post(
        f"/api/v1/projects/{pid}/facility-revisions",
        json={"facility": facility},
    )
    layout = load("valid/fx-m1-ok-layout.json")
    client.post(
        f"/api/v1/layouts/{layout['id']}/revisions",
        json={"projectId": pid, "baseRevision": None, "document": layout},
    )
    variant = client.post(
        f"/api/v1/projects/{pid}/variants",
        json={
            "name": "方案 A",
            "source": "manual",
            "layoutRef": {"id": layout["id"], "revision": layout["revision"]},
        },
    ).json()

    # prepare + DES（报告绑定）
    prep = client.post(
        f"/api/v1/layouts/{layout['id']}/prepare-jobs",
        json={
            "projectId": pid,
            "layoutRef": {"id": layout["id"], "revision": layout["revision"]},
            "facilityRef": {"id": facility["id"], "revision": facility["revision"]},
            "sync": True,
        },
    )
    assert prep.status_code == 202, prep.text
    assert prep.json()["simulationReady"] is True

    demand = load("valid/fx-m3-demand-outbound.json")
    operating = load("valid/fx-m3-operating.json")
    client.post("/api/v1/demands", json={"projectId": pid, "demand": demand})
    client.post("/api/v1/operating-profiles", json={"projectId": pid, "operating": operating})
    scenario = load("valid/fx-m3-scenario-package.json")
    sim = client.post(
        "/api/v1/simulation-jobs",
        json={
            "projectId": pid,
            "variantRef": {"id": variant["id"], "revision": variant["revision"]},
            "scenarioPackage": scenario,
            "demand": demand,
            "operating": operating,
            "expectedLayoutRevision": layout["revision"],
        },
    )
    assert sim.status_code == 202, sim.text
    run_id = sim.json()["runId"]
    assert sim.json()["layoutRevision"] == layout["revision"]

    pb_ok = load("valid/fx-m4-price-book-complete.json")
    pb_miss = load("valid/fx-m4-price-book-missing.json")
    basis = load("valid/fx-m4-cost-basis.json")
    profile = load("valid/fx-m4-score-profile.json")
    client.post("/api/v1/price-books", json={"projectId": pid, "priceBook": pb_ok})
    client.post("/api/v1/price-books", json={"projectId": pid, "priceBook": pb_miss})
    client.post("/api/v1/cost-bases", json={"projectId": pid, "costBasis": basis})
    client.post("/api/v1/score-profiles", json={"projectId": pid, "scoreProfile": profile})

    # 第二布局（缺价书对应同一布局结构，用于 incomplete）
    layout_b = deepcopy(layout)
    layout_b["id"] = "layout-doc-fx-m4-b"
    layout_b["revision"] = "ld-m4-b1"
    # 略增容量：多一层
    layout_b["elements"][0]["params"]["levels"] = 5
    client.post(
        f"/api/v1/layouts/{layout_b['id']}/revisions",
        json={"projectId": pid, "baseRevision": None, "document": layout_b},
    )
    variant_b = client.post(
        f"/api/v1/projects/{pid}/variants",
        json={
            "name": "方案 B（缺价）",
            "source": "manual",
            "layoutRef": {"id": layout_b["id"], "revision": layout_b["revision"]},
        },
    ).json()
    client.post(
        f"/api/v1/layouts/{layout_b['id']}/prepare-jobs",
        json={
            "projectId": pid,
            "layoutRef": {"id": layout_b["id"], "revision": layout_b["revision"]},
            "facilityRef": {"id": facility["id"], "revision": facility["revision"]},
            "sync": True,
        },
    )

    est_a = client.post(
        "/api/v1/cost-estimate-jobs",
        json={
            "projectId": pid,
            "variantRef": {"id": variant["id"], "revision": variant["revision"]},
            "priceBookRef": {"id": pb_ok["id"], "revision": pb_ok["revision"]},
            "costBasisRef": {"id": basis["id"], "revision": basis["revision"]},
            "operatingRef": {"id": operating["id"], "revision": operating["revision"]},
        },
    )
    assert est_a.status_code == 202, est_a.text
    assert est_a.json()["status"] == "complete"
    assert est_a.json()["eligibleForLowestCostRanking"] is True
    id_a = est_a.json()["costEstimateId"]

    est_b = client.post(
        "/api/v1/cost-estimate-jobs",
        json={
            "projectId": pid,
            "variantRef": {"id": variant_b["id"], "revision": variant_b["revision"]},
            "priceBookRef": {"id": pb_miss["id"], "revision": pb_miss["revision"]},
            "costBasisRef": {"id": basis["id"], "revision": basis["revision"]},
            "operatingRef": {"id": operating["id"], "revision": operating["revision"]},
        },
    )
    assert est_b.status_code == 202, est_b.text
    assert est_b.json()["status"] == "incomplete"
    assert est_b.json()["eligibleForLowestCostRanking"] is False
    assert est_b.json()["totals"]["total"] is None
    id_b = est_b.json()["costEstimateId"]

    rank = client.post(
        "/api/v1/cost-ranking",
        json={"projectId": pid, "costEstimateIds": [id_b, id_a]},
    ).json()
    assert rank["winner"]["estimateId"] == id_a
    assert any(x["estimateId"] == id_b for x in rank["excluded"])

    cmp_res = client.post(
        "/api/v1/comparisons",
        json={
            "projectId": pid,
            "mode": "layout_only",
            "commonBasis": {
                "demandRef": {"id": demand["id"], "revision": demand["revision"]},
                "engineVersion": "m3-des-0.1",
            },
            "scoreProfileRef": {"id": profile["id"], "revision": profile["revision"]},
            "entries": [
                {
                    "entryId": "a",
                    "label": "A",
                    "variantRef": {"id": variant["id"], "revision": variant["revision"]},
                    "layoutRef": {"id": layout["id"], "revision": layout["revision"]},
                    "runId": run_id,
                    "costEstimateId": id_a,
                    "operatingRef": {"id": operating["id"], "revision": operating["revision"]},
                    "completedCycleMeanSec": 120,
                },
                {
                    "entryId": "b",
                    "label": "B",
                    "variantRef": {"id": variant_b["id"], "revision": variant_b["revision"]},
                    "layoutRef": {"id": layout_b["id"], "revision": layout_b["revision"]},
                    "costEstimateId": id_b,
                    "operatingRef": {"id": operating["id"], "revision": operating["revision"]},
                    "completedCycleMeanSec": 110,
                },
            ],
        },
    )
    assert cmp_res.status_code == 201, cmp_res.text
    body = cmp_res.json()
    comparison = body["comparison"]
    assert comparison["mode"] == "layout_only"
    # B 缺价 → 投资轴 missing → 雷达关闭
    assert comparison["radar"]["radarEnabled"] is False
    assert body["recommendations"]["lowestCapex"]["winner"]["estimateId"] == id_a

    # whole_solution + 加人
    extra = load("valid/fx-m4-operating-extra-labor.json")
    client.post("/api/v1/operating-profiles", json={"projectId": pid, "operating": extra})
    cmp_ws = client.post(
        "/api/v1/comparisons",
        json={
            "projectId": pid,
            "mode": "whole_solution",
            "commonBasis": {},
            "scoreProfileRef": {"id": profile["id"], "revision": profile["revision"]},
            "entries": [
                {
                    "entryId": "a",
                    "label": "A",
                    "variantRef": {"id": variant["id"], "revision": variant["revision"]},
                    "layoutRef": {"id": layout["id"], "revision": layout["revision"]},
                    "costEstimateId": id_a,
                    "operatingRef": {"id": operating["id"], "revision": operating["revision"]},
                    "effectiveCapacity": 8,
                    "completedCycleMeanSec": 120,
                },
                {
                    "entryId": "extra",
                    "label": "加人",
                    "variantRef": {"id": variant["id"], "revision": variant["revision"]},
                    "layoutRef": {"id": layout["id"], "revision": layout["revision"]},
                    "costEstimateId": id_a,
                    "operatingRef": {"id": extra["id"], "revision": extra["revision"]},
                    "effectiveCapacity": 8,
                    "completedCycleMeanSec": 90,
                },
            ],
        },
    )
    assert cmp_ws.status_code == 201, cmp_ws.text
    assert cmp_ws.json()["comparison"]["comparability"]["comparable"] is True

    rpt = client.post(
        "/api/v1/reports",
        json={
            "projectId": pid,
            "variantRef": {"id": variant["id"], "revision": variant["revision"]},
            "layoutRef": {"id": layout["id"], "revision": layout["revision"]},
            "runId": run_id,
            "costEstimateId": id_a,
            "comparisonId": comparison["id"],
        },
    )
    assert rpt.status_code == 201, rpt.text
    assert rpt.json()["versionConsistent"] is True
    assert layout["revision"] in rpt.json()["html"]
    assert run_id in rpt.json()["html"]

    # 错误 revision 应失败
    bad = client.post(
        "/api/v1/reports",
        json={
            "projectId": pid,
            "variantRef": {"id": variant["id"], "revision": variant["revision"]},
            "layoutRef": {"id": layout["id"], "revision": "NOT-THE-RUN"},
            "runId": run_id,
            "costEstimateId": id_a,
        },
    )
    # layout 不存在 → 404；或存在但不一致 → mismatch
    assert bad.status_code in {404, 422}
    print("OK API e2e: cost/compare/report bound to historical revision")


def test_select_radar_helper() -> None:
    r = select_radar_axes(
        [
            {"storage": "available", "efficiency": "available", "investment": "missing"},
            {"storage": "available", "efficiency": "available", "investment": "available"},
        ]
    )
    assert r["radarEnabled"] is False
    assert "investment" not in r["commonAxes"]
    print("OK radar helper")


def main() -> int:
    tests = [
        test_cost_missing_price_blocks_ranking,
        test_reuse_vs_purchase_no_double_count,
        test_radar_missing_axis_no_zero,
        test_layout_only_vs_whole_solution,
        test_report_version_consistency,
        test_select_radar_helper,
        test_api_e2e,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}", file=sys.stderr)
            import traceback

            traceback.print_exc()
    if failed:
        print(f"\n{failed}/{len(tests)} failed", file=sys.stderr)
        return 1
    print(f"\nAll {len(tests)} M4 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
