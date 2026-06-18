"""Small import helpers for Houdini's `hou` module."""

from __future__ import annotations

from types import ModuleType


def get_hou() -> ModuleType:
    """Import and return Houdini's HOM module.

    Returns:
        The imported `hou` module.

    Raises:
        RuntimeError: If the code is running outside Houdini.
    """
    try:
        import hou  # type: ignore[import-not-found]
    except ImportError as error:
        message = "This function must run inside Houdini or hython where the hou module exists."
        raise RuntimeError(message) from error
    return hou
