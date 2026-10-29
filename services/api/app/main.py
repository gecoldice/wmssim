"""simapp API — M1 手动布局路径：项目/版本/派生校验/推演准备。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from simapp_derive import derive_layout_snapshot, derived_index, input_fingerprint
from simapp_validate import is_simulation_ready, validate_layout

from .store import STORE, RevisionConflict

CONTRACT_VERSION = "0.3"
ROOT = Path(__file__).resolve().parents[3]

app = FastAPI(
    title="simapp API",
    version="0.3.1",
    description="M1 manual layout path: project/workbench/layoutRevision + derive/validate.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1)
    unitSystem: str = Field(pattern="^metric$")


class Project(BaseModel):
    contractVersion: str
    id: str
    name: str
    unitSystem: str
    createdAt: str


class RevisionRef(BaseModel):
    id: str
    revision: str


class SaveLayoutRevisionRequest(BaseModel):
    baseRevision: Optional[str] = None
    projectId: str
    document: Dict[str, Any]


class CreateVariantRequest(BaseModel):
    name: str
    source: str = Field(pattern="^(manual|template|generated|edited)$")
    layoutRef: RevisionRef
    operatingRef: Optional[RevisionRef] = None


class PrepareJobRequest(BaseModel):
    projectId: str
    layoutRef: RevisionRef
    facilityRef: RevisionRef
    ruleSetRefs: List[RevisionRef] = Field(default_factory=list)
    catalogRef: Optional[RevisionRef] = None
    sync: bool = True  # M1：默认同步完成派生+校验


class PutFacilityRequest(BaseModel):
    facility: Dict[str, Any]


def _error(code: str, message: str, *, details: Any = None, status: int = 422) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "code": code,
            "message": message,
            "details": details,
            "retryable": False,
            "traceId": None,
        },
    )


@app.get("/api/v1/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "contractVersion": CONTRACT_VERSION,
        "snapshotSchemaVersion": "0.2",
        "equipSchemaVersion": "0.2",
        "milestone": "M1",
        "capabilities": {
            "manualLayout": True,
            "deriveValidate": True,
            "planning": False,
            "des": False,
            "kpiFromUiDemo": False,
        },
        "contractsRoot": str(ROOT / "contracts"),
    }


@app.post("/api/v1/projects", status_code=201)
def create_project(body: CreateProjectRequest) -> Project:
    project = STORE.create_project(body.name, body.unitSystem)
    return Project(**project)


@app.get("/api/v1/projects/{project_id}")
def get_project(project_id: str) -> Dict[str, Any]:
    project = STORE.get_project(project_id)
    if not project:
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)
    rec = STORE.projects[project_id]
    return {
        **project,
        "facilityHead": rec.facility_head,
        "layoutHeads": dict(rec.layout_heads),
        "variantCount": len(rec.variants),
    }


@app.post("/api/v1/projects/{project_id}/facility-revisions", status_code=201)
def put_facility(project_id: str, body: PutFacilityRequest) -> Dict[str, Any]:
    if not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)
    facility = body.facility
    if facility.get("contractVersion") != CONTRACT_VERSION:
        raise _error("CONTRACT_VERSION", "facility contractVersion must be 0.3")
    return STORE.put_facility(project_id, facility)


@app.get("/api/v1/projects/{project_id}/facility-revisions/{revision}")
def get_facility(project_id: str, revision: str) -> Dict[str, Any]:
    doc = STORE.get_facility(project_id, revision)
    if not doc:
        raise _error("NOT_FOUND", "facility revision not found", status=404)
    return doc


@app.post("/api/v1/projects/{project_id}/variants", status_code=201)
def create_variant(project_id: str, body: CreateVariantRequest) -> Dict[str, Any]:
    if not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)
    layout = STORE.get_layout(project_id, body.layoutRef.id, body.layoutRef.revision)
    if not layout:
        raise _error("NOT_FOUND", "layout revision not found", status=404)
    variant = {
        "contractVersion": CONTRACT_VERSION,
        "id": f"variant-{uuid4().hex[:8]}",
        "revision": f"vr-{uuid4().hex[:6]}",
        "name": body.name,
        "source": body.source,
        "layoutRef": body.layoutRef.model_dump(),
        "operatingRef": body.operatingRef.model_dump() if body.operatingRef else None,
        "parentRef": None,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "prepareStatus": "saved",
        "simulationReady": False,
    }
    return STORE.put_variant(project_id, variant)


@app.get("/api/v1/projects/{project_id}/variants")
def list_variants(project_id: str) -> Dict[str, Any]:
    if not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)
    return {"items": STORE.list_variants(project_id)}


@app.post("/api/v1/layouts/{layout_id}/revisions", status_code=201)
def save_layout_revision(layout_id: str, body: SaveLayoutRevisionRequest) -> Dict[str, Any]:
    if not STORE.get_project(body.projectId):
        raise _error("NOT_FOUND", f"project {body.projectId} not found", status=404)
    document = dict(body.document)
    if document.get("id") != layout_id:
        raise _error("INPUT_UNCONFIRMED", "document.id must match path layout_id")
    if document.get("contractVersion") != CONTRACT_VERSION:
        raise _error("CONTRACT_VERSION", "layout contractVersion must be 0.3")
    try:
        saved = STORE.put_layout_revision(
            body.projectId, document, base_revision=body.baseRevision
        )
    except RevisionConflict as exc:
        raise _error(
            "REVISION_CONFLICT",
            exc.message,
            details={"layoutId": exc.layout_id, "expected": exc.expected, "actual": exc.actual},
            status=409,
        ) from exc
    return {
        "layoutRef": {"id": saved["id"], "revision": saved["revision"]},
        "document": saved,
        "prepareStatus": "saved",
        "simulationReady": False,
        "note": "保存成功；需 prepare 后才可进入推演准备",
    }


@app.get("/api/v1/layouts/{layout_id}/revisions/{revision}")
def get_layout_revision(layout_id: str, revision: str, projectId: str) -> Dict[str, Any]:
    doc = STORE.get_layout(projectId, layout_id, revision)
    if not doc:
        raise _error("NOT_FOUND", "layout revision not found", status=404)
    prepare = STORE.get_prepare_result(projectId, layout_id, revision)
    return {
        "document": doc,
        "prepare": prepare,
        "simulationReady": bool(prepare and prepare.get("simulationReady")),
    }


@app.post("/api/v1/layouts/{layout_id}/prepare-jobs", status_code=202)
def prepare_layout(layout_id: str, body: PrepareJobRequest) -> Dict[str, Any]:
    """派生货位/通道/accessNode + 权威校验；通过则 simulationReady。"""
    if body.layoutRef.id != layout_id:
        raise _error("INPUT_UNCONFIRMED", "layoutRef.id must match path")
    if not STORE.get_project(body.projectId):
        raise _error("NOT_FOUND", f"project {body.projectId} not found", status=404)

    layout = STORE.get_layout(body.projectId, layout_id, body.layoutRef.revision)
    if not layout:
        raise _error("NOT_FOUND", "layout revision not found", status=404)
    facility = STORE.get_facility(body.projectId, body.facilityRef.revision)
    if not facility:
        # 允许请求体侧已注册；否则 404
        raise _error("NOT_FOUND", "facility revision not found — POST facility-revisions first", status=404)
    if facility.get("id") != body.facilityRef.id:
        raise _error("INPUT_UNCONFIRMED", "facilityRef.id mismatch")

    job_id = f"job-{uuid4().hex[:10]}"
    job: Dict[str, Any] = {
        "id": job_id,
        "kind": "prepare",
        "state": "running",
        "phase": "derivation",
        "outcome": None,
        "layoutRef": body.layoutRef.model_dump(),
        "facilityRef": body.facilityRef.model_dump(),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "resultRefs": None,
    }
    STORE.attach_job(body.projectId, job)

    try:
        snapshot = derive_layout_snapshot(
            layout,
            facility,
            layout_id=layout_id,
            layout_revision=body.layoutRef.revision,
        )
        index = derived_index(snapshot, layout)
        job["phase"] = "validation"
        STORE.attach_job(body.projectId, job)

        refs = [r.model_dump() for r in body.ruleSetRefs]
        report = validate_layout(
            snapshot,
            facility,
            layout,
            rule_set_refs=refs or None,
        )
        ready = is_simulation_ready(report)
        prepare_payload = {
            "prepareStatus": "ready" if ready else "failed",
            "simulationReady": ready,
            "layoutRevision": body.layoutRef.revision,
            "inputFingerprint": report.get("inputFingerprint")
            or input_fingerprint(layout, facility, refs),
            "derivedLayout": {
                "layoutRef": body.layoutRef.model_dump(),
                "facilityRef": body.facilityRef.model_dump(),
                "derivationVersion": snapshot.get("validation", {}).get("derivationVersion"),
                "layoutSnapshot": snapshot,
                "derivedIndex": index,
            },
            "validationReport": report,
        }
        STORE.save_prepare_result(
            body.projectId, layout_id, body.layoutRef.revision, prepare_payload
        )
        job["state"] = "succeeded"
        job["phase"] = "validation"
        job["outcome"] = "ready" if ready else "validation_failed"
        job["finishedAt"] = datetime.now(timezone.utc).isoformat()
        job["resultRefs"] = {
            "prepareStatus": prepare_payload["prepareStatus"],
            "simulationReady": ready,
            "validationReportId": report["id"],
            "validationStatus": report["status"],
            "layoutRevision": body.layoutRef.revision,
        }
        STORE.attach_job(body.projectId, job)
        return {
            "jobId": job_id,
            "state": job["state"],
            "outcome": job["outcome"],
            "simulationReady": ready,
            "prepareStatus": prepare_payload["prepareStatus"],
            "validationStatus": report["status"],
            "layoutRevision": body.layoutRef.revision,
            "validationReport": report,
            "derivedLayout": prepare_payload["derivedLayout"],
        }
    except Exception as exc:  # noqa: BLE001 — surface as job failure
        job["state"] = "failed"
        job["error"] = {
            "code": "COMPUTATION_FAILED",
            "message": str(exc),
            "details": None,
            "retryable": True,
            "traceId": None,
        }
        job["finishedAt"] = datetime.now(timezone.utc).isoformat()
        STORE.attach_job(body.projectId, job)
        raise _error("COMPUTATION_FAILED", str(exc), status=500) from exc


@app.get("/api/v1/layouts/{layout_id}/prepare")
def get_prepare(layout_id: str, projectId: str, revision: str) -> Dict[str, Any]:
    data = STORE.get_prepare_result(projectId, layout_id, revision)
    if not data:
        raise _error("NOT_FOUND", "prepare result not found — run prepare-jobs", status=404)
    return data


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = STORE.get_job(job_id)
    if not job:
        return {
            "id": job_id,
            "state": "failed",
            "phase": None,
            "outcome": None,
            "error": {
                "code": "NOT_FOUND",
                "message": f"job {job_id} not found",
                "details": None,
                "retryable": False,
                "traceId": None,
            },
        }
    return job
