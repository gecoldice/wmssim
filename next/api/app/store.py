"""In-process store. Revisions are server-issued opaque strings."""

from __future__ import annotations

import json
import secrets
import threading
from pathlib import Path
from typing import Any, Dict, Optional


def issue_revision(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


class Store:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.projects: Dict[str, Dict[str, Any]] = {}
        self.facilities: Dict[str, Dict[str, Any]] = {}
        self.layouts: Dict[str, Dict[str, Any]] = {}
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.runs: Dict[str, Dict[str, Any]] = {}
        if path and path.exists():
            self._load(path)

    def _load(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self.projects = data.get("projects") or {}
        self.facilities = data.get("facilities") or {}
        self.layouts = data.get("layouts") or {}
        self.jobs = data.get("jobs") or {}
        self.runs = data.get("runs") or {}

    def persist(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "projects": self.projects,
            "facilities": self.facilities,
            "layouts": self.layouts,
            "jobs": self.jobs,
            "runs": self.runs,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
