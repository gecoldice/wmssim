"""G-CV-01/02/03 and MX-D1-CV.

Assert pass does not change fixture status. These files stay spec_only.
That is not UA S-D1, not a substitute for MX-D1-EB, and not curve/merge/divert runtime.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple

from des.conveyor import LINEAR_TYPES
from des.errors import DesError
from des.gold import run_fixture
from des.mxeval import build_snapshot, run_case

CV = Path(__file__).resolve().parents[1] / "fixtures" / "conveyor"
REJECT_TYPES = (
    "CV-CURVE-01",
    "CV-MERGE-01",
    "CV-DIV-01",
    "CV-BUF-01",
    "CV-VERT-01",
    "CV-CHUTE-01",
    "CV-LOOP-01",
    "CV-INDUCT-EACH-01",
    "MH-AGV-01",
    "MH-CRANE-01",
    "ST-ASRS-01",
)


def _load(name: str) -> Dict[str, Any]:
    return json.loads((CV / name).read_text(encoding="utf-8"))


def _finite(value: Any, label: str, problems: List[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        problems.append(f"{label} 不是有限数：{value}")


def _honesty(fixture: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    if fixture.get("status") != "spec_only":
        problems.append(f"status 必须保持 spec_only，实际 {fixture.get('status')}")
    return problems


def _cards(result: Dict[str, Any], problems: List[str], *, require_util: bool) -> None:
    if result.get("kpiFromUiDemo") is not False:
        problems.append("kpiFromUiDemo 不是 false")
    cards = result.get("cards") or {}
    if set(cards) != {"throughput", "wait", "utilization", "bottleneck"}:
        problems.append(f"主卡不是四张：{sorted(cards)}")
    _finite((cards.get("throughput") or {}).get("value"), "throughput.value", problems)
    _finite((cards.get("wait") or {}).get("meanSec"), "wait.meanSec", problems)
    _finite((cards.get("wait") or {}).get("p95Sec"), "wait.p95Sec", problems)
    util_rows = (cards.get("utilization") or {}).get("byResourceType") or []
    if require_util and not util_rows:
        problems.append("有叉车时利用率没有人/车样本")
    for row in util_rows:
        _finite(row.get("utilization"), f"util {row.get('resourceType')}", problems)
    for row in (cards.get("bottleneck") or {}).get("topN") or []:
        _finite(row.get("waitSec"), f"bottleneck {row.get('entityId')}", problems)
        _finite(row.get("share"), f"share {row.get('entityId')}", problems)


def _timing(result: Dict[str, Any], length_m: float, speed_mpm: float) -> Tuple[float, float]:
    expected = length_m / (speed_mpm / 60.0)
    enters = [event for event in result["events"] if event.get("kind") == "convey_enter"]
    exits = [event for event in result["events"] if event.get("kind") == "convey_exit"]
    if not enters or not exits:
        return expected, float("nan")
    return expected, float(exits[0]["t"]) - float(enters[0]["t"])


def evaluate_g01(fixture: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    problems = _honesty(fixture)
    result: Dict[str, Any] = {}
    try:
        result = run_fixture(fixture)
    except DesError as exc:
        problems.append(f"G-CV-01 拒载 {exc.code} {exc.message}")
        return problems, result
    if not result["inventoryConservation"].get("ok"):
        problems.append(f"conservation 不成立 {result['inventoryConservation']}")
    kinds = {event["kind"] for event in result["events"]}
    if "convey_enter" not in kinds or "convey_exit" not in kinds:
        problems.append(f"缺输送事件 {sorted(kinds)}")
    expected, got = _timing(result, 12, 30)
    if not math.isfinite(got) or abs(got - expected) > expected * 0.05:
        problems.append(f"enter→exit {got}s，期望 {expected}s ±5%")
    segs = [seg for seg in result["trajectory"]["segments"] if seg.get("mode") == "conveyor"]
    if not segs or segs[0].get("elementId") != "CV-STR-01":
        problems.append(f"缺 mode=conveyor / CV-STR-01：{segs[:1]}")
    _cards(result, problems, require_util=False)
    tasks = result["trajectory"]["tasks"]
    if not tasks or any(row.get("status") != "done" for row in tasks):
        problems.append(f"任务未完成 {tasks}")
    for type_id in ("CV-ROL-01", "CV-BELT-01"):
        clone = deepcopy(fixture)
        for el in clone["layoutSnapshot"]["elements"]:
            if el.get("instanceId") == "CV1":
                el["elementId"] = type_id
        try:
            rolled = run_fixture(clone)
        except DesError as exc:
            problems.append(f"{type_id} 应与直线同模型，却拒载 {exc.code} {exc.message}")
            continue
        _, rolled_dt = _timing(rolled, 12, 30)
        if not math.isfinite(rolled_dt) or abs(rolled_dt - expected) > expected * 0.05:
            problems.append(f"{type_id} 时长 {rolled_dt}s，期望 {expected}s")
        if not any(seg.get("mode") == "conveyor" and seg.get("elementId") == type_id for seg in rolled["trajectory"]["segments"]):
            problems.append(f"{type_id} 没有对应输送段")
    return problems, result


def evaluate_g02(fixture: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    problems = _honesty(fixture)
    result: Dict[str, Any] = {}
    try:
        result = run_fixture(fixture)
    except DesError as exc:
        problems.append(f"G-CV-02 拒载 {exc.code} {exc.message}")
        return problems, result
    if not result["inventoryConservation"].get("ok"):
        problems.append(f"conservation 不成立 {result['inventoryConservation']}")
    kinds = {event["kind"] for event in result["events"]}
    if "convey_enter" not in kinds or "convey_exit" not in kinds:
        problems.append(f"缺输送事件 {sorted(kinds)}")
    segs = result["trajectory"]["segments"]
    if not any(seg.get("mode") == "conveyor" for seg in segs):
        problems.append("没有 mode=conveyor 段")
    if not any(seg.get("edgeId") for seg in segs):
        problems.append("叉车没有走通道边")
    _cards(result, problems, require_util=True)
    if not result["trajectory"]["tasks"] or any(row.get("status") != "done" for row in result["trajectory"]["tasks"]):
        problems.append("任务未完成")
    return problems, result


def _run_case(fixture: Dict[str, Any]) -> Dict[str, Any]:
    return run_fixture(fixture)


def _reject_problem(case_id: str, exc: DesError | None, produced: Dict[str, Any] | None, needle: str) -> List[str]:
    problems: List[str] = []
    if produced is not None:
        problems.append(f"{case_id} 产生了运行结果")
        return problems
    if exc is None:
        problems.append(f"{case_id} 没有拒载")
        return problems
    if needle not in exc.message:
        problems.append(f"{case_id} 人话不含 {needle!r}：{exc.message}")
    if "—" in exc.message:
        problems.append(f"{case_id} 人话含空卡「—」")
    return problems


def evaluate_g03(base: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    spec = _load("G-CV-03.json")
    problems.extend(_honesty(spec))
    if spec.get("status") != "spec_only":
        problems.append("G-CV-03 status 被改掉了")

    def attempt(case_id: str, mutate, needle: str, code: str | None = None) -> None:
        fixture = deepcopy(base)
        mutate(fixture)
        produced = None
        caught = None
        try:
            produced = _run_case(fixture)
        except DesError as exc:
            caught = exc
        problems.extend(_reject_problem(case_id, caught, produced, needle))
        if code and caught is not None and caught.code != code:
            problems.append(f"{case_id} 码 {caught.code}，期望 {code}")
        if caught is not None:
            print(f"  {case_id} 加载即停 {caught.code}：{caught.message}")

    def strip_ports(fixture: Dict[str, Any]) -> None:
        for el in fixture["layoutSnapshot"]["elements"]:
            if el.get("instanceId") == "CV1":
                el["ports"] = []
                el["connector_ids"] = []

    def drop_links(fixture: Dict[str, Any]) -> None:
        fixture["layoutSnapshot"]["connections"] = []

    def insert_type(type_id: str):
        def mutate(fixture: Dict[str, Any]) -> None:
            fixture["layoutSnapshot"]["elements"].append(
                {
                    "instanceId": "X1",
                    "elementId": type_id,
                    "kind": "device",
                    "pose": {"x": 6, "y": 1},
                    "params": {
                        "length_m": 2,
                        "width_m": 2,
                        "orientation_deg": 0,
                        "speed_mpm": 30,
                        "throughput_uph": 60,
                        "max_load_kg": 500,
                        "direction": "forward",
                        "allow_load_types": ["pallet"],
                    },
                    "connector_ids": ["a", "b"],
                    "ports": [{"id": "a", "role": "in"}, {"id": "b", "role": "out"}],
                }
            )
            fixture["layoutSnapshot"]["connections"] = [
                {"from": {"instanceId": "SRC", "portId": "to_cv"}, "to": {"instanceId": "X1", "portId": "a"}},
                {"from": {"instanceId": "X1", "portId": "b"}, "to": {"instanceId": "CV1", "portId": "p_in"}},
                {"from": {"instanceId": "CV1", "portId": "p_out"}, "to": {"instanceId": "DST", "portId": "from_cv"}},
            ]

        return mutate

    def agv(fixture: Dict[str, Any]) -> None:
        fixture["layoutSnapshot"]["elements"].append(
            {"instanceId": "AGV1", "elementId": "MH-AGV-01", "kind": "device", "pose": {"x": 1, "y": 1}}
        )
        fixture["scenario"]["tasks"][0]["dependsOn"] = "AGV1"

    def revision(fixture: Dict[str, Any]) -> None:
        fixture["scenario"]["expectedLayoutRevision"] = "not-the-snapshot"

    def load_type(fixture: Dict[str, Any]) -> None:
        for el in fixture["layoutSnapshot"]["elements"]:
            if el.get("instanceId") == "CV1":
                el["params"]["allow_load_types"] = ["case"]

    attempt("R1_missing_connector", strip_ports, "输送还没接上", "CONVEYOR_UNLINKED")
    attempt("R2_broken_link", drop_links, "输送还没接上", "CONVEYOR_UNLINKED")
    attempt("R3_curve_on_path", insert_type("CV-CURVE-01"), "本切片暂不仿真该类", "UNSUPPORTED_SCENARIO")
    attempt("R4_merge_on_path", insert_type("CV-MERGE-01"), "本切片暂不仿真该类", "UNSUPPORTED_SCENARIO")
    attempt("R4_div_on_path", insert_type("CV-DIV-01"), "本切片暂不仿真该类", "UNSUPPORTED_SCENARIO")
    attempt("R4_buf_on_path", insert_type("CV-BUF-01"), "本切片暂不仿真该类", "UNSUPPORTED_SCENARIO")
    attempt("R5_agv_required", agv, "MH-AGV-01", "UNSUPPORTED_SCENARIO")
    attempt("R6_revision_mismatch", revision, "layoutRevision", "LAYOUT_REVISION_MISMATCH")
    attempt("R7_allow_load_mismatch", load_type, "CV-STR-01", "UNSUPPORTED_SCENARIO")
    for type_id in REJECT_TYPES:
        if type_id in {"CV-CURVE-01", "CV-MERGE-01", "CV-DIV-01", "CV-BUF-01", "MH-AGV-01"}:
            continue
        attempt(f"extra_{type_id}", insert_type(type_id), type_id, "UNSUPPORTED_SCENARIO")
    return problems


def evaluate_mx(fixture: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    problems = _honesty(fixture)
    if "MX-D1-EB" not in json.dumps(fixture, ensure_ascii=False):
        problems.append("MX-D1-CV 没有声明与 MX-D1-EB 的边界")
    result: Dict[str, Any] = {}
    try:
        from des.mxeval import _load as load_mx

        d1 = load_mx("MX-D1-EB.json")
        snapshot = build_snapshot(d1)
        snapshot["elements"].append(
            {
                "elementId": "cv-1",
                "instanceId": "cv-1",
                "typeElementId": "CV-STR-01",
                "kind": "device",
                "pose": {"x": 22, "y": 12, "yawDeg": 0},
                "footprint": {"w": 8, "d": 0.9},
                "params": {
                    "length_m": 8,
                    "width_m": 0.9,
                    "orientation_deg": 0,
                    "speed_mpm": 30,
                    "throughput_uph": 120,
                    "max_load_kg": 1500,
                    "direction": "forward",
                    "allow_load_types": ["pallet"],
                },
                "connector_ids": ["p_in", "p_out"],
                "ports": [{"id": "p_in", "role": "in"}, {"id": "p_out", "role": "out"}],
            }
        )
        snapshot["connections"] = [
            {"from": {"instanceId": "rack-001", "portId": "to_cv"}, "to": {"instanceId": "cv-1", "portId": "p_in"}},
            {"from": {"instanceId": "cv-1", "portId": "p_out"}, "to": {"instanceId": "dock-out", "portId": "from_cv"}},
        ]
        result = run_case(snapshot, d1["scenario"], int(d1["scenario"]["forklifts"]), d1["layoutRevision"], "run-mx-d1-cv")
    except DesError as exc:
        problems.append(f"MX-D1-CV 拒载 {exc.code} {exc.message}")
        return problems, result
    if not result["inventoryConservation"].get("ok"):
        problems.append(f"conservation 不成立 {result['inventoryConservation']}")
    if not result["trajectory"]["segments"]:
        problems.append("segments 为空")
    if not any(event.get("kind") == "convey_enter" for event in result["events"]):
        problems.append("直线段没有 convey_enter")
    if not any(seg.get("mode") == "conveyor" and seg.get("elementId") in LINEAR_TYPES for seg in result["trajectory"]["segments"]):
        problems.append("没有直线输送段")
    _cards(result, problems, require_util=True)
    top = [row.get("entityId") for row in result["cards"]["bottleneck"]["topN"]]
    print("  bottleneck TopN", top)
    return problems, result


def run_suite() -> int:
    print("command: PYTHONPATH=next python3 next/scripts/run_cv.py")
    print("honesty: assert pass keeps status=spec_only; not UA S-D1; not MX-D1-EB; not curve/merge/divert")
    failures = 0
    g01 = _load("G-CV-01.json")
    g02 = _load("G-CV-02.json")
    p1, result1 = evaluate_g01(g01)
    if p1:
        failures += len(p1)
        print("FAIL", g01["fixtureId"])
        for problem in p1:
            print("  ", problem)
    else:
        expected, got = _timing(result1, 12, 30)
        cards = result1["cards"]
        print("PASS", g01["fixtureId"], "status", g01["status"])
        print(
            "  observed enter→exit",
            round(got, 4),
            "s expected",
            expected,
            "throughput",
            cards["throughput"]["value"],
            "waitMean",
            cards["wait"]["meanSec"],
            "utilRows",
            len(cards["utilization"]["byResourceType"]),
        )
        print("  ", (g01.get("expected") or {}).get("kpiHonesty"))
    p2, result2 = evaluate_g02(g02)
    if p2:
        failures += len(p2)
        print("FAIL", g02["fixtureId"])
        for problem in p2:
            print("  ", problem)
    else:
        cards = result2["cards"]
        print("PASS", g02["fixtureId"], "status", g02["status"])
        print(
            "  observed throughput",
            cards["throughput"]["value"],
            "waitMean",
            cards["wait"]["meanSec"],
            "util",
            cards["utilization"]["byResourceType"],
            "conveyorSegments",
            sum(1 for seg in result2["trajectory"]["segments"] if seg.get("mode") == "conveyor"),
            "aisleSegments",
            sum(1 for seg in result2["trajectory"]["segments"] if seg.get("edgeId")),
        )
        print("  ", (g02.get("expected") or {}).get("kpiHonesty"))
    p3 = evaluate_g03(g01)
    if p3:
        failures += len(p3)
        print("FAIL G-CV-03")
        for problem in p3:
            print("  ", problem)
    else:
        print("PASS G-CV-03 status", _load("G-CV-03.json")["status"])
        print("  ", (_load("G-CV-03.json").get("expected") or {}).get("kpiHonesty"))
    mx = _load("MX-D1-CV.json")
    p4, result4 = evaluate_mx(mx)
    if p4:
        failures += len(p4)
        print("FAIL", mx["fixtureId"])
        for problem in p4:
            print("  ", problem)
    else:
        cards = result4["cards"]
        print("PASS", mx["fixtureId"], "status", mx["status"])
        print(
            "  observed throughput",
            cards["throughput"]["value"],
            "waitMean",
            cards["wait"]["meanSec"],
            "segments",
            len(result4["trajectory"]["segments"]),
            "conveyEnter",
            sum(1 for event in result4["events"] if event.get("kind") == "convey_enter"),
        )
        print("  ", (mx.get("expected") or {}).get("kpiHonesty"))
    print("failures", failures)
    return 1 if failures else 0
