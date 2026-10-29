"""simapp API — M2 可选自动规划：场地确认 / PlanningJob / 采用与局部重排。

手动路径（M1）仍独立可用；quick 评估不宣称运营效率。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from simapp_derive import derive_layout_snapshot, derived_index, input_fingerprint
from simapp_plan import adopt_candidate, run_planning_job
from simapp_plan.confirm import FacilityGateError, assert_facility_usable_for_planning, facility_confirmation_status
from simapp_plan.locks import LockConflictError, assert_locks_preserved
from simapp_validate import is_simulation_ready, validate_layout

from .store import STORE, RevisionConflict

CONTRACT_VERSION = "0.3"
ROOT = Path(__file__).resolve().parents[3]

app = FastAPI(
    title="simapp API",
    version="0.3.2",
    description="M2 optional planning: facility confirm, PlanningJob, adopt/replan; M1 manual path intact.",
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
    sync: bool = True


class PutFacilityRequest(BaseModel):
    facility: Dict[str, Any]
    drawingId: Optional[str] = None


class PutDrawingRequest(BaseModel):
    filename: str = Field(min_length=1)
    meta: Dict[str, Any] = Field(default_factory=dict)
    # meta.metersPerPixel 或 meta.scaleDeclared=true 表示已标定
    status: str = Field(default="uploaded")  # uploaded | calibrated | rejected


class PutDemandRequest(BaseModel):
    projectId: str
    demand: Dict[str, Any]


class PlanningDraftRequest(BaseModel):
    draftId: Optional[str] = None
    request: Dict[str, Any]


class AdoptCandidateRequest(BaseModel):
    projectId: str
    currentVariantRef: RevisionRef
    newName: str = Field(min_length=1)
    # 乐观锁：须与当前 variant.revision 字符串相等
    expectedVariantRevision: Optional[str] = None


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
        "milestone": "M2",
        "capabilities": {
            "manualLayout": True,
            "deriveValidate": True,
            "planning": True,
            "planningScope": "DEC-05 ambient single-floor axis-aligned + ST-PAL-01",
            "evaluationLevel": ["quick"],
            "des": False,
            "kpiFromUiDemo": False,
            "claimsOperationalEfficiency": False,
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
        "drawingCount": len(rec.drawings),
    }


@app.post("/api/v1/projects/{project_id}/drawings", status_code=201)
def put_drawing(project_id: str, body: PutDrawingRequest) -> Dict[str, Any]:
    """DEV-06 切片：登记底图元数据。上传 ≠ 确认；未标定不得当正式几何。"""
    if not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)
    drawing_id = f"drawing-{uuid4().hex[:8]}"
    status = body.status
    meta = dict(body.meta)
    calibrated = bool(meta.get("metersPerPixel") or meta.get("scaleDeclared") is True)
    if status == "calibrated" and not calibrated:
        raise _error(
            "INPUT_UNCONFIRMED",
            "声明 calibrated 须提供 metersPerPixel 或 scaleDeclared",
            details={"fieldPaths": ["meta.metersPerPixel", "meta.scaleDeclared"]},
        )
    if calibrated and status == "uploaded":
        status = "calibrated"
    drawing = {
        "id": drawing_id,
        "projectId": project_id,
        "filename": body.filename,
        "status": status,
        "meta": meta,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "note": "文件内容本切片仅存元数据；上传不等于场地确认",
    }
    return STORE.put_drawing(project_id, drawing)


@app.get("/api/v1/projects/{project_id}/drawings/{drawing_id}")
def get_drawing(project_id: str, drawing_id: str) -> Dict[str, Any]:
    doc = STORE.get_drawing(project_id, drawing_id)
    if not doc:
        raise _error("NOT_FOUND", "drawing not found", status=404)
    return doc


@app.post("/api/v1/projects/{project_id}/facility-revisions", status_code=201)
def put_facility(project_id: str, body: PutFacilityRequest) -> Dict[str, Any]:
    if not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)
    facility = body.facility
    if facility.get("contractVersion") != CONTRACT_VERSION:
        raise _error("CONTRACT_VERSION", "facility contractVersion must be 0.3")
    drawing = STORE.get_drawing(project_id, body.drawingId) if body.drawingId else None
    saved = STORE.put_facility(project_id, facility)
    confirm = facility_confirmation_status(saved)
    gate: Dict[str, Any] = {
        "confirmationStatus": confirm,
        "usableForValidatedPlanning": False,
        "reason": None,
    }
    try:
        support = assert_facility_usable_for_planning(saved, drawing=drawing, require_confirmed=True)
        gate["usableForValidatedPlanning"] = True
        gate["support"] = support
    except FacilityGateError as exc:
        gate["reason"] = {"code": exc.code, "message": exc.message, "details": exc.details}
    return {"facility": saved, "gate": gate, "drawingId": body.drawingId}


@app.get("/api/v1/projects/{project_id}/facility-revisions/{revision}")
def get_facility(project_id: str, revision: str) -> Dict[str, Any]:
    doc = STORE.get_facility(project_id, revision)
    if not doc:
        raise _error("NOT_FOUND", "facility revision not found", status=404)
    return doc


@app.post("/api/v1/demands", status_code=201)
def put_demand(body: PutDemandRequest) -> Dict[str, Any]:
    demand = body.demand
    if demand.get("contractVersion") != CONTRACT_VERSION:
        raise _error("CONTRACT_VERSION", "demand contractVersion must be 0.3")
    project_id = body.projectId
    if not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)
    return STORE.put_demand(project_id, demand)


@app.post("/api/v1/projects/{project_id}/planning-drafts", status_code=201)
def save_planning_draft(project_id: str, body: PlanningDraftRequest) -> Dict[str, Any]:
    """DEV-07：向导草稿；关闭重开不丢。"""
    if not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)
    draft_id = body.draftId or f"draft-{uuid4().hex[:8]}"
    req = dict(body.request)
    req["projectId"] = project_id
    # 缺数据目标禁用原因
    disabled_goals: List[Dict[str, str]] = []
    goals = list(req.get("goals") or [])
    if "cost" in goals and not req.get("priceBookRef"):
        disabled_goals.append({"goal": "cost", "reason": "缺少 priceBookRef；不填假价格"})
    if "efficiency" in goals and req.get("evaluationLevel") != "detailed":
        disabled_goals.append(
            {
                "goal": "efficiency",
                "reason": "运营效率需 M3 DES（evaluationLevel=detailed）；M2 quick 不可宣称",
            }
        )
    saved = STORE.put_planning_draft(project_id, draft_id, req)
    return {**saved, "disabledGoals": disabled_goals}


@app.get("/api/v1/projects/{project_id}/planning-drafts/{draft_id}")
def get_planning_draft(project_id: str, draft_id: str) -> Dict[str, Any]:
    doc = STORE.get_planning_draft(project_id, draft_id)
    if not doc:
        raise _error("NOT_FOUND", "planning draft not found", status=404)
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
    except Exception as exc:  # noqa: BLE001
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


@app.post("/api/v1/planning-jobs", status_code=202)
def create_planning_job(request: Dict[str, Any]) -> Dict[str, Any]:
    """DEV-07/08：提交 PlanningRequest；M2 默认同步完成搜索。"""
    if request.get("contractVersion") != CONTRACT_VERSION:
        raise _error("CONTRACT_VERSION", "PlanningRequest contractVersion must be 0.3")
    project_id = request.get("projectId")
    if not project_id or not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)

    facility_ref = request.get("facilityRef") or {}
    facility = STORE.get_facility(project_id, facility_ref.get("revision"))
    if not facility or facility.get("id") != facility_ref.get("id"):
        raise _error("NOT_FOUND", "facility revision not found", status=404)

    demand = None
    demand_ref = request.get("demandRef") or {}
    if demand_ref.get("id"):
        demand = STORE.get_demand(project_id, demand_ref["id"], demand_ref.get("revision"))

    base_layout = None
    base_variant_ref = request.get("baseVariantRef") or {}
    if base_variant_ref.get("id"):
        variant = STORE.get_variant(project_id, base_variant_ref["id"])
        if variant:
            if (
                base_variant_ref.get("revision")
                and variant.get("revision") != base_variant_ref.get("revision")
            ):
                # 来源变更：仍可规划，但标记 staleBase
                pass
            lr = variant.get("layoutRef") or {}
            base_layout = STORE.get_layout(project_id, lr.get("id"), lr.get("revision"))

    result = run_planning_job(
        request,
        facility=facility,
        base_layout=base_layout,
        demand=demand,
        drawing=None,
    )
    job = result["job"]
    candidates = result["candidates"]
    STORE.attach_job(project_id, job)
    STORE.put_candidates(project_id, candidates)

    # 响应不嵌入完整 layoutDocument（列表摘要）；详情走 GET /candidates/{id}
    summaries = [
        {
            "id": c["id"],
            "feasibilityStatus": c["feasibilityStatus"],
            "evaluationLevel": c["evaluationLevel"],
            "claimsOperationalEfficiency": False,
            "metrics": c["metrics"],
            "layoutDocumentRef": c["layoutDocumentRef"],
            "searchManifestRef": c.get("searchManifestRef"),
        }
        for c in candidates
    ]
    return {
        "jobId": job["id"],
        "state": job["state"],
        "phase": job["phase"],
        "outcome": job["outcome"],
        "terminationReason": job.get("terminationReason"),
        "counts": job.get("counts"),
        "partialResults": job.get("partialResults"),
        "error": job.get("error"),
        "resultRefs": job.get("resultRefs"),
        "candidates": summaries,
        "note": "quick 评估≠运营效率验证；手动路径仍可独立使用",
    }


@app.get("/api/v1/planning-jobs/{job_id}/candidates")
def list_planning_candidates(job_id: str) -> Dict[str, Any]:
    project_id = STORE.project_id_for_job(job_id)
    if not project_id:
        raise _error("NOT_FOUND", f"job {job_id} not found", status=404)
    items = STORE.list_candidates(project_id, job_id)
    return {
        "jobId": job_id,
        "items": [
            {
                "id": c["id"],
                "feasibilityStatus": c["feasibilityStatus"],
                "evaluationLevel": c["evaluationLevel"],
                "claimsOperationalEfficiency": c.get("claimsOperationalEfficiency", False),
                "metrics": c["metrics"],
                "layoutDocumentRef": c["layoutDocumentRef"],
                "explanation": c.get("explanation"),
            }
            for c in items
            if c.get("feasibilityStatus") != "rejected"
        ],
    }


@app.get("/api/v1/candidates/{candidate_id}")
def get_candidate(candidate_id: str) -> Dict[str, Any]:
    cand = STORE.get_candidate(candidate_id)
    if not cand:
        raise _error("NOT_FOUND", "candidate not found", status=404)
    # 返回可编辑布局全文
    out = dict(cand)
    out.pop("derivedSnapshot", None)  # 体积；采用后重新 prepare
    return out


@app.post("/api/v1/candidates/{candidate_id}/adoptions", status_code=201)
def adopt(candidate_id: str, body: AdoptCandidateRequest) -> Dict[str, Any]:
    """DEV-09：采用 = 新方案分支；并发乐观锁不覆盖。"""
    cand = STORE.get_candidate(candidate_id)
    if not cand:
        raise _error("NOT_FOUND", "candidate not found", status=404)
    project_id = body.projectId
    if STORE.project_id_for_candidate(candidate_id) != project_id:
        raise _error("NOT_FOUND", "candidate not in project", status=404)

    current = STORE.get_variant(project_id, body.currentVariantRef.id)
    if not current:
        raise _error("NOT_FOUND", "current variant not found", status=404)

    expected_rev = body.expectedVariantRevision or body.currentVariantRef.revision
    if current.get("revision") != expected_rev:
        raise _error(
            "REVISION_CONFLICT",
            "工作副本已更新，采用不覆盖；请另存或基于最新 revision 重算",
            details={
                "variantId": current["id"],
                "expected": expected_rev,
                "actual": current.get("revision"),
            },
            status=409,
        )

    # 锁定再校验
    locks = list((cand.get("layoutDocument") or {}).get("locks") or [])
    base_variant = current
    base_layout_ref = base_variant.get("layoutRef") or {}
    base_layout = STORE.get_layout(project_id, base_layout_ref.get("id"), base_layout_ref.get("revision"))
    if locks and base_layout:
        try:
            assert_locks_preserved(
                base_layout.get("elements") or [],
                (cand.get("layoutDocument") or {}).get("elements") or [],
                locks,
            )
        except LockConflictError as exc:
            raise _error("LOCK_CONFLICT", exc.message, details=exc.details) from exc

    adopted = adopt_candidate(candidate=cand, new_name=body.newName, project_id=project_id)
    layout_doc = adopted["layoutDocument"]
    try:
        STORE.put_layout_revision(project_id, layout_doc, base_revision=None)
    except RevisionConflict as exc:
        raise _error(
            "REVISION_CONFLICT",
            exc.message,
            details={"layoutId": exc.layout_id, "expected": exc.expected, "actual": exc.actual},
            status=409,
        ) from exc
    variant = STORE.put_variant(project_id, adopted["variant"])
    return {
        "variant": variant,
        "layoutRef": variant["layoutRef"],
        "instanceMap": adopted["instanceMap"],
        "diff": cand.get("diff"),
        "note": adopted["note"],
        "claimsOperationalEfficiency": False,
    }


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


@app.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> Dict[str, Any]:
    job = STORE.get_job(job_id)
    if not job:
        raise _error("NOT_FOUND", f"job {job_id} not found", status=404)
    state = job.get("state")
    if state in {"succeeded", "failed", "cancelled"}:
        return job
    project_id = STORE.project_id_for_job(job_id)
    job["state"] = "cancelled"
    job["outcome"] = "cancelled"
    job["terminationReason"] = "cancelled"
    job["finishedAt"] = datetime.now(timezone.utc).isoformat()
    if project_id:
        STORE.attach_job(project_id, job)
    return job
