"""Smallest forklift count whose mean wait is within a stated target.

The search runs the same engine once per count and stops at the first count
that meets the target. It does not price equipment and it does not compare layouts.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from des.errors import DesError
from des.gold import run_fixture

PLAN = Path(__file__).resolve().parents[1] / "fixtures" / "plan"


def with_forklift_count(fixture: Dict[str, Any], count: int) -> Dict[str, Any]:
    clone = deepcopy(fixture)
    resources = list((clone.get("scenario") or {}).get("resources") or [])
    template = next((row for row in resources if (row.get("kind") or row.get("resourceType")) == "forklift"), None)
    if template is None:
        raise DesError("NO_RESOURCES", "至少需要 1 台叉车作为样板", {"resourceType": "forklift"})
    others = [row for row in resources if (row.get("kind") or row.get("resourceType")) != "forklift"]
    trucks = []
    for index in range(count):
        truck = deepcopy(template)
        truck["resourceId"] = f"FL{index + 1}"
        trucks.append(truck)
    clone["scenario"]["resources"] = others + trucks
    return clone


def smallest_forklift_count(fixture: Dict[str, Any], *, wait_mean_max: float, max_count: int) -> Dict[str, Any]:
    if max_count < 1:
        raise DesError("INPUT_UNCONFIRMED", "叉车搜索上限至少是 1", {"maxCount": max_count})
    tried: List[Dict[str, Any]] = []
    for count in range(1, max_count + 1):
        result = run_fixture(with_forklift_count(fixture, count))
        if result.get("kpiFromUiDemo") is not False:
            raise DesError("COMPUTATION_FAILED", "kpiFromUiDemo 必须为 false")
        mean = (result.get("cards") or {}).get("wait", {}).get("meanSec")
        p95 = (result.get("cards") or {}).get("wait", {}).get("p95Sec")
        tried.append({"forkliftCount": count, "waitMeanSec": mean, "waitP95Sec": p95})
        if mean is not None and float(mean) <= float(wait_mean_max) + 1e-9:
            return {
                "forkliftCount": count,
                "waitMeanMaxSec": wait_mean_max,
                "tried": tried,
                "kpiFromUiDemo": False,
            }
    raise DesError(
        "INPUT_UNCONFIRMED",
        "加到上限等待仍超过目标",
        {"tried": tried, "waitMeanMaxSec": wait_mean_max, "maxCount": max_count},
    )


def _near(got: Any, want: float, label: str, problems: List[str]) -> None:
    if got is None or abs(float(got) - float(want)) > 1e-6:
        problems.append(f"{label} {got}，期望 {want}")


def evaluate(fixture: Dict[str, Any]) -> List[str]:
    expected = fixture.get("expected") or {}
    problems: List[str] = []
    if fixture.get("status") != "measured_pass":
        problems.append(f"status 仍是 {fixture.get('status')}")
    measured = fixture.get("measured") or {}
    if measured.get("kpiAcAllGreen") is not False:
        problems.append("measured.kpiAcAllGreen 必须显式为 false")
    try:
        found = smallest_forklift_count(
            fixture,
            wait_mean_max=float(expected["waitMeanMaxSec"]),
            max_count=int(expected["maxCount"]),
        )
    except DesError as exc:
        if expected.get("mustReject"):
            if exc.code != expected.get("rejectReasonCode"):
                problems.append(f"拒载码 {exc.code}，期望 {expected.get('rejectReasonCode')}")
            needle = expected.get("rejectMessageContains")
            if needle and needle not in exc.message:
                problems.append(f"人话不含 {needle!r}：{exc.message}")
            return problems
        problems.append(f"搜索失败 {exc.code} {exc.message}")
        return problems
    if expected.get("mustReject"):
        problems.append("期望拒绝，但找到了叉车数")
        return problems
    if found.get("kpiFromUiDemo") is not False:
        problems.append("kpiFromUiDemo 不是 false")
    if found.get("forkliftCount") != expected.get("forkliftCount"):
        problems.append(f"叉车数 {found.get('forkliftCount')}，期望 {expected.get('forkliftCount')}")
    tried = found.get("tried") or []
    wanted = expected.get("tried") or []
    if len(tried) != len(wanted):
        problems.append(f"尝试次数 {len(tried)}，期望 {len(wanted)}")
    for got, want in zip(tried, wanted):
        if got.get("forkliftCount") != want.get("forkliftCount"):
            problems.append(f"尝试台数 {got.get('forkliftCount')}，期望 {want.get('forkliftCount')}")
        _near(got.get("waitMeanSec"), want["waitMeanSec"], f"{want.get('forkliftCount')} 台等待均值", problems)
        _near(got.get("waitP95Sec"), want["waitP95Sec"], f"{want.get('forkliftCount')} 台等待 P95", problems)
    return problems


def load_fixtures() -> List[Dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(PLAN.glob("G-PLAN-*.json"))]


def run_suite() -> int:
    failures = 0
    print("command: PYTHONPATH=next python3 next/scripts/run_plan.py")
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
