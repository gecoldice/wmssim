"""进程内项目/布局/派生/校验存储（M1 本地）。无远程 DB。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProjectRecord:
    project: Dict[str, Any]
    facilities: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # revision -> doc
    facility_head: Optional[str] = None
    layouts: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    # layoutId -> revision -> LayoutDocumentRevision
    layout_heads: Dict[str, str] = field(default_factory=dict)
    variants: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # variantId -> VariantRevision head payload
    derived: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # key layoutId@revision -> {snapshot, index, report, prepareStatus}
    jobs: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class MemoryStore:
    def __init__(self) -> None:
        self.projects: Dict[str, ProjectRecord] = {}

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
        # 保存使派生/校验过期
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

    def list_variants(self, project_id: str) -> list[Dict[str, Any]]:
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

    def put_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        # jobs are global by id for GET /jobs/{id}
        for rec in self.projects.values():
            if job["id"] in rec.jobs:
                rec.jobs[job["id"]] = deepcopy(job)
                return deepcopy(job)
        # attach to first project if unknown — store on a side map
        if not hasattr(self, "_orphan_jobs"):
            self._orphan_jobs: Dict[str, Dict[str, Any]] = {}
        self._orphan_jobs[job["id"]] = deepcopy(job)
        return deepcopy(job)

    def attach_job(self, project_id: str, job: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.projects[project_id]
        rec.jobs[job["id"]] = deepcopy(job)
        return deepcopy(job)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        for rec in self.projects.values():
            if job_id in rec.jobs:
                return deepcopy(rec.jobs[job_id])
        orphan = getattr(self, "_orphan_jobs", {}).get(job_id)
        return deepcopy(orphan) if orphan else None


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
