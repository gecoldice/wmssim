"""Load JSON Schemas shipped under contracts/schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "contracts" / "schemas"


@lru_cache(maxsize=32)
def load_schema(relative: str) -> Dict[str, Any]:
    path = SCHEMAS / relative
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def manifest() -> Dict[str, Any]:
    return load_schema("manifest.json")
