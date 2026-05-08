"""Shared helpers for optional third-party integrations."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Optional


class IntegrationUnavailableError(RuntimeError):
    """Raised when an optional integration dependency is not installed or configured."""


def require_optional_dependency(module_name: str, *, extra: str = "ai-integrations") -> ModuleType:
    """Import an optional module with a project-specific install hint."""

    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise IntegrationUnavailableError(
            "optional integration dependency is unavailable: "
            f"{module_name}. Install with `pip install -e '.[{extra}]'`."
        ) from exc


def optional_dependency(module_name: str) -> Optional[ModuleType]:
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None
