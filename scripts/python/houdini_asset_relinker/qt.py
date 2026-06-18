"""Qt binding compatibility for Houdini and standalone launches."""

from __future__ import annotations

from types import ModuleType

QT_BACKEND_NAME = ""

try:
    from PySide6 import QtCore, QtGui, QtWidgets

    QT_BACKEND_NAME = "PySide6"
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets  # type: ignore[assignment]

        QT_BACKEND_NAME = "PySide2"
    except ImportError as error:
        message = "Install PySide6 for standalone use, or run inside Houdini with PySide2."
        raise RuntimeError(message) from error


def qt_enum(enum_name: str, member_name: str) -> object:
    """Return a Qt enum member across PySide2 and PySide6.

    Args:
        enum_name: Scoped enum name used by PySide6, for example `ItemDataRole`.
        member_name: Member name, for example `DisplayRole`.

    Returns:
        The matching Qt enum value.
    """
    enum_owner = getattr(QtCore.Qt, enum_name, QtCore.Qt)
    return getattr(enum_owner, member_name)


__all__ = ["QT_BACKEND_NAME", "QtCore", "QtGui", "QtWidgets", "qt_enum"]

QtCore: ModuleType
QtGui: ModuleType
QtWidgets: ModuleType
