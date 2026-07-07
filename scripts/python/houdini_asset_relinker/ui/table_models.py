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
    UpdateStatus,
    is_broken_relink_target,
    normalized_reference_role,
)
from houdini_asset_relinker.path_utils import matches_find_text
from houdini_asset_relinker.qt import QtCore, QtGui
from houdini_asset_relinker.ui.qt_constants import (
    BACKGROUND_ROLE,
    CASE_INSENSITIVE,
    DISPLAY_ROLE,
    FOREGROUND_ROLE,
    HORIZONTAL,
    INVALID_INDEX,
    TOOLTIP_ROLE,
    USER_ROLE,
)
from houdini_asset_relinker.ui.reference_display import (
    REFERENCE_STATUS_GENERATED_OUTPUT,
    REFERENCE_STATUS_MISSING,
    REFERENCE_STATUS_READ_ONLY,
    REFERENCE_STATUS_READY,
    REFERENCE_STATUS_UNDEFINED_VARIABLE,
    missing_variables_text,
    reference_note_text,
    reference_status,
    reference_status_text,
)
from houdini_asset_relinker.ui.style import (
    FIND_MATCH_ROW_COLOR,
    REPORT_STATUS_TINT_MIX,
    REPORT_TABLE_ALT_BASE_COLOR,
    REPORT_TABLE_BASE_COLOR,
    STATUS_COLOR_MISSING,
    STATUS_COLOR_NOT_UPDATABLE,
    STATUS_COLOR_READY,
    STATUS_COLOR_UNDEFINED_VARIABLE,
)

_STATUS_COLOR_BY_REFERENCE_STATUS = {
    REFERENCE_STATUS_GENERATED_OUTPUT: STATUS_COLOR_NOT_UPDATABLE,
    REFERENCE_STATUS_UNDEFINED_VARIABLE: STATUS_COLOR_UNDEFINED_VARIABLE,
    REFERENCE_STATUS_MISSING: STATUS_COLOR_MISSING,
    REFERENCE_STATUS_READ_ONLY: STATUS_COLOR_NOT_UPDATABLE,
    REFERENCE_STATUS_READY: STATUS_COLOR_READY,
}


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
        self._find_text = ""
        self._find_case_sensitive = False

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
        if role == BACKGROUND_ROLE and self._reference_matches_find(reference):
            return QtGui.QBrush(QtGui.QColor(FIND_MATCH_ROW_COLOR))
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

    def set_find_highlight(self, find_text: str, case_sensitive: bool = False) -> None:
        """Highlight rows whose raw path matches the current relink Find text."""
        self._find_text = find_text
        self._find_case_sensitive = case_sensitive
        if not self._references:
            return
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self._references) - 1, len(self._columns) - 1)
        self.dataChanged.emit(top_left, bottom_right, [BACKGROUND_ROLE])

    def find_match_count(self) -> int:
        """Return how many references match the current relink Find text."""
        if not self._find_text:
            return 0
        return sum(1 for reference in self._references if self._reference_matches_find(reference))

    def _reference_matches_find(self, reference: AssetReference) -> bool:
        return matches_find_text(
            reference.raw_path,
            self._find_text,
            self._find_case_sensitive,
        )

    def _display_value(self, reference: AssetReference, key: str) -> str:
        if key == "status":
            return reference_status_text(reference)
        if key == "kind":
            return "HDA Library" if reference.kind == ReferenceKind.HDA_LIBRARY else "File Parm"
        if key == "reference_role":
            return _reference_role_text(reference)
        if key == "parm_path":
            return _parameter_name(reference.parm_path)
        if key == "can_update":
            return "Yes" if reference.can_update else "No"
        if key == "reason":
            return reference_note_text(reference)
        value = getattr(reference, key)
        return str(value or "")

    def _tooltip(self, reference: AssetReference) -> str:
        location = reference.parm_path or reference.node_path or "<session/reference>"
        note = reference_note_text(reference)
        return "\n".join(
            [
                f"Location: {location}",
                f"Status: {reference_status_text(reference)}",
                f"Role: {_reference_role_text(reference)}",
                f"Path family: {reference.path_family}",
                f"Raw: {reference.raw_path}",
                f"Expanded: {reference.expanded_path}",
                f"Sequence pattern: {reference.sequence_pattern}",
                f"Note: {note}",
            ]
        )

    def _status_brush(self, reference: AssetReference) -> QtGui.QBrush:
        color = _STATUS_COLOR_BY_REFERENCE_STATUS[reference_status(reference)]
        return QtGui.QBrush(QtGui.QColor(color))


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
        self._update_filter_state("_search_text", text.casefold().strip())

    def set_show_missing_only(self, enabled: bool) -> None:
        """Set whether only broken relink target rows are shown."""
        self._update_filter_state("_show_missing_only", enabled)

    def set_show_writable_only(self, enabled: bool) -> None:
        """Set whether only writable references are shown."""
        self._update_filter_state("_show_writable_only", enabled)

    def set_kind_filter(self, kind_filter: str) -> None:
        """Set the reference-kind filter."""
        self._update_filter_state("_kind_filter", kind_filter)

    def _update_filter_state(self, attribute_name: str, value: object) -> None:
        """Update filter state across PySide versions without deprecation noise."""
        begin_filter_change = getattr(self, "beginFilterChange", None)
        end_filter_change = getattr(self, "endFilterChange", None)
        if callable(begin_filter_change) and callable(end_filter_change):
            begin_filter_change()
            setattr(self, attribute_name, value)
            end_filter_change()
            return
        setattr(self, attribute_name, value)
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
                missing_variables_text(reference),
                reference.reason,
            ]
        ).casefold()
        return self._search_text in haystack


class UpdateResultTableModel(QtCore.QAbstractTableModel):
    """Table model for path update previews and apply reports."""

    _columns = (
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
            return _result_tooltip(result)
        if role == BACKGROUND_ROLE:
            return _result_status_tint_brush(result, index.row())
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


def _result_status_label(result: UpdateResult) -> str:
    """Return a user-visible label for an update result."""
    if result.status == UpdateStatus.WOULD_CHANGE:
        return "Planned change"
    if result.status == UpdateStatus.CHANGED:
        return "Applied"
    if result.status == UpdateStatus.SKIPPED:
        return "Skipped"
    if result.status == UpdateStatus.FAILED:
        return "Failed"
    return result.status.value


def _result_status_color(result: UpdateResult) -> Optional[str]:
    """Return the status accent color for an update result."""
    if result.status == UpdateStatus.FAILED:
        return STATUS_COLOR_MISSING
    if result.status == UpdateStatus.SKIPPED:
        return STATUS_COLOR_NOT_UPDATABLE
    if result.status == UpdateStatus.CHANGED:
        return STATUS_COLOR_READY
    return None


def _blend_hex_color(base_hex: str, accent_hex: str, mix: float) -> QtGui.QColor:
    """Blend an accent color onto a base background as an opaque tint."""
    base = QtGui.QColor(base_hex)
    accent = QtGui.QColor(accent_hex)
    ratio = max(0.0, min(mix, 1.0))
    inverse = 1.0 - ratio
    return QtGui.QColor(
        int(base.red() * inverse + accent.red() * ratio),
        int(base.green() * inverse + accent.green() * ratio),
        int(base.blue() * inverse + accent.blue() * ratio),
    )


def _result_status_tint_brush(result: UpdateResult, row: int) -> QtGui.QBrush:
    """Return an opaque row background tint for an update result."""
    base = REPORT_TABLE_ALT_BASE_COLOR if row % 2 else REPORT_TABLE_BASE_COLOR
    accent = _result_status_color(result)
    if accent is None:
        return QtGui.QBrush(QtGui.QColor(base))
    color = _blend_hex_color(base, accent, REPORT_STATUS_TINT_MIX)
    return QtGui.QBrush(color)


def _result_tooltip(result: UpdateResult) -> str:
    """Return tooltip text for an update result row."""
    parts = [
        f"Status: {_result_status_label(result)}",
        result.old_path,
        result.new_path,
        result.message,
    ]
    return "\n".join(part for part in parts if part).strip()


def _parameter_name(parm_path: Optional[str]) -> str:
    if not parm_path:
        return ""
    return parm_path.rsplit("/", 1)[-1]


def _reference_role_text(reference: AssetReference) -> str:
    """Return a user-visible high-level role for a reference."""
    role = normalized_reference_role(reference)
    if role == ReferenceRole.GENERATED_OUTPUT.value:
        return "Generated output"
    if role == ReferenceRole.HDA_LIBRARY.value:
        return "HDA library"
    return "Inbound dependency"
