"""Domain errors for the manual slice. Codes live in next/contracts."""

from __future__ import annotations

from typing import Any


class DesError(Exception):
    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details if details is not None else {}
