"""Load next/contracts schemas. This package does not import the old tree."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"

FORMAL_TYPE = r"^[A-Z]+(-[A-Z]+)+-[0-9]{2}$"


@lru_cache(maxsize=None)
def schema(rel: str) -> Dict[str, Any]:
    return json.loads((SCHEMAS / rel).read_text(encoding="utf-8"))


def schema_errors(instance: Dict[str, Any], rel: str) -> List[str]:
    validator = Draft7Validator(schema(rel))
    found = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    out = []
    for err in found:
        loc = "/".join(str(p) for p in err.path) or "(root)"
        out.append(f"{loc}: {err.message}")
    return out
