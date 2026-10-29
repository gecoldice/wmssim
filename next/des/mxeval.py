"""MX-D1/D2/D3-EB against template.mixed_wh_v0.

Assert pass is not a fixture status change. These files stay spec_only.
That is not UA S-D1, not three-flow D1, and not a substitute for G-EDGE/G-BREAK.
"""

from __future__ import annotations

import json
import math
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple

from des.derive import derive_snapshot
from des.engine import run_des
from des.errors import DesError

ROOT = Path(__file__).resolve().parents[2]
MX = Path(__file__).resolve().parents[1] / "fixtures" / "mx"
REVISION = "mx-wh-rev-eb"


def _load(name: str) -> Dict[str, Any]:
    return json.loads((MX / name).read_text(encoding="utf-8"))


def _honesty(fixture: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    if fixture.get("status") != "spec_only":
        problems.append(f"status 必须保持 spec_only，实际 {fixture.get('status')}")
    measured = fixture.get("measured") or {}
    for key in ("kpiAcAllGreen", "d1AllFlows", "sD1UaPass", "miniGoldSubstitutesMx"):
        if measured.get(key) is not False:
            problems.append(f"measured.{key} 必须显式为 false")
    return problems


def _finite(value: Any, label: str, problems: List[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        problems.append(f"{label} 不是有限数：{value}")


def _capacity(layout: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    layout = deepcopy(layout)
    found = False
    for el in layout.get("elements") or []:
        if el.get("instanceId") == override.get("instanceId"):
            el.setdefault("params", {})["palletsPerBay"] = override["palletsPerBay"]
            found = True
    if not found:
        raise RuntimeError(f"capacity override missed {override.get('instanceId')}")
    return layout


def build_snapshot(fixture: Dict[str, Any]) -> Dict[str, Any]:
    layout = _capacity(_load(fixture["layoutFile"]), fixture["capacityOverride"])
    facility = _load(fixture["facilityFile"])
    return derive_snapshot(layout, facility, layout_revision=fixture["layoutRevision"])


def _demand(scenario: Dict[str, Any]) -> Dict[str, Any]:
    flows = scenario["flows"]
    pallet_qty = int(flows["full_pallet"]) + int(flows["break_bulk"])
    goods = {
        "id": "gg-std-pallet",
        "loadUnit": "pallet",
        "dimensionsM": {"length": 1.2, "width": 1.0, "height": 1.5},
        "grossWeightKg": 800,
        "stackability": "stackable",
        "allowedStorageTypes": ["ST-PAL-01"],
        "quantityUnit": "pallet",
        "evidence": {
            "sourceKind": "manual",
            "sourceRef": "mx-eb",
            "confirmationStatus": "confirmed",
            "updatedAt": "2026-10-29T00:00:00+00:00",
        },
    }
    return {
        "contractVersion": "0.3",
        "id": "demand-mx-eb",
        "revision": "fixture",
        "parentRef": None,
        "goodsGroups": [goods],
        "inventoryTargets": [{"goodsGroupId": "gg-std-pallet", "quantity": pallet_qty, "unit": "pallet"}],
        "initialInventory": [
            {
                "goodsGroupId": "gg-std-pallet",
                "quantity": pallet_qty,
                "unit": "pallet",
                "locationInstanceId": "rack-001",
            }
        ],
        "flows": [
            {
                "flowKind": "full_pallet",
                "intent": "outbound",
                "inputBasis": "explicit_quantity",
                "quantity": flows["full_pallet"],
                "unit": "pallet",
                "source": "storage",
                "downstream": None,
                "conversionRef": None,
                "parentFlowId": None,
            },
            {
                "flowKind": "break_bulk",
                "intent": "outbound",
                "inputBasis": "explicit_quantity",
                "quantity": flows["break_bulk"],
                "unit": "pallet",
                "source": "storage",
                "downstream": None,
                "conversionRef": None,
                "parentFlowId": None,
            },
            {
                "flowKind": "piece_pick",
                "intent": "outbound",
                "inputBasis": "explicit_quantity",
                "quantity": flows["piece_pick"],
                "unit": "pallet",
                "source": "storage",
                "downstream": {"mode": "generate_only"},
                "conversionRef": None,
                "parentFlowId": None,
            },
        ],
        "arrivalProfile": {
            "kind": "uniform",
            "windowSec": scenario["windowSec"],
            "unit": "pallet",
            "paramsSource": "mx-eb-fixture",
        },
        "serviceTargets": [],
        "assumptions": [
            "夹具输入，不是项目默认值，也不是业务接量结论",
            scenario.get("windowNote") or "",
        ],
    }


def _operating(scenario: Dict[str, Any], forklifts: int) -> Dict[str, Any]:
    speeds = scenario["speeds"]
    horizon = float(scenario["horizonSec"])
    return {
        "contractVersion": "0.3",
        "id": "op-mx-eb",
        "revision": "fixture",
        "parentRef": None,
        "resourcePools": [
            {
                "id": "pool-forklift",
                "resourceType": "forklift",
                "count": forklifts,
                "capabilityRef": "cap-forklift-mx-eb",
                "availableWindowSec": horizon,
                "homeInstanceIds": [],
            }
        ],
        "serviceParameters": {
            "travelSpeedMps": speeds["travelSpeedMps"],
            "emptySpeedMps": speeds["emptySpeedMps"],
            "processSec": {
                "pick": speeds["pick"],
                "ship": speeds["ship"],
                "break_bulk": speeds["break_bulk"],
            },
            "casesPerPallet": scenario["casesPerPallet"],
            "paramsSource": "mx-eb-fixture",
        },
        "routingPolicy": {"kind": "shortest_path"},
        "shiftWindow": {"startSec": 0, "endSec": horizon},
    }


def _control(scenario: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "horizonSec": scenario["horizonSec"],
        "seedStreams": {"demand": scenario["seed"]},
        "metricDefinitionVersion": "metrics-slice-manual-v1",
    }


def run_case(snapshot: Dict[str, Any], scenario: Dict[str, Any], forklifts: int, revision: str, run_id: str) -> Dict[str, Any]:
    return run_des(
        snapshot=snapshot,
        demand=_demand(scenario),
        operating=_operating(scenario, forklifts),
        run_control=_control(scenario),
        expected_layout_revision=revision,
        run_id=run_id,
    )


def _check_cards(result: Dict[str, Any], problems: List[str]) -> None:
    if result.get("kpiFromUiDemo") is not False:
        problems.append("kpiFromUiDemo 不是 false")
    cards = result["cards"]
    _finite(cards["throughput"]["value"], "throughput.value", problems)
    _finite(cards["wait"]["meanSec"], "wait.meanSec", problems)
    _finite(cards["wait"]["p95Sec"], "wait.p95Sec", problems)
    for row in cards["utilization"]["byResourceType"]:
        _finite(row["utilization"], f"util {row.get('resourceType')}", problems)
    for row in cards["utilization"]["byResource"]:
        _finite(row["utilization"], f"util {row.get('resourceId')}", problems)
    for row in cards["bottleneck"]["topN"]:
        _finite(row["waitSec"], f"bottleneck {row.get('entityId')}", problems)
        _finite(row["share"], f"share {row.get('entityId')}", problems)


def _edge_ids(snapshot: Dict[str, Any]) -> set:
    return {edge["edgeId"] for edge in snapshot.get("edges") or []}


def evaluate_d1(fixture: Dict[str, Any], snapshot: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    problems = _honesty(fixture)
    if not fixture.get("edgeOccupancy", {}).get("enabled"):
        problems.append("edgeOccupancy.enabled 必须为 true")
    if fixture.get("scenario", {}).get("piecePick") != "generate_only":
        problems.append("piece_pick 必须是 generate_only")
    caps = {edge.get("maxConcurrent") for edge in snapshot.get("edges") or []}
    if not caps or any(cap is None or int(cap) < 1 for cap in caps):
        problems.append(f"派生边缺 maxConcurrent：{caps}")
    stations = [
        el["elementId"]
        for el in snapshot["elements"]
        if el.get("kind") == "station" and "break_bulk" in (el.get("labels") or [])
    ]
    if "depal-001" not in stations:
        problems.append(f"样例仓没有拆托站标签：{stations}")
    result: Dict[str, Any] = {}
    try:
        result = run_case(snapshot, fixture["scenario"], int(fixture["scenario"]["forklifts"]), fixture["layoutRevision"], "run-mx-d1")
    except DesError as exc:
        problems.append(f"D1 拒载 {exc.code} {exc.message}")
        return problems, result
    conservation = result["inventoryConservation"]
    if not conservation.get("ok"):
        problems.append(f"conservation 不成立 {conservation}")
    cases_per = float(fixture["scenario"]["casesPerPallet"])
    converted = float(conservation.get("converted") or 0)
    cases = float(conservation.get("casesCreated") or 0)
    if abs(cases - converted * cases_per) > 1e-6:
        problems.append(f"换箱 {cases}，期望 {converted}×{cases_per}")
    kinds = {event["kind"] for event in result["events"]}
    if "occupy_request" not in kinds or "occupy_grant" not in kinds:
        problems.append(f"缺 occupy 事件 {sorted(kinds)}")
    if not result["trajectory"]["segments"]:
        problems.append("segments 为空")
    _check_cards(result, problems)
    pieces = result.get("piecePickTasks") or []
    if not pieces:
        problems.append("没有生成箱任务")
    if any(row.get("status") == "done" for row in pieces):
        problems.append("箱任务被跑成 done")
    done_break = [
        row
        for row in result["trajectory"]["tasks"]
        if row.get("direction") == "break_bulk" and row.get("status") == "done"
    ]
    if len(done_break) != int(fixture["scenario"]["flows"]["break_bulk"]):
        problems.append(f"拆托完成 {len(done_break)}")
    if len(pieces) != len(done_break):
        problems.append(f"箱任务 {len(pieces)} 与完成拆托 {len(done_break)} 不一致")
    positive = [row for row in result.get("edgeWaits") or [] if float(row["edgeWaitSec"]) > 1e-9]
    edge_ids = _edge_ids(snapshot)
    top_edges = [row["entityId"] for row in result["cards"]["bottleneck"]["topN"] if row["entityId"] in edge_ids]
    if not positive:
        problems.append("没有正的边等待")
    if not top_edges:
        problems.append(f"瓶颈不含通道边 {[row['entityId'] for row in result['cards']['bottleneck']['topN']]}")
    return problems, result


def evaluate_d2(fixture: Dict[str, Any], snapshot: Dict[str, Any], d1: Dict[str, Any]) -> List[str]:
    problems = _honesty(fixture)
    if fixture.get("sameRevisionAs") != "MX-D1-EB":
        problems.append("D2 必须声明同一 layoutRevision")
    counts = fixture.get("forklifts") or []
    if counts != [3, 2]:
        problems.append(f"叉车差分必须是 3→2，实际 {counts}")
    scenario = d1["scenario"]
    runs: Dict[int, Dict[str, Any]] = {}
    for count in counts:
        try:
            runs[count] = run_case(snapshot, scenario, int(count), d1["layoutRevision"], f"run-mx-d2-{count}")
        except DesError as exc:
            problems.append(f"{count} 台拒载 {exc.code} {exc.message}")
    if len(runs) != 2:
        return problems
    left, right = runs[3], runs[2]
    if left["layoutRevision"] != right["layoutRevision"]:
        problems.append("两次 layoutRevision 不同")
    for label, result in (("3", left), ("2", right)):
        if not result["inventoryConservation"].get("ok"):
            problems.append(f"{label} 台 conservation 失败")
        _check_cards(result, problems)
    thr3 = left["cards"]["throughput"]["value"]
    thr2 = right["cards"]["throughput"]["value"]
    wait3 = left["cards"]["wait"]["meanSec"]
    wait2 = right["cards"]["wait"]["meanSec"]
    if thr3 == thr2 and wait3 == wait2:
        problems.append("吞吐和等待都无法区分")
    blob3 = json.dumps(left["cards"], sort_keys=True, ensure_ascii=False)
    blob2 = json.dumps(right["cards"], sort_keys=True, ensure_ascii=False)
    if blob3 == blob2:
        problems.append("四卡逐字段完全相同，且没有说明")
    edge_ids = _edge_ids(snapshot)
    def edge_positive(result: Dict[str, Any]) -> int:
        return sum(1 for row in result.get("edgeWaits") or [] if float(row["edgeWaitSec"]) > 1e-9 and row["edgeId"] in edge_ids)
    print(
        f"  口述差分 叉车3 吞吐={thr3} 等待均值={wait3} 边正等待={edge_positive(left)}；"
        f"叉车2 吞吐={thr2} 等待均值={wait2} 边正等待={edge_positive(right)}"
    )
    print("  吞吐相同只表示外部发运托数/8h 相同；等待均值和边等待不同。这不是业务接量结论。")
    return problems


def _mutate(snapshot: Dict[str, Any], kind: str) -> str:
    if kind == "revision":
        return REVISION + "-mismatch"
    if kind == "strip-break-station":
        snapshot["elements"] = [
            el for el in snapshot["elements"] if "break_bulk" not in (el.get("labels") or [])
        ]
    elif kind == "strip-access":
        for el in snapshot["elements"]:
            if el.get("elementId") == "rack-001":
                el.pop("accessNodeId", None)
    elif kind == "drop-edges":
        snapshot["edges"] = []
    else:
        raise RuntimeError(kind)
    return REVISION


def evaluate_d3(fixture: Dict[str, Any], snapshot: Dict[str, Any], d1: Dict[str, Any]) -> List[str]:
    problems = _honesty(fixture)
    cases = fixture.get("cases") or []
    if len(cases) != 4:
        problems.append(f"D3 应有四案，实际 {len(cases)}")
    for case in cases:
        snap = deepcopy(snapshot)
        revision = _mutate(snap, case["mutate"])
        produced = None
        try:
            produced = run_case(snap, d1["scenario"], int(d1["scenario"]["forklifts"]), revision, f"run-mx-d3-{case['id']}")
        except DesError as exc:
            if exc.code != case["rejectReasonCode"]:
                problems.append(f"{case['id']} 码 {exc.code}，期望 {case['rejectReasonCode']}")
            else:
                print(f"  {case['id']} 加载即停 {exc.code}（无运行结果）")
            continue
        if produced is not None:
            problems.append(f"{case['id']} 产生了运行结果，四卡不应出现")
    return problems


def assert_template_bytes() -> List[str]:
    esbuild = ROOT / "next" / "web" / "node_modules" / "esbuild" / "bin" / "esbuild"
    script = ROOT / "next" / "web" / "scripts" / "export-mixed-layout.mjs"
    if not esbuild.exists():
        print("SKIP template byte check（没有 esbuild）")
        return []
    out = Path("/tmp/export-mixed-mxeval.mjs")
    bundle = subprocess.run(
        [str(esbuild), str(script), "--bundle", "--platform=node", "--format=esm", f"--outfile={out}"],
        cwd=ROOT / "next" / "web",
        text=True,
        capture_output=True,
        check=False,
    )
    if bundle.returncode != 0:
        return [f"导出模板失败 {bundle.stderr[-400:]}"]
    ran = subprocess.run(["node", str(out)], cwd=ROOT / "next" / "web", text=True, capture_output=True, check=False)
    if ran.returncode != 0:
        return [f"导出模板失败 {ran.stderr[-400:]}"]
    problems = []
    for name in ("layout-mixed-wh-v0.json", "facility-mixed.json"):
        fresh_name = "/tmp/mx-layout.json" if name.startswith("layout") else "/tmp/mx-facility.json"
        fresh = Path(fresh_name).read_bytes()
        committed = (MX / name).read_bytes()
        if fresh != committed:
            problems.append(f"{name} 与 template.mixed_wh_v0 现导出不一致")
    if not problems:
        print("template bytes match template.mixed_wh_v0")
    return problems


def run_suite() -> int:
    print("command: PYTHONPATH=next python3 next/scripts/run_mx.py")
    print("honesty: assert pass keeps status=spec_only; not UA S-D1; not three-flow D1; mini gold does not replace MX")
    failures = 0
    problems = assert_template_bytes()
    if problems:
        failures += len(problems)
        for problem in problems:
            print("FAIL template", problem)
    d1 = _load("MX-D1-EB.json")
    d2 = _load("MX-D2-EB.json")
    d3 = _load("MX-D3-EB.json")
    snapshot = build_snapshot(d1)
    print("derived", d1["layoutRevision"], "edges", len(snapshot["edges"]), "break", [
        el["elementId"] for el in snapshot["elements"] if "break_bulk" in (el.get("labels") or [])
    ])
    p1, result = evaluate_d1(d1, snapshot)
    if p1:
        failures += len(p1)
        print("FAIL", d1["fixtureId"])
        for problem in p1:
            print("  ", problem)
    else:
        cards = result["cards"]
        print("PASS", d1["fixtureId"], "status", d1["status"])
        print(
            "  observed throughput",
            cards["throughput"]["value"],
            "waitMean",
            cards["wait"]["meanSec"],
            "cases",
            result["inventoryConservation"]["casesCreated"],
            "segments",
            len(result["trajectory"]["segments"]),
        )
        print("  ", (d1.get("expected") or {}).get("kpiHonesty"))
    p2 = evaluate_d2(d2, snapshot, d1)
    if p2:
        failures += len(p2)
        print("FAIL", d2["fixtureId"])
        for problem in p2:
            print("  ", problem)
    else:
        print("PASS", d2["fixtureId"], "status", d2["status"])
        print("  ", (d2.get("expected") or {}).get("kpiHonesty"))
    p3 = evaluate_d3(d3, snapshot, d1)
    if p3:
        failures += len(p3)
        print("FAIL", d3["fixtureId"])
        for problem in p3:
            print("  ", problem)
    else:
        print("PASS", d3["fixtureId"], "status", d3["status"])
        print("  ", (d3.get("expected") or {}).get("kpiHonesty"))
    print("failures", failures)
    return 1 if failures else 0
