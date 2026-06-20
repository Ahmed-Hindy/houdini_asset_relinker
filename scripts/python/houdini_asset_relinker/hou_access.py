"""Small import helpers for Houdini's `hou` module."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
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


@contextmanager
def undo_group(label: str) -> Generator[None, None, None]:
    """Context manager to group Houdini operations into a single undo block."""
    import hou  # type: ignore[import-not-found]

    with hou.undos.group(label):
        yield
