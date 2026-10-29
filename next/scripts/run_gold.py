#!/usr/bin/env python3
"""G-EDGE-01..03 and G-BREAK-01..04. A passing fixture is not a warehouse-wide KPI claim."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "next"))

from des.gold import run_suite  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run_suite())
