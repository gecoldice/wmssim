#!/usr/bin/env python3
"""SQLite：项目、布局、跑次在新的存储实例里仍在。

Usage:
  PYTHONPATH=shared/python:services/api python3 scripts/run_persist_checks.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(tempfile.mkdtemp(prefix="simapp-db-")) / "simapp.sqlite"
os.environ["SIMAPP_DB"] = str(DB_PATH)
sys.path.insert(0, str(ROOT / "shared" / "python"))
sys.path.insert(0, str(ROOT / "services" / "api"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.store import MemoryStore, STORE  # noqa: E402

FIXTURES = ROOT / "fixtures"


def load(rel: str):
    with (FIXTURES / rel).open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    info = STORE.persistence_info()
    assert info["durable"] is True, info
    assert info["engine"] == "sqlite"
    assert Path(info["path"]) == DB_PATH

    client = TestClient(app)
    health = client.get("/api/v1/health").json()
    assert health["persistence"]["durable"] is True
    assert health["capabilities"]["durableStore"] is True

    project = client.post(
        "/api/v1/projects", json={"name": "工作台方案", "unitSystem": "metric"}
    ).json()
    pid = project["id"]
    facility = load("valid/fx01-small-rect-facility.json")
    assert (
        client.post(
            f"/api/v1/projects/{pid}/facility-revisions",
            json={"facility": facility},
        ).status_code
        == 201
    )
    layout = load("valid/fx-m1-ok-layout.json")
    saved = client.post(
        f"/api/v1/layouts/{layout['id']}/revisions",
        json={"projectId": pid, "baseRevision": None, "document": layout},
    ).json()
    layout_ref = saved["layoutRef"]
    variant = client.post(
        f"/api/v1/projects/{pid}/variants",
        json={"name": "当前方案", "source": "manual", "layoutRef": layout_ref},
    ).json()
    prep = client.post(
        f"/api/v1/layouts/{layout_ref['id']}/prepare-jobs",
        json={
            "projectId": pid,
            "layoutRef": layout_ref,
            "facilityRef": {"id": facility["id"], "revision": facility["revision"]},
            "ruleSetRefs": [{"id": "ruleset.m1.geometry", "revision": "0.1"}],
            "sync": True,
        },
    ).json()
    assert prep["simulationReady"] is True, prep

    demand = load("valid/fx-m3-demand-outbound.json")
    operating = load("valid/fx-m3-operating.json")
    client.post("/api/v1/demands", json={"projectId": pid, "demand": demand})
    client.post("/api/v1/operating-profiles", json={"projectId": pid, "operating": operating})
    scenario = load("valid/fx-m3-scenario-package.json")
    scenario["expectedLayoutRevision"] = layout_ref["revision"]
    ran = client.post(
        "/api/v1/simulation-jobs",
        json={
            "projectId": pid,
            "variantRef": {"id": variant["id"], "revision": variant["revision"]},
            "scenarioPackage": scenario,
        },
    )
    assert ran.status_code == 202, ran.text
    body = ran.json()
    assert body["kpi"]["cards"]["throughput"]["outboundPalletEq"] == 4.0

    listed = client.get("/api/v1/projects").json()
    assert any(item["id"] == pid and item["runCount"] == 1 for item in listed["items"])
    workspace = client.get(f"/api/v1/projects/{pid}/workspace").json()
    assert workspace["layout"]["revision"] == layout_ref["revision"]
    assert workspace["run"]["runId"] == body["runId"]
    assert workspace["run"]["kpi"]["cards"]["throughput"]["outboundPalletEq"] == 4.0
    assert "events" not in workspace["run"]
    assert workspace["prepare"]["simulationReady"] is True

    assert STORE._conn is not None
    STORE._conn.execute("PRAGMA wal_checkpoint(FULL)")
    STORE._conn.close()

    revived = MemoryStore(db_path=DB_PATH)
    assert revived.get_project(pid)["name"] == "工作台方案"
    loaded_layout = revived.get_layout(pid, layout_ref["id"], layout_ref["revision"])
    assert loaded_layout is not None
    assert loaded_layout["revision"] == layout_ref["revision"]
    loaded_run = revived.get_run(body["runId"])
    assert loaded_run is not None
    assert loaded_run["kpi"]["cards"]["throughput"]["outboundPalletEq"] == 4.0
    again = revived.workspace(pid)
    assert again is not None
    assert again["layout"]["id"] == layout_ref["id"]
    assert again["run"]["runId"] == body["runId"]
    assert again["variant"]["id"] == variant["id"]

    # 叉车加一是旁路布局，不能抢走当前画布
    alt = deepcopy(layout)
    alt["id"] = "layout-workbench-alt"
    alt["revision"] = "ld-alt-persist"
    revived.put_layout_revision(pid, alt, base_revision=None)
    revived.put_variant(
        pid,
        {
            "id": "variant-alt",
            "revision": "vr-alt",
            "name": "叉车加一",
            "layoutRef": {"id": alt["id"], "revision": alt["revision"]},
        },
    )
    kept = revived.workspace(pid)
    assert kept is not None
    assert kept["layout"]["id"] == layout_ref["id"]
    assert kept["run"]["runId"] == body["runId"]

    print(f"PASS persist sqlite reload runId={body['runId']} db={DB_PATH}")


if __name__ == "__main__":
    main()
