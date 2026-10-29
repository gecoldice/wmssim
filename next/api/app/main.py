"""Manual-slice HTTP API.

Only the endpoints in the rewrite plan, plus the read halves needed to reload a
saved layout. Planning, cost, compare, and recognition are not registered.
Prepare and simulation return 202 and a jobId; the worker is in-process.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from des.derive import derive_snapshot
from des.engine import run_des
from des.errors import DesError
from des.validate import validate_layout

from .contracts import schema_errors
from .store import Store, issue_revision

FORMAL = re.compile(r"^[A-Z]+(-[A-Z]+)+-[0-9]{2}$")
DATA = os.environ.get("NEXT_STORE")
store = Store(Path(DATA) if DATA else None)

app = FastAPI(title="仓序 manual slice", version="slice-0.1", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error(status: int, code: str, message: str, details: Optional[Dict[str, Any]] = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "details": details or {},
            "retryable": status >= 500,
            "traceId": None,
        },
    )


def _job_view(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jobId": job["jobId"],
        "kind": job["kind"],
        "status": job["status"],
        "kpiFromUiDemo": False,
        "result": job.get("result"),
        "error": job.get("error"),
    }


def _fingerprint(demand: Dict[str, Any], operating: Dict[str, Any], run_control: Dict[str, Any]) -> str:
    payload = {
        "flows": demand.get("flows"),
        "initialInventory": demand.get("initialInventory"),
        "arrivalProfile": demand.get("arrivalProfile"),
        "resourcePools": [
            {
                "id": p.get("id"),
                "resourceType": p.get("resourceType"),
                "count": p.get("count"),
            }
            for p in (operating.get("resourcePools") or [])
        ],
        "serviceParameters": operating.get("serviceParameters"),
        "horizonSec": run_control.get("horizonSec"),
        "seedStreams": run_control.get("seedStreams"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _outbound_qty(demand: Dict[str, Any]) -> float:
    total = 0.0
    for flow in demand.get("flows") or []:
        if flow.get("flowKind") == "full_pallet" and flow.get("intent") in {"outbound", "outbound_ship"}:
            total += float(flow.get("quantity") or 0)
        elif flow.get("flowKind") == "full_pallet" and flow.get("source") in {"storage", "inventory"}:
            total += float(flow.get("quantity") or 0)
    return total


def _spawn(job_id: str, target) -> None:
    def runner() -> None:
        with store.lock:
            job = store.jobs[job_id]
            job["status"] = "running"
            store.persist()
        try:
            target()
        except DesError as exc:
            with store.lock:
                job = store.jobs[job_id]
                job["status"] = "failed"
                job["error"] = {"code": exc.code, "message": exc.message, "details": exc.details}
                job["result"] = None
                store.persist()
        except Exception as exc:  # noqa: BLE001 — surface as a failed job, not a hung poll
            with store.lock:
                job = store.jobs[job_id]
                job["status"] = "failed"
                job["error"] = {"code": "COMPUTATION_FAILED", "message": str(exc), "details": {}}
                store.persist()

    threading.Thread(target=runner, daemon=True).start()


@app.get("/api/v1/health")
def health() -> Dict[str, Any]:
    return {"slice": "manual", "planning": False, "kpiFromUiDemo": False, "engineVersion": "slice-des-0.1"}


@app.post("/api/v1/projects", status_code=201)
def create_project(body: Dict[str, Any]) -> Any:
    name = (body or {}).get("name") or ""
    if not str(name).strip():
        return _error(422, "INPUT_UNCONFIRMED", "项目名称未填写")
    if body.get("unitSystem") not in (None, "metric"):
        return _error(422, "INPUT_UNCONFIRMED", "本切片只接受米制")
    from datetime import datetime, timezone

    project = {
        "contractVersion": "0.3",
        "id": issue_revision("pj"),
        "name": str(name).strip(),
        "unitSystem": "metric",
        "createdAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    problems = schema_errors(project, "v0.3/project.schema.json")
    if problems:
        return _error(422, "INPUT_UNCONFIRMED", "项目文档未通过 schema", {"problems": problems})
    with store.lock:
        store.projects[project["id"]] = project
        store.persist()
    return project


@app.get("/api/v1/projects/{project_id}")
def get_project(project_id: str) -> Any:
    with store.lock:
        project = store.projects.get(project_id)
        if not project:
            return _error(404, "INPUT_UNCONFIRMED", "项目不存在")
        facility = store.facilities.get(project_id)
        layouts = [
            {"id": lid, "revision": row["revision"]}
            for lid, row in store.layouts.items()
            if row.get("projectId") == project_id
        ]
        return {
            "project": project,
            "facilityRef": (
                {"id": facility["document"]["id"], "revision": facility["revision"]} if facility else None
            ),
            "layouts": layouts,
        }


@app.post("/api/v1/projects/{project_id}/facility-revisions", status_code=201)
def save_facility(project_id: str, body: Dict[str, Any]) -> Any:
    with store.lock:
        if project_id not in store.projects:
            return _error(404, "INPUT_UNCONFIRMED", "项目不存在")
        facility = deepcopy((body or {}).get("facility") or {})
        current = store.facilities.get(project_id)
        claimed = (body or {}).get("baseRevision")
        if claimed is None:
            claimed = facility.get("revision") if current else None
        if current and claimed != current["revision"]:
            return _error(
                409,
                "REVISION_CONFLICT",
                "场地修订与服务器已存修订不一致，未覆盖",
                {"expected": current["revision"], "actual": claimed},
            )
        facility["contractVersion"] = "0.3"
        facility.setdefault("id", f"facility-{project_id}")
        facility["revision"] = current["revision"] if current else "pending"
        problems = schema_errors(facility, "v0.3/facility-revision.schema.json")
        if problems:
            return _error(422, "INPUT_UNCONFIRMED", "场地未通过 schema", {"problems": problems})
        new_rev = issue_revision("fr")
        facility["revision"] = new_rev
        facility["parentRef"] = (
            {"id": current["document"]["id"], "revision": current["revision"]} if current else None
        )
        store.facilities[project_id] = {"revision": new_rev, "document": facility}
        store.persist()
        return {"facilityRef": {"id": facility["id"], "revision": new_rev}, "facility": facility}


@app.get("/api/v1/projects/{project_id}/facility")
def get_facility(project_id: str) -> Any:
    with store.lock:
        row = store.facilities.get(project_id)
        if not row:
            return _error(404, "INPUT_UNCONFIRMED", "还没有场地")
        return {"facilityRef": {"id": row["document"]["id"], "revision": row["revision"]}, "facility": row["document"]}


@app.post("/api/v1/layouts/{layout_id}/revisions", status_code=201)
def save_layout(layout_id: str, body: Dict[str, Any]) -> Any:
    project_id = (body or {}).get("projectId")
    document = deepcopy((body or {}).get("document") or {})
    with store.lock:
        if project_id not in store.projects:
            return _error(404, "INPUT_UNCONFIRMED", "项目不存在")
        if store.facilities.get(project_id) is None:
            return _error(422, "INPUT_UNCONFIRMED", "请先保存场地")
        current = store.layouts.get(layout_id)
        claimed = (body or {}).get("baseRevision")
        if current is None:
            if claimed not in (None, ""):
                return _error(409, "REVISION_CONFLICT", "布局尚无修订，不能带着旧修订覆盖")
        else:
            if claimed != current["revision"]:
                return _error(
                    409,
                    "REVISION_CONFLICT",
                    "布局修订与服务器已存修订不一致，未覆盖",
                    {"stored": current["revision"], "baseRevision": claimed},
                )
            if document.get("revision") and document.get("revision") != current["revision"]:
                return _error(
                    409,
                    "REVISION_CONFLICT",
                    "请求体里的 revision 与已存修订冲突，未覆盖",
                    {"stored": current["revision"], "revision": document.get("revision")},
                )
        for el in document.get("elements") or []:
            tid = el.get("typeElementId") or ""
            if not FORMAL.match(tid):
                return _error(
                    422,
                    "ELEMENT_ID",
                    f"类型 ID 必须是正式 ID，拒绝 {tid}",
                    {"typeElementId": tid, "instanceId": el.get("instanceId")},
                )
        facility = store.facilities[project_id]["document"]
        document["contractVersion"] = "0.3"
        document["id"] = layout_id
        document["facilityRef"] = {"id": facility["id"], "revision": facility["revision"]}
        document["revision"] = current["revision"] if current else "pending"
        document.setdefault("parentRef", None)
        document.setdefault("locks", [])
        document.setdefault("aisles", [])
        document.setdefault("catalogVersion", "catalog-slice-manual")
        problems = schema_errors(document, "v0.3/layout-document-revision.schema.json")
        if problems:
            return _error(422, "INPUT_UNCONFIRMED", "布局未通过 schema", {"problems": problems})
        new_rev = issue_revision("lr")
        document["revision"] = new_rev
        document["parentRef"] = (
            {"id": layout_id, "revision": current["revision"]} if current else None
        )
        store.layouts[layout_id] = {
            "projectId": project_id,
            "revision": new_rev,
            "document": document,
            "prepared": {},
        }
        store.persist()
        return {
            "layoutRef": {"id": layout_id, "revision": new_rev},
            "document": document,
            "kpiFromUiDemo": False,
        }


@app.get("/api/v1/layouts/{layout_id}")
def get_layout(layout_id: str) -> Any:
    with store.lock:
        row = store.layouts.get(layout_id)
        if not row:
            return _error(404, "INPUT_UNCONFIRMED", "布局不存在")
        ready = (row.get("prepared") or {}).get(row["revision"]) or {}
        return {
            "layoutRef": {"id": layout_id, "revision": row["revision"]},
            "document": row["document"],
            "projectId": row["projectId"],
            "simulationReady": bool(ready.get("simulationReady")),
        }


@app.post("/api/v1/layouts/{layout_id}/prepare-jobs", status_code=202)
def prepare_layout(layout_id: str, body: Dict[str, Any]) -> Any:
    with store.lock:
        row = store.layouts.get(layout_id)
        if not row:
            return _error(404, "INPUT_UNCONFIRMED", "布局不存在")
        layout_ref = (body or {}).get("layoutRef") or {}
        if layout_ref.get("id") not in (None, layout_id):
            return _error(422, "INPUT_UNCONFIRMED", "layoutRef.id 与路径不一致")
        if layout_ref.get("revision") and layout_ref.get("revision") != row["revision"]:
            return _error(
                409,
                "LAYOUT_REVISION_MISMATCH",
                "准备请求的修订与当前布局修订不相等",
                {"stored": row["revision"], "revision": layout_ref.get("revision")},
            )
        facility = store.facilities.get(row["projectId"])
        if not facility:
            return _error(422, "INPUT_UNCONFIRMED", "项目没有场地")
        job_id = issue_revision("job")
        revision = row["revision"]
        document = deepcopy(row["document"])
        facility_doc = deepcopy(facility["document"])
        store.jobs[job_id] = {
            "jobId": job_id,
            "kind": "prepare",
            "status": "queued",
            "result": None,
            "error": None,
        }
        store.persist()

    def work() -> None:
        snapshot = derive_snapshot(document, facility_doc, layout_revision=revision)
        if snapshot.get("schemaVersion") != "0.2":
            raise DesError("CONTRACT_VERSION", "派生快照版本不是 0.2")
        problems = schema_errors(snapshot, "v0.2/layout-snapshot.schema.json")
        if problems:
            raise DesError("COMPUTATION_FAILED", "派生快照未通过 schema", {"problems": problems})
        report = validate_layout(snapshot, facility_doc, document)
        ready = report["status"] == "pass"
        with store.lock:
            current = store.layouts.get(layout_id)
            if current and current["revision"] == revision:
                current.setdefault("prepared", {})[revision] = {
                    "simulationReady": ready,
                    "snapshot": snapshot,
                    "validationReport": report,
                }
            job = store.jobs[job_id]
            job["status"] = "succeeded"
            job["result"] = {
                "simulationReady": ready,
                "layoutRef": {"id": layout_id, "revision": revision},
                "validationReport": report,
                "snapshot": snapshot,
                "kpiFromUiDemo": False,
            }
            store.persist()

    _spawn(job_id, work)
    return {"jobId": job_id, "status": "queued", "kind": "prepare", "kpiFromUiDemo": False}


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> Any:
    with store.lock:
        job = store.jobs.get(job_id)
        if not job:
            return _error(404, "INPUT_UNCONFIRMED", "任务不存在")
        return _job_view(job)


@app.post("/api/v1/simulation-jobs", status_code=202)
def simulate(body: Dict[str, Any]) -> Any:
    layout_ref = (body or {}).get("layoutRef") or {}
    demand = (body or {}).get("demand") or {}
    operating = (body or {}).get("operating") or {}
    run_control = (body or {}).get("runControl") or {}
    for flow in demand.get("flows") or []:
        if flow.get("flowKind") != "full_pallet":
            return _error(
                422,
                "UNSUPPORTED_SCENARIO",
                f"本切片只接受整托 full_pallet，收到 {flow.get('flowKind')}",
                {"flowKind": flow.get("flowKind")},
            )
    with store.lock:
        row = store.layouts.get(layout_ref.get("id"))
        if not row:
            return _error(404, "INPUT_UNCONFIRMED", "布局不存在")
        if layout_ref.get("revision") != row["revision"]:
            return _error(
                409,
                "LAYOUT_REVISION_MISMATCH",
                "推演绑定的布局修订与当前修订不相等",
                {"stored": row["revision"], "revision": layout_ref.get("revision")},
            )
        prepared = (row.get("prepared") or {}).get(row["revision"])
        if not prepared or not prepared.get("simulationReady"):
            checks = ((prepared or {}).get("validationReport") or {}).get("checks") or []
            ids = []
            for check in checks:
                if check.get("status") == "fail":
                    ids.extend(check.get("objectIds") or [])
            return _error(
                409,
                "NOT_SIMULATION_READY",
                "布局尚未准备通过，拒绝推演",
                {"objectIds": ids, "layoutRevision": row["revision"]},
            )
        demand = deepcopy(demand)
        operating = deepcopy(operating)
        demand["contractVersion"] = "0.3"
        operating["contractVersion"] = "0.3"
        demand.setdefault("id", "demand-inline")
        operating.setdefault("id", "op-inline")
        demand["revision"] = "pending"
        operating["revision"] = "pending"
        demand.setdefault("parentRef", None)
        operating.setdefault("parentRef", None)
        demand_problems = schema_errors(demand, "v0.3/demand-revision.schema.json")
        op_problems = schema_errors(operating, "v0.3/operating-profile-revision.schema.json")
        if demand_problems or op_problems:
            return _error(
                422,
                "INPUT_UNCONFIRMED",
                "需求或工况未通过 schema",
                {"demand": demand_problems, "operating": op_problems},
            )
        snapshot = deepcopy(prepared["snapshot"])
        if snapshot.get("schemaVersion") != "0.2":
            return _error(422, "CONTRACT_VERSION", "快照版本不是 0.2")
        expected = layout_ref["revision"]
        if snapshot.get("layoutRevision") != expected:
            return _error(
                409,
                "LAYOUT_REVISION_MISMATCH",
                "快照修订与请求修订不相等",
                {"snapshot": snapshot.get("layoutRevision"), "expected": expected},
            )
        job_id = issue_revision("job")
        run_id = issue_revision("run")
        store.jobs[job_id] = {
            "jobId": job_id,
            "kind": "simulation",
            "status": "queued",
            "result": None,
            "error": None,
        }
        store.persist()

    def work() -> None:
        demand["revision"] = issue_revision("dm")
        operating["revision"] = issue_revision("op")
        result = run_des(
            snapshot=snapshot,
            demand=demand,
            operating=operating,
            run_control=run_control,
            expected_layout_revision=expected,
            run_id=run_id,
        )
        if result.get("kpiFromUiDemo") is not False:
            raise DesError("COMPUTATION_FAILED", "kpiFromUiDemo 必须为 false")
        result["scenarioFingerprint"] = _fingerprint(demand, operating, run_control)
        result["demandOutboundQty"] = _outbound_qty(demand)
        result["kpiFromUiDemo"] = False
        with store.lock:
            store.runs[run_id] = result
            job = store.jobs[job_id]
            job["status"] = "succeeded"
            job["result"] = {"runId": run_id, "kpiFromUiDemo": False}
            store.persist()

    _spawn(job_id, work)
    return {"jobId": job_id, "status": "queued", "kind": "simulation", "kpiFromUiDemo": False}


@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str) -> Any:
    with store.lock:
        run = store.runs.get(run_id)
        if not run:
            return _error(404, "INPUT_UNCONFIRMED", "运行不存在")
        return run
