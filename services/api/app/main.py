"""Minimal FastAPI skeleton for M0 — health + contract metadata only."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

CONTRACT_VERSION = "0.3"
ROOT = Path(__file__).resolve().parents[3]

app = FastAPI(
    title="simapp API",
    version="0.3.0",
    description="M0 skeleton. Business endpoints land in later milestones.",
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


@app.get("/api/v1/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "contractVersion": CONTRACT_VERSION,
        "snapshotSchemaVersion": "0.2",
        "equipSchemaVersion": "0.2",
        "contractsRoot": str(ROOT / "contracts"),
    }


@app.post("/api/v1/projects", status_code=201)
def create_project(body: CreateProjectRequest) -> Project:
    return Project(
        contractVersion=CONTRACT_VERSION,
        id=f"project-{uuid4().hex[:8]}",
        name=body.name,
        unitSystem=body.unitSystem,
        createdAt=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    return {
        "id": job_id,
        "state": "failed",
        "phase": None,
        "outcome": None,
        "error": {
            "code": "COMPUTATION_FAILED",
            "message": "Job store not implemented in M0 skeleton",
            "details": None,
            "retryable": False,
            "traceId": None,
        },
    }
