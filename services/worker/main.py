"""Worker entrypoint — M3：DES 经 API /simulation-jobs；规划/派生同进程可调。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="simapp worker")
    parser.add_argument("--ping", action="store_true", help="print capability JSON and exit")
    args = parser.parse_args()
    try:
        from simapp_des import ENGINE_VERSION
    except ImportError:
        ENGINE_VERSION = "unavailable"
    payload = {
        "role": "compute-worker",
        "status": "idle",
        "contractVersion": "0.3",
        "milestone": "M3",
        "engineVersion": ENGINE_VERSION,
        "capabilities": {
            "geometry": "aabb+segment",
            "derive": True,
            "validate": True,
            "planning": True,
            "planningScope": "DEC-05 ambient single-floor axis-aligned + ST-PAL-01",
            "evaluationLevel": ["quick", "detailed"],
            "des": True,
            "kpiFromUiDemo": False,
            "claimsOperationalEfficiency": True,
        },
        "contracts": str(ROOT / "contracts"),
        "fixtures": str(ROOT / "fixtures"),
        "message": "M3: DES via API /simulation-jobs; prepare required; KPI from events not UI demo",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.ping:
        print("No job loop; use API /simulation-jobs, /planning-jobs, /layouts/{id}/prepare-jobs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
