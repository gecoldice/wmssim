#!/usr/bin/env python3
"""G-CV-01/02/03 and MX-D1-CV. Passing asserts do not flip status off spec_only."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "next"))

from des.cveval import run_suite  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run_suite())
