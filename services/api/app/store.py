"""项目/布局/跑次/成本/比较存储。

默认落到 simapp/data/simapp.sqlite（重启不丢）。
SIMAPP_DB=off|memory|:memory: 时只留在进程内，供回归测试使用。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

_AUTO = object()
_MEMORY_TOKENS = {"", "off", "memory", ":memory:"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_db_path(explicit: Any = _AUTO) -> Optional[Path]:
    """None 表示不落盘。显式路径优先；未指定时读 SIMAPP_DB，再默认到 data/simapp.sqlite。"""
    if explicit is _AUTO:
        raw = os.environ.get("SIMAPP_DB")
        if raw is None:
            return Path(__file__).resolve().parents[3] / "data" / "simapp.sqlite"
        text = raw.strip()
    elif explicit is None:
        return None
    else:
        text = str(explicit).strip()
    if text.lower() in _MEMORY_TOKENS:
        return None
    return Path(text)


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
    def __init__(self, db_path: Any = _AUTO) -> None:
        self.projects: Dict[str, ProjectRecord] = {}
        self._orphan_jobs: Dict[str, Dict[str, Any]] = {}
        self._global_candidates: Dict[str, Dict[str, Any]] = {}
        self._global_runs: Dict[str, str] = {}  # runId -> projectId
        self._global_estimates: Dict[str, str] = {}  # estimateId -> projectId
        self._global_comparisons: Dict[str, str] = {}
        self._global_reports: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._db_path = resolve_db_path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        if self._db_path is not None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshot (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL
                )
                """
            )
            self._conn.commit()
            self._load()

    def persistence_info(self) -> Dict[str, Any]:
        return {
            "engine": "sqlite" if self._db_path else "memory",
            "durable": self._db_path is not None,
            "path": str(self._db_path) if self._db_path else None,
        }

    def _dump_state(self) -> Dict[str, Any]:
        return {
            "projects": {pid: asdict(rec) for pid, rec in self.projects.items()},
            "orphanJobs": self._orphan_jobs,
            "globalCandidates": self._global_candidates,
            "globalRuns": self._global_runs,
            "globalEstimates": self._global_estimates,
            "globalComparisons": self._global_comparisons,
            "globalReports": self._global_reports,
        }

    def _load_state(self, payload: Dict[str, Any]) -> None:
        known = {item.name for item in fields(ProjectRecord)}
        projects: Dict[str, ProjectRecord] = {}
        for pid, blob in (payload.get("projects") or {}).items():
            if not isinstance(blob, dict) or "project" not in blob:
                continue
            kwargs = {key: blob[key] for key in known if key in blob}
            projects[str(pid)] = ProjectRecord(**kwargs)
        self.projects = projects
        self._orphan_jobs = dict(payload.get("orphanJobs") or {})
        self._global_candidates = dict(payload.get("globalCandidates") or {})
        self._global_runs = dict(payload.get("globalRuns") or {})
        self._global_estimates = dict(payload.get("globalEstimates") or {})
        self._global_comparisons = dict(payload.get("globalComparisons") or {})
        self._global_reports = dict(payload.get("globalReports") or {})

    def _load(self) -> None:
        if self._conn is None:
            return
        row = self._conn.execute("SELECT payload FROM snapshot WHERE id = 1").fetchone()
        if not row:
            return
        self._load_state(json.loads(row[0]))

    def _commit_unlocked(self) -> None:
        if self._conn is None:
            return
        payload = json.dumps(self._dump_state(), ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO snapshot (id, payload) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
            """,
            (payload,),
        )
        self._conn.commit()

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

    def list_projects(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for rec in self.projects.values():
            project = rec.project
            items.append(
                {
                    "id": project.get("id"),
                    "name": project.get("name"),
                    "unitSystem": project.get("unitSystem"),
                    "createdAt": project.get("createdAt"),
                    "contractVersion": project.get("contractVersion"),
                    "facilityHead": rec.facility_head,
                    "layoutCount": len(rec.layout_heads),
                    "runCount": len(rec.runs),
                    "comparisonCount": len(rec.comparisons),
                }
            )
        items.sort(key=lambda row: row.get("createdAt") or "", reverse=True)
        return items

    def workspace(self, project_id: str) -> Optional[Dict[str, Any]]:
        """工作台恢复用的当前方案。不含事件轨迹和派生快照。"""
        rec = self.projects.get(project_id)
        if not rec:
            return None
        layout_id = _preferred_layout_id(rec)
        layout = self.get_layout(project_id, layout_id) if layout_id else None
        revision = layout.get("revision") if layout else None
        variant = _variant_for_layout(rec, layout_id, revision)
        run = _run_for_layout(rec, layout_id, revision)
        prepare = None
        if layout_id and revision:
            raw_prepare = self.get_prepare_result(project_id, layout_id, revision)
            prepare = _slim_prepare(raw_prepare)
        manifest = (run or {}).get("runManifest") or {}
        op_ref = manifest.get("operatingRef") or {}
        demand_ref = manifest.get("demandRef") or {}
        operating = (
            self.get_operating(project_id, op_ref.get("id"), op_ref.get("revision"))
            if op_ref.get("id")
            else None
        )
        demand = (
            self.get_demand(project_id, demand_ref.get("id"), demand_ref.get("revision"))
            if demand_ref.get("id")
            else None
        )
        comparison = deepcopy(next(reversed(rec.comparisons.values()))) if rec.comparisons else None
        return {
            "project": deepcopy(rec.project),
            "facility": self.get_facility(project_id),
            "layout": layout,
            "variant": variant,
            "prepare": prepare,
            "operating": operating,
            "demand": demand,
            "run": _slim_run(run),
            "comparison": comparison,
            "persistence": self.persistence_info(),
        }


def _preferred_layout_id(rec: ProjectRecord) -> Optional[str]:
    """编辑中的方案。叉车加一写在 layout-workbench-alt，不把它当成当前画布。"""
    for variant in reversed(list(rec.variants.values())):
        lid = (variant.get("layoutRef") or {}).get("id")
        if lid and lid != "layout-workbench-alt" and lid in rec.layout_heads:
            return lid
    if "layout-workbench" in rec.layout_heads:
        return "layout-workbench"
    if not rec.layout_heads:
        return None
    return next(iter(rec.layout_heads))


def _variant_for_layout(
    rec: ProjectRecord, layout_id: Optional[str], revision: Optional[str]
) -> Optional[Dict[str, Any]]:
    if not rec.variants:
        return None
    if layout_id and revision:
        matched = [
            item
            for item in rec.variants.values()
            if (item.get("layoutRef") or {}).get("id") == layout_id
            and (item.get("layoutRef") or {}).get("revision") == revision
        ]
        if matched:
            return deepcopy(matched[-1])
    plain = [
        item
        for item in rec.variants.values()
        if (item.get("layoutRef") or {}).get("id") != "layout-workbench-alt"
    ]
    return deepcopy((plain or list(rec.variants.values()))[-1])


def _run_for_layout(
    rec: ProjectRecord, layout_id: Optional[str], revision: Optional[str]
) -> Optional[Dict[str, Any]]:
    if not revision:
        return None
    matched: List[Dict[str, Any]] = []
    for run in rec.runs.values():
        manifest = run.get("runManifest") or {}
        bound = run.get("layoutSnapshotBound") or {}
        lref = manifest.get("layoutRef") or {}
        rev_ok = (
            run.get("layoutRevision") == revision
            or bound.get("layoutRevision") == revision
            or lref.get("revision") == revision
        )
        id_ok = layout_id is None or lref.get("id") in {None, layout_id} or bound.get("layoutId") in {
            None,
            layout_id,
        }
        if rev_ok and id_ok:
            matched.append(run)
    if not matched:
        return None
    return deepcopy(matched[-1])


def _slim_run(run: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not run:
        return None
    return {
        "runId": run.get("runId"),
        "layoutRevision": run.get("layoutRevision"),
        "kpi": deepcopy(run.get("kpi")),
        "runManifest": deepcopy(run.get("runManifest")),
        "replayBinding": deepcopy(run.get("replayBinding")),
    }


def _slim_prepare(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not payload:
        return None
    report = payload.get("validationReport") or {}
    return {
        "simulationReady": payload.get("simulationReady"),
        "prepareStatus": payload.get("prepareStatus"),
        "validationStatus": report.get("status"),
        "layoutRevision": payload.get("layoutRevision"),
        "checks": deepcopy(report.get("checks") or []),
    }


_MUTATORS = (
    "create_project",
    "put_drawing",
    "put_facility",
    "put_demand",
    "put_operating",
    "put_run",
    "put_planning_draft",
    "put_layout_revision",
    "put_variant",
    "save_prepare_result",
    "attach_job",
    "put_candidates",
    "put_price_book",
    "put_cost_basis",
    "put_score_profile",
    "put_cost_estimate",
    "put_comparison",
    "put_report",
)


def _install_persistence(cls: type) -> None:
    for name in _MUTATORS:
        original = getattr(cls, name)

        def make(fn):
            def wrapped(self, *args, **kwargs):
                with self._lock:
                    result = fn(self, *args, **kwargs)
                    self._commit_unlocked()
                    return result

            wrapped.__name__ = fn.__name__
            wrapped.__doc__ = fn.__doc__
            return wrapped

        setattr(cls, name, make(original))


_install_persistence(MemoryStore)


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
