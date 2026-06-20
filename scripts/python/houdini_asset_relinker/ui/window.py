"""PySide asset relinker window for Houdini and standalone sessions."""

from __future__ import annotations

import os
import traceback
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from houdini_asset_relinker import __version__
from houdini_asset_relinker.export import write_references_csv
from houdini_asset_relinker.hou_access import get_hou
from houdini_asset_relinker.models import (
    AssetReference,
    ReferenceKind,
    UpdateReport,
    UpdateResult,
    is_broken_relink_target,
    is_generated_output,
    normalized_reference_role,
)
from houdini_asset_relinker.path_utils import normalize_for_compare
from houdini_asset_relinker.qt import QtCore, QtWidgets
from houdini_asset_relinker.scanner import scan_assets
from houdini_asset_relinker.ui.houdini import (
    default_export_path,
    frame_network_editor_selection,
    houdini_parent,
    jump_network_editor_to_node,
    network_editor_for_current_desktop,
)
from houdini_asset_relinker.ui.qt_constants import (
    ACTION_CLASS,
    ARROW_CURSOR,
    ASCENDING_ORDER,
    CUSTOM_CONTEXT_MENU,
    HEADER_INTERACTIVE,
    MESSAGE_CANCEL,
    MESSAGE_CRITICAL,
    MESSAGE_OK,
    SELECT_ROWS,
    SINGLE_SELECTION,
    WAIT_CURSOR,
)
from houdini_asset_relinker.ui.style import ASSET_RELINKER_STYLESHEET
from houdini_asset_relinker.ui.table_models import (
    ReferenceFilterProxy,
    ReferenceTableModel,
    UpdateResultTableModel,
)
from houdini_asset_relinker.updater import replace_hda_library_paths, replace_path_text

WINDOW_OBJECT_NAME = "houdiniAssetRelinkerWindow"
REFERENCE_PATH_FAMILY_COLUMN = 5
SCOPE_VISIBLE_ROWS = "visible_rows"
SCOPE_SELECTED_ROW = "selected_row"
SCOPE_PATH_FAMILY = "path_family"
SCOPE_MISSING_UNDER_ROOT = "missing_under_root"
SCOPE_ALL_ROWS = "all_rows"
_WINDOW: Optional[AssetRelinkerWindow] = None


@dataclass(frozen=True)
class ReplaceRequest:
    """User-selected path replacement settings."""

    find_text: str
    replace_with: str
    case_sensitive: bool
    include_hda_libraries: bool
    uninstall_old_hda_libraries: bool
    scope: str


class AssetRelinkerWindow(QtWidgets.QMainWindow):
    """Main PySide window for scanning and relinking Houdini asset paths."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle(f"Asset Relinker {__version__}")
        self.resize(1280, 760)

        self._reference_model = ReferenceTableModel(self)
        self._proxy_model = ReferenceFilterProxy(self)
        self._proxy_model.setSourceModel(self._reference_model)
        self._report_model = UpdateResultTableModel(self)
        self._preview_report: Optional[UpdateReport] = None
        self._preview_request: Optional[ReplaceRequest] = None
        self._preview_references: tuple[AssetReference, ...] = ()
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
                recurse_in_locked_nodes=self.recurse_locked_check.isChecked(),
            )
        except Exception as error:
            self._show_error("Scan failed", error)
            return
        finally:
            self._set_busy(False)

        self._reference_model.set_references(references)
        self._clear_report()
        self._update_summary()
        output_count = sum(is_generated_output(reference) for reference in references)
        context_note = (
            f" ({output_count} generated outputs kept for context)" if output_count else ""
        )
        self._set_status(f"Scanned {len(references)} references{context_note}.")
        if references:
            self.reference_table.selectRow(0)

    def preview_replace(self) -> None:
        """Run a dry-run replacement preview from the current settings."""
        request = self._current_replace_request()
        if not request.find_text:
            self._warn("Find text cannot be empty.")
            return
        if not self._reference_model.references():
            self._warn("Scan the scene before previewing replacements.")
            return
        references = self._resolve_replace_references(request)
        if not references:
            self._warn(
                f"No references match the selected relink scope: {_scope_label(request.scope)}."
            )
            return

        self._set_busy(True)
        try:
            report = self._build_replace_report(request, references, dry_run=True)
        except Exception as error:
            self._show_error("Preview failed", error)
            return
        finally:
            self._set_busy(False)

        self._preview_report = report
        self._preview_request = request
        self._preview_references = tuple(references)
        self._current_report = report
        self._report_model.set_report(report)
        self.apply_button.setEnabled(bool(report.results))
        self.copy_report_button.setEnabled(bool(report.results))
        self._set_status(
            f"Preview found {report.changed_count} planned changes, "
            f"{report.skipped_count} skipped, {report.failed_count} failed."
        )

    def apply_replace(self) -> None:
        """Apply the last previewed replacement after confirmation."""
        preview_request = self._preview_request
        if self._preview_report is None or not self._preview_report.results:
            self._warn("Preview replacements before applying changes.")
            return
        if preview_request != self._current_replace_request():
            self._invalidate_preview()
            self._warn("Replacement settings changed. Preview the relink again before applying.")
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

        self._set_busy(True)
        try:
            report = self._build_replace_report(
                preview_request,
                self._preview_references,
                dry_run=False,
            )
        except Exception as error:
            self._show_error("Apply failed", error)
            return
        finally:
            self._set_busy(False)

        self._preview_report = None
        self._preview_request = None
        self._preview_references = ()
        self.scan()
        self._current_report = report
        self._report_model.set_report(report)
        self.apply_button.setEnabled(False)
        self.copy_report_button.setEnabled(bool(report.results))
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
        output_path, _selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Asset Relinker CSV",
            default_export_path(),
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
            network_editor = network_editor_for_current_desktop(hou)
            if network_editor is not None:
                jump_network_editor_to_node(network_editor, node)
            node.setSelected(True, clear_all_selected=True)
            if network_editor is not None:
                frame_network_editor_selection(network_editor)
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
        self.copy_path_action = ACTION_CLASS("Copy Raw Path", self)
        self.copy_path_action.setToolTip("Copy the selected reference's raw path expression.")
        self.copy_path_action.setStatusTip("Copy the selected reference's raw path expression.")
        self.reveal_action = ACTION_CLASS("Reveal on Disk", self)
        self.reveal_action.setToolTip("Open the selected reference's folder in Explorer.")
        self.reveal_action.setStatusTip("Open the selected reference's folder in Explorer.")
        self.jump_to_node_action = ACTION_CLASS("Jump to Node", self)
        self.jump_to_node_action.setToolTip(
            "Jump the Network Editor to the selected reference's node and select it."
        )
        self.jump_to_node_action.setStatusTip(
            "Jump the Network Editor to the selected reference's node and select it."
        )

    def _build_ui(self) -> None:
        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        main_layout.addWidget(self._build_scan_bar())

        self.main_splitter = QtWidgets.QSplitter(self)
        self.main_splitter.addWidget(self._build_reference_panel())
        self.main_splitter.addWidget(self._build_side_panel())
        self.main_splitter.setSizes([860, 420])
        main_layout.addWidget(self.main_splitter, 1)

        self.status_label = QtWidgets.QLabel(self)
        self.statusBar().addPermanentWidget(self.status_label, 1)
        self.setStyleSheet(ASSET_RELINKER_STYLESHEET)

    def _build_scan_bar(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget(self)
        panel.setObjectName("scanBar")
        layout = QtWidgets.QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.project_variable_edit = QtWidgets.QLineEdit("HIP", self)
        self.project_variable_edit.setMaximumWidth(90)
        self.project_variable_edit.setToolTip(
            "Houdini project variable passed to hou.fileReferences, usually HIP."
        )
        self.include_all_refs_check = QtWidgets.QCheckBox("All file refs", self)
        self.include_all_refs_check.setChecked(True)
        self.include_all_refs_check.setToolTip(
            "Include all Houdini file references instead of only selected references."
        )
        self.include_hda_check = QtWidgets.QCheckBox("Loaded HDA libraries", self)
        self.include_hda_check.setChecked(False)
        self.include_hda_check.setToolTip("Include loaded HDA library files in the scan.")
        self.recurse_locked_check = QtWidgets.QCheckBox("Locked-node contents", self)
        self.recurse_locked_check.setChecked(False)
        self.recurse_locked_check.setToolTip(
            "Inspect child nodes inside locked assets when scanning file references."
        )

        self.scan_button = QtWidgets.QPushButton("Scan Scene", self)
        self.scan_button.setObjectName("primaryButton")
        self.scan_button.setDefault(True)
        self.scan_button.setMinimumWidth(92)
        self.scan_button.setShortcut("F5")
        self.scan_button.setToolTip("Scan the current Houdini scene for external asset references.")

        section_label = QtWidgets.QLabel("Scene scan", self)
        section_label.setObjectName("sectionLabel")
        layout.addWidget(section_label)
        layout.addWidget(QtWidgets.QLabel("Project var", self))
        layout.addWidget(self.project_variable_edit)
        layout.addWidget(self.include_all_refs_check)
        layout.addWidget(self.include_hda_check)
        layout.addWidget(self.recurse_locked_check)
        layout.addStretch(1)
        layout.addWidget(self.scan_button)
        return panel

    def _build_reference_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setMinimumWidth(260)
        self.search_edit.setPlaceholderText("Filter by node, parameter, path, or note")
        self.search_edit.setToolTip("Filter references by node, parameter, path, kind, or note.")
        self.missing_only_check = QtWidgets.QCheckBox("Broken targets", self)
        self.missing_only_check.setToolTip(
            "Show only inbound relink targets that are missing or use undefined variables."
        )
        self.missing_only_check.setChecked(True)
        self.writable_only_check = QtWidgets.QCheckBox("Writable only", self)
        self.writable_only_check.setToolTip("Show only references the relinker can update.")
        self.writable_only_check.setChecked(True)
        self.kind_combo = QtWidgets.QComboBox(self)
        self.kind_combo.setMinimumWidth(112)
        self.kind_combo.setToolTip("Limit the table to a specific reference kind.")
        self.kind_combo.addItem("All kinds", "all")
        self.kind_combo.addItem("File parameters", "file")
        self.kind_combo.addItem("HDA libraries", "hda")
        self.reset_filters_button = QtWidgets.QPushButton("Reset", self)
        self.reset_filters_button.setObjectName("secondaryButton")
        self.reset_filters_button.setToolTip("Clear table filters.")

        filter_row = QtWidgets.QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)
        filter_label = QtWidgets.QLabel("References", self)
        filter_label.setObjectName("sectionLabel")
        filter_row.addWidget(filter_label)
        filter_row.addWidget(self.search_edit, 1)
        filter_row.addWidget(self.missing_only_check)
        filter_row.addWidget(self.writable_only_check)
        filter_row.addWidget(self.kind_combo)
        filter_row.addWidget(self.reset_filters_button)
        layout.addLayout(filter_row)

        table_action_row = QtWidgets.QHBoxLayout()
        table_action_row.setContentsMargins(0, 0, 0, 0)
        table_action_row.setSpacing(8)
        self.summary_label = QtWidgets.QLabel(
            "0 total | 0 broken targets | 0 generated outputs | 0 writable | 0 HDA | 0 visible",
            self,
        )
        self.summary_label.setObjectName("summaryLabel")
        self.export_button = QtWidgets.QPushButton("Export CSV", self)
        self.export_button.setObjectName("secondaryButton")
        self.export_button.setEnabled(False)
        self.export_button.setToolTip("Export the current reference table to a CSV report.")
        table_action_row.addWidget(self.summary_label, 1)
        table_action_row.addWidget(self.export_button)
        layout.addLayout(table_action_row)

        self.reference_table = QtWidgets.QTableView(self)
        self.reference_table.setModel(self._proxy_model)
        self.reference_table.setSortingEnabled(True)
        self.reference_table.sortByColumn(REFERENCE_PATH_FAMILY_COLUMN, ASCENDING_ORDER)
        self.reference_table.setSelectionBehavior(SELECT_ROWS)
        self.reference_table.setSelectionMode(SINGLE_SELECTION)
        self.reference_table.setAlternatingRowColors(True)
        self.reference_table.setContextMenuPolicy(CUSTOM_CONTEXT_MENU)
        self.reference_table.verticalHeader().setVisible(False)
        self.reference_table.horizontalHeader().setStretchLastSection(True)
        self.reference_table.horizontalHeader().setSectionResizeMode(HEADER_INTERACTIVE)
        self.reference_table.setColumnWidth(0, 120)
        self.reference_table.setColumnWidth(1, 65)
        self.reference_table.setColumnWidth(2, 130)
        self.reference_table.setColumnWidth(3, 190)
        self.reference_table.setColumnWidth(4, 100)
        self.reference_table.setColumnWidth(5, 220)
        self.reference_table.setColumnWidth(6, 300)
        self.reference_table.setColumnWidth(7, 300)
        self.reference_table.setColumnWidth(9, 600)
        self.reference_table.setToolTip(
            "Right-click a reference to copy its path, reveal it on disk, or select its node."
        )
        layout.addWidget(self.reference_table, 1)
        return panel

    def _build_side_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QTabWidget(self)
        panel.addTab(self._build_replace_panel(), "Relink")
        panel.addTab(self._build_details_panel(), "Selected Reference")
        return panel

    def _build_replace_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        form = QtWidgets.QFormLayout()
        self.find_edit = QtWidgets.QLineEdit(self)
        self.find_edit.setPlaceholderText("P:/old_show or $JOB/assets")
        self.find_edit.setToolTip(
            "Path text to find in writable references. Matching ignores letter case by default."
        )
        self.replace_edit = QtWidgets.QLineEdit(self)
        self.replace_edit.setPlaceholderText("P:/new_show or $HIP/assets")
        self.replace_edit.setToolTip("Replacement text to write into matching references.")
        self.scope_combo = QtWidgets.QComboBox(self)
        self.scope_combo.setMinimumWidth(190)
        self.scope_combo.setToolTip("Limit preview and apply to a safer subset of scanned rows.")
        self.scope_combo.addItem("Visible filtered rows", SCOPE_VISIBLE_ROWS)
        self.scope_combo.addItem("Selected row", SCOPE_SELECTED_ROW)
        self.scope_combo.addItem("Selected path family", SCOPE_PATH_FAMILY)
        self.scope_combo.addItem("Missing under Find root", SCOPE_MISSING_UNDER_ROOT)
        self.scope_combo.addItem("All scanned rows", SCOPE_ALL_ROWS)
        form.addRow("Find", self.find_edit)
        form.addRow("Replace with", self.replace_edit)
        form.addRow("Scope", self.scope_combo)
        layout.addLayout(form)

        self.case_sensitive_check = QtWidgets.QCheckBox("Exact case only", self)
        self.case_sensitive_check.setChecked(False)
        self.case_sensitive_check.setToolTip(
            "Opt in to exact letter-case matching. Leave off for common Windows path casing "
            "differences."
        )
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
        self.preview_button.setObjectName("primaryButton")
        self.preview_button.setToolTip(
            "Preview case-insensitive relink changes without modifying the scene."
        )
        self.apply_button = QtWidgets.QPushButton("Apply", self)
        self.apply_button.setObjectName("applyButton")
        self.apply_button.setEnabled(False)
        self.apply_button.setToolTip("Apply the latest previewed relink changes.")
        self.copy_report_button = QtWidgets.QPushButton("Copy Report", self)
        self.copy_report_button.setEnabled(False)
        self.copy_report_button.setToolTip("Copy the latest preview or apply report.")
        button_row.addWidget(self.preview_button)
        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.copy_report_button)
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
        self.copy_path_action.triggered.connect(self.copy_selected_reference_path)
        self.reveal_action.triggered.connect(self.reveal_selected_reference)
        self.jump_to_node_action.triggered.connect(self.select_selected_node)
        self.scan_button.clicked.connect(self.scan)
        self.export_button.clicked.connect(self.export_csv)
        self.reset_filters_button.clicked.connect(self._reset_reference_filters)
        self.preview_button.clicked.connect(self.preview_replace)
        self.apply_button.clicked.connect(self.apply_replace)
        self.copy_report_button.clicked.connect(self.copy_report)
        self.search_edit.textChanged.connect(self._proxy_model.set_search_text)
        self.search_edit.textChanged.connect(self._update_summary)
        self.missing_only_check.toggled.connect(self._proxy_model.set_show_missing_only)
        self.missing_only_check.toggled.connect(self._update_summary)
        self.writable_only_check.toggled.connect(self._proxy_model.set_show_writable_only)
        self.writable_only_check.toggled.connect(self._update_summary)
        self.kind_combo.currentIndexChanged.connect(self._kind_filter_changed)
        self.reference_table.customContextMenuRequested.connect(self._show_reference_menu)
        self.reference_table.doubleClicked.connect(self._reference_double_clicked)

        for signal in (
            self.find_edit.textChanged,
            self.replace_edit.textChanged,
            self.case_sensitive_check.toggled,
            self.include_hda_replace_check.toggled,
            self.uninstall_old_hda_check.toggled,
            self.scope_combo.currentIndexChanged,
        ):
            signal.connect(self._invalidate_preview)

        selection = self.reference_table.selectionModel()
        selection.selectionChanged.connect(self._selection_changed)
        self._proxy_model.rowsInserted.connect(self._update_summary)
        self._proxy_model.rowsRemoved.connect(self._update_summary)
        self._proxy_model.modelReset.connect(self._update_summary)
        self._sync_reference_filters()

    def _kind_filter_changed(self, *_args: object) -> None:
        self._proxy_model.set_kind_filter(self.kind_combo.currentData())
        self._update_summary()

    def _sync_reference_filters(self) -> None:
        """Apply initial widget filter state to the proxy model."""
        self._proxy_model.set_search_text(self.search_edit.text())
        self._proxy_model.set_show_missing_only(self.missing_only_check.isChecked())
        self._proxy_model.set_show_writable_only(self.writable_only_check.isChecked())
        self._proxy_model.set_kind_filter(self.kind_combo.currentData())
        self._update_summary()

    def _reset_reference_filters(self) -> None:
        self.search_edit.clear()
        self.missing_only_check.setChecked(True)
        self.writable_only_check.setChecked(True)
        self.kind_combo.setCurrentIndex(0)

    def _selection_changed(self, *_args: object) -> None:
        reference = self._selected_reference()
        if reference is None:
            self.detail_text.clear()
            return
        lines = [
            f"Kind: {reference.kind.value}",
            f"Role: {normalized_reference_role(reference)}",
            f"Status: {_reference_status_text(reference)}",
            f"Writable: {'yes' if reference.can_update else 'no'}",
            f"Node: {reference.node_path or ''}",
            f"Parameter: {reference.parm_path or ''}",
            f"Path family: {reference.path_family}",
        ]
        if reference.missing_variables:
            lines.append(f"Undefined variables: {', '.join(reference.missing_variables)}")
        if reference.sequence_pattern:
            lines.append(f"Sequence pattern: {reference.sequence_pattern}")
        lines.extend(
            [
                "",
                f"Raw path:\n{reference.raw_path}",
                "",
                f"Expanded path:\n{reference.expanded_path}",
                "",
                f"Note:\n{_reference_note_text(reference)}",
            ]
        )
        self.detail_text.setPlainText("\n".join(lines))

    def _selected_reference(self) -> Optional[AssetReference]:
        selection = self.reference_table.selectionModel()
        if selection is None or not selection.selectedRows():
            return None
        proxy_index = selection.selectedRows()[0]
        source_index = self._proxy_model.mapToSource(proxy_index)
        return self._reference_model.reference_at(source_index.row())

    def _reference_double_clicked(self, index: QtCore.QModelIndex) -> None:
        if index.isValid():
            self.reference_table.selectRow(index.row())
        self.select_selected_node()

    def _show_reference_menu(self, position: QtCore.QPoint) -> None:
        clicked_index = self.reference_table.indexAt(position)
        if clicked_index.isValid():
            self.reference_table.selectRow(clicked_index.row())
        menu = QtWidgets.QMenu(self)
        menu.addAction(self.jump_to_node_action)
        menu.addAction(self.copy_path_action)
        menu.addAction(self.reveal_action)
        _exec_dialog(menu, self.reference_table.viewport().mapToGlobal(position))

    def _update_summary(self, *_args: object) -> None:
        references = self._reference_model.references()
        broken_count = sum(is_broken_relink_target(reference) for reference in references)
        output_count = sum(is_generated_output(reference) for reference in references)
        undefined_count = sum(bool(reference.missing_variables) for reference in references)
        writable_count = sum(reference.can_update for reference in references)
        hda_count = sum(reference.kind == ReferenceKind.HDA_LIBRARY for reference in references)
        self.summary_label.setText(
            f"{len(references)} total | {broken_count} broken targets | "
            f"{output_count} generated outputs | {undefined_count} undefined vars | "
            f"{writable_count} writable | {hda_count} HDA | "
            f"{self._proxy_model.rowCount()} visible"
        )
        self.export_button.setEnabled(bool(references))

    def _current_replace_request(self) -> ReplaceRequest:
        return ReplaceRequest(
            find_text=self.find_edit.text(),
            replace_with=self.replace_edit.text(),
            case_sensitive=self.case_sensitive_check.isChecked(),
            include_hda_libraries=self.include_hda_replace_check.isChecked(),
            uninstall_old_hda_libraries=self.uninstall_old_hda_check.isChecked(),
            scope=self.scope_combo.currentData(),
        )

    def _resolve_replace_references(self, request: ReplaceRequest) -> list[AssetReference]:
        """Return the scanned references targeted by the selected relink scope."""
        if request.scope == SCOPE_SELECTED_ROW:
            selected = self._selected_reference()
            return [selected] if selected is not None else []
        if request.scope == SCOPE_VISIBLE_ROWS:
            return self._visible_references()
        if request.scope == SCOPE_PATH_FAMILY:
            selected = self._selected_reference()
            if selected is None:
                return []
            return [
                reference
                for reference in self._reference_model.references()
                if reference.path_family == selected.path_family
            ]
        if request.scope == SCOPE_MISSING_UNDER_ROOT:
            return [
                reference
                for reference in self._reference_model.references()
                if is_broken_relink_target(reference)
                and _path_is_under_or_equal(reference.raw_path, request.find_text)
            ]
        return self._reference_model.references()

    def _visible_references(self) -> list[AssetReference]:
        """Return references accepted by the current proxy filters in proxy order."""
        references = []
        for row in range(self._proxy_model.rowCount()):
            proxy_index = self._proxy_model.index(row, 0)
            source_index = self._proxy_model.mapToSource(proxy_index)
            references.append(self._reference_model.reference_at(source_index.row()))
        return references

    def _build_replace_report(
        self,
        request: ReplaceRequest,
        references: Iterable[AssetReference],
        dry_run: bool,
    ) -> UpdateReport:
        reports = [
            replace_path_text(
                request.find_text,
                request.replace_with,
                dry_run=dry_run,
                references=references,
                case_sensitive=request.case_sensitive,
            )
        ]
        if request.include_hda_libraries:
            reports.append(
                replace_hda_library_paths(
                    request.find_text,
                    request.replace_with,
                    dry_run=dry_run,
                    uninstall_old=request.uninstall_old_hda_libraries,
                    references=references,
                    case_sensitive=request.case_sensitive,
                )
            )
        return _merge_reports(dry_run, reports)

    def _invalidate_preview(self, *_args: object) -> None:
        if self._preview_report is None and self._preview_request is None:
            return
        self._preview_report = None
        self._preview_request = None
        self._preview_references = ()
        self._current_report = None
        self._report_model.set_report(None)
        self.apply_button.setEnabled(False)
        self.copy_report_button.setEnabled(False)
        self._set_status("Replacement settings changed. Preview again before applying.")

    def _clear_report(self) -> None:
        self._preview_report = None
        self._preview_request = None
        self._preview_references = ()
        self._current_report = None
        self._report_model.set_report(None)
        self.apply_button.setEnabled(False)
        self.copy_report_button.setEnabled(False)

    def _set_busy(self, busy: bool) -> None:
        self.setCursor(WAIT_CURSOR if busy else ARROW_CURSOR)
        self.scan_button.setEnabled(not busy)
        self.preview_button.setEnabled(not busy)
        self.export_button.setEnabled(not busy and bool(self._reference_model.references()))

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


def open_dialog() -> AssetRelinkerWindow:
    """Open or raise the asset relinker window inside Houdini."""
    app = _application()
    parent = houdini_parent()
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


def _reference_status_text(reference: AssetReference) -> str:
    """Return the selected-reference status text."""
    if is_generated_output(reference):
        return "generated output"
    if reference.missing_variables:
        return "undefined variable"
    if not reference.exists:
        return "missing"
    if not reference.can_update:
        return "read only"
    return "ready"


def _reference_note_text(reference: AssetReference) -> str:
    """Return the selected-reference note text."""
    if is_generated_output(reference):
        return reference.reason or "Generated output path kept for context."
    if reference.missing_variables:
        return f"Undefined variables: {', '.join(reference.missing_variables)}"
    return reference.reason or ""


def _path_is_under_or_equal(path_value: str, root_value: str) -> bool:
    """Return whether a raw path is exactly at or under a root value."""
    normalized_path = normalize_for_compare(path_value)
    normalized_root = normalize_for_compare(root_value)
    if not normalized_path or not normalized_root:
        return False
    return normalized_path == normalized_root or normalized_path.startswith(f"{normalized_root}/")


def _scope_label(scope: str) -> str:
    """Return a user-facing label for a relink scope id."""
    labels = {
        SCOPE_VISIBLE_ROWS: "Visible filtered rows",
        SCOPE_SELECTED_ROW: "Selected row",
        SCOPE_PATH_FAMILY: "Selected path family",
        SCOPE_MISSING_UNDER_ROOT: "Missing under Find root",
        SCOPE_ALL_ROWS: "All scanned rows",
    }
    return labels.get(scope, scope)


if __name__ == "__main__":
    raise SystemExit(main())
