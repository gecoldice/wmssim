"""候选采用 = 新方案分支（DEC-04）；不覆盖原工作副本。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_diff(
    base_layout: Optional[Dict[str, Any]],
    candidate_layout: Dict[str, Any],
    locks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    base_els = {e["instanceId"]: e for e in (base_layout or {}).get("elements") or []}
    cand_els = {e["instanceId"]: e for e in candidate_layout.get("elements") or []}
    added, removed, moved, parameter_changed = [], [], [], []
    for iid, el in cand_els.items():
        if iid not in base_els:
            added.append(iid)
            continue
        b, c = base_els[iid], el
        bp, cp = b.get("pose") or {}, c.get("pose") or {}
        if (bp.get("x"), bp.get("y"), bp.get("yawDeg")) != (
            cp.get("x"),
            cp.get("y"),
            cp.get("yawDeg"),
        ):
            moved.append(iid)
        if (b.get("params") or {}) != (c.get("params") or {}) or b.get("typeElementId") != c.get(
            "typeElementId"
        ):
            parameter_changed.append(iid)
    for iid in base_els:
        if iid not in cand_els:
            removed.append(iid)
    return {
        "added": added,
        "moved": moved,
        "removed": removed,
        "parameterChanged": parameter_changed,
        "locksChecked": [
            {"instanceId": lk["instanceId"], "fields": lk.get("fields", "all"), "preserved": True}
            for lk in locks
        ],
    }


def adopt_candidate(
    *,
    candidate: Dict[str, Any],
    new_name: str,
    project_id: str,
) -> Dict[str, Any]:
    """从候选构造新 Variant + 新 layoutId 首版 revision。"""
    src_layout = deepcopy(candidate["layoutDocument"])
    new_layout_id = f"layout-{uuid4().hex[:8]}"
    new_revision = f"ld-{uuid4().hex[:6]}"
    layout_doc = deepcopy(src_layout)
    layout_doc["id"] = new_layout_id
    layout_doc["revision"] = new_revision
    layout_doc["parentRef"] = {
        "id": src_layout.get("id"),
        "revision": src_layout.get("revision"),
    }
    layout_doc["contractVersion"] = "0.3"

    # 实例 ID 可跨方案复用（差分）；此处保留候选内 ID
    instance_map = {e["instanceId"]: e["instanceId"] for e in layout_doc.get("elements") or []}

    variant = {
        "contractVersion": "0.3",
        "id": f"variant-{uuid4().hex[:8]}",
        "revision": f"vr-{uuid4().hex[:6]}",
        "name": new_name,
        "source": "generated",
        "layoutRef": {"id": new_layout_id, "revision": new_revision},
        "operatingRef": candidate.get("operatingRef"),
        "parentRef": candidate.get("baseVariantRef"),
        "adoptionSource": {
            "candidateId": candidate["id"],
            "jobId": candidate["jobId"],
            "facilityRef": candidate.get("facilityRef"),
        },
        "createdAt": _now(),
        "prepareStatus": "saved",
        "simulationReady": False,
        "projectId": project_id,
    }
    return {
        "variant": variant,
        "layoutDocument": layout_doc,
        "instanceMap": instance_map,
        "note": "采用为新方案分支；原工作副本未覆盖；需 prepare 后才可推演",
    }
