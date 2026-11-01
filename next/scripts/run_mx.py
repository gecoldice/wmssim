#!/usr/bin/env python3
"""MX-D1/D2/D3-EB. Passing asserts do not flip status off spec_only."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "next"))

from des.mxeval import run_suite  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run_suite())
