"""Run a G-EDGE / G-BREAK fixture against the slice engine and check its asserts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from des.engine import run_des
from des.errors import DesError

GOLD = Path(__file__).resolve().parents[1] / "fixtures" / "gold"


def _initial_rows(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return list(raw)
    rows: List[Dict[str, Any]] = []
    if not isinstance(raw, dict):
        return rows
    for loc, val in raw.items():
        if isinstance(val, dict):
            pallets = float(val.get("pallets") or 0)
            cases = float(val.get("cases") or 0)
        else:
            pallets = float(val or 0)
            cases = 0.0
        if pallets > 0:
            rows.append({"locationInstanceId": loc, "quantity": pallets, "unit": "pallet"})
        if cases > 0:
            rows.append({"locationInstanceId": loc, "quantity": cases, "unit": "case"})
    return rows


def run_fixture(fixture: Dict[str, Any]) -> Dict[str, Any]:
    scenario = fixture["scenario"]
    resources = scenario.get("resources") or []
    speed = resources[0] if resources else {}
    defaults = ((fixture.get("layoutSnapshot") or {}).get("defaults") or {}).get("processSec") or {}
    return run_des(
        snapshot=fixture["layoutSnapshot"],
        demand={
            "flows": [],
            "initialInventory": _initial_rows(scenario.get("initialInventory")),
            "arrivalProfile": {"windowSec": 1},
        },
        operating={
            "resourcePools": [],
            "serviceParameters": {
                "travelSpeedMps": float(speed.get("travelSpeedMps") or 1),
                "emptySpeedMps": float(speed.get("emptySpeedMps") or 1),
                "processSec": dict(defaults),
            },
        },
        run_control={
            "horizonSec": float(scenario["horizonSec"]),
            "seedStreams": {"demand": scenario.get("seed") or 1},
            "metricDefinitionVersion": "metrics-slice-manual-v1",
        },
        expected_layout_revision=scenario["expectedLayoutRevision"],
        run_id=f"run-{fixture['fixtureId'].lower()}",
        direct={
            "resources": resources,
            "tasks": scenario.get("tasks") or [],
            "casesPerPallet": scenario.get("casesPerPallet"),
            "downstream": (
                "run"
                if scenario.get("downstreamPiecePick") == "run"
                else bool(scenario.get("downstreamPiecePick"))
            ),
        },
    )


def _events(result: Dict[str, Any], kind: str, edge_id: str) -> List[Dict[str, Any]]:
    return [event for event in result["events"] if event.get("kind") == kind and event.get("edgeId") == edge_id]


def evaluate(fixture: Dict[str, Any]) -> List[str]:
    """Return human-readable failures. Empty means this fixture's asserts passed."""
    expected = fixture.get("expected") or {}
    problems: List[str] = []
    if fixture.get("status") != "measured_pass":
        problems.append(f"status 仍是 {fixture.get('status')}，工程实测前不得保持 spec_only")
    measured = fixture.get("measured") or {}
    if measured.get("kpiAcAllGreen") is not False:
        problems.append("measured.kpiAcAllGreen 必须显式为 false")
    if str(fixture.get("fixtureId", "")).startswith("G-BREAK") and measured.get("d1AllFlows") is not False:
        problems.append("measured.d1AllFlows 必须显式为 false")
    try:
        result = run_fixture(fixture)
    except DesError as exc:
        if expected.get("mustReject"):
            if exc.code != expected.get("rejectReasonCode"):
                problems.append(f"拒载码 {exc.code}，期望 {expected.get('rejectReasonCode')}")
            needle = expected.get("rejectMessageContains")
            if needle and needle not in exc.message:
                problems.append(f"人话不含 {needle!r}：{exc.message}")
            if fixture.get("fixtureId") == "G-TURN-02":
                problems.extend(_straight_turn_still_runs(fixture))
            return problems
        problems.append(f"推演失败 {exc.code} {exc.message}")
        return problems
    if expected.get("mustReject"):
        problems.append("期望拒载，但推演完成了")
        return problems
    conservation = result["inventoryConservation"]
    if expected.get("conservationOk") and not conservation.get("ok"):
        problems.append(f"conservation 不成立 {conservation}")
    _check_edges(fixture, result, problems)
    _check_break(fixture, result, problems)
    _check_pick(fixture, result, problems)
    _check_motion(fixture, result, problems)
    return problems


def _check_edges(fixture: Dict[str, Any], result: Dict[str, Any], problems: List[str]) -> None:
    expected = fixture["expected"]
    waits = result.get("edgeWaits") or []
    segments = result["trajectory"]["segments"]
    for spec in expected.get("edgeWaits") or []:
        edge_id = spec["edgeId"]
        rows = [row for row in waits if row["edgeId"] == edge_id]
        if "minWaitersWithPositiveWait" in spec:
            positive = {row["resourceId"] for row in rows if float(row["edgeWaitSec"]) > 1e-9}
            if len(positive) < int(spec["minWaitersWithPositiveWait"]):
                problems.append(f"{edge_id} 正等待资源 {len(positive)}，期望 ≥ {spec['minWaitersWithPositiveWait']}")
        if spec.get("allEdgeWaitSec") == 0:
            if not rows:
                problems.append(f"{edge_id} 没有占用记录")
            bad = [row for row in rows if abs(float(row["edgeWaitSec"])) > 1e-9]
            if bad:
                problems.append(f"{edge_id} 仍有边等待 {bad}")
    if expected.get("overlapAllowed"):
        edge_id = (expected.get("edgeWaits") or [{}])[0].get("edgeId")
        segs = [seg for seg in segments if seg.get("edgeId") == edge_id]
        hit = False
        for i, left in enumerate(segs):
            for right in segs[i + 1 :]:
                if left["t0"] < right["t1"] - 1e-9 and right["t0"] < left["t1"] - 1e-9:
                    hit = True
        if not hit:
            problems.append(f"{edge_id} 没有重叠占用窗口")
    ordering = expected.get("segmentOrdering")
    if ordering:
        edge_id = ordering["edgeId"]
        segs = sorted((seg for seg in segments if seg.get("edgeId") == edge_id), key=lambda seg: (seg["t0"], seg["t1"]))
        for prev, nxt in zip(segs, segs[1:]):
            if nxt["t0"] + 1e-9 < prev["t1"]:
                problems.append(f"{edge_id} 后车 t0={nxt['t0']} < 前车 t1={prev['t1']}")
    contains = expected.get("bottleneckTopContains") or []
    top = [row["entityId"] for row in result["cards"]["bottleneck"]["topN"]]
    for entity in contains:
        if entity not in top:
            problems.append(f"瓶颈 Top 不含 {entity}，实际 {top}")
    fifo = expected.get("fifoWakeOrder")
    if fifo:
        edge_id = fifo["edgeId"]
        reqs = _events(result, "occupy_request", edge_id)
        grants = _events(result, "occupy_grant", edge_id)
        releases = _events(result, "occupy_release", edge_id)
        if [event["resourceId"] for event in grants] != [event["resourceId"] for event in reqs]:
            problems.append(
                "FIFO 不一致 "
                + str([event["resourceId"] for event in reqs])
                + " -> "
                + str([event["resourceId"] for event in grants])
            )
        if expected.get("thirdWaitsUntilSecondRelease") and len(reqs) >= 3:
            second = reqs[1]["resourceId"]
            third = reqs[2]["resourceId"]
            rel = next(event["t"] for event in releases if event["resourceId"] == second)
            grant = next(event["t"] for event in grants if event["resourceId"] == third)
            if grant + 1e-9 < rel:
                problems.append(f"第三车 grant {grant} 早于第二车 release {rel}")
    if fixture["fixtureId"].startswith("G-EDGE"):
        for task_id in {seg["taskId"] for seg in segments}:
            chain = [seg["from"] for seg in sorted((s for s in segments if s["taskId"] == task_id), key=lambda s: s["t0"])]
            last = [seg for seg in segments if seg["taskId"] == task_id]
            if last:
                chain.append(sorted(last, key=lambda s: s["t0"])[-1]["to"])
            if chain != ["N_home", "N_mid_a", "N_mid_b", "N_ship"]:
                problems.append(f"{task_id} 路径被改写 {chain}")


def _check_break(fixture: Dict[str, Any], result: Dict[str, Any], problems: List[str]) -> None:
    if not str(fixture.get("fixtureId", "")).startswith("G-BREAK"):
        return
    expected = fixture["expected"]
    tasks = {row["taskId"]: row for row in result["trajectory"]["tasks"]}
    for task_id, status in (expected.get("taskStatus") or {}).items():
        got = (tasks.get(task_id) or {}).get("status")
        if got != status:
            problems.append(f"{task_id} 状态 {got}，期望 {status}")
    conservation = result["inventoryConservation"]
    spec = expected.get("conservation") or {}
    for loc, delta in (spec.get("palletsDelta") or {}).items():
        initial = _pallet_initial(fixture, loc)
        ending = float((conservation.get("onHand") or {}).get(loc) or 0)
        if abs((ending - initial) - float(delta)) > 1e-6:
            problems.append(f"{loc} 托盘变化 {ending - initial}，期望 {delta}")
    if "casesCreated" in spec and abs(float(conservation.get("casesCreated") or 0) - float(spec["casesCreated"])) > 1e-6:
        problems.append(f"箱数 {conservation.get('casesCreated')}，期望 {spec['casesCreated']}")
    if not conservation.get("ok"):
        problems.append(f"conservation 不成立 {conservation}")
    if expected.get("flowKindUnsupportedForbidden"):
        if any(event.get("kind") == "UNSUPPORTED_SCENARIO" for event in result["events"]):
            problems.append("仍然走了 UNSUPPORTED")
    busy_min = expected.get("stationBusySecMin")
    if busy_min is not None:
        busy = sum(float(row["t1"]) - float(row["t0"]) for row in result.get("stationWindows") or [])
        if busy + 1e-6 < float(busy_min):
            problems.append(f"工位占用 {busy}s，期望 ≥ {busy_min}")
    generated = expected.get("downstreamGenerated")
    if generated:
        kids = [row for row in result.get("piecePickTasks") or [] if row.get("flowKind") == generated["flowKind"]]
        total = sum(float(row.get("qtyCases") or 0) for row in kids)
        if len(kids) < int(generated["minTaskCount"]):
            problems.append(f"下游箱任务 {len(kids)}，期望 ≥ {generated['minTaskCount']}")
        if abs(total - float(generated["totalCases"])) > 1e-6:
            problems.append(f"下游箱数 {total}，期望 {generated['totalCases']}")
        if any(row.get("parentTaskId") != generated["parentTaskId"] for row in kids):
            problems.append("下游任务 parentTaskId 不对")
    serial = expected.get("stationSerialize")
    if serial:
        windows = [row for row in result.get("stationWindows") or [] if row["stationId"] == serial["stationId"]]
        windows.sort(key=lambda row: (row["t0"], row["t1"]))
        if len(windows) < 2:
            problems.append(f"{serial['stationId']} 工位窗口不足")
        else:
            for prev, nxt in zip(windows, windows[1:]):
                if nxt["t0"] + 1e-9 < prev["t1"]:
                    problems.append(f"工位窗口重叠 {prev} {nxt}")
                if float(nxt.get("waitSec") or 0) <= 1e-9 and nxt["t0"] + 1e-9 < prev["t1"]:
                    problems.append("后一托没有等到前一托结束")


def _near(got: Any, want: float, label: str, problems: List[str]) -> None:
    if got is None or abs(float(got) - float(want)) > 1e-6:
        problems.append(f"{label} {got}，期望 {want}")


def _check_pick(fixture: Dict[str, Any], result: Dict[str, Any], problems: List[str]) -> None:
    if not str(fixture.get("fixtureId", "")).startswith("G-PICK"):
        return
    expected = fixture["expected"]
    tasks = {row["taskId"]: row for row in result["trajectory"]["tasks"]}
    for task_id, status in (expected.get("taskStatus") or {}).items():
        got = (tasks.get(task_id) or {}).get("status")
        if got != status:
            problems.append(f"{task_id} 状态 {got}，期望 {status}")
    cards = result["cards"]
    _near(cards["wait"]["meanSec"], expected["waitMeanSec"], "等待均值", problems)
    _near(cards["wait"]["p95Sec"], expected["waitP95Sec"], "等待 P95", problems)
    _near(cards["throughput"]["outboundPalletEq"], expected["palletEq"], "托当量", problems)
    _near(result["inventoryConservation"].get("casesShipped"), expected["casesShipped"], "发出箱数", problems)
    picker_busy = sum(float(row["busySec"]) for row in result["resources"] if row["resourceType"] == "picker")
    forklift_busy = sum(float(row["busySec"]) for row in result["resources"] if row["resourceType"] == "forklift")
    _near(picker_busy, expected["pickerBusySec"], "拣货人占用秒", problems)
    if "forkliftBusySec" in expected:
        _near(forklift_busy, expected["forkliftBusySec"], "叉车占用秒", problems)
    if cards["throughput"]["value"] not in (0, 0.0):
        problems.append(f"箱作业把托盘吞吐写成了 {cards['throughput']['value']}")
    if not result["trajectory"]["segments"]:
        problems.append("没有拣选轨迹")
    if not any(row["resourceType"] == "picker" and float(row["utilization"] or 0) > 0 for row in cards["utilization"]["byResourceType"]):
        problems.append("拣货人利用率仍是 0")


def _pallet_initial(fixture: Dict[str, Any], loc: str) -> float:
    raw = (fixture.get("scenario") or {}).get("initialInventory") or {}
    val = raw.get(loc)
    if isinstance(val, dict):
        return float(val.get("pallets") or 0)
    if val is None:
        return 0.0
    return float(val)


def _path_nodes(result: Dict[str, Any], task_id: str) -> List[str]:
    segs = sorted(
        (seg for seg in result["trajectory"]["segments"] if seg.get("taskId") == task_id and seg.get("from")),
        key=lambda seg: (seg["t0"], seg["t1"]),
    )
    if not segs:
        return []
    chain = [seg["from"] for seg in segs]
    chain.append(segs[-1]["to"])
    return chain


def _check_motion(fixture: Dict[str, Any], result: Dict[str, Any], problems: List[str]) -> None:
    if not str(fixture.get("fixtureId", "")).startswith(("G-WAY", "G-TURN")):
        return
    expected = fixture["expected"]
    cards = result["cards"]
    _near(cards["wait"]["meanSec"], expected["waitMeanSec"], "等待均值", problems)
    _near(cards["wait"]["p95Sec"], expected["waitP95Sec"], "等待 P95", problems)
    _near(cards["throughput"]["value"], expected["throughput"], "吞吐", problems)
    _near(cards["throughput"]["outboundPalletEq"], expected["palletEq"], "托当量", problems)
    busy = sum(float(row["busySec"]) for row in result["resources"] if row["resourceType"] == "forklift")
    _near(busy, expected["forkliftBusySec"], "叉车占用秒", problems)
    task_id = expected.get("taskId") or "T1"
    nodes = _path_nodes(result, task_id)
    if nodes != expected.get("pathNodes"):
        problems.append(f"路径 {nodes}，期望 {expected.get('pathNodes')}")
    status = next((row.get("status") for row in result["trajectory"]["tasks"] if row.get("taskId") == task_id), None)
    if status != "done":
        problems.append(f"{task_id} 状态 {status}")


def _straight_turn_still_runs(fixture: Dict[str, Any]) -> List[str]:
    """Same radius on a straight aisle is not a turn."""
    from copy import deepcopy

    clone = deepcopy(fixture)
    clone["fixtureId"] = "G-TURN-02-straight"
    for el in clone["layoutSnapshot"]["elements"]:
        if el.get("elementId") == "N_ship":
            el["pose"] = {"x": 20, "y": 0}
    try:
        result = run_fixture(clone)
    except DesError as exc:
        return [f"直道不应因转向半径拒载 {exc.code} {exc.message}"]
    problems: List[str] = []
    _near(result["cards"]["throughput"]["value"], 6, "直道吞吐", problems)
    busy = sum(float(row["busySec"]) for row in result["resources"] if row["resourceType"] == "forklift")
    _near(busy, 20, "直道叉车占用秒", problems)
    if _path_nodes(result, "T1") != ["N_home", "N_corner", "N_ship"]:
        problems.append(f"直道路径 {_path_nodes(result, 'T1')}")
    return problems


def load_fixtures() -> List[Dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(GOLD.glob("G-*.json"))]


def run_suite() -> int:
    failures = 0
    print("command: PYTHONPATH=next python3 next/scripts/run_gold.py")
    for fixture in load_fixtures():
        problems = evaluate(fixture)
        label = fixture["fixtureId"]
        honesty = (fixture.get("expected") or {}).get("kpiHonesty") or ""
        if problems:
            failures += len(problems)
            print("FAIL", label)
            for problem in problems:
                print("  ", problem)
        else:
            print("PASS", label)
        if honesty:
            print("  ", honesty)
    print("failures", failures)
    return 1 if failures else 0
