"""Worker entrypoint — M1 可被 API 同进程调用派生/校验；无 DES/规划。"""

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
        "milestone": "M1",
        "capabilities": {
            "geometry": "aabb+segment",
            "derive": True,
            "validate": True,
            "planning": False,
            "des": False,
            "kpiFromUiDemo": False,
        },
        "contracts": str(ROOT / "contracts"),
        "fixtures": str(ROOT / "fixtures"),
        "message": "M1: derive/validate available via API prepare-jobs; no DES/planning",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.ping:
        print("No job loop; use API /layouts/{id}/prepare-jobs for M1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
