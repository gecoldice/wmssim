"""Worker entrypoint — M2：规划基线可被 API 同进程调用；无 DES。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="simapp worker")
    parser.add_argument("--ping", action="store_true", help="print capability JSON and exit")
    args = parser.parse_args()
    payload = {
        "role": "compute-worker",
        "status": "idle",
        "contractVersion": "0.3",
        "milestone": "M2",
        "capabilities": {
            "geometry": "aabb+segment",
            "derive": True,
            "validate": True,
            "planning": True,
            "planningScope": "DEC-05 ambient single-floor axis-aligned + ST-PAL-01",
            "evaluationLevel": ["quick"],
            "des": False,
            "kpiFromUiDemo": False,
            "claimsOperationalEfficiency": False,
        },
        "contracts": str(ROOT / "contracts"),
        "fixtures": str(ROOT / "fixtures"),
        "message": "M2: planning baseline via API /planning-jobs; quick geo/path only; no DES",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.ping:
        print("No job loop; use API /planning-jobs and /layouts/{id}/prepare-jobs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
