"""进程内项目/布局/规划/派生/跑次/成本/比较存储（M4 本地）。无远程 DB。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProjectRecord:
    project: Dict[str, Any]
    facilities: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # revision -> doc
    facility_head: Optional[str] = None
    drawings: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # drawingId -> meta
    demands: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    # demandId -> revision -> DemandRevision
    demand_heads: Dict[str, str] = field(default_factory=dict)
    operating: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    # operatingId -> revision -> OperatingProfileRevision
    operating_heads: Dict[str, str] = field(default_factory=dict)
    layouts: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    # layoutId -> revision -> LayoutDocumentRevision
    layout_heads: Dict[str, str] = field(default_factory=dict)
    variants: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # variantId -> VariantRevision head payload
    derived: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # key layoutId@revision -> {snapshot, index, report, prepareStatus}
    jobs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    candidates: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # candidateId -> cand
    planning_drafts: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # draftId -> request
    runs: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # runId -> run result
    # M4
    price_books: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    price_book_heads: Dict[str, str] = field(default_factory=dict)
    cost_bases: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    cost_basis_heads: Dict[str, str] = field(default_factory=dict)
    score_profiles: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    score_profile_heads: Dict[str, str] = field(default_factory=dict)
    cost_estimates: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    comparisons: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    reports: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class MemoryStore:
    def __init__(self) -> None:
        self.projects: Dict[str, ProjectRecord] = {}
        self._orphan_jobs: Dict[str, Dict[str, Any]] = {}
        self._global_candidates: Dict[str, Dict[str, Any]] = {}
        self._global_runs: Dict[str, str] = {}  # runId -> projectId
        self._global_estimates: Dict[str, str] = {}  # estimateId -> projectId
        self._global_comparisons: Dict[str, str] = {}
        self._global_reports: Dict[str, str] = {}

    def create_project(self, name: str, unit_system: str = "metric") -> Dict[str, Any]:
        pid = f"project-{uuid4().hex[:8]}"
        project = {
            "contractVersion": "0.3",
            "id": pid,
            "name": name,
            "unitSystem": unit_system,
            "createdAt": _now(),
        }
        self.projects[pid] = ProjectRecord(project=project)
        return deepcopy(project)

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        return deepcopy(rec.project) if rec else None

    def put_drawing(self, project_id: str, drawing: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        did = drawing["id"]
        rec.drawings[did] = deepcopy(drawing)
        return deepcopy(drawing)

    def get_drawing(self, project_id: str, drawing_id: str) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec:
            return None
        doc = rec.drawings.get(drawing_id)
        return deepcopy(doc) if doc else None

    def put_facility(self, project_id: str, facility: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        rev = facility["revision"]
        rec.facilities[rev] = deepcopy(facility)
        rec.facility_head = rev
        return deepcopy(facility)

    def get_facility(self, project_id: str, revision: Optional[str] = None) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec:
            return None
        rev = revision or rec.facility_head
        if not rev:
            return None
        doc = rec.facilities.get(rev)
        return deepcopy(doc) if doc else None

    def put_demand(self, project_id: str, demand: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        did = demand["id"]
        rev = demand["revision"]
        if did not in rec.demands:
            rec.demands[did] = {}
        rec.demands[did][rev] = deepcopy(demand)
        rec.demand_heads[did] = rev
        return deepcopy(demand)

    def get_demand(
        self, project_id: str, demand_id: str, revision: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec or demand_id not in rec.demands:
            return None
        rev = revision or rec.demand_heads.get(demand_id)
        if not rev:
            return None
        doc = rec.demands[demand_id].get(rev)
        return deepcopy(doc) if doc else None

    def put_operating(self, project_id: str, operating: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        oid = operating["id"]
        rev = operating["revision"]
        if oid not in rec.operating:
            rec.operating[oid] = {}
        rec.operating[oid][rev] = deepcopy(operating)
        rec.operating_heads[oid] = rev
        return deepcopy(operating)

    def get_operating(
        self, project_id: str, operating_id: str, revision: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec or operating_id not in rec.operating:
            return None
        rev = revision or rec.operating_heads.get(operating_id)
        if not rev:
            return None
        doc = rec.operating[operating_id].get(rev)
        return deepcopy(doc) if doc else None

    def put_run(self, project_id: str, run: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        rid = run["runId"]
        rec.runs[rid] = deepcopy(run)
        self._global_runs[rid] = project_id
        return deepcopy(run)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        pid = self._global_runs.get(run_id)
        if pid:
            rec = self.projects.get(pid)
            if rec and run_id in rec.runs:
                return deepcopy(rec.runs[run_id])
        for rec in self.projects.values():
            if run_id in rec.runs:
                return deepcopy(rec.runs[run_id])
        return None

    def put_planning_draft(self, project_id: str, draft_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        payload = {"id": draft_id, "updatedAt": _now(), "request": deepcopy(request)}
        rec.planning_drafts[draft_id] = payload
        return deepcopy(payload)

    def get_planning_draft(self, project_id: str, draft_id: str) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec:
            return None
        doc = rec.planning_drafts.get(draft_id)
        return deepcopy(doc) if doc else None

    def put_layout_revision(
        self,
        project_id: str,
        layout_doc: Dict[str, Any],
        *,
        base_revision: Optional[str] = None,
    ) -> Dict[str, Any]:
        rec = self.projects[project_id]
        lid = layout_doc["id"]
        rev = layout_doc["revision"]
        if lid not in rec.layouts:
            rec.layouts[lid] = {}
        if base_revision is not None and rec.layout_heads.get(lid) != base_revision:
            raise RevisionConflict(lid, expected=base_revision, actual=rec.layout_heads.get(lid))
        if rev in rec.layouts[lid]:
            raise RevisionConflict(lid, expected=None, actual=rev, message="revision already exists")
        rec.layouts[lid][rev] = deepcopy(layout_doc)
        rec.layout_heads[lid] = rev
        key_prefix = f"{lid}@"
        for k in list(rec.derived.keys()):
            if k.startswith(key_prefix):
                rec.derived[k]["prepareStatus"] = "stale"
                rec.derived[k]["simulationReady"] = False
        return deepcopy(layout_doc)

    def get_layout(
        self, project_id: str, layout_id: str, revision: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec or layout_id not in rec.layouts:
            return None
        rev = revision or rec.layout_heads.get(layout_id)
        if not rev:
            return None
        doc = rec.layouts[layout_id].get(rev)
        return deepcopy(doc) if doc else None

    def put_variant(self, project_id: str, variant: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        rec.variants[variant["id"]] = deepcopy(variant)
        return deepcopy(variant)

    def get_variant(self, project_id: str, variant_id: str) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec:
            return None
        doc = rec.variants.get(variant_id)
        return deepcopy(doc) if doc else None

    def list_variants(self, project_id: str) -> List[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec:
            return []
        return [deepcopy(v) for v in rec.variants.values()]

    def save_prepare_result(
        self,
        project_id: str,
        layout_id: str,
        layout_revision: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        rec = self.projects[project_id]
        key = f"{layout_id}@{layout_revision}"
        rec.derived[key] = deepcopy(payload)
        return deepcopy(payload)

    def get_prepare_result(
        self, project_id: str, layout_id: str, layout_revision: str
    ) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec:
            return None
        data = rec.derived.get(f"{layout_id}@{layout_revision}")
        return deepcopy(data) if data else None

    def attach_job(self, project_id: str, job: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        rec.jobs[job["id"]] = deepcopy(job)
        return deepcopy(job)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        for rec in self.projects.values():
            if job_id in rec.jobs:
                return deepcopy(rec.jobs[job_id])
        orphan = self._orphan_jobs.get(job_id)
        return deepcopy(orphan) if orphan else None

    def put_candidates(self, project_id: str, candidates: List[Dict[str, Any]]) -> None:
        rec = self.projects[project_id]
        for c in candidates:
            # 存储时去掉体积大的 derivedSnapshot 可选保留
            rec.candidates[c["id"]] = deepcopy(c)
            self._global_candidates[c["id"]] = {"projectId": project_id, "candidateId": c["id"]}

    def get_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        meta = self._global_candidates.get(candidate_id)
        if not meta:
            # 扫描
            for rec in self.projects.values():
                if candidate_id in rec.candidates:
                    return deepcopy(rec.candidates[candidate_id])
            return None
        rec = self.projects.get(meta["projectId"])
        if not rec:
            return None
        doc = rec.candidates.get(candidate_id)
        return deepcopy(doc) if doc else None

    def list_candidates(self, project_id: str, job_id: str) -> List[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec:
            return []
        items = [deepcopy(c) for c in rec.candidates.values() if c.get("jobId") == job_id]
        return items

    def project_id_for_job(self, job_id: str) -> Optional[str]:
        for pid, rec in self.projects.items():
            if job_id in rec.jobs:
                return pid
        return None

    def project_id_for_candidate(self, candidate_id: str) -> Optional[str]:
        meta = self._global_candidates.get(candidate_id)
        if meta:
            return meta["projectId"]
        for pid, rec in self.projects.items():
            if candidate_id in rec.candidates:
                return pid
        return None

    def put_price_book(self, project_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        did = doc["id"]
        rev = doc["revision"]
        if did not in rec.price_books:
            rec.price_books[did] = {}
        rec.price_books[did][rev] = deepcopy(doc)
        rec.price_book_heads[did] = rev
        return deepcopy(doc)

    def get_price_book(
        self, project_id: str, book_id: str, revision: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec or book_id not in rec.price_books:
            return None
        rev = revision or rec.price_book_heads.get(book_id)
        if not rev:
            return None
        doc = rec.price_books[book_id].get(rev)
        return deepcopy(doc) if doc else None

    def put_cost_basis(self, project_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        did = doc["id"]
        rev = doc["revision"]
        if did not in rec.cost_bases:
            rec.cost_bases[did] = {}
        rec.cost_bases[did][rev] = deepcopy(doc)
        rec.cost_basis_heads[did] = rev
        return deepcopy(doc)

    def get_cost_basis(
        self, project_id: str, basis_id: str, revision: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec or basis_id not in rec.cost_bases:
            return None
        rev = revision or rec.cost_basis_heads.get(basis_id)
        if not rev:
            return None
        doc = rec.cost_bases[basis_id].get(rev)
        return deepcopy(doc) if doc else None

    def put_score_profile(self, project_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        did = doc["id"]
        rev = doc["revision"]
        if did not in rec.score_profiles:
            rec.score_profiles[did] = {}
        rec.score_profiles[did][rev] = deepcopy(doc)
        rec.score_profile_heads[did] = rev
        return deepcopy(doc)

    def get_score_profile(
        self, project_id: str, profile_id: str, revision: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        rec = self.projects.get(project_id)
        if not rec or profile_id not in rec.score_profiles:
            return None
        rev = revision or rec.score_profile_heads.get(profile_id)
        if not rev:
            return None
        doc = rec.score_profiles[profile_id].get(rev)
        return deepcopy(doc) if doc else None

    def put_cost_estimate(self, project_id: str, estimate: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        eid = estimate["id"]
        rec.cost_estimates[eid] = deepcopy(estimate)
        self._global_estimates[eid] = project_id
        return deepcopy(estimate)

    def get_cost_estimate(self, estimate_id: str) -> Optional[Dict[str, Any]]:
        pid = self._global_estimates.get(estimate_id)
        if pid and pid in self.projects:
            doc = self.projects[pid].cost_estimates.get(estimate_id)
            if doc:
                return deepcopy(doc)
        for rec in self.projects.values():
            if estimate_id in rec.cost_estimates:
                return deepcopy(rec.cost_estimates[estimate_id])
        return None

    def put_comparison(self, project_id: str, comparison: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        cid = comparison["id"]
        rec.comparisons[cid] = deepcopy(comparison)
        self._global_comparisons[cid] = project_id
        return deepcopy(comparison)

    def get_comparison(self, comparison_id: str) -> Optional[Dict[str, Any]]:
        pid = self._global_comparisons.get(comparison_id)
        if pid and pid in self.projects:
            doc = self.projects[pid].comparisons.get(comparison_id)
            if doc:
                return deepcopy(doc)
        for rec in self.projects.values():
            if comparison_id in rec.comparisons:
                return deepcopy(rec.comparisons[comparison_id])
        return None

    def put_report(self, project_id: str, report: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        rid = report["id"]
        rec.reports[rid] = deepcopy(report)
        self._global_reports[rid] = project_id
        return deepcopy(report)

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        pid = self._global_reports.get(report_id)
        if pid and pid in self.projects:
            doc = self.projects[pid].reports.get(report_id)
            if doc:
                return deepcopy(doc)
        for rec in self.projects.values():
            if report_id in rec.reports:
                return deepcopy(rec.reports[report_id])
        return None


class RevisionConflict(Exception):
    def __init__(
        self,
        layout_id: str,
        *,
        expected: Optional[str],
        actual: Optional[str],
        message: str = "revision conflict",
    ) -> None:
        super().__init__(message)
        self.layout_id = layout_id
        self.expected = expected
        self.actual = actual
        self.message = message


STORE = MemoryStore()
