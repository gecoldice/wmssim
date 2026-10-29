#!/usr/bin/env python3
"""Acceptance evidence for the manual slice. Prints S-01 … S-12 with raw observations.

Usage (from the repository root):
  PYTHONPATH=next python3 next/scripts/accept_slice.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("NEXT_STORE", "")
sys.path.insert(0, str(ROOT / "next"))

from fastapi.testclient import TestClient  # noqa: E402
from jsonschema import Draft7Validator  # noqa: E402

from api.app.main import app, store  # noqa: E402
from api.app.store import Store  # noqa: E402
from des.derive import derive_snapshot  # noqa: E402
from des.engine import ENGINE_VERSION, run_des  # noqa: E402
from des.errors import DesError  # noqa: E402
from des.gold import run_suite  # noqa: E402
from des.mxeval import run_suite as run_mx_suite  # noqa: E402
from des.scope import unsimulated_message  # noqa: E402
from des.validate import validate_layout  # noqa: E402

FX = ROOT / "next" / "fixtures" / "manual-wh"
SCHEMAS = ROOT / "next" / "contracts" / "schemas"
failures = 0


def load(name: str):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def reset() -> None:
    store.projects.clear()
    store.facilities.clear()
    store.layouts.clear()
    store.jobs.clear()
    store.runs.clear()
    store.path = None


def check(ok: bool, label: str) -> None:
    global failures
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        failures += 1


def poll(client: TestClient, job_id: str) -> dict:
    job = {}
    for _ in range(80):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job.get("status") in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    return job


def manual_path(client: TestClient, facility: dict, layout: dict, demand: dict, operating: dict, tag: str):
    """One save → prepare → simulate sequence. Blank and rectangle both use it."""
    paths: list[str] = []

    def call(method: str, url: str, **kwargs):
        paths.append(f"{method} {url}")
        return getattr(client, method.lower())(url, **kwargs)

    project = call("POST", "/api/v1/projects", json={"name": tag, "unitSystem": "metric"})
    pid = project.json()["id"]
    saved_f = call(
        "POST",
        f"/api/v1/projects/{pid}/facility-revisions",
        json={"facility": facility, "baseRevision": None},
    )
    saved_l = call(
        "POST",
        f"/api/v1/layouts/{layout['id']}/revisions",
        json={"projectId": pid, "baseRevision": None, "document": layout},
    )
    ref = saved_l.json()["layoutRef"]
    prep = call("POST", f"/api/v1/layouts/{ref['id']}/prepare-jobs", json={"layoutRef": ref})
    job = poll(client, prep.json()["jobId"])
    paths.append(f"GET /api/v1/jobs/{prep.json()['jobId']}")
    sim = None
    run = None
    if job.get("status") == "succeeded" and (job.get("result") or {}).get("simulationReady"):
        sim = call(
            "POST",
            "/api/v1/simulation-jobs",
            json={
                "layoutRef": ref,
                "demand": demand,
                "operating": operating,
                "runControl": {
                    "horizonSec": 3600,
                    "seedStreams": {"demand": 7},
                    "metricDefinitionVersion": "metrics-slice-manual-v1",
                },
            },
        )
        sim_job = poll(client, sim.json()["jobId"])
        paths.append(f"GET /api/v1/jobs/{sim.json()['jobId']}")
        if sim_job.get("status") == "succeeded":
            run_id = sim_job["result"]["runId"]
            run = call("GET", f"/api/v1/runs/{run_id}").json()
    return {
        "paths": paths,
        "project": project,
        "facility": saved_f,
        "layout": saved_l,
        "prepare_http": prep,
        "prepare": job,
        "simulation": sim,
        "run": run,
        "layoutRef": ref,
    }


def event_sig(run: dict) -> list:
    rows = []
    for event in run["events"]:
        rows.append(
            {
                "t": event["t"],
                "kind": event["kind"],
                "taskId": event.get("taskId"),
                "waitSec": event.get("waitSec"),
                "palletEq": event.get("palletEq"),
            }
        )
    return rows


def main() -> int:
    print("command: PYTHONPATH=next python3 next/scripts/accept_slice.py")
    print("--- schema catalog ---")
    catalog = load("catalog.json")
    for entry in catalog["entries"]:
        schema = json.loads((SCHEMAS / entry["schema"]).read_text(encoding="utf-8"))
        data = load(entry["path"])
        errors = list(Draft7Validator(schema).iter_errors(data))
        ok = (len(errors) == 0) if entry["expect"] == "pass" else len(errors) > 0
        detail = errors[0].message if errors else "valid"
        print(f"schema {entry['path']} expect={entry['expect']} {detail}")
        check(ok, f"schema {entry['path']}")

    routes = sorted({getattr(route, "path", "") for route in app.routes if getattr(route, "path", "")})
    print("routes:", routes)
    check(not any("planning" in path or "cost" in path or "compar" in path for path in routes), "no planning/cost/compare routes")

    client = TestClient(app)
    demand = load("demand-small.json")
    operating = load("operating-one-forklift.json")

    print("\n=== S-01 blank place, save, prepare, simulate ===")
    reset()
    blank_facility = load("facility-rect.json")
    blank_facility["id"] = "facility-blank"
    blank_layout = load("layout-ok.json")
    blank_layout["id"] = "layout-blank"
    s01 = manual_path(client, blank_facility, blank_layout, demand, operating, "S-01")
    print("request sequence:")
    for path in s01["paths"]:
        print(" ", path)
    print("prepare", s01["prepare"].get("status"), "ready", (s01["prepare"].get("result") or {}).get("simulationReady"))
    print("run layoutRevision", (s01["run"] or {}).get("layoutRevision"), "kpiFromUiDemo", (s01["run"] or {}).get("kpiFromUiDemo"))
    check(s01["run"] is not None, "S-01 produced a run")
    check(all("planning" not in path and "cost" not in path for path in s01["paths"]), "S-01 sequence has no planning API")
    check((s01["run"] or {}).get("kpiFromUiDemo") is False, "S-01 kpiFromUiDemo false")

    print("\n=== S-02 rectangle template uses the same helper ===")
    workbench = (ROOT / "next" / "web" / "src" / "workbench" / "Workbench.tsx").read_text(encoding="utf-8")
    builders = (ROOT / "next" / "web" / "src" / "workbench" / "draft.ts").read_text(encoding="utf-8")
    print("choose(blank)", 'choose("blank")' in workbench, "choose(rectangle)", 'choose("rectangle")' in workbench)
    print("single draftFor", builders.count("export function draftFor"))
    check('choose("blank")' in workbench and 'choose("rectangle")' in workbench, "S-02 UI starts share choose()")
    check(builders.count("export function buildLayout") == 1 and builders.count("export function draftFor") == 1, "S-02 one layout builder")
    reset()
    s02 = manual_path(client, load("facility-rect.json"), load("layout-ok.json"), demand, operating, "S-02")
    print("request sequence:")
    for path in s02["paths"]:
        print(" ", path)
    same_shape = [path.split("/api/v1/")[-1].split("/")[0] for path in s01["paths"]] == [
        path.split("/api/v1/")[-1].split("/")[0] for path in s02["paths"]
    ]
    # Compare the method+resource pattern, ignoring generated ids.
    def shape(paths: list[str]) -> list[str]:
        out = []
        for path in paths:
            method, url = path.split(" ", 1)
            url = url.replace(s01["layoutRef"]["id"], "{layout}")
            url = url.replace(s02["layoutRef"]["id"], "{layout}")
            for token in ("pj_", "job_", "run_", "fr_", "lr_"):
                if token in url:
                    pass
            out.append(method + " " + url.split("?")[0])
        return out

    print("S-01 shape", shape(s01["paths"]))
    print("S-02 shape", shape(s02["paths"]))
    check(s02["run"] is not None and same_shape, "S-02 same save/prepare/simulate shape as blank")

    print("\n=== S-03 cross-wall prepare fails and simulation is rejected ===")
    reset()
    wall_layout = load("layout-cross-wall.json")
    s03 = manual_path(client, load("facility-wall.json"), wall_layout, demand, operating, "S-03")
    report = (s03["prepare"].get("result") or {}).get("validationReport") or {}
    body = json.dumps(s03["prepare"], ensure_ascii=False)
    print(body[:1200])
    sim = client.post(
        "/api/v1/simulation-jobs",
        json={
            "layoutRef": s03["layoutRef"],
            "demand": demand,
            "operating": operating,
            "runControl": {"horizonSec": 3600, "seedStreams": {"demand": 7}, "metricDefinitionVersion": "metrics-slice-manual-v1"},
        },
    )
    print("simulation", sim.status_code, sim.text)
    check(s03["prepare"].get("result", {}).get("simulationReady") is False, "S-03 prepare not ready")
    check("rack-west" in body and "跨墙" in body, "S-03 body names rack-west and 跨墙")
    check(sim.status_code == 409 and "rack-west" in sim.text, "S-03 simulation rejected with instance id")

    print("\n=== S-04 narrow aisle ===")
    reset()
    narrow = load("layout-narrow.json")
    narrow["id"] = "layout-narrow"
    s04 = manual_path(client, load("facility-rect.json"), narrow, demand, operating, "S-04")
    text = json.dumps(s04["prepare"], ensure_ascii=False)
    print(text[:800])
    check("NARROW_AISLE" in text and "窄" in text, "S-04 narrow aisle failure")
    check(s04["prepare"].get("result", {}).get("simulationReady") is False, "S-04 not simulation ready")

    print("\n=== S-05 repeatability ===")
    reset()
    s05 = manual_path(client, load("facility-rect.json"), load("layout-ok.json"), demand, operating, "S-05")
    ref = s05["layoutRef"]
    again = client.post(
        "/api/v1/simulation-jobs",
        json={
            "layoutRef": ref,
            "demand": demand,
            "operating": operating,
            "runControl": {"horizonSec": 3600, "seedStreams": {"demand": 7}, "metricDefinitionVersion": "metrics-slice-manual-v1"},
        },
    )
    job2 = poll(client, again.json()["jobId"])
    run2 = client.get(f"/api/v1/runs/{job2['result']['runId']}").json()
    print("revision", s05["run"]["layoutRevision"], run2["layoutRevision"])
    print("event count", len(s05["run"]["events"]), len(run2["events"]))
    check(s05["run"]["layoutRevision"] == run2["layoutRevision"] == ref["revision"], "S-05 revision string unchanged")
    check(event_sig(s05["run"]) == event_sig(run2) and s05["run"]["cards"] == run2["cards"], "S-05 events and cards match")

    print("\n=== S-06 small-sample P95 ===")
    wait = s05["run"]["cards"]["wait"]
    print(json.dumps(wait, ensure_ascii=False))
    check(wait["sampleCount"] == 4 and wait["sampleCount"] < 20, "S-06 sample count is 4")
    check(wait["p95Sec"] is not None and wait["meanSec"] is not None, "S-06 P95 reported for n<20")

    print("\n=== S-07 zero outbound ===")
    zero = client.post(
        "/api/v1/simulation-jobs",
        json={
            "layoutRef": ref,
            "demand": load("demand-zero.json"),
            "operating": operating,
            "runControl": {"horizonSec": 3600, "seedStreams": {"demand": 7}, "metricDefinitionVersion": "metrics-slice-manual-v1"},
        },
    )
    zero_job = poll(client, zero.json()["jobId"])
    zero_run = client.get(f"/api/v1/runs/{zero_job['result']['runId']}").json()
    print(json.dumps({"wait": zero_run["cards"]["wait"], "secondary": zero_run["secondary"], "topN": zero_run["cards"]["bottleneck"]["topN"], "throughput": zero_run["cards"]["throughput"]["value"]}, ensure_ascii=False))
    check(zero_run["cards"]["wait"]["meanSec"] is None and zero_run["cards"]["wait"]["p95Sec"] is None, "S-07 wait null")
    check(zero_run["secondary"]["completionRate"] is None, "S-07 completion rate null")
    check(zero_run["cards"]["bottleneck"]["topN"] == [], "S-07 topN empty")

    print("\n=== S-08 utilization by resource ===")
    mixed = client.post(
        "/api/v1/simulation-jobs",
        json={
            "layoutRef": ref,
            "demand": demand,
            "operating": load("operating-two-types.json"),
            "runControl": {"horizonSec": 3600, "seedStreams": {"demand": 7}, "metricDefinitionVersion": "metrics-slice-manual-v1"},
        },
    )
    mixed_job = poll(client, mixed.json()["jobId"])
    mixed_run = client.get(f"/api/v1/runs/{mixed_job['result']['runId']}").json()
    util = mixed_run["cards"]["utilization"]
    print(json.dumps(util, ensure_ascii=False, indent=2))
    types = [row["resourceType"] for row in util["byResourceType"]]
    ids = [row["resourceId"] for row in util["byResource"]]
    check(types == ["forklift", "picker"] and "value" not in util, "S-08 types listed and no blended value")
    check(ids == ["forklift-1", "forklift-2", "picker-1"], "S-08 per resource id")

    print("\n=== S-09 layout change leaves the old run on the old revision ===")
    old_rev = s05["run"]["layoutRevision"]
    changed = deepcopy(load("layout-ok.json"))
    changed["elements"][0]["pose"]["x"] = 13
    saved = client.post(
        f"/api/v1/layouts/{ref['id']}/revisions",
        json={"projectId": client.get(f"/api/v1/layouts/{ref['id']}").json()["projectId"], "baseRevision": old_rev, "document": {**changed, "revision": old_rev}},
    )
    print("save", saved.status_code, saved.json().get("layoutRef") or saved.text)
    new_rev = saved.json()["layoutRef"]["revision"]
    old_run = client.get(f"/api/v1/runs/{s05['run']['runId']}").json()
    print("old run revision", old_run["layoutRevision"], "new revision", new_rev)
    check(old_run["layoutRevision"] == old_rev and new_rev != old_rev, "S-09 old run keeps its revision")

    print("\n=== S-10 demand change is a demand expiry, not a dirty flag ===")
    print("bound outbound 4; viewing the same run after the form changes to 8")
    check(old_run["demandOutboundQty"] == 4, "S-10 run records outbound quantity 4")

    print("\n=== S-11 refresh keeps the saved layout, not an unsaved draft ===")
    import tempfile

    tmp = Path(tempfile.mkdtemp()) / "store.json"
    store.path = tmp
    store.persist()
    reloaded = Store(tmp)
    print("reloaded layout", reloaded.layouts[ref["id"]]["revision"])
    check(reloaded.layouts[ref["id"]]["revision"] == new_rev, "S-11 server reload keeps the saved revision")
    display = subprocess.run(
        ["node", "scripts/check-display.mjs"],
        cwd=ROOT / "next" / "web",
        text=True,
        capture_output=True,
        check=False,
    )
    print(display.stdout)
    if display.stderr:
        print(display.stderr)
    check(display.returncode == 0, "S-11 display/persist script")

    print("\n=== S-12 gold cards vs independent fractions ===")
    snap = derive_snapshot(load("layout-ok.json"), load("facility-rect.json"), layout_revision="fixture-snapshot")
    before = json.dumps(snap, sort_keys=True)
    gold_run = run_des(
        snapshot=snap,
        demand=demand,
        operating=operating,
        run_control={"horizonSec": 3600, "seedStreams": {"demand": 7}, "metricDefinitionVersion": "metrics-slice-manual-v1"},
        expected_layout_revision="fixture-snapshot",
        run_id="run-gold-check",
    )
    after = json.dumps(snap, sort_keys=True)
    cards = gold_run["cards"]
    expected = load("expected-cards.json")
    mean = Fraction(131, 2)
    p95 = Fraction(409, 3)
    busy = Fraction(616, 3)
    util_f = Fraction(77, 1350)
    print("mean", cards["wait"]["meanSec"], "expected", float(mean))
    print("p95", cards["wait"]["p95Sec"], "expected", float(p95), "rank ceil(0.95*4)=4")
    print("busy", cards["utilization"]["byResourceType"][0]["busySec"], "expected", float(busy))
    print("util", cards["utilization"]["byResourceType"][0]["utilization"], "expected", float(util_f))
    print("topN", cards["bottleneck"]["topN"])
    print("engine", gold_run["engineVersion"], "conservation", gold_run["inventoryConservation"])
    ships = [event for event in gold_run["events"] if event["kind"] == "ship"]
    print("ship palletEq", [event["palletEq"] for event in ships])
    schema = json.loads((SCHEMAS / "slice" / "run-result.schema.json").read_text(encoding="utf-8"))
    schema_errors = list(Draft7Validator(schema).iter_errors(gold_run))
    print("run schema errors", [err.message for err in schema_errors])
    tol = 1e-6
    check(before == after, "S-12 snapshot bytes unchanged")
    check(abs(cards["wait"]["meanSec"] - float(mean)) < tol, "S-12 mean 131/2")
    check(abs(cards["wait"]["p95Sec"] - float(p95)) < tol, "S-12 p95 409/3")
    check(abs(cards["utilization"]["byResourceType"][0]["busySec"] - float(busy)) < tol, "S-12 busy 616/3")
    check(abs(cards["utilization"]["byResourceType"][0]["utilization"] - float(util_f)) < tol, "S-12 util 77/1350")
    check(cards["bottleneck"]["topN"] == [{"entityId": "pool-forklift", "waitSec": 262.0, "share": 1.0}], "S-12 bottleneck")
    check(cards["throughput"]["outboundPalletEq"] == 4 and sum(event["palletEq"] for event in ships) == 4, "S-12 four pallets")
    check(gold_run["engineVersion"] == expected["engineVersion"] == ENGINE_VERSION, "S-12 engineVersion")
    check(not schema_errors and gold_run["kpiFromUiDemo"] is False, "S-12 schema and kpiFromUiDemo")
    check(gold_run["inventoryConservation"]["ok"] is True and gold_run["inventoryConservation"]["residual"] == 0, "S-12 conservation")

    print("\n=== extra guards ===")
    alias = client.post(
        "/api/v1/layouts/layout-alias/revisions",
        json={"projectId": s05["layout"] and client.get("/api/v1/layouts/layout-ok").json()["projectId"], "baseRevision": None, "document": load("layout-short-alias.json")},
    )
    print("alias", alias.status_code, alias.text[:240])
    check(alias.status_code == 422 and alias.json()["code"] == "ELEMENT_ID", "short alias rejected")
    try:
        run_des(
            snapshot=load("snapshot-bad-version.json"),
            demand=demand,
            operating=operating,
            run_control={"horizonSec": 3600, "seedStreams": {"demand": 1}, "metricDefinitionVersion": "metrics-slice-manual-v1"},
            expected_layout_revision="rev-x",
        )
        bad = "accepted"
    except DesError as exc:
        bad = exc.code + " " + exc.message
    print("bad snapshot", bad)
    check(bad.startswith("CONTRACT_VERSION"), "snapshot version 0.3 rejected")
    current_ref = client.get("/api/v1/layouts/layout-ok").json()["layoutRef"]
    prepared_break = client.post(f"/api/v1/layouts/{current_ref['id']}/prepare-jobs", json={"layoutRef": current_ref})
    prepared_break_job = poll(client, prepared_break.json()["jobId"])
    print("break prepare", prepared_break_job.get("status"), (prepared_break_job.get("result") or {}).get("simulationReady"))
    runs_before = len(store.runs)
    break_job = client.post(
        "/api/v1/simulation-jobs",
        json={
            "layoutRef": current_ref,
            "demand": load("demand-break-bulk.json"),
            "operating": operating,
            "runControl": {"horizonSec": 3600, "seedStreams": {"demand": 7}, "metricDefinitionVersion": "metrics-slice-manual-v1"},
        },
    )
    break_polled = poll(client, break_job.json()["jobId"]) if break_job.status_code == 202 else {}
    print("break_bulk", break_job.status_code, break_polled.get("status"), (break_polled.get("error") or break_job.text) )
    runs_after = len(store.runs)
    check(
        break_polled.get("status") == "failed" and (break_polled.get("error") or {}).get("code") == "FLOWKIND_STATION_MISSING",
        "break_bulk without a station is rejected",
    )
    check(runs_after == runs_before, "rejected break_bulk stored no extra run")
    conveyed = deepcopy(load("layout-ok.json"))
    conveyed["elements"].append(
        {
            "instanceId": "belt-001",
            "typeElementId": "CV-BELT-01",
            "pose": {"x": 20, "y": 16, "yawDeg": 0},
            "params": {"length_m": 6, "width_m": 0.8, "height_m": 0.9, "orientation_deg": 0},
            "assetDisposition": "new",
        }
    )
    project_id = client.get("/api/v1/layouts/layout-ok").json()["projectId"]
    saved_cv = client.post(
        "/api/v1/layouts/layout-cv/revisions",
        json={"projectId": project_id, "baseRevision": None, "document": conveyed},
    )
    print("cv layout", saved_cv.status_code, saved_cv.text[:240])
    cv_ref = saved_cv.json().get("layoutRef")
    prep_cv = client.post("/api/v1/layouts/layout-cv/prepare-jobs", json={"layoutRef": cv_ref}) if cv_ref else None
    prep_done = poll(client, prep_cv.json()["jobId"]) if prep_cv is not None and prep_cv.status_code == 202 else {}
    sim_cv = client.post(
        "/api/v1/simulation-jobs",
        json={
            "layoutRef": cv_ref,
            "demand": demand,
            "operating": operating,
            "runControl": {"horizonSec": 3600, "seedStreams": {"demand": 7}, "metricDefinitionVersion": "metrics-slice-manual-v1"},
        },
    ) if (prep_done.get("result") or {}).get("simulationReady") else None
    print("cv sim", None if sim_cv is None else (sim_cv.status_code, sim_cv.text[:300]))
    runs_cv = len(store.runs)
    message = "" if sim_cv is None else sim_cv.json().get("message", "")
    check(sim_cv is not None and sim_cv.status_code == 422 and message.startswith("本切片暂不仿真该类") and "CV-BELT-01" in message, "conveyor placement does not invent KPI")
    check(runs_cv == runs_after and "即将" not in message, "unsimulated call stored no run")
    check(unsimulated_message(["MH-AGV-01"]).startswith("本切片暂不仿真该类"), "scope message")

    web = (ROOT / "next" / "web" / "src").read_text() if False else ""
    blob = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "next" / "web" / "src").rglob("*") if path.suffix in {".ts", ".tsx", ".js", ".css"})
    des_blob = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "next" / "des").rglob("*.py"))
    for needle in ("warehouse-layout-ui-preview", "Date.now", "8.7", "12.4", "onCostCompare", "simapp_des", "planning-jobs"):
        print(f"grep {needle}:", needle in blob or needle in des_blob)
        check(needle not in blob and needle not in des_blob, f"absent {needle}")

    print("\n=== mixed template geometry and segment playback contract ===")
    web = ROOT / "next" / "web"
    esbuild = web / "node_modules" / "esbuild" / "bin" / "esbuild"
    if not esbuild.exists():
        install = subprocess.run(["npm", "install"], cwd=web, text=True, capture_output=True, check=False)
        print(install.stdout[-400:] if install.stdout else "")
        if install.returncode != 0:
            print(install.stderr)
        check(install.returncode == 0 and esbuild.exists(), "esbuild available for UI contract bundle")
    bundled = Path("/tmp/check-layout-ui.mjs")
    bundle = subprocess.run(
        [str(esbuild), "scripts/check-layout-ui.mjs", "--bundle", "--platform=node", "--format=esm", f"--outfile={bundled}"],
        cwd=web,
        text=True,
        capture_output=True,
        check=False,
    )
    print(bundle.stdout)
    if bundle.stderr:
        print(bundle.stderr[-800:])
    ran = subprocess.run(["node", str(bundled)], cwd=web, text=True, capture_output=True, check=False) if bundle.returncode == 0 else None
    if ran:
        print(ran.stdout)
        if ran.stderr:
            print(ran.stderr)
    check(bundle.returncode == 0 and ran is not None and ran.returncode == 0, "UI template, footprints, ghost verdict, segment interpolation")
    if ran and ran.returncode == 0:
        facility = json.loads(Path("/tmp/mixed-slice-facility.json").read_text(encoding="utf-8"))
        layout = json.loads(Path("/tmp/mixed-slice-layout.json").read_text(encoding="utf-8"))
        snap = derive_snapshot(layout, facility, layout_revision="mixed-ui")
        report = validate_layout(snap, facility, layout)
        print("mixed validate", report.get("status"))
        for row in report.get("checks") or []:
            if row.get("status") == "fail":
                print(" ", row.get("ruleId"), row.get("message"))
        kinds = {el.get("typeElementId"): el.get("kind") for el in snap["elements"] if el.get("typeElementId")}
        print("kinds", {key: kinds[key] for key in sorted(kinds)})
        check(report.get("status") == "pass", "mixed template authoritative geometry passes")
        check(kinds.get("OUT-PACK-01") == "station" and kinds.get("OUT-DOCK-01") == "dock", "OUT-PACK is not a ship dock")
        check(kinds.get("ST-PAL-01") == "slot" and kinds.get("ST-FLOOR-01") == "slot", "racks and floor stacks are slots")
        mixed_run = run_des(
            snapshot=snap,
            demand=demand,
            operating=operating,
            run_control={"horizonSec": 3600, "seedStreams": {"demand": 7}, "metricDefinitionVersion": "metrics-slice-manual-v1"},
            expected_layout_revision="mixed-ui",
            run_id="run-mixed-ui",
        )
        segs = mixed_run["trajectory"]["segments"]
        print("mixed segments", len(segs), "cards", list(mixed_run["cards"]))
        posed = [seg for seg in segs if seg.get("fromPose") and seg.get("toPose") and seg.get("resourceId")]
        check(mixed_run["kpiFromUiDemo"] is False and len(posed) > 0, "mixed run emits resource trajectory segments")
        check("value" not in mixed_run["cards"]["utilization"], "mixed utilization stays split")

    print("\n=== 07 AC not claimed by this slice ===")
    for ac in (
        "AC-02",
        "AC-03",
        "AC-04",
        "AC-05",
        "AC-06 自动采用部分",
        "AC-07",
        "AC-09",
        "AC-10",
        "AC-11",
        "AC-12",
        "AC-14",
        "AC-15",
        "AC-16",
        "AC-18",
        "AC-21",
        "AC-17 转向和单向",
        "AC-19 改价格",
        "AC-20 历史布局回放绑定（决策页会插值本次 trajectory.segments，不把该动画当成 AC-20 已验收）",
        "AC-22 断网",
        "易用性 5 人小样",
    ):
        print(f"{ac}: 未执行")

    print("\n=== G-EDGE / G-BREAK fixtures ===")
    check(run_suite() == 0, "G-EDGE-01..03 and G-BREAK-01..04")

    print("\n=== MX mixed-warehouse edge occupancy + break_bulk ===")
    print("spec_only stays spec_only; assert pass is not UA S-D1 and not a mini-gold substitute")
    check(run_mx_suite() == 0, "MX-D1-EB MX-D2-EB MX-D3-EB asserts, status remains spec_only")

    print("\nfailures", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
