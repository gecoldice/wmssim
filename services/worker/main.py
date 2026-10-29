"""Worker entrypoint skeleton.

M0 does not run DES/planning; this process only reports capability and
refuses to invent KPI from UI demo formulas.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="simapp worker skeleton")
    parser.add_argument("--ping", action="store_true", help="print capability JSON and exit")
    args = parser.parse_args()
    payload = {
        "role": "compute-worker",
        "status": "idle",
        "contractVersion": "0.3",
        "capabilities": {
            "geometry": "planned",
            "planning": "planned",
            "des": "planned",
            "kpiFromUiDemo": False,
        },
        "contracts": str(ROOT / "contracts"),
        "fixtures": str(ROOT / "fixtures"),
        "message": "M0 skeleton only — no compute yet",
    }
    if args.ping:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("Worker has no job loop in M0. Exit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
