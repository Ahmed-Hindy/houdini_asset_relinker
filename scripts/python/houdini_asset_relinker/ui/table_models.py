"""Qt table models for scanned references and update reports."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Optional

from houdini_asset_relinker.models import (
    AssetReference,
    ReferenceKind,
    ReferenceRole,
    UpdateReport,
    UpdateResult,
    is_broken_relink_target,
    is_generated_output,
    normalized_reference_role,
)
from houdini_asset_relinker.qt import QtCore, QtGui
from houdini_asset_relinker.ui.qt_constants import (
    CASE_INSENSITIVE,
    DISPLAY_ROLE,
    FOREGROUND_ROLE,
    HORIZONTAL,
    INVALID_INDEX,
    TOOLTIP_ROLE,
    USER_ROLE,
)
from houdini_asset_relinker.ui.style import (
    STATUS_COLOR_MISSING,
    STATUS_COLOR_NOT_UPDATABLE,
    STATUS_COLOR_READY,
    STATUS_COLOR_UNDEFINED_VARIABLE,
)


class ReferenceTableModel(QtCore.QAbstractTableModel):
    """Table model for scanned Houdini references."""

    _columns = (
        ("status", "Status"),
        ("kind", "Kind"),
        ("reference_role", "Role"),
        ("node_path", "Node"),
        ("parm_path", "Parameter"),
        ("path_family", "Path Family"),
        ("raw_path", "Raw Path"),
        ("expanded_path", "Expanded Path"),
        ("can_update", "Writable"),
        ("reason", "Note"),
    )

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._references: list[AssetReference] = []

    def rowCount(self, parent: QtCore.QModelIndex = INVALID_INDEX) -> int:
        """Return the number of references in the model."""
        if parent.isValid():
            return 0
        return len(self._references)

    def columnCount(self, parent: QtCore.QModelIndex = INVALID_INDEX) -> int:
        """Return the number of visible reference columns."""
        if parent.isValid():
            return 0
        return len(self._columns)

    def data(self, index: QtCore.QModelIndex, role: int = DISPLAY_ROLE) -> object:
        """Return model data for a reference cell."""
        if not index.isValid():
            return None
        reference = self._references[index.row()]
        key = self._columns[index.column()][0]
        if role == DISPLAY_ROLE:
            return self._display_value(reference, key)
        if role == TOOLTIP_ROLE:
            return self._tooltip(reference)
        if role == FOREGROUND_ROLE and key == "status":
            return self._status_brush(reference)
        if role == USER_ROLE:
            return reference
        return None

    def headerData(self, section: int, orientation: object, role: int = DISPLAY_ROLE) -> object:
        """Return table header text."""
        if orientation == HORIZONTAL and role == DISPLAY_ROLE:
            return self._columns[section][1]
        return None

    def set_references(self, references: Iterable[AssetReference]) -> None:
        """Replace all references in the model."""
        self.beginResetModel()
        self._references = list(references)
        self.endResetModel()

    def references(self) -> list[AssetReference]:
        """Return a copy of the current references."""
        return list(self._references)

    def reference_at(self, row: int) -> AssetReference:
        """Return a reference by source-model row."""
        return self._references[row]

    def _display_value(self, reference: AssetReference, key: str) -> str:
        if key == "status":
            return _status_text(reference)
        if key == "kind":
            return "HDA Library" if reference.kind == ReferenceKind.HDA_LIBRARY else "File Parm"
        if key == "reference_role":
            return _reference_role_text(reference)
        if key == "parm_path":
            return _parameter_name(reference.parm_path)
        if key == "can_update":
            return "Yes" if reference.can_update else "No"
        if key == "reason":
            return _note_text(reference)
        value = getattr(reference, key)
        return str(value or "")

    def _tooltip(self, reference: AssetReference) -> str:
        location = reference.parm_path or reference.node_path or "<session/reference>"
        note = _note_text(reference)
        return "\n".join(
            [
                f"Location: {location}",
                f"Status: {_status_text(reference)}",
                f"Role: {_reference_role_text(reference)}",
                f"Path family: {reference.path_family}",
                f"Raw: {reference.raw_path}",
                f"Expanded: {reference.expanded_path}",
                f"Sequence pattern: {reference.sequence_pattern}",
                f"Note: {note}",
            ]
        )

    def _status_brush(self, reference: AssetReference) -> QtGui.QBrush:
        if is_generated_output(reference):
            return QtGui.QBrush(QtGui.QColor(STATUS_COLOR_NOT_UPDATABLE))
        if reference.missing_variables:
            return QtGui.QBrush(QtGui.QColor(STATUS_COLOR_UNDEFINED_VARIABLE))
        if not reference.exists:
            return QtGui.QBrush(QtGui.QColor(STATUS_COLOR_MISSING))
        if not reference.can_update:
            return QtGui.QBrush(QtGui.QColor(STATUS_COLOR_NOT_UPDATABLE))
        return QtGui.QBrush(QtGui.QColor(STATUS_COLOR_READY))


class ReferenceFilterProxy(QtCore.QSortFilterProxyModel):
    """Filter proxy for scanned references."""

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._search_text = ""
        self._show_missing_only = False
        self._show_writable_only = False
        self._kind_filter = "all"
        self.setFilterCaseSensitivity(CASE_INSENSITIVE)

    def set_search_text(self, text: str) -> None:
        """Set the free-text reference filter."""
        self._search_text = text.casefold().strip()
        self.invalidateFilter()

    def set_show_missing_only(self, enabled: bool) -> None:
        """Set whether only broken relink target rows are shown."""
        self._show_missing_only = enabled
        self.invalidateFilter()

    def set_show_writable_only(self, enabled: bool) -> None:
        """Set whether only writable references are shown."""
        self._show_writable_only = enabled
        self.invalidateFilter()

    def set_kind_filter(self, kind_filter: str) -> None:
        """Set the reference-kind filter."""
        self._kind_filter = kind_filter
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:
        """Return whether a source row should be visible."""
        source = self.sourceModel()
        if source is None:
            return False
        del source_parent
        reference = source.reference_at(source_row)
        if self._show_missing_only and not is_broken_relink_target(reference):
            return False
        if self._show_writable_only and not reference.can_update:
            return False
        if self._kind_filter == "file" and reference.kind != ReferenceKind.FILE_PARAMETER:
            return False
        if self._kind_filter == "hda" and reference.kind != ReferenceKind.HDA_LIBRARY:
            return False
        if not self._search_text:
            return True
        haystack = " ".join(
            [
                reference.kind.value,
                normalized_reference_role(reference),
                reference.node_path or "",
                reference.parm_path or "",
                reference.path_family,
                reference.raw_path,
                reference.expanded_path,
                reference.sequence_pattern,
                _missing_variables_text(reference),
                reference.reason,
            ]
        ).casefold()
        return self._search_text in haystack


class UpdateResultTableModel(QtCore.QAbstractTableModel):
    """Table model for path update previews and apply reports."""

    _columns = (
        ("status", "Status"),
        ("parm_path", "Target"),
        ("old_path", "Old Path"),
        ("new_path", "New Path"),
        ("message", "Message"),
    )

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._results: list[UpdateResult] = []

    def rowCount(self, parent: QtCore.QModelIndex = INVALID_INDEX) -> int:
        """Return the number of update results."""
        if parent.isValid():
            return 0
        return len(self._results)

    def columnCount(self, parent: QtCore.QModelIndex = INVALID_INDEX) -> int:
        """Return the number of update result columns."""
        if parent.isValid():
            return 0
        return len(self._columns)

    def data(self, index: QtCore.QModelIndex, role: int = DISPLAY_ROLE) -> object:
        """Return model data for an update-result cell."""
        if not index.isValid():
            return None
        result = self._results[index.row()]
        key = self._columns[index.column()][0]
        if role == DISPLAY_ROLE:
            return str(getattr(result, key) or "")
        if role == TOOLTIP_ROLE:
            return "\n".join([result.old_path, result.new_path, result.message]).strip()
        if role == FOREGROUND_ROLE and key == "status":
            return self._status_brush(result)
        return None

    def headerData(self, section: int, orientation: object, role: int = DISPLAY_ROLE) -> object:
        """Return table header text."""
        if orientation == HORIZONTAL and role == DISPLAY_ROLE:
            return self._columns[section][1]
        return None

    def set_report(self, report: Optional[UpdateReport]) -> None:
        """Replace all update results from a report."""
        self.beginResetModel()
        self._results = list(report.results) if report is not None else []
        self.endResetModel()

    def _status_brush(self, result: UpdateResult) -> QtGui.QBrush:
        if result.status == "failed":
            return QtGui.QBrush(QtGui.QColor(STATUS_COLOR_MISSING))
        if result.status == "skipped":
            return QtGui.QBrush(QtGui.QColor(STATUS_COLOR_NOT_UPDATABLE))
        return QtGui.QBrush(QtGui.QColor(STATUS_COLOR_READY))


def _parameter_name(parm_path: Optional[str]) -> str:
    if not parm_path:
        return ""
    return parm_path.rsplit("/", 1)[-1]


def _status_text(reference: AssetReference) -> str:
    """Return the user-visible reference status."""
    if is_generated_output(reference):
        return "Generated output"
    if reference.missing_variables:
        return "Undefined variable"
    if not reference.exists:
        return "Missing"
    if not reference.can_update:
        return "Read only"
    return "Ready"


def _note_text(reference: AssetReference) -> str:
    """Return the user-visible note for a reference."""
    if is_generated_output(reference):
        return reference.reason or "Generated output path kept for context"
    if reference.missing_variables:
        return _missing_variables_text(reference)
    return reference.reason or ("Writable reference" if reference.can_update else "Not writable")


def _reference_role_text(reference: AssetReference) -> str:
    """Return a user-visible high-level role for a reference."""
    role = normalized_reference_role(reference)
    if role == ReferenceRole.GENERATED_OUTPUT.value:
        return "Generated output"
    if role == ReferenceRole.HDA_LIBRARY.value:
        return "HDA library"
    return "Inbound dependency"


def _missing_variables_text(reference: AssetReference) -> str:
    """Return a readable undefined-variable note."""
    if not reference.missing_variables:
        return ""
    return f"Undefined variables: {', '.join(reference.missing_variables)}"
