"""Manual-slice DES, derive, and validate. No dependency on the legacy engine package."""

from .engine import ENGINE_VERSION, METRIC_DEFINITION_VERSION, run_des
from .errors import DesError

__all__ = ["ENGINE_VERSION", "METRIC_DEFINITION_VERSION", "DesError", "run_des"]
