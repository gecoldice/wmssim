"""simapp API — M5 扩展失败路径 + M4 成本/比较 + M3 DES + M2 规划 + M1 手动路径。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from simapp_compare import (
    COMPARE_ENGINE_VERSION,
    CompareError,
    build_comparison,
    build_delivery_report,
    recommend_from_comparison,
)
from simapp_cost import COST_ENGINE_VERSION, CostError, estimate_cost, recommend_lowest_capex
from simapp_derive import derive_layout_snapshot, derived_index, input_fingerprint
from simapp_des import ENGINE_VERSION, DesError, run_des
from simapp_extend import EXTEND_VERSION, assess_advanced, assess_recognition
from simapp_plan import adopt_candidate, run_planning_job
from simapp_plan.confirm import FacilityGateError, assert_facility_usable_for_planning, facility_confirmation_status
from simapp_plan.locks import LockConflictError, assert_locks_preserved
from simapp_validate import is_simulation_ready, validate_layout

from .store import STORE, RevisionConflict

CONTRACT_VERSION = "0.3"
ROOT = Path(__file__).resolve().parents[3]

app = FastAPI(
    title="simapp API",
    version="0.3.5",
    description=(
        "M5 recognition/advanced explicit unsupported paths; "
        "M4 cost/BOM/compare/report; M3 DES; M2 planning; M1 manual prepare."
    ),
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


class PutOperatingRequest(BaseModel):
    projectId: str
    operating: Dict[str, Any]


class SimulationJobRequest(BaseModel):
    projectId: str
    variantRef: RevisionRef
    scenarioPackage: Dict[str, Any]
    # 可选内嵌；否则按 scenarioPackage 的 demandRef/operatingRef 从 store 取
    demand: Optional[Dict[str, Any]] = None
    operating: Optional[Dict[str, Any]] = None
    expectedLayoutRevision: Optional[str] = None
    validationRef: Optional[Dict[str, Any]] = None
    sync: bool = True


class PutPriceBookRequest(BaseModel):
    projectId: str
    priceBook: Dict[str, Any]


class PutCostBasisRequest(BaseModel):
    projectId: str
    costBasis: Dict[str, Any]


class PutScoreProfileRequest(BaseModel):
    projectId: str
    scoreProfile: Dict[str, Any]


class CostEstimateJobRequest(BaseModel):
    projectId: str
    variantRef: RevisionRef
    layoutRef: Optional[RevisionRef] = None
    priceBookRef: RevisionRef
    costBasisRef: RevisionRef
    operatingRef: Optional[RevisionRef] = None
    sync: bool = True


class ComparisonRequest(BaseModel):
    projectId: str
    mode: str = Field(pattern="^(layout_only|whole_solution)$")
    entries: List[Dict[str, Any]]
    commonBasis: Dict[str, Any] = Field(default_factory=dict)
    scoreProfileRef: Optional[RevisionRef] = None
    # 可选内嵌 scoreProfile（测试/夹具）
    scoreProfile: Optional[Dict[str, Any]] = None


class ReportRequest(BaseModel):
    projectId: str
    variantRef: RevisionRef
    layoutRef: RevisionRef
    runId: Optional[str] = None
    costEstimateId: Optional[str] = None
    comparisonId: Optional[str] = None
    format: str = Field(default="html", pattern="^html$")


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
        "milestone": "M5",
        "engineVersion": ENGINE_VERSION,
        "costEngineVersion": COST_ENGINE_VERSION,
        "compareEngineVersion": COMPARE_ENGINE_VERSION,
        "extendVersion": EXTEND_VERSION,
        "capabilities": {
            "manualLayout": True,
            "deriveValidate": True,
            "planning": True,
            "planningScope": "DEC-05 ambient single-floor axis-aligned + ST-PAL-01",
            "evaluationLevel": ["quick", "detailed"],
            "des": True,
            "kpiFromUiDemo": False,
            "claimsOperationalEfficiency": True,
            "fourCards": ["throughput", "wait", "utilization", "bottleneck"],
            "bomCost": True,
            "comparison": True,
            "comparisonModes": ["layout_only", "whole_solution"],
            "radarAxesM4": ["storage", "efficiency", "investment"],
            "deliveryReport": True,
            "missingPriceBlocksLowestCost": True,
            "missingAxisNoZeroFill": True,
            "recognitionImplemented": False,
            "nsga2Implemented": False,
            "lifecycleCostImplemented": False,
            "claimsUnimplementedM5": False,
            "recognition": {
                "dxfVectorExtract": False,
                "ocrAssist": False,
                "polygonHeightPartition": False,
            },
            "advanced": {
                "nsga2": False,
                "multiObjectiveBeyondBaseline": False,
                "lifecycleCost": False,
                "expansionScale": False,
                "operabilityScale": False,
                "calibratedAutomation": False,
                "claimsBenefitOverBaseline": False,
            },
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


@app.post("/api/v1/operating-profiles", status_code=201)
def put_operating(body: PutOperatingRequest) -> Dict[str, Any]:
    operating = body.operating
    if operating.get("contractVersion") != CONTRACT_VERSION:
        raise _error("CONTRACT_VERSION", "operating contractVersion must be 0.3")
    if not STORE.get_project(body.projectId):
        raise _error("NOT_FOUND", f"project {body.projectId} not found", status=404)
    return STORE.put_operating(body.projectId, operating)


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


@app.post("/api/v1/simulation-jobs", status_code=202)
def create_simulation_job(body: SimulationJobRequest) -> Dict[str, Any]:
    """DEV-10/11：在 simulationReady 的历史布局 Snapshot 上跑真实 DES。"""
    project_id = body.projectId
    if not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)

    scenario = body.scenarioPackage
    if scenario.get("contractVersion") != CONTRACT_VERSION:
        raise _error("CONTRACT_VERSION", "scenarioPackage contractVersion must be 0.3")

    variant = STORE.get_variant(project_id, body.variantRef.id)
    if not variant:
        raise _error("NOT_FOUND", "variant not found", status=404)
    if body.variantRef.revision and variant.get("revision") != body.variantRef.revision:
        raise _error(
            "REVISION_CONFLICT",
            "variant revision mismatch",
            details={
                "expected": body.variantRef.revision,
                "actual": variant.get("revision"),
            },
            status=409,
        )

    layout_ref = variant.get("layoutRef") or {}
    layout_id = layout_ref.get("id")
    layout_revision = layout_ref.get("revision")
    if not layout_id or not layout_revision:
        raise _error("INPUT_UNCONFIRMED", "variant 缺少 layoutRef")

    prepare = STORE.get_prepare_result(project_id, layout_id, layout_revision)
    if not prepare or not prepare.get("simulationReady"):
        raise _error(
            "NOT_SIMULATION_READY",
            "须先 prepare 且 validation pass（simulationReady）",
            details={"layoutId": layout_id, "revision": layout_revision},
            status=409,
        )

    derived = prepare.get("derivedLayout") or {}
    snapshot = derived.get("layoutSnapshot")
    if not snapshot:
        raise _error("NOT_FOUND", "prepare 结果缺 layoutSnapshot", status=404)

    expected_rev = (
        body.expectedLayoutRevision
        or scenario.get("expectedLayoutRevision")
        or layout_revision
    )
    if expected_rev != snapshot.get("layoutRevision"):
        raise _error(
            "LAYOUT_REVISION_MISMATCH",
            "expectedLayoutRevision 与历史快照 layoutRevision 不相等",
            details={"expected": expected_rev, "actual": snapshot.get("layoutRevision")},
        )

    demand = body.demand
    if demand is None:
        dref = scenario.get("demandRef") or {}
        demand = STORE.get_demand(project_id, dref.get("id"), dref.get("revision"))
    if not demand:
        raise _error("NOT_FOUND", "demand 未找到；请 POST /demands 或内嵌 demand", status=404)

    operating = body.operating
    if operating is None:
        oref = scenario.get("operatingRef") or {}
        operating = STORE.get_operating(project_id, oref.get("id"), oref.get("revision"))
    if not operating:
        raise _error(
            "NOT_FOUND",
            "operating 未找到；请 POST /operating-profiles 或内嵌 operating",
            status=404,
        )

    job_id = f"simjob-{uuid4().hex[:10]}"
    job: Dict[str, Any] = {
        "id": job_id,
        "kind": "simulation",
        "state": "running",
        "phase": "des",
        "outcome": None,
        "variantRef": body.variantRef.model_dump(),
        "layoutRef": {"id": layout_id, "revision": layout_revision},
        "scenarioId": scenario.get("scenarioId"),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "resultRefs": None,
    }
    STORE.attach_job(project_id, job)

    try:
        result = run_des(
            snapshot=snapshot,
            demand=demand,
            operating=operating,
            run_control=scenario.get("runControl") or {},
            expected_layout_revision=expected_rev,
            scenario_id=scenario.get("scenarioId"),
            variant_ref={"id": variant["id"], "revision": variant["revision"]},
            validation_ref=body.validationRef
            or {
                "validationReportId": (prepare.get("validationReport") or {}).get("id"),
                "status": (prepare.get("validationReport") or {}).get("status"),
            },
            faults=list(operating.get("faults") or scenario.get("faults") or []),
            skill_tags_present=any(
                bool(p.get("skillTags")) for p in (operating.get("resourcePools") or [])
            ),
            shift_schedule_present=bool(operating.get("shiftSchedule")),
        )
        # 回放绑定历史布局修订（不可指向当前草稿）
        result["replayBinding"] = {
            "layoutId": layout_id,
            "layoutRevision": layout_revision,
            "prepareInputFingerprint": prepare.get("inputFingerprint"),
            "note": "轨迹/KPI 绑定本次 prepare 的只读 Snapshot，不使用当前未 prepare 草稿",
        }
        STORE.put_run(project_id, result)
        job["state"] = "succeeded"
        job["outcome"] = "completed"
        job["finishedAt"] = datetime.now(timezone.utc).isoformat()
        job["resultRefs"] = {
            "runId": result["runId"],
            "layoutRevision": layout_revision,
            "engineVersion": result.get("engineVersion"),
        }
        STORE.attach_job(project_id, job)
        return {
            "jobId": job_id,
            "state": job["state"],
            "outcome": job["outcome"],
            "runId": result["runId"],
            "layoutRevision": layout_revision,
            "kpi": result["kpi"],
            "kpiEvidence": result["kpiEvidence"],
            "runManifest": result["runManifest"],
            "inventoryConservation": {
                k: result["inventoryConservation"][k]
                for k in (
                    "ok",
                    "initial",
                    "inbound",
                    "outbound",
                    "ending",
                    "loss",
                    "residual",
                    "formula",
                )
            },
            "trajectorySummary": {
                "segmentCount": len(result["trajectory"].get("segments") or []),
                "taskCount": len(result["trajectory"].get("tasks") or []),
                "layoutRevision": result["trajectory"].get("layoutRevision"),
            },
            "replayBinding": result["replayBinding"],
            "warnings": result["runManifest"].get("warnings"),
            "kpiFromUiDemo": False,
        }
    except DesError as exc:
        job["state"] = "failed"
        job["outcome"] = "rejected"
        job["error"] = {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "retryable": False,
            "traceId": None,
        }
        job["finishedAt"] = datetime.now(timezone.utc).isoformat()
        STORE.attach_job(project_id, job)
        raise _error(exc.code, exc.message, details=exc.details, status=422) from exc
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
        STORE.attach_job(project_id, job)
        raise _error("COMPUTATION_FAILED", str(exc), status=500) from exc


@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    """RunManifest + 四卡 + 事件证据 + 轨迹；回放绑历史 layoutRevision。"""
    run = STORE.get_run(run_id)
    if not run:
        raise _error("NOT_FOUND", f"run {run_id} not found", status=404)
    return run


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


# ----- M4：PriceBook / CostBasis / CostEstimate / Comparison / Report -----


@app.post("/api/v1/price-books", status_code=201)
def put_price_book(body: PutPriceBookRequest) -> Dict[str, Any]:
    if not STORE.get_project(body.projectId):
        raise _error("NOT_FOUND", f"project {body.projectId} not found", status=404)
    pb = body.priceBook
    if pb.get("contractVersion") != CONTRACT_VERSION:
        raise _error("CONTRACT_VERSION", "priceBook contractVersion must be 0.3")
    return STORE.put_price_book(body.projectId, pb)


@app.get("/api/v1/projects/{project_id}/price-books/{book_id}")
def get_price_book(project_id: str, book_id: str, revision: Optional[str] = None) -> Dict[str, Any]:
    doc = STORE.get_price_book(project_id, book_id, revision)
    if not doc:
        raise _error("NOT_FOUND", "price book not found", status=404)
    return doc


@app.post("/api/v1/cost-bases", status_code=201)
def put_cost_basis(body: PutCostBasisRequest) -> Dict[str, Any]:
    if not STORE.get_project(body.projectId):
        raise _error("NOT_FOUND", f"project {body.projectId} not found", status=404)
    cb = body.costBasis
    if cb.get("contractVersion") != CONTRACT_VERSION:
        raise _error("CONTRACT_VERSION", "costBasis contractVersion must be 0.3")
    return STORE.put_cost_basis(body.projectId, cb)


@app.get("/api/v1/projects/{project_id}/cost-bases/{basis_id}")
def get_cost_basis(project_id: str, basis_id: str, revision: Optional[str] = None) -> Dict[str, Any]:
    doc = STORE.get_cost_basis(project_id, basis_id, revision)
    if not doc:
        raise _error("NOT_FOUND", "cost basis not found", status=404)
    return doc


@app.post("/api/v1/score-profiles", status_code=201)
def put_score_profile(body: PutScoreProfileRequest) -> Dict[str, Any]:
    if not STORE.get_project(body.projectId):
        raise _error("NOT_FOUND", f"project {body.projectId} not found", status=404)
    sp = body.scoreProfile
    if sp.get("contractVersion") != CONTRACT_VERSION:
        raise _error("CONTRACT_VERSION", "scoreProfile contractVersion must be 0.3")
    # 校验锚点方向
    for axis_id, anchors in (sp.get("axes") or {}).items():
        direction = anchors.get("direction")
        bad, good = anchors.get("bad"), anchors.get("good")
        if direction == "higher_better" and not (good > bad):
            raise _error(
                "SCORE_PROFILE_INVALID",
                f"轴 {axis_id}: higher_better 要求 good > bad",
                details={"axisId": axis_id, "bad": bad, "good": good},
            )
        if direction == "lower_better" and not (bad > good):
            raise _error(
                "SCORE_PROFILE_INVALID",
                f"轴 {axis_id}: lower_better 要求 bad > good",
                details={"axisId": axis_id, "bad": bad, "good": good},
            )
    return STORE.put_score_profile(body.projectId, sp)


@app.post("/api/v1/cost-estimate-jobs", status_code=202)
def create_cost_estimate_job(body: CostEstimateJobRequest) -> Dict[str, Any]:
    """DEV-12：BOM × PriceBook × CostBasis → CostEstimate；缺价不给完整 total。"""
    project_id = body.projectId
    if not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)

    variant = STORE.get_variant(project_id, body.variantRef.id)
    if not variant:
        raise _error("NOT_FOUND", "variant not found", status=404)

    layout_ref = body.layoutRef.model_dump() if body.layoutRef else (variant.get("layoutRef") or {})
    layout = STORE.get_layout(project_id, layout_ref.get("id"), layout_ref.get("revision"))
    if not layout:
        raise _error("NOT_FOUND", "layout revision not found", status=404)

    price_book = STORE.get_price_book(
        project_id, body.priceBookRef.id, body.priceBookRef.revision
    )
    if not price_book:
        raise _error("NOT_FOUND", "price book not found", status=404)
    cost_basis = STORE.get_cost_basis(
        project_id, body.costBasisRef.id, body.costBasisRef.revision
    )
    if not cost_basis:
        raise _error("NOT_FOUND", "cost basis not found", status=404)

    operating = None
    if body.operatingRef:
        operating = STORE.get_operating(
            project_id, body.operatingRef.id, body.operatingRef.revision
        )
        if not operating:
            raise _error("NOT_FOUND", "operating profile not found", status=404)

    job_id = f"costjob-{uuid4().hex[:10]}"
    job: Dict[str, Any] = {
        "id": job_id,
        "kind": "cost_estimate",
        "state": "running",
        "phase": "bom_cost",
        "outcome": None,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "resultRefs": None,
    }
    STORE.attach_job(project_id, job)

    try:
        estimate = estimate_cost(
            layout=layout,
            price_book=price_book,
            cost_basis=cost_basis,
            variant_ref={"id": variant["id"], "revision": variant.get("revision")},
            operating=operating,
        )
        STORE.put_cost_estimate(project_id, estimate)
        job["state"] = "succeeded"
        job["outcome"] = "completed"
        job["finishedAt"] = datetime.now(timezone.utc).isoformat()
        job["resultRefs"] = {
            "costEstimateId": estimate["id"],
            "layoutRevision": layout.get("revision"),
            "status": estimate["status"],
            "eligibleForLowestCostRanking": estimate["eligibleForLowestCostRanking"],
        }
        STORE.attach_job(project_id, job)
        return {
            "jobId": job_id,
            "state": job["state"],
            "outcome": job["outcome"],
            "costEstimateId": estimate["id"],
            "status": estimate["status"],
            "eligibleForLowestCostRanking": estimate["eligibleForLowestCostRanking"],
            "totals": estimate["totals"],
            "missingItems": estimate["missingItems"],
            "layoutRef": estimate["layoutRef"],
            "costEngineVersion": estimate["costEngineVersion"],
        }
    except CostError as exc:
        job["state"] = "failed"
        job["outcome"] = "rejected"
        job["error"] = {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "retryable": False,
            "traceId": None,
        }
        job["finishedAt"] = datetime.now(timezone.utc).isoformat()
        STORE.attach_job(project_id, job)
        raise _error(exc.code, exc.message, details=exc.details) from exc


@app.get("/api/v1/cost-estimates/{estimate_id}")
def get_cost_estimate(estimate_id: str) -> Dict[str, Any]:
    est = STORE.get_cost_estimate(estimate_id)
    if not est:
        raise _error("NOT_FOUND", f"cost estimate {estimate_id} not found", status=404)
    return est


@app.post("/api/v1/cost-ranking")
def rank_costs(body: Dict[str, Any]) -> Dict[str, Any]:
    """对已有 CostEstimate id 列表做最低初投推荐（缺价排除）。"""
    project_id = body.get("projectId")
    ids = body.get("costEstimateIds") or []
    if not project_id or not STORE.get_project(project_id):
        raise _error("NOT_FOUND", "project not found", status=404)
    estimates = []
    for eid in ids:
        est = STORE.get_cost_estimate(eid)
        if not est:
            raise _error("NOT_FOUND", f"cost estimate {eid} not found", status=404)
        estimates.append(est)
    return recommend_lowest_capex(estimates)


@app.post("/api/v1/comparisons", status_code=201)
def create_comparison(body: ComparisonRequest) -> Dict[str, Any]:
    """DEV-13：ComparisonSet；不隐式批跑；缺轴不补分。"""
    project_id = body.projectId
    if not STORE.get_project(project_id):
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)

    score_profile = body.scoreProfile
    if score_profile is None and body.scoreProfileRef:
        score_profile = STORE.get_score_profile(
            project_id, body.scoreProfileRef.id, body.scoreProfileRef.revision
        )
        if not score_profile:
            raise _error("NOT_FOUND", "score profile not found", status=404)

    # 补齐 entries 中的 run / costEstimate / operating / layout 引用载荷
    resolved_entries: List[Dict[str, Any]] = []
    for raw in body.entries:
        entry = dict(raw)
        if entry.get("runId") and not entry.get("run"):
            run = STORE.get_run(entry["runId"])
            if not run:
                raise _error("NOT_FOUND", f"run {entry['runId']} not found", status=404)
            entry["run"] = run
            entry["runRef"] = {"runId": entry["runId"]}
        if entry.get("costEstimateId") and not entry.get("costEstimate"):
            est = STORE.get_cost_estimate(entry["costEstimateId"])
            if not est:
                raise _error(
                    "NOT_FOUND", f"cost estimate {entry['costEstimateId']} not found", status=404
                )
            entry["costEstimate"] = est
            entry["costEstimateRef"] = {"id": est["id"]}
        if entry.get("operatingRef") and not entry.get("operating"):
            oref = entry["operatingRef"]
            op = STORE.get_operating(project_id, oref.get("id"), oref.get("revision"))
            entry["operating"] = op
        if entry.get("layoutRef") and entry.get("effectiveCapacity") is None:
            # 可选：从 prepare 派生容量
            lref = entry["layoutRef"]
            prep = STORE.get_prepare_result(project_id, lref.get("id"), lref.get("revision"))
            if prep:
                snap = (prep.get("derivedLayout") or {}).get("layoutSnapshot") or {}
                slots = [
                    e
                    for e in (snap.get("elements") or [])
                    if e.get("kind") == "slot" and e.get("capacityPallets")
                ]
                entry["effectiveCapacity"] = float(
                    sum(float(s.get("capacityPallets") or 0) for s in slots)
                )
        resolved_entries.append(entry)

    try:
        comparison = build_comparison(
            mode=body.mode,
            entries=resolved_entries,
            common_basis=body.commonBasis,
            score_profile=score_profile,
        )
    except CompareError as exc:
        raise _error(exc.code, exc.message, details=exc.details) from exc

    STORE.put_comparison(project_id, comparison)
    recommendations = recommend_from_comparison(
        comparison,
        cost_estimates=[
            e.get("costEstimate")
            for e in resolved_entries
            if e.get("costEstimate")
        ]
        or None,
    )
    return {
        "comparison": comparison,
        "recommendations": recommendations,
        "note": "比较不改原方案；加入方案不改已锁定 ScoreProfile 绝对分",
    }


@app.get("/api/v1/comparisons/{comparison_id}")
def get_comparison(comparison_id: str) -> Dict[str, Any]:
    doc = STORE.get_comparison(comparison_id)
    if not doc:
        raise _error("NOT_FOUND", f"comparison {comparison_id} not found", status=404)
    return doc


@app.post("/api/v1/reports", status_code=201)
def create_report(body: ReportRequest) -> Dict[str, Any]:
    """DEV-14：报告绑定历史 layoutRevision / run；与界面数值版本一致。"""
    project_id = body.projectId
    project = STORE.get_project(project_id)
    if not project:
        raise _error("NOT_FOUND", f"project {project_id} not found", status=404)

    variant = STORE.get_variant(project_id, body.variantRef.id)
    if not variant:
        raise _error("NOT_FOUND", "variant not found", status=404)

    layout = STORE.get_layout(
        project_id, body.layoutRef.id, body.layoutRef.revision
    )
    if not layout:
        raise _error("NOT_FOUND", "layout revision not found — 不得用草稿替代历史修订", status=404)

    run = STORE.get_run(body.runId) if body.runId else None
    if body.runId and not run:
        raise _error("NOT_FOUND", f"run {body.runId} not found", status=404)

    cost_estimate = (
        STORE.get_cost_estimate(body.costEstimateId) if body.costEstimateId else None
    )
    if body.costEstimateId and not cost_estimate:
        raise _error("NOT_FOUND", f"cost estimate {body.costEstimateId} not found", status=404)

    comparison = STORE.get_comparison(body.comparisonId) if body.comparisonId else None
    if body.comparisonId and not comparison:
        raise _error("NOT_FOUND", f"comparison {body.comparisonId} not found", status=404)

    report = build_delivery_report(
        project=project,
        variant=variant,
        layout_ref=body.layoutRef.model_dump(),
        run=run,
        cost_estimate=cost_estimate,
        comparison=comparison,
    )
    if not report.get("versionConsistent"):
        raise _error(
            "LAYOUT_REVISION_MISMATCH",
            "报告引用与 run/成本版本不一致",
            details={"inconsistencies": report.get("inconsistencies")},
        )
    STORE.put_report(project_id, report)
    return {
        "reportId": report["id"],
        "versionConsistent": report["versionConsistent"],
        "layoutRef": report["layoutRef"],
        "runRef": report["runRef"],
        "costEstimateRef": report["costEstimateRef"],
        "comparisonRef": report["comparisonRef"],
        "versions": report["versions"],
        "html": report["html"],
        "supportScope": report["supportScope"],
    }


@app.get("/api/v1/reports/{report_id}")
def get_report(report_id: str) -> Dict[str, Any]:
    doc = STORE.get_report(report_id)
    if not doc:
        raise _error("NOT_FOUND", f"report {report_id} not found", status=404)
    return doc


class RecognitionJobRequest(BaseModel):
    projectId: str
    capability: str
    drawingId: Optional[str] = None
    source: Dict[str, Any] = Field(default_factory=dict)


class AdvancedEvalRequest(BaseModel):
    projectId: Optional[str] = None
    capability: str
    inputs: Dict[str, Any] = Field(default_factory=dict)


@app.post("/api/v1/recognition-jobs", status_code=200)
def create_recognition_job(body: RecognitionJobRequest) -> Dict[str, Any]:
    """DEV-15：识图能力只返回失败/待确认/不支持。不写场地，不删底图。"""
    if not STORE.get_project(body.projectId):
        raise _error("NOT_FOUND", f"project {body.projectId} not found", status=404)
    drawing = None
    if body.drawingId:
        drawing = STORE.get_drawing(body.projectId, body.drawingId)
        if not drawing:
            raise _error("NOT_FOUND", "drawing not found", status=404)
    head_before = STORE.projects[body.projectId].facility_head
    assessed = assess_recognition(
        capability=body.capability,
        source=body.source,
        drawing=drawing,
    )
    job_id = f"recjob-{uuid4().hex[:10]}"
    job = {
        "id": job_id,
        "kind": "recognition",
        "state": "succeeded",
        "phase": "rejected",
        "outcome": assessed["status"],
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "resultRefs": {
            "capability": body.capability,
            "drawingId": body.drawingId,
            "producedGeometry": None,
            "claimsValidatedGeometry": False,
        },
        "assessment": assessed,
    }
    STORE.attach_job(body.projectId, job)
    if body.drawingId:
        still = STORE.get_drawing(body.projectId, body.drawingId)
        if not still:
            raise _error("COMPUTATION_FAILED", "识图失败路径意外删除了底图", status=500)
        assessed["drawingRetained"] = True
        assessed["drawingStatus"] = still.get("status")
    else:
        assessed["drawingRetained"] = False
    head_after = STORE.projects[body.projectId].facility_head
    assessed["facilityHeadUnchanged"] = head_before == head_after
    assessed["facilityWritten"] = False
    if head_before != head_after:
        raise _error("COMPUTATION_FAILED", "识图失败路径意外写入了场地", status=500)
    return {"jobId": job_id, "state": "succeeded", **assessed}


@app.post("/api/v1/advanced-evaluations", status_code=200)
def create_advanced_evaluation(body: AdvancedEvalRequest) -> Dict[str, Any]:
    """DEV-16：自动化/多目标/长期成本只返回不支持。不产生分数或候选。"""
    if body.projectId and not STORE.get_project(body.projectId):
        raise _error("NOT_FOUND", f"project {body.projectId} not found", status=404)
    assessed = assess_advanced(capability=body.capability, inputs=body.inputs)
    job_id = f"advjob-{uuid4().hex[:10]}"
    if body.projectId:
        STORE.attach_job(
            body.projectId,
            {
                "id": job_id,
                "kind": "advanced",
                "state": "succeeded",
                "phase": "rejected",
                "outcome": assessed["status"],
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "finishedAt": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "resultRefs": {
                    "capability": body.capability,
                    "score": None,
                    "claimsBetterThanBaseline": False,
                },
                "assessment": assessed,
            },
        )
    return {"jobId": job_id, "state": "succeeded", **assessed}
