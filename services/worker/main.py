"""Worker entrypoint — M4：成本/比较经 API；DES/规划同进程可调。"""

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
    try:
        from simapp_cost import COST_ENGINE_VERSION
    except ImportError:
        COST_ENGINE_VERSION = "unavailable"
    try:
        from simapp_compare import COMPARE_ENGINE_VERSION
    except ImportError:
        COMPARE_ENGINE_VERSION = "unavailable"
    payload = {
        "role": "compute-worker",
        "status": "idle",
        "contractVersion": "0.3",
        "milestone": "M4",
        "engineVersion": ENGINE_VERSION,
        "costEngineVersion": COST_ENGINE_VERSION,
        "compareEngineVersion": COMPARE_ENGINE_VERSION,
        "capabilities": {
            "geometry": "aabb+segment",
            "derive": True,
            "validate": True,
            "planning": True,
            "planningScope": "DEC-05 ambient single-floor axis-aligned + ST-PAL-01",
            "evaluationLevel": ["quick", "detailed"],
            "des": True,
            "bomCost": True,
            "comparison": True,
            "deliveryReport": True,
            "kpiFromUiDemo": False,
            "claimsOperationalEfficiency": True,
            "missingPriceBlocksLowestCost": True,
            "missingAxisNoZeroFill": True,
        },
        "contracts": str(ROOT / "contracts"),
        "fixtures": str(ROOT / "fixtures"),
        "message": (
            "M4: cost-estimate / comparisons / reports via API; "
            "DES via /simulation-jobs; missing price blocks lowest-cost ranking"
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.ping:
        print(
            "No job loop; use API /cost-estimate-jobs, /comparisons, /reports, "
            "/simulation-jobs, /planning-jobs, /layouts/{id}/prepare-jobs."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
