"""PySide asset relinker window for Houdini and standalone sessions."""

from __future__ import annotations

import os
import traceback
from collections.abc import Iterable
from pathlib import Path
from typing import Optional

from houdini_asset_relinker.export import write_references_csv
from houdini_asset_relinker.hou_access import get_hou
from houdini_asset_relinker.models import AssetReference, ReferenceKind, UpdateReport, UpdateResult
from houdini_asset_relinker.qt import QT_BACKEND_NAME, QtCore, QtGui, QtWidgets, qt_enum
from houdini_asset_relinker.scanner import scan_assets
from houdini_asset_relinker.updater import replace_hda_library_paths, replace_path_text

DISPLAY_ROLE = qt_enum("ItemDataRole", "DisplayRole")
FOREGROUND_ROLE = qt_enum("ItemDataRole", "ForegroundRole")
TOOLTIP_ROLE = qt_enum("ItemDataRole", "ToolTipRole")
USER_ROLE = qt_enum("ItemDataRole", "UserRole")
HORIZONTAL = qt_enum("Orientation", "Horizontal")
CASE_INSENSITIVE = qt_enum("CaseSensitivity", "CaseInsensitive")
CUSTOM_CONTEXT_MENU = qt_enum("ContextMenuPolicy", "CustomContextMenu")
ASCENDING_ORDER = qt_enum("SortOrder", "AscendingOrder")
WAIT_CURSOR = qt_enum("CursorShape", "WaitCursor")
ARROW_CURSOR = qt_enum("CursorShape", "ArrowCursor")
TOOL_BUTTON_TEXT_ONLY = qt_enum("ToolButtonStyle", "ToolButtonTextOnly")
INVALID_INDEX = QtCore.QModelIndex()
try:
    ACTION_CLASS = QtGui.QAction
    SELECT_ROWS = QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
    SINGLE_SELECTION = QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
    HEADER_INTERACTIVE = QtWidgets.QHeaderView.ResizeMode.Interactive
    MESSAGE_OK = QtWidgets.QMessageBox.StandardButton.Ok
    MESSAGE_CANCEL = QtWidgets.QMessageBox.StandardButton.Cancel
    MESSAGE_CRITICAL = QtWidgets.QMessageBox.Icon.Critical
except AttributeError:
    ACTION_CLASS = QtWidgets.QAction
    SELECT_ROWS = QtWidgets.QAbstractItemView.SelectRows
    SINGLE_SELECTION = QtWidgets.QAbstractItemView.SingleSelection
    HEADER_INTERACTIVE = QtWidgets.QHeaderView.Interactive
    MESSAGE_OK = QtWidgets.QMessageBox.Ok
    MESSAGE_CANCEL = QtWidgets.QMessageBox.Cancel
    MESSAGE_CRITICAL = QtWidgets.QMessageBox.Critical

WINDOW_OBJECT_NAME = "houdiniAssetRelinkerWindow"
_WINDOW: Optional[AssetRelinkerWindow] = None


class ReferenceTableModel(QtCore.QAbstractTableModel):
    """Table model for scanned Houdini references."""

    _columns = (
        ("status", "Status"),
        ("kind", "Kind"),
        ("node_path", "Node"),
        ("parm_path", "Parameter"),
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
            if not reference.exists:
                return "Missing"
            if not reference.can_update:
                return "Read only"
            return "Ready"
        if key == "kind":
            return "HDA Library" if reference.kind == ReferenceKind.HDA_LIBRARY else "File Parm"
        if key == "parm_path":
            return _parameter_name(reference.parm_path)
        if key == "can_update":
            return "Yes" if reference.can_update else "No"
        value = getattr(reference, key)
        return str(value or "")

    def _tooltip(self, reference: AssetReference) -> str:
        location = reference.parm_path or reference.node_path or "<session/reference>"
        note = reference.reason or (
            "Writable reference" if reference.can_update else "Not writable"
        )
        return "\n".join(
            [
                f"Location: {location}",
                f"Raw: {reference.raw_path}",
                f"Expanded: {reference.expanded_path}",
                f"Note: {note}",
            ]
        )

    def _status_brush(self, reference: AssetReference) -> QtGui.QBrush:
        if not reference.exists:
            return QtGui.QBrush(QtGui.QColor("#d9534f"))
        if not reference.can_update:
            return QtGui.QBrush(QtGui.QColor("#d99000"))
        return QtGui.QBrush(QtGui.QColor("#2f8f46"))


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
        """Set whether only missing references are shown."""
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
        if self._show_missing_only and reference.exists:
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
                reference.node_path or "",
                reference.parm_path or "",
                reference.raw_path,
                reference.expanded_path,
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
            return QtGui.QBrush(QtGui.QColor("#d9534f"))
        if result.status == "skipped":
            return QtGui.QBrush(QtGui.QColor("#d99000"))
        return QtGui.QBrush(QtGui.QColor("#2f8f46"))


class AssetRelinkerWindow(QtWidgets.QMainWindow):
    """Main PySide window for scanning and relinking Houdini asset paths."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle(f"Asset Relinker - {QT_BACKEND_NAME}")
        self.resize(1280, 760)

        self._reference_model = ReferenceTableModel(self)
        self._proxy_model = ReferenceFilterProxy(self)
        self._proxy_model.setSourceModel(self._reference_model)
        self._report_model = UpdateResultTableModel(self)
        self._preview_report: Optional[UpdateReport] = None
        self._current_report: Optional[UpdateReport] = None

        self._build_actions()
        self._build_ui()
        self._connect_signals()
        self._set_status("Ready. Scan the current Houdini session to begin.")

    def scan(self) -> None:
        """Scan the current Houdini session and update the reference table."""
        self._set_busy(True)
        try:
            references = scan_assets(
                project_dir_variable=self.project_variable_edit.text().strip() or "HIP",
                include_all_refs=self.include_all_refs_check.isChecked(),
                include_hda_libraries=self.include_hda_check.isChecked(),
            )
        except Exception as error:
            self._show_error("Scan failed", error)
            return
        finally:
            self._set_busy(False)

        self._reference_model.set_references(references)
        self._clear_report()
        self._update_summary()
        self._set_status(f"Scanned {len(references)} references.")
        if references:
            self.reference_table.selectRow(0)

    def preview_replace(self) -> None:
        """Run a dry-run replacement preview from the current settings."""
        find_text = self.find_edit.text()
        replace_with = self.replace_edit.text()
        if not find_text:
            self._warn("Find text cannot be empty.")
            return
        references = self._reference_model.references()
        if not references:
            self._warn("Scan the scene before previewing replacements.")
            return

        self._set_busy(True)
        try:
            reports = [
                replace_path_text(
                    find_text,
                    replace_with,
                    dry_run=True,
                    references=references,
                    case_sensitive=self.case_sensitive_check.isChecked(),
                )
            ]
            if self.include_hda_replace_check.isChecked():
                reports.append(
                    replace_hda_library_paths(
                        find_text,
                        replace_with,
                        dry_run=True,
                        references=references,
                        case_sensitive=self.case_sensitive_check.isChecked(),
                    )
                )
        except Exception as error:
            self._show_error("Preview failed", error)
            return
        finally:
            self._set_busy(False)

        self._preview_report = _merge_reports(True, reports)
        self._current_report = self._preview_report
        self._report_model.set_report(self._preview_report)
        self.apply_button.setEnabled(bool(self._preview_report.results))
        self.copy_report_action.setEnabled(bool(self._preview_report.results))
        self._set_status(
            f"Preview found {self._preview_report.changed_count} planned changes, "
            f"{self._preview_report.skipped_count} skipped, "
            f"{self._preview_report.failed_count} failed."
        )

    def apply_replace(self) -> None:
        """Apply the last previewed replacement after confirmation."""
        if self._preview_report is None or not self._preview_report.results:
            self._warn("Preview replacements before applying changes.")
            return
        answer = QtWidgets.QMessageBox.warning(
            self,
            "Apply Asset Relinks",
            (
                "This will update writable Houdini parameters"
                " and selected HDA library references in the current session.\n\n"
                "Save a copy of the hip file before applying large relinks."
            ),
            MESSAGE_OK | MESSAGE_CANCEL,
            MESSAGE_CANCEL,
        )
        if answer != MESSAGE_OK:
            return

        find_text = self.find_edit.text()
        replace_with = self.replace_edit.text()
        references = self._reference_model.references()
        self._set_busy(True)
        try:
            reports = [
                replace_path_text(
                    find_text,
                    replace_with,
                    dry_run=False,
                    references=references,
                    case_sensitive=self.case_sensitive_check.isChecked(),
                )
            ]
            if self.include_hda_replace_check.isChecked():
                reports.append(
                    replace_hda_library_paths(
                        find_text,
                        replace_with,
                        dry_run=False,
                        uninstall_old=self.uninstall_old_hda_check.isChecked(),
                        references=references,
                        case_sensitive=self.case_sensitive_check.isChecked(),
                    )
                )
        except Exception as error:
            self._show_error("Apply failed", error)
            return
        finally:
            self._set_busy(False)

        report = _merge_reports(False, reports)
        self._preview_report = None
        self.scan()
        self._current_report = report
        self._report_model.set_report(report)
        self.apply_button.setEnabled(False)
        self.copy_report_action.setEnabled(bool(report.results))
        self._set_status(
            f"Applied {report.changed_count} changes, "
            f"{report.skipped_count} skipped, {report.failed_count} failed."
        )

    def export_csv(self) -> None:
        """Export the current scan result table to CSV."""
        references = self._reference_model.references()
        if not references:
            self._warn("Scan the scene before exporting a CSV report.")
            return
        default_path = _default_export_path()
        output_path, _selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Asset Relinker CSV",
            default_path,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not output_path:
            return
        try:
            written_path = write_references_csv(references, output_path)
        except Exception as error:
            self._show_error("Export failed", error)
            return
        self._set_status(f"Wrote CSV report: {written_path}")

    def copy_selected_reference_path(self) -> None:
        """Copy the selected reference path to the clipboard."""
        reference = self._selected_reference()
        if reference is None:
            return
        QtWidgets.QApplication.clipboard().setText(reference.raw_path)
        self._set_status("Copied raw path to clipboard.")

    def reveal_selected_reference(self) -> None:
        """Open the selected reference in Explorer when it exists on disk."""
        reference = self._selected_reference()
        if reference is None:
            return
        path = Path(reference.expanded_path)
        target = path if path.exists() and path.is_dir() else path.parent
        if not target.exists():
            self._warn("The selected expanded path does not exist on disk.")
            return
        os.startfile(str(target))  # noqa: S606

    def select_selected_node(self) -> None:
        """Select the owning Houdini node for the selected reference when possible."""
        reference = self._selected_reference()
        if reference is None or not reference.node_path:
            return
        try:
            hou = get_hou()
            node = hou.node(reference.node_path)
            if node is None:
                self._warn("The selected node no longer exists.")
                return
            network_editor = self._network_editor_for_current_desktop(hou)
            if network_editor is not None:
                self._jump_network_editor_to_node(network_editor, node)
            node.setSelected(True, clear_all_selected=True)
            if network_editor is not None:
                self._frame_network_editor_selection(network_editor)
                self._set_status(f"Selected and framed node: {reference.node_path}")
            else:
                self._set_status(f"Selected node: {reference.node_path}")
        except Exception as error:
            self._show_error("Could not select node", error)

    def copy_report(self) -> None:
        """Copy the current update report to the clipboard."""
        if self._current_report is None or not self._current_report.results:
            return
        QtWidgets.QApplication.clipboard().setText(self._current_report.to_text(max_rows=10_000))
        self._set_status("Copied update report to clipboard.")

    def _build_actions(self) -> None:
        self.scan_action = ACTION_CLASS("Scan", self)
        self.scan_action.setToolTip("Scan the current Houdini scene for external asset references.")
        self.scan_action.setStatusTip(
            "Scan the current Houdini scene for external asset references."
        )
        self.scan_action.setShortcut("F5")
        self.export_action = ACTION_CLASS("Export CSV", self)
        self.export_action.setToolTip("Export the current reference table to a CSV report.")
        self.export_action.setStatusTip("Export the current reference table to a CSV report.")
        self.copy_path_action = ACTION_CLASS("Copy Raw Path", self)
        self.copy_path_action.setToolTip("Copy the selected reference's raw path expression.")
        self.copy_path_action.setStatusTip("Copy the selected reference's raw path expression.")
        self.reveal_action = ACTION_CLASS("Reveal on Disk", self)
        self.reveal_action.setToolTip("Open the selected reference's folder in Explorer.")
        self.reveal_action.setStatusTip("Open the selected reference's folder in Explorer.")
        self.select_node_action = ACTION_CLASS("Select Node", self)
        self.select_node_action.setToolTip(
            "Jump the Network Editor to the selected reference's node and select it."
        )
        self.select_node_action.setStatusTip(
            "Jump the Network Editor to the selected reference's node and select it."
        )
        self.copy_report_action = ACTION_CLASS("Copy Report", self)
        self.copy_report_action.setToolTip("Copy the latest preview or apply report.")
        self.copy_report_action.setStatusTip("Copy the latest preview or apply report.")
        self.copy_report_action.setEnabled(False)

    def _build_ui(self) -> None:
        toolbar = self.addToolBar("Asset Relinker")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(TOOL_BUTTON_TEXT_ONLY)
        toolbar.addAction(self.scan_action)
        toolbar.addAction(self.export_action)
        toolbar.addSeparator()
        toolbar.addAction(self.copy_path_action)
        toolbar.addAction(self.reveal_action)
        toolbar.addAction(self.select_node_action)
        toolbar.addSeparator()
        toolbar.addAction(self.copy_report_action)

        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        main_layout.addWidget(self._build_scan_bar())
        main_layout.addWidget(self._build_summary_row())

        self.main_splitter = QtWidgets.QSplitter(self)
        self.main_splitter.addWidget(self._build_reference_panel())
        self.main_splitter.addWidget(self._build_side_panel())
        self.main_splitter.setSizes([860, 420])
        main_layout.addWidget(self.main_splitter, 1)

        self.status_label = QtWidgets.QLabel(self)
        self.statusBar().addPermanentWidget(self.status_label, 1)
        self._apply_style()

    def _build_scan_bar(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.project_variable_edit = QtWidgets.QLineEdit("HIP", self)
        self.project_variable_edit.setMaximumWidth(90)
        self.project_variable_edit.setToolTip(
            "Houdini project variable passed to hou.fileReferences, usually HIP."
        )
        self.include_all_refs_check = QtWidgets.QCheckBox("All refs", self)
        self.include_all_refs_check.setChecked(True)
        self.include_all_refs_check.setToolTip(
            "Include all Houdini file references instead of only selected references."
        )
        self.include_hda_check = QtWidgets.QCheckBox("HDA libraries", self)
        self.include_hda_check.setChecked(True)
        self.include_hda_check.setToolTip("Include loaded HDA library files in the scan.")

        self.scan_button = QtWidgets.QPushButton("Scan Scene", self)
        self.scan_button.setDefault(True)
        self.scan_button.setMinimumWidth(92)
        self.scan_button.setToolTip("Scan the current Houdini scene for external asset references.")
        self.export_button = QtWidgets.QPushButton("Export CSV", self)
        self.export_button.setMinimumWidth(92)
        self.export_button.setToolTip("Export the current reference table to a CSV report.")

        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("Filter by node, parameter, path, or note")
        self.search_edit.setToolTip("Filter references by node, parameter, path, kind, or note.")
        self.missing_only_check = QtWidgets.QCheckBox("Missing only", self)
        self.missing_only_check.setToolTip("Show only references whose expanded paths are missing.")
        self.writable_only_check = QtWidgets.QCheckBox("Writable only", self)
        self.writable_only_check.setToolTip("Show only references the relinker can update.")
        self.kind_combo = QtWidgets.QComboBox(self)
        self.kind_combo.setToolTip("Limit the table to a specific reference kind.")
        self.kind_combo.addItem("All kinds", "all")
        self.kind_combo.addItem("File parameters", "file")
        self.kind_combo.addItem("HDA libraries", "hda")

        layout.addWidget(QtWidgets.QLabel("Project var", self))
        layout.addWidget(self.project_variable_edit)
        layout.addWidget(self.include_all_refs_check)
        layout.addWidget(self.include_hda_check)
        layout.addWidget(self.scan_button)
        layout.addWidget(self.export_button)
        layout.addSpacing(12)
        layout.addWidget(self.search_edit, 1)
        layout.addWidget(self.missing_only_check)
        layout.addWidget(self.writable_only_check)
        layout.addWidget(self.kind_combo)
        return panel

    def _build_summary_row(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.total_stat = self._stat_label("Total", "0")
        self.missing_stat = self._stat_label("Missing", "0")
        self.writable_stat = self._stat_label("Writable", "0")
        self.hda_stat = self._stat_label("HDA", "0")
        self.visible_stat = self._stat_label("Visible", "0")
        for widget in [
            self.total_stat,
            self.missing_stat,
            self.writable_stat,
            self.hda_stat,
            self.visible_stat,
        ]:
            layout.addWidget(widget)
        layout.addStretch(1)
        return panel

    def _build_reference_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.reference_table = QtWidgets.QTableView(self)
        self.reference_table.setModel(self._proxy_model)
        self.reference_table.setSortingEnabled(True)
        self.reference_table.sortByColumn(0, ASCENDING_ORDER)
        self.reference_table.setSelectionBehavior(SELECT_ROWS)
        self.reference_table.setSelectionMode(SINGLE_SELECTION)
        self.reference_table.setAlternatingRowColors(True)
        self.reference_table.setContextMenuPolicy(CUSTOM_CONTEXT_MENU)
        self.reference_table.verticalHeader().setVisible(False)
        self.reference_table.horizontalHeader().setStretchLastSection(True)
        self.reference_table.horizontalHeader().setSectionResizeMode(HEADER_INTERACTIVE)
        self.reference_table.setColumnWidth(0, 86)
        self.reference_table.setColumnWidth(1, 100)
        self.reference_table.setColumnWidth(2, 190)
        self.reference_table.setColumnWidth(3, 220)
        self.reference_table.setColumnWidth(4, 300)
        self.reference_table.setColumnWidth(5, 300)
        self.reference_table.setToolTip(
            "Right-click a reference to copy its path, reveal it on disk, or select its node."
        )
        layout.addWidget(self.reference_table, 1)
        return panel

    def _build_side_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QTabWidget(self)
        panel.addTab(self._build_replace_panel(), "Relink")
        panel.addTab(self._build_details_panel(), "Details")
        return panel

    def _build_replace_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        form = QtWidgets.QFormLayout()
        self.find_edit = QtWidgets.QLineEdit(self)
        self.find_edit.setPlaceholderText("P:/old_show or $JOB/assets")
        self.find_edit.setToolTip("Path text to find in writable references.")
        self.replace_edit = QtWidgets.QLineEdit(self)
        self.replace_edit.setPlaceholderText("P:/new_show or $HIP/assets")
        self.replace_edit.setToolTip("Replacement text to write into matching references.")
        form.addRow("Find", self.find_edit)
        form.addRow("Replace with", self.replace_edit)
        layout.addLayout(form)

        self.case_sensitive_check = QtWidgets.QCheckBox("Case sensitive", self)
        self.case_sensitive_check.setChecked(True)
        self.case_sensitive_check.setToolTip("Match path text using exact letter case.")
        self.include_hda_replace_check = QtWidgets.QCheckBox("Relink HDA libraries too", self)
        self.include_hda_replace_check.setChecked(False)
        self.include_hda_replace_check.setToolTip(
            "Apply the replacement to matching loaded HDA library paths too."
        )
        self.uninstall_old_hda_check = QtWidgets.QCheckBox(
            "Uninstall old HDA libraries after install", self
        )
        self.uninstall_old_hda_check.setToolTip(
            "After installing replacement HDA libraries, unload the old matching libraries."
        )
        layout.addWidget(self.case_sensitive_check)
        layout.addWidget(self.include_hda_replace_check)
        layout.addWidget(self.uninstall_old_hda_check)

        button_row = QtWidgets.QHBoxLayout()
        self.preview_button = QtWidgets.QPushButton("Preview", self)
        self.preview_button.setToolTip("Preview relink changes without modifying the scene.")
        self.apply_button = QtWidgets.QPushButton("Apply", self)
        self.apply_button.setEnabled(False)
        self.apply_button.setToolTip("Apply the latest previewed relink changes.")
        button_row.addWidget(self.preview_button)
        button_row.addWidget(self.apply_button)
        layout.addLayout(button_row)

        self.report_table = QtWidgets.QTableView(self)
        self.report_table.setModel(self._report_model)
        self.report_table.setAlternatingRowColors(True)
        self.report_table.verticalHeader().setVisible(False)
        self.report_table.horizontalHeader().setStretchLastSection(True)
        self.report_table.horizontalHeader().setSectionResizeMode(HEADER_INTERACTIVE)
        self.report_table.setColumnWidth(0, 90)
        self.report_table.setColumnWidth(1, 180)
        self.report_table.setColumnWidth(2, 250)
        self.report_table.setColumnWidth(3, 250)
        self.report_table.setToolTip("Preview and apply results for the latest relink operation.")
        layout.addWidget(self.report_table, 1)
        return panel

    def _build_details_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        self.detail_text = QtWidgets.QPlainTextEdit(self)
        self.detail_text.setReadOnly(True)
        self.detail_text.setToolTip("Full details for the selected reference.")
        layout.addWidget(self.detail_text, 1)
        return panel

    def _connect_signals(self) -> None:
        self.scan_action.triggered.connect(self.scan)
        self.export_action.triggered.connect(self.export_csv)
        self.copy_path_action.triggered.connect(self.copy_selected_reference_path)
        self.reveal_action.triggered.connect(self.reveal_selected_reference)
        self.select_node_action.triggered.connect(self.select_selected_node)
        self.copy_report_action.triggered.connect(self.copy_report)
        self.scan_button.clicked.connect(self.scan)
        self.export_button.clicked.connect(self.export_csv)
        self.preview_button.clicked.connect(self.preview_replace)
        self.apply_button.clicked.connect(self.apply_replace)
        self.search_edit.textChanged.connect(self._proxy_model.set_search_text)
        self.search_edit.textChanged.connect(self._update_summary)
        self.missing_only_check.toggled.connect(self._proxy_model.set_show_missing_only)
        self.missing_only_check.toggled.connect(self._update_summary)
        self.writable_only_check.toggled.connect(self._proxy_model.set_show_writable_only)
        self.writable_only_check.toggled.connect(self._update_summary)
        self.kind_combo.currentIndexChanged.connect(self._kind_filter_changed)
        self.reference_table.customContextMenuRequested.connect(self._show_reference_menu)
        selection = self.reference_table.selectionModel()
        selection.selectionChanged.connect(self._selection_changed)
        self._proxy_model.rowsInserted.connect(self._update_summary)
        self._proxy_model.rowsRemoved.connect(self._update_summary)
        self._proxy_model.modelReset.connect(self._update_summary)

    def _kind_filter_changed(self, *_args: object) -> None:
        self._proxy_model.set_kind_filter(self.kind_combo.currentData())
        self._update_summary()

    def _selection_changed(self, *_args: object) -> None:
        reference = self._selected_reference()
        if reference is None:
            self.detail_text.clear()
            return
        self.detail_text.setPlainText(
            "\n".join(
                [
                    f"Kind: {reference.kind.value}",
                    f"Status: {'exists' if reference.exists else 'missing'}",
                    f"Writable: {'yes' if reference.can_update else 'no'}",
                    f"Node: {reference.node_path or ''}",
                    f"Parameter: {reference.parm_path or ''}",
                    "",
                    f"Raw path:\n{reference.raw_path}",
                    "",
                    f"Expanded path:\n{reference.expanded_path}",
                    "",
                    f"Note:\n{reference.reason or ''}",
                ]
            )
        )

    def _selected_reference(self) -> Optional[AssetReference]:
        selection = self.reference_table.selectionModel()
        if selection is None or not selection.selectedRows():
            return None
        proxy_index = selection.selectedRows()[0]
        source_index = self._proxy_model.mapToSource(proxy_index)
        return self._reference_model.reference_at(source_index.row())

    def _show_reference_menu(self, position: QtCore.QPoint) -> None:
        clicked_index = self.reference_table.indexAt(position)
        if clicked_index.isValid():
            self.reference_table.selectRow(clicked_index.row())
        menu = QtWidgets.QMenu(self)
        menu.addAction(self.copy_path_action)
        menu.addAction(self.reveal_action)
        menu.addAction(self.select_node_action)
        _exec_dialog(menu, self.reference_table.viewport().mapToGlobal(position))

    def _network_editor_for_current_desktop(self, hou: object) -> Optional[object]:
        hou_ui = getattr(hou, "ui", None)
        current_desktop = getattr(hou_ui, "curDesktop", None)
        if current_desktop is None:
            return None
        desktop = current_desktop()
        if desktop is None:
            return None

        pane_tab_type = getattr(hou, "paneTabType", None)
        network_editor_type = getattr(pane_tab_type, "NetworkEditor", None)
        pane_tab_of_type = getattr(desktop, "paneTabOfType", None)
        if pane_tab_of_type is not None and network_editor_type is not None:
            network_editor = pane_tab_of_type(network_editor_type)
            if network_editor is not None:
                return network_editor

        pane_tabs = getattr(desktop, "paneTabs", None)
        if pane_tabs is None:
            return None
        for pane_tab in pane_tabs():
            pane_type = getattr(pane_tab, "type", None)
            if network_editor_type is not None and pane_type is not None:
                if pane_type() != network_editor_type:
                    continue
            if getattr(pane_tab, "setPwd", None) is not None:
                return pane_tab
        return None

    def _jump_network_editor_to_node(self, network_editor: object, node: object) -> None:
        parent_node = None
        parent = getattr(node, "parent", None)
        if parent is not None:
            parent_node = parent()

        set_pwd = getattr(network_editor, "setPwd", None)
        if set_pwd is not None:
            set_pwd(parent_node or node)

        set_current_node = getattr(network_editor, "setCurrentNode", None)
        if set_current_node is not None:
            set_current_node(node)

    def _frame_network_editor_selection(self, network_editor: object) -> None:
        for method_name in ("homeToSelection", "frameSelection"):
            frame_selection = getattr(network_editor, method_name, None)
            if frame_selection is not None:
                frame_selection()
                return

    def _stat_label(self, label: str, value: str) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame(self)
        frame.setObjectName("statFrame")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        value_label = QtWidgets.QLabel(value, frame)
        value_label.setObjectName("statValue")
        text_label = QtWidgets.QLabel(label, frame)
        text_label.setObjectName("statLabel")
        layout.addWidget(value_label)
        layout.addWidget(text_label)
        frame.value_label = value_label  # type: ignore[attr-defined]
        return frame

    def _update_summary(self, *_args: object) -> None:
        references = self._reference_model.references()
        total = len(references)
        missing = sum(not reference.exists for reference in references)
        writable = sum(reference.can_update for reference in references)
        hda = sum(reference.kind == ReferenceKind.HDA_LIBRARY for reference in references)
        visible = self._proxy_model.rowCount()
        self.total_stat.value_label.setText(str(total))  # type: ignore[attr-defined]
        self.missing_stat.value_label.setText(str(missing))  # type: ignore[attr-defined]
        self.writable_stat.value_label.setText(str(writable))  # type: ignore[attr-defined]
        self.hda_stat.value_label.setText(str(hda))  # type: ignore[attr-defined]
        self.visible_stat.value_label.setText(str(visible))  # type: ignore[attr-defined]

    def _clear_report(self) -> None:
        self._preview_report = None
        self._current_report = None
        self._report_model.set_report(None)
        self.apply_button.setEnabled(False)
        self.copy_report_action.setEnabled(False)

    def _set_busy(self, busy: bool) -> None:
        self.setCursor(WAIT_CURSOR if busy else ARROW_CURSOR)
        self.scan_button.setEnabled(not busy)
        self.preview_button.setEnabled(not busy)
        self.export_button.setEnabled(not busy)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _warn(self, message: str) -> None:
        QtWidgets.QMessageBox.warning(self, "Asset Relinker", message)

    def _show_error(self, title: str, error: Exception) -> None:
        details = traceback.format_exc()
        message = QtWidgets.QMessageBox(self)
        message.setIcon(MESSAGE_CRITICAL)
        message.setWindowTitle(title)
        message.setText(str(error))
        message.setDetailedText(details)
        _exec_dialog(message)
        self._set_status(f"{title}: {error}")

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #202326;
                color: #e8eaed;
                font-size: 10pt;
            }
            QToolBar {
                background: #292d31;
                border: 0;
                spacing: 6px;
                padding: 5px;
            }
            QToolBar QToolButton {
                min-width: 120px;
                padding: 7px 12px;
            }
            QLineEdit, QPlainTextEdit, QComboBox {
                background: #16181b;
                border: 1px solid #3c4248;
                border-radius: 4px;
                padding: 5px;
                selection-background-color: #4a7ebf;
            }
            QPushButton, QToolButton {
                background: #3b4652;
                border: 1px solid #56616d;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QPushButton:hover, QToolButton:hover {
                background: #465665;
            }
            QPushButton:disabled {
                color: #80868b;
                background: #2b3035;
            }
            QTableView {
                background: #17191c;
                alternate-background-color: #1d2024;
                border: 1px solid #343a40;
                gridline-color: #30363c;
                selection-background-color: #365577;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background: #2d3339;
                border: 0;
                border-right: 1px solid #3d454d;
                padding: 5px;
            }
            QTabWidget::pane {
                border: 1px solid #343a40;
            }
            QTabBar::tab {
                background: #2a2f35;
                border: 1px solid #343a40;
                padding: 7px 14px;
            }
            QTabBar::tab:selected {
                background: #39434d;
            }
            QFrame#statFrame {
                background: #292f35;
                border: 1px solid #3b444d;
                border-radius: 5px;
                min-width: 96px;
            }
            QLabel#statValue {
                font-size: 18pt;
                font-weight: 700;
            }
            QLabel#statLabel {
                color: #aab0b6;
            }
            """
        )


def open_dialog() -> AssetRelinkerWindow:
    """Open or raise the asset relinker window inside Houdini."""
    app = _application()
    parent = _houdini_parent()
    window = _show_window(parent)
    if not app.property("houdiniAssetRelinkerManaged"):
        app.setProperty("houdiniAssetRelinkerManaged", True)
    return window


def main() -> int:
    """Run the asset relinker as a standalone Qt app."""
    app = _application()
    window = _show_window()
    window.show()
    return _exec_dialog(app)


def _application() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _show_window(parent: Optional[QtWidgets.QWidget] = None) -> AssetRelinkerWindow:
    global _WINDOW
    if _WINDOW is None:
        _WINDOW = AssetRelinkerWindow(parent)
    elif parent is not None and _WINDOW.parent() is None:
        _WINDOW.setParent(parent)
    _WINDOW.show()
    _WINDOW.raise_()
    _WINDOW.activateWindow()
    return _WINDOW


def _houdini_parent() -> Optional[QtWidgets.QWidget]:
    try:
        hou = get_hou()
        return hou.qt.mainWindow()
    except Exception:
        return None


def _default_export_path() -> str:
    try:
        hou = get_hou()
        expanded = hou.expandString("$HIP/asset_relinker_report.csv")
        if expanded:
            return expanded
    except Exception:
        pass
    return str(Path.cwd() / "asset_relinker_report.csv")


def _parameter_name(parm_path: Optional[str]) -> str:
    if not parm_path:
        return ""
    return parm_path.rsplit("/", 1)[-1]


def _merge_reports(dry_run: bool, reports: Iterable[UpdateReport]) -> UpdateReport:
    results: list[UpdateResult] = []
    for report in reports:
        results.extend(report.results)
    return UpdateReport(dry_run=dry_run, results=tuple(results))


def _exec_dialog(target: object, *args: object) -> int:
    exec_method = getattr(target, "exec", None) or getattr(target, "exec_", None)
    if exec_method is None:
        return 0
    return exec_method(*args)


if __name__ == "__main__":
    raise SystemExit(main())
