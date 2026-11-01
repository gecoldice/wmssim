#!/usr/bin/env python3
"""Run the forklift-count search golds. Passing does not price a layout."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "next"))

from des.plan import run_suite  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run_suite())
