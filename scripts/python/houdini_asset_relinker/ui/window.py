"""PySide asset relinker window for Houdini and standalone sessions."""

from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Optional

from houdini_asset_relinker import __version__
from houdini_asset_relinker.export import write_references_csv
from houdini_asset_relinker.hou_access import get_hou
from houdini_asset_relinker.models import (
    AssetReference,
    ReferenceKind,
    is_broken_relink_target,
    is_generated_output,
    normalized_reference_role,
)
from houdini_asset_relinker.path_utils import matches_find_text, normalize_for_compare
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
    MESSAGE_CANCEL,
    MESSAGE_CRITICAL,
    MESSAGE_OK,
    WAIT_CURSOR,
)
from houdini_asset_relinker.ui.reference_display import (
    reference_note_text,
    reference_status_text,
)
from houdini_asset_relinker.ui.relink_state import (
    SCOPE_ALL_ROWS,
    SCOPE_MISSING_UNDER_ROOT,
    SCOPE_PATH_FAMILY,
    SCOPE_SELECTED_ROW,
    SCOPE_VISIBLE_ROWS,
    RelinkState,
    ReplaceRequest,
    build_replace_report,
)
from houdini_asset_relinker.ui.table_models import (
    ReferenceFilterProxy,
    ReferenceTableModel,
    UpdateResultTableModel,
)
from houdini_asset_relinker.ui.view_builders import build_main_window

WINDOW_OBJECT_NAME = "houdiniAssetRelinkerWindow"
_WINDOW: Optional[AssetRelinkerWindow] = None


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
        self._relink_state = RelinkState()
        self._live_relink_preview_depth = 0
        self._live_relink_preview_timer = QtCore.QTimer(self)
        self._live_relink_preview_timer.setSingleShot(True)
        self._live_relink_preview_timer.timeout.connect(self._run_scheduled_live_relink_preview)

        self._build_actions()
        self._build_ui()
        self._connect_signals()
        self._set_status("Ready. Scan the current Houdini session to begin.")

    def scan(self, clear_report: bool = True) -> None:
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
        if clear_report:
            self._clear_report()
        self._update_find_match_highlight()
        if clear_report:
            self._run_scheduled_live_relink_preview()
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
        self._update_live_relink_preview(show_warnings=True)

    def apply_replace(self) -> None:
        """Apply the last previewed replacement after confirmation."""
        preview_request = self._relink_state.preview_request
        if preview_request is None or not self._relink_state.has_preview_results():
            self._warn("Preview replacements before applying changes.")
            return
        if preview_request != self._current_replace_request():
            self._update_live_relink_preview()
            self._warn("Replacement settings changed. Review the live preview before applying.")
            return

        answer = QtWidgets.QMessageBox.warning(
            self,
            "Apply Asset Relinks",
            (
                "This will update Houdini parameters"
                " and selected HDA libraries.\n\n"
                "Save a copy of the hip file before applying large relinks."
            ),
            MESSAGE_OK | MESSAGE_CANCEL,
            MESSAGE_CANCEL,
        )
        if answer != MESSAGE_OK:
            return

        self._set_busy(True)
        try:
            from houdini_asset_relinker.hou_access import undo_group

            with undo_group("Relink Assets"):
                report = build_replace_report(
                    preview_request,
                    self._relink_state.preview_references,
                    dry_run=False,
                )
        except Exception as error:
            self._show_error("Apply failed", error)
            return
        finally:
            self._set_busy(False)

        self._relink_state.set_applied_report(report, preview_request)
        self.scan(clear_report=False)
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
        current_report = self._relink_state.current_report
        if current_report is None or not current_report.results:
            return
        QtWidgets.QApplication.clipboard().setText(current_report.to_text(max_rows=10_000))
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
        widgets = build_main_window(self, self._proxy_model, self._report_model)
        self._ui_widgets = widgets
        self.main_splitter = widgets.main_splitter
        self.status_label = widgets.status_label

        self.project_variable_edit = widgets.scan_bar.project_variable_edit
        self.include_all_refs_check = widgets.scan_bar.include_all_refs_check
        self.include_hda_check = widgets.scan_bar.include_hda_check
        self.recurse_locked_check = widgets.scan_bar.recurse_locked_check
        self.scan_button = widgets.scan_bar.scan_button

        self.search_edit = widgets.reference_panel.search_edit
        self.missing_only_check = widgets.reference_panel.missing_only_check
        self.writable_only_check = widgets.reference_panel.writable_only_check
        self.kind_combo = widgets.reference_panel.kind_combo
        self.reset_filters_button = widgets.reference_panel.reset_filters_button
        self.summary_label = widgets.reference_panel.summary_label
        self.export_button = widgets.reference_panel.export_button
        self.reference_table = widgets.reference_panel.reference_table

        self.find_edit = widgets.relink_panel.find_edit
        self.replace_edit = widgets.relink_panel.replace_edit
        self.scope_combo = widgets.relink_panel.scope_combo
        self.find_match_label = widgets.relink_panel.find_match_label
        self.case_sensitive_check = widgets.relink_panel.case_sensitive_check
        self.include_hda_replace_check = widgets.relink_panel.include_hda_replace_check
        self.uninstall_old_hda_check = widgets.relink_panel.uninstall_old_hda_check
        self.apply_button = widgets.relink_panel.apply_button
        self.copy_report_button = widgets.relink_panel.copy_report_button
        self.report_table = widgets.relink_panel.report_table

        self.detail_text = widgets.details_panel.detail_text

    def _connect_signals(self) -> None:
        self.copy_path_action.triggered.connect(self.copy_selected_reference_path)
        self.reveal_action.triggered.connect(self.reveal_selected_reference)
        self.jump_to_node_action.triggered.connect(self.select_selected_node)
        self.scan_button.clicked.connect(self.scan)
        self.export_button.clicked.connect(self.export_csv)
        self.reset_filters_button.clicked.connect(self._reset_reference_filters)
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
            self.search_edit.textChanged,
            self.missing_only_check.toggled,
            self.writable_only_check.toggled,
            self.kind_combo.currentIndexChanged,
        ):
            signal.connect(self._schedule_live_relink_preview)

        self.find_edit.textChanged.connect(self._update_find_match_highlight)
        self.case_sensitive_check.toggled.connect(self._update_find_match_highlight)
        self.search_edit.textChanged.connect(self._update_find_match_highlight)
        self.missing_only_check.toggled.connect(self._update_find_match_highlight)
        self.writable_only_check.toggled.connect(self._update_find_match_highlight)
        self.kind_combo.currentIndexChanged.connect(self._update_find_match_highlight)

        selection = self.reference_table.selectionModel()
        selection.selectionChanged.connect(self._selection_changed)
        self._proxy_model.rowsInserted.connect(self._update_summary)
        self._proxy_model.rowsRemoved.connect(self._update_summary)
        self._proxy_model.modelReset.connect(self._update_summary)
        self._sync_reference_filters()
        self._update_find_match_highlight()
        self._run_scheduled_live_relink_preview()

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
            f"Status: {reference_status_text(reference, style='lower')}",
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
                f"Note:\n{reference_note_text(reference)}",
            ]
        )
        self.detail_text.setPlainText("\n".join(lines))
        if self.scope_combo.currentData() in (SCOPE_SELECTED_ROW, SCOPE_PATH_FAMILY):
            self._schedule_live_relink_preview()

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

    def _update_find_match_highlight(self, *_args: object) -> None:
        """Update live Find match counts and highlight matching reference rows."""
        find_text = self.find_edit.text()
        case_sensitive = self.case_sensitive_check.isChecked()
        self._reference_model.set_find_highlight(find_text, case_sensitive)

        if not find_text.strip():
            self.find_match_label.clear()
            self.find_match_label.hide()
            return

        match_count = self._reference_model.find_match_count()
        visible_match_count = sum(
            1
            for reference in self._visible_references()
            if matches_find_text(reference.raw_path, find_text, case_sensitive)
        )
        noun = "reference" if match_count == 1 else "references"
        verb = "matches" if match_count == 1 else "match"
        label = f"{match_count} {noun} {verb} Find"
        if visible_match_count != match_count:
            visible_noun = "reference" if visible_match_count == 1 else "references"
            label += f" ({visible_match_count} {visible_noun} visible)"
        self.find_match_label.setText(label)
        self.find_match_label.setVisible(True)

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

    def _schedule_live_relink_preview(self, *_args: object) -> None:
        """Queue a live relink preview refresh on the next event-loop tick."""
        if not self._live_relink_preview_timer.isActive():
            self._live_relink_preview_timer.start(0)

    def _run_scheduled_live_relink_preview(self) -> None:
        """Run the queued live relink preview refresh."""
        self._update_live_relink_preview(show_warnings=False)

    def _update_live_relink_preview(self, show_warnings: bool = False, *_args: object) -> None:
        """Rebuild the relink report table from the current replacement settings."""
        if self._live_relink_preview_depth:
            return
        self._live_relink_preview_depth += 1
        try:
            request = self._current_replace_request()
            if (
                self._relink_state.current_report is not None
                and not self._relink_state.current_report.dry_run
            ):
                if self._relink_state.should_keep_applied_report(request):
                    return
                self._relink_state.clear_applied_request()

            if not request.find_text.strip():
                self._clear_report()
                return
            if not self._reference_model.references():
                self._clear_report()
                if show_warnings:
                    self._warn("Scan the scene before previewing replacements.")
                return

            references = self._resolve_replace_references(request)
            if not references:
                self._clear_report()
                if show_warnings:
                    self._warn(
                        f"No references match the selected relink scope: "
                        f"{_scope_label(request.scope)}."
                    )
                return

            try:
                report = build_replace_report(request, references, dry_run=True)
            except Exception as error:
                self._clear_report()
                if show_warnings:
                    self._show_error("Preview failed", error)
                else:
                    self._set_status(f"Relink preview failed: {error}")
                return

            self._relink_state.set_preview(report, request, references)
            self._report_model.set_report(report)
            self.apply_button.setEnabled(bool(report.results))
            self.copy_report_button.setEnabled(bool(report.results))
            self._set_status(
                f"Preview: {report.changed_count} planned changes, "
                f"{report.skipped_count} skipped, {report.failed_count} failed."
            )
        finally:
            self._live_relink_preview_depth -= 1

    def _clear_report(self) -> None:
        self._relink_state.clear_report()
        self._report_model.set_report(None)
        self.apply_button.setEnabled(False)
        self.copy_report_button.setEnabled(False)

    def _set_busy(self, busy: bool) -> None:
        self.setCursor(WAIT_CURSOR if busy else ARROW_CURSOR)
        self.scan_button.setEnabled(not busy)
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


def _exec_dialog(target: object, *args: object) -> int:
    exec_method = getattr(target, "exec", None) or getattr(target, "exec_", None)
    if exec_method is None:
        return 0
    return exec_method(*args)


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
