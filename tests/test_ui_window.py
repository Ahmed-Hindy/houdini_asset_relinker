"""Tests for the asset relinker Qt window workflow."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from houdini_asset_relinker.models import (
    AssetReference,
    ReferenceKind,
    ReferenceRole,
    UpdateReport,
    UpdateResult,
)
from houdini_asset_relinker.ui import window as window_module
from houdini_asset_relinker.ui.qt_constants import (
    BACKGROUND_ROLE,
    DISPLAY_ROLE,
    HORIZONTAL,
    SCROLL_PER_PIXEL,
    TOOLTIP_ROLE,
)
from houdini_asset_relinker.ui.style import (
    REPORT_STATUS_TINT_MIX,
    REPORT_TABLE_ALT_BASE_COLOR,
    REPORT_TABLE_BASE_COLOR,
    STATUS_COLOR_MISSING,
    STATUS_COLOR_NOT_UPDATABLE,
    STATUS_COLOR_READY,
)
from houdini_asset_relinker.ui.table_models import UpdateResultTableModel, _blend_hex_color
from houdini_asset_relinker.ui.window import (
    REFERENCE_PATH_FAMILY_COLUMN,
    SCOPE_MISSING_UNDER_ROOT,
    SCOPE_PATH_FAMILY,
    SCOPE_SELECTED_ROW,
    SCOPE_VISIBLE_ROWS,
    AssetRelinkerWindow,
    ReplaceRequest,
)


@pytest.fixture
def qt_app():
    """Return a QApplication for offscreen widget tests."""
    app = window_module.QtWidgets.QApplication.instance()
    if app is None:
        app = window_module.QtWidgets.QApplication([])
    return app


@pytest.fixture
def relinker_window(qt_app):
    """Create and close an asset relinker window for each test."""
    del qt_app
    relinker = AssetRelinkerWindow()
    relinker._reference_model.set_references(
        [
            AssetReference(
                kind=ReferenceKind.FILE_PARAMETER,
                raw_path="P:/old_show/cache/a.bgeo.sc",
                expanded_path="P:/old_show/cache/a.bgeo.sc",
                exists=False,
                sequence_pattern="",
                parm_path="/obj/geo1/file1/file",
                node_path="/obj/geo1",
                can_update=True,
            )
        ]
    )
    yield relinker
    relinker.close()


def _set_scope(relinker: AssetRelinkerWindow, scope: str) -> None:
    """Set the relink scope combo by stored scope id."""
    index = relinker.scope_combo.findData(scope)
    assert index >= 0
    relinker.scope_combo.setCurrentIndex(index)


def _flush_live_relink_preview(qt_app) -> None:
    """Process pending Qt events so scheduled live relink previews run in tests."""
    qt_app.processEvents()


def _select_reference_by_raw_path(relinker: AssetRelinkerWindow, raw_path: str) -> None:
    """Select a reference row by raw path through the current proxy model."""
    for row in range(relinker._proxy_model.rowCount()):
        proxy_index = relinker._proxy_model.index(row, 0)
        source_index = relinker._proxy_model.mapToSource(proxy_index)
        reference = relinker._reference_model.reference_at(source_index.row())
        if reference.raw_path == raw_path:
            relinker.reference_table.selectRow(row)
            return
    raise AssertionError(f"Could not select reference: {raw_path}")


def _reference(
    raw_path: str,
    *,
    exists: bool = False,
    can_update: bool = True,
    path_family: str = "P:/old_show/cache",
    parm_path: str = "/obj/geo1/file/file",
    missing_variables: tuple[str, ...] = (),
    reference_role: str = ReferenceRole.INBOUND_DEPENDENCY.value,
) -> AssetReference:
    """Build a file-parameter reference for window tests."""
    return AssetReference(
        kind=ReferenceKind.FILE_PARAMETER,
        raw_path=raw_path,
        expanded_path=raw_path,
        exists=exists,
        sequence_pattern="",
        path_family=path_family,
        parm_path=parm_path,
        node_path=parm_path.rsplit("/", 2)[0],
        reference_role=reference_role,
        can_update=can_update,
        missing_variables=missing_variables,
    )


def test_startup_filters_match_checked_widgets(qt_app) -> None:
    """It applies checked missing/writable filters before the user toggles them."""
    del qt_app
    relinker = AssetRelinkerWindow()
    try:
        relinker._reference_model.set_references(
            [
                AssetReference(
                    kind=ReferenceKind.FILE_PARAMETER,
                    raw_path="P:/show/cache/missing.bgeo.sc",
                    expanded_path="P:/show/cache/missing.bgeo.sc",
                    exists=False,
                    sequence_pattern="",
                    parm_path="/obj/geo1/file1/file",
                    node_path="/obj/geo1",
                    can_update=True,
                ),
                AssetReference(
                    kind=ReferenceKind.FILE_PARAMETER,
                    raw_path="P:/show/cache/ready.bgeo.sc",
                    expanded_path="P:/show/cache/ready.bgeo.sc",
                    exists=True,
                    sequence_pattern="",
                    parm_path="/obj/geo1/file2/file",
                    node_path="/obj/geo1",
                    can_update=True,
                ),
                AssetReference(
                    kind=ReferenceKind.FILE_PARAMETER,
                    raw_path="P:/show/cache/locked.bgeo.sc",
                    expanded_path="P:/show/cache/locked.bgeo.sc",
                    exists=False,
                    sequence_pattern="",
                    parm_path="/obj/geo1/file3/file",
                    node_path="/obj/geo1",
                    can_update=False,
                    reason="Parameter is locked",
                ),
            ]
        )

        assert relinker.missing_only_check.text() == "Broken targets"
        assert relinker.missing_only_check.isChecked()
        assert relinker.writable_only_check.isChecked()
        assert relinker._proxy_model.rowCount() == 1
    finally:
        relinker.close()


def test_table_scroll_modes(qt_app) -> None:
    """It configures scroll modes to ScrollPerPixel for both tables."""
    del qt_app
    relinker = AssetRelinkerWindow()
    try:
        assert relinker.reference_table.verticalScrollMode() == SCROLL_PER_PIXEL
        assert relinker.reference_table.horizontalScrollMode() == SCROLL_PER_PIXEL
        assert relinker.report_table.verticalScrollMode() == SCROLL_PER_PIXEL
        assert relinker.report_table.horizontalScrollMode() == SCROLL_PER_PIXEL
    finally:
        relinker.close()


def test_report_table_model_uses_row_tints_and_readable_tooltips(qt_app) -> None:
    """It omits the status column and encodes outcomes with row tints and tooltips."""
    del qt_app
    model = UpdateResultTableModel()
    model.set_report(
        UpdateReport(
            dry_run=True,
            results=(
                UpdateResult(
                    status="would_change",
                    old_path="/old/a",
                    new_path="/new/a",
                    parm_path="/obj/geo1/file",
                ),
                UpdateResult(
                    status="skipped",
                    old_path="/old/b",
                    new_path="/new/b",
                    message="Already matches.",
                ),
                UpdateResult(
                    status="failed",
                    old_path="/old/c",
                    new_path="/new/c",
                    message="Permission denied.",
                ),
            ),
        )
    )

    assert model.columnCount() == 4
    assert model.headerData(0, HORIZONTAL, DISPLAY_ROLE) == "Target"
    assert model.data(model.index(0, 0)) == "/obj/geo1/file"

    expected = (
        ("Planned change", STATUS_COLOR_READY),
        ("Skipped", STATUS_COLOR_NOT_UPDATABLE),
        ("Failed", STATUS_COLOR_MISSING),
    )
    for row, (status_label, status_color) in enumerate(expected):
        tooltip = model.data(model.index(row, 0), TOOLTIP_ROLE)
        assert tooltip.startswith(f"Status: {status_label}")
        for column in range(model.columnCount()):
            brush = model.data(model.index(row, column), BACKGROUND_ROLE)
            assert brush is not None
            color = brush.color()
            assert color.alpha() == 255
            expected_color = _blend_hex_color(
                REPORT_TABLE_ALT_BASE_COLOR if row % 2 else REPORT_TABLE_BASE_COLOR,
                status_color,
                REPORT_STATUS_TINT_MIX,
            )
            assert color.name() == expected_color.name()


def test_report_table_layout_and_legend(qt_app) -> None:
    """It sizes report columns without a status field and shows the status legend."""
    del qt_app
    relinker = AssetRelinkerWindow()
    try:
        assert relinker._report_model.columnCount() == 4
        assert relinker.report_table.columnWidth(0) == 200
        assert relinker.report_table.columnWidth(1) == 280
        assert relinker.report_table.columnWidth(2) == 280
        legend_labels = {
            widget.text()
            for widget in relinker.findChildren(window_module.QtWidgets.QLabel)
            if widget.text() in {"Change", "Skipped", "Failed"}
        }
        assert legend_labels == {"Change", "Skipped", "Failed"}
    finally:
        relinker.close()


def test_reference_table_sorts_by_path_family_by_default(qt_app) -> None:
    """It opens the scan table sorted by raw-path family."""
    del qt_app
    relinker = AssetRelinkerWindow()
    try:
        assert relinker._proxy_model.sortColumn() == REFERENCE_PATH_FAMILY_COLUMN
        assert relinker.reference_table.horizontalHeader().sortIndicatorSection() == (
            REFERENCE_PATH_FAMILY_COLUMN
        )
    finally:
        relinker.close()


def test_reference_table_reports_undefined_variables(qt_app) -> None:
    """It names undefined variables in table status, note, and details."""
    del qt_app
    relinker = AssetRelinkerWindow()
    try:
        relinker._reference_model.set_references(
            [
                AssetReference(
                    kind=ReferenceKind.FILE_PARAMETER,
                    raw_path="$AYON_CACHE/cache/sim.$F4.bgeo.sc",
                    expanded_path="G:/projects/Data_folder/Houdini_Cache////geo/sim.1052.bgeo.sc",
                    exists=False,
                    sequence_pattern="$AYON_CACHE/cache/sim.*.bgeo.sc",
                    parm_path="/obj/geo1/filecache1/sopoutput",
                    node_path="/obj/geo1/filecache1",
                    missing_variables=("AYON_CACHE",),
                    can_update=True,
                )
            ]
        )

        status_index = relinker._reference_model.index(0, 0)
        note_index = relinker._reference_model.index(0, 9)
        assert relinker._reference_model.data(status_index) == "Undefined variable"
        assert relinker._reference_model.data(note_index) == "Undefined variables: AYON_CACHE"
        assert "Undefined variables: AYON_CACHE" in relinker._reference_model.data(
            status_index, TOOLTIP_ROLE
        )

        relinker.reference_table.selectRow(0)
        relinker._selection_changed()
        detail_text = relinker.detail_text.toPlainText()
        assert "Status: undefined variable" in detail_text
        assert "Undefined variables: AYON_CACHE" in detail_text
        assert "Sequence pattern: $AYON_CACHE/cache/sim.*.bgeo.sc" in detail_text
    finally:
        relinker.close()


def test_reference_table_keeps_generated_outputs_out_of_broken_target_filter(qt_app) -> None:
    """It shows generated outputs as context rows, not broken relink targets."""
    del qt_app
    relinker = AssetRelinkerWindow()
    try:
        relinker._reference_model.set_references(
            [
                _reference("P:/old_show/textures/missing.exr"),
                _reference(
                    "P:/old_show/cache/out.$F4.bgeo.sc",
                    parm_path="/obj/geo1/filecache1/sopoutput",
                    can_update=False,
                    reference_role=ReferenceRole.GENERATED_OUTPUT.value,
                    path_family="P:/old_show/cache",
                ),
            ]
        )

        assert relinker._proxy_model.rowCount() == 1
        status_index = relinker._reference_model.index(1, 0)
        role_index = relinker._reference_model.index(1, 2)
        note_index = relinker._reference_model.index(1, 9)
        assert relinker._reference_model.data(status_index) == "Generated output"
        assert relinker._reference_model.data(role_index) == "Generated output"
        assert relinker._reference_model.data(note_index) == (
            "Generated output path kept for context"
        )

        relinker.missing_only_check.setChecked(False)
        relinker.writable_only_check.setChecked(False)
        assert relinker._proxy_model.rowCount() == 2
        _select_reference_by_raw_path(relinker, "P:/old_show/cache/out.$F4.bgeo.sc")
        relinker._selection_changed()
        detail_text = relinker.detail_text.toPlainText()
        assert "Role: generated_output" in detail_text
        assert "Status: generated output" in detail_text
        assert "Generated output path kept for context" in detail_text
        assert "1 broken targets" in relinker.summary_label.text()
        assert "1 generated outputs" in relinker.summary_label.text()
    finally:
        relinker.close()


def test_replacement_input_change_updates_live_preview(qt_app, relinker_window) -> None:
    """It keeps the relink report in sync while Find text changes."""
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")
    _flush_live_relink_preview(qt_app)

    assert relinker_window.apply_button.isEnabled()
    assert relinker_window._preview_request == ReplaceRequest(
        find_text="P:/old_show",
        replace_with="P:/new_show",
        case_sensitive=False,
        include_hda_libraries=False,
        uninstall_old_hda_libraries=False,
        scope=SCOPE_VISIBLE_ROWS,
    )
    assert relinker_window._report_model.rowCount() == 1

    relinker_window.find_edit.setText("P:/other_show")
    _flush_live_relink_preview(qt_app)

    assert relinker_window._preview_report is not None
    assert relinker_window._preview_request == ReplaceRequest(
        find_text="P:/other_show",
        replace_with="P:/new_show",
        case_sensitive=False,
        include_hda_libraries=False,
        uninstall_old_hda_libraries=False,
        scope=SCOPE_VISIBLE_ROWS,
    )
    assert not relinker_window.apply_button.isEnabled()
    assert relinker_window._report_model.rowCount() == 0


def test_live_relink_preview_updates_without_preview_button(qt_app, relinker_window) -> None:
    """It populates the relink report as the user edits Find and Replace with."""
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")
    _flush_live_relink_preview(qt_app)

    assert relinker_window._report_model.rowCount() == 1
    assert relinker_window._current_report is not None
    assert relinker_window._current_report.results[0].new_path == "P:/new_show/cache/a.bgeo.sc"

    relinker_window.replace_edit.setText("P:/renamed_show")
    _flush_live_relink_preview(qt_app)

    assert relinker_window._report_model.rowCount() == 1
    assert relinker_window._current_report is not None
    assert relinker_window._current_report.results[0].new_path == "P:/renamed_show/cache/a.bgeo.sc"


def test_live_relink_preview_clears_when_find_is_empty(qt_app, relinker_window) -> None:
    """It clears the relink report when Find is empty."""
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")
    _flush_live_relink_preview(qt_app)
    assert relinker_window._report_model.rowCount() == 1

    relinker_window.find_edit.clear()
    _flush_live_relink_preview(qt_app)

    assert relinker_window._preview_report is None
    assert relinker_window._report_model.rowCount() == 0
    assert not relinker_window.apply_button.isEnabled()


def test_apply_uses_the_stored_preview_request(monkeypatch, qt_app, relinker_window) -> None:
    """It applies the request that produced the preview."""
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")
    _flush_live_relink_preview(qt_app)

    captured_requests: list[ReplaceRequest] = []

    def fake_build_replace_report(
        request: ReplaceRequest,
        references: list[AssetReference],
        dry_run: bool,
    ) -> UpdateReport:
        del references
        assert not dry_run
        captured_requests.append(request)
        return UpdateReport(
            dry_run=False,
            results=(
                UpdateResult(
                    status="changed",
                    old_path="P:/old_show/cache/a.bgeo.sc",
                    new_path="P:/new_show/cache/a.bgeo.sc",
                    parm_path="/obj/geo1/file1/file",
                ),
            ),
        )

    monkeypatch.setattr(relinker_window, "_build_replace_report", fake_build_replace_report)
    monkeypatch.setattr(relinker_window, "scan", lambda: None)
    monkeypatch.setattr(
        window_module.QtWidgets.QMessageBox,
        "warning",
        lambda *_args, **_kwargs: window_module.MESSAGE_OK,
    )

    relinker_window.apply_replace()

    assert captured_requests == [
        ReplaceRequest(
            find_text="P:/old_show",
            replace_with="P:/new_show",
            case_sensitive=False,
            include_hda_libraries=False,
            uninstall_old_hda_libraries=False,
            scope=SCOPE_VISIBLE_ROWS,
        )
    ]


def test_preview_defaults_to_case_insensitive_windows_paths(relinker_window) -> None:
    """It previews relinks when Windows-style path casing differs."""
    relinker_window._reference_model.set_references([_reference("P:/OLD_SHOW/Cache/a.bgeo.sc")])
    relinker_window.find_edit.setText("p:/old_show/cache")
    relinker_window.replace_edit.setText("P:/new_show/cache")

    relinker_window.preview_replace()

    assert relinker_window._preview_request == ReplaceRequest(
        find_text="p:/old_show/cache",
        replace_with="P:/new_show/cache",
        case_sensitive=False,
        include_hda_libraries=False,
        uninstall_old_hda_libraries=False,
        scope=SCOPE_VISIBLE_ROWS,
    )
    assert relinker_window.apply_button.isEnabled()
    assert relinker_window._current_report is not None
    assert relinker_window._current_report.results[0].new_path == ("P:/new_show/cache/a.bgeo.sc")


def test_exact_case_checkbox_skips_case_mismatched_preview(relinker_window) -> None:
    """It keeps exact-case matching as an opt-in."""
    relinker_window._reference_model.set_references([_reference("P:/OLD_SHOW/Cache/a.bgeo.sc")])
    relinker_window.find_edit.setText("p:/old_show/cache")
    relinker_window.replace_edit.setText("P:/new_show/cache")
    relinker_window.case_sensitive_check.setChecked(True)

    relinker_window.preview_replace()

    assert relinker_window._preview_request == ReplaceRequest(
        find_text="p:/old_show/cache",
        replace_with="P:/new_show/cache",
        case_sensitive=True,
        include_hda_libraries=False,
        uninstall_old_hda_libraries=False,
        scope=SCOPE_VISIBLE_ROWS,
    )
    assert not relinker_window.apply_button.isEnabled()
    assert relinker_window._current_report is not None
    assert relinker_window._current_report.results == ()


def test_visible_scope_previews_only_filtered_rows(relinker_window) -> None:
    """It limits preview targets to the rows accepted by current table filters."""
    relinker_window._reference_model.set_references(
        [
            _reference("P:/old_show/cache/missing.bgeo.sc"),
            _reference("P:/old_show/cache/ready.bgeo.sc", exists=True),
            _reference("P:/old_show/cache/locked.bgeo.sc", can_update=False),
        ]
    )
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")

    relinker_window.preview_replace()

    assert [reference.raw_path for reference in relinker_window._preview_references] == [
        "P:/old_show/cache/missing.bgeo.sc"
    ]
    assert relinker_window._report_model.rowCount() == 1


def test_selected_row_scope_previews_only_selected_reference(relinker_window) -> None:
    """It limits preview targets to the selected reference row."""
    relinker_window._reference_model.set_references(
        [
            _reference("P:/old_show/cache/a.bgeo.sc", path_family="P:/old_show/cache"),
            _reference("P:/old_show/textures/diffuse.exr", path_family="P:/old_show/textures"),
        ]
    )
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")
    _set_scope(relinker_window, SCOPE_SELECTED_ROW)
    _select_reference_by_raw_path(relinker_window, "P:/old_show/textures/diffuse.exr")

    relinker_window.preview_replace()

    assert [reference.raw_path for reference in relinker_window._preview_references] == [
        "P:/old_show/textures/diffuse.exr"
    ]
    assert relinker_window._report_model.rowCount() == 1


def test_path_family_scope_previews_selected_family(relinker_window) -> None:
    """It targets all scanned references in the selected path family."""
    relinker_window._reference_model.set_references(
        [
            _reference("P:/old_show/cache/a.bgeo.sc", path_family="P:/old_show/cache"),
            _reference("P:/old_show/cache/b.bgeo.sc", path_family="P:/old_show/cache"),
            _reference("P:/old_show/textures/diffuse.exr", path_family="P:/old_show/textures"),
        ]
    )
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")
    _set_scope(relinker_window, SCOPE_PATH_FAMILY)
    _select_reference_by_raw_path(relinker_window, "P:/old_show/cache/a.bgeo.sc")

    relinker_window.preview_replace()

    assert {reference.raw_path for reference in relinker_window._preview_references} == {
        "P:/old_show/cache/a.bgeo.sc",
        "P:/old_show/cache/b.bgeo.sc",
    }
    assert relinker_window._report_model.rowCount() == 2


def test_missing_under_find_root_scope_excludes_existing_and_nonmatching_rows(
    relinker_window,
) -> None:
    """It targets writable missing rows whose raw path is under the Find root."""
    relinker_window._reference_model.set_references(
        [
            _reference("P:/old_show/cache/missing.bgeo.sc"),
            _reference("P:/old_show/cache/ready.bgeo.sc", exists=True),
            _reference("P:/old_show/cache/locked.bgeo.sc", can_update=False),
            _reference("P:/other_show/cache/missing.bgeo.sc"),
            _reference(
                "$ASSET_ROOT/cache/missing.bgeo.sc",
                missing_variables=("ASSET_ROOT",),
                path_family="$ASSET_ROOT",
            ),
        ]
    )
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")
    _set_scope(relinker_window, SCOPE_MISSING_UNDER_ROOT)

    relinker_window.preview_replace()

    assert [reference.raw_path for reference in relinker_window._preview_references] == [
        "P:/old_show/cache/missing.bgeo.sc"
    ]
    assert relinker_window._report_model.rowCount() == 1


def test_apply_uses_current_live_preview_scope(monkeypatch, qt_app, relinker_window) -> None:
    """It applies the references currently shown in the live relink preview."""
    relinker_window._reference_model.set_references(
        [
            _reference("P:/old_show/cache/a.bgeo.sc"),
            _reference("P:/old_show/cache/b.bgeo.sc"),
        ]
    )
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")
    _flush_live_relink_preview(qt_app)

    applied_references: list[str] = []

    def fake_build_replace_report(
        request: ReplaceRequest,
        references: list[AssetReference],
        dry_run: bool,
    ) -> UpdateReport:
        del request
        if dry_run:
            return UpdateReport(
                dry_run=True,
                results=tuple(
                    UpdateResult(
                        status="would_change",
                        old_path=reference.raw_path,
                        new_path=reference.raw_path.replace("old_show", "new_show"),
                        parm_path=reference.parm_path,
                    )
                    for reference in references
                ),
            )
        applied_references.extend(reference.raw_path for reference in references)
        return UpdateReport(
            dry_run=False,
            results=tuple(
                UpdateResult(
                    status="changed",
                    old_path=reference.raw_path,
                    new_path=reference.raw_path.replace("old_show", "new_show"),
                    parm_path=reference.parm_path,
                )
                for reference in references
            ),
        )

    monkeypatch.setattr(relinker_window, "_build_replace_report", fake_build_replace_report)
    monkeypatch.setattr(relinker_window, "scan", lambda: None)
    monkeypatch.setattr(
        window_module.QtWidgets.QMessageBox,
        "warning",
        lambda *_args, **_kwargs: window_module.MESSAGE_OK,
    )
    relinker_window.search_edit.setText("a.bgeo")
    _flush_live_relink_preview(qt_app)

    relinker_window.apply_replace()

    assert applied_references == ["P:/old_show/cache/a.bgeo.sc"]


def test_find_match_label_updates_for_matching_paths(relinker_window) -> None:
    """It shows a live Find match count while the user types."""
    relinker_window.missing_only_check.setChecked(False)
    relinker_window.writable_only_check.setChecked(False)
    relinker_window._reference_model.set_references(
        [
            _reference("$CACHE/sim.$F4.bgeo.sc"),
            _reference("$CACHE_G/sim.$F4.bgeo.sc"),
        ]
    )
    relinker_window._sync_reference_filters()

    relinker_window.find_edit.setText("$CACHE")

    assert not relinker_window.find_match_label.isHidden()
    assert relinker_window.find_match_label.text() == "1 reference matches Find"


def test_find_match_label_includes_visible_count_when_filtered(relinker_window) -> None:
    """It reports how many Find matches are currently visible in the table."""
    relinker_window.missing_only_check.setChecked(False)
    relinker_window.writable_only_check.setChecked(False)
    relinker_window._reference_model.set_references(
        [
            _reference("$CACHE/sim.$F4.bgeo.sc"),
            _reference("$HIP/$CACHE/other.bgeo.sc"),
        ]
    )
    relinker_window._sync_reference_filters()
    relinker_window.search_edit.setText("$HIP")

    relinker_window.find_edit.setText("$CACHE")

    assert (
        relinker_window.find_match_label.text() == "2 references match Find (1 reference visible)"
    )


def test_find_match_highlight_marks_matching_rows(relinker_window) -> None:
    """It highlights reference rows whose raw path matches Find."""
    from houdini_asset_relinker.ui.qt_constants import BACKGROUND_ROLE

    relinker_window.missing_only_check.setChecked(False)
    relinker_window.writable_only_check.setChecked(False)
    relinker_window._reference_model.set_references(
        [
            _reference("$CACHE/sim.$F4.bgeo.sc"),
            _reference("$CACHE_G/sim.$F4.bgeo.sc"),
        ]
    )
    relinker_window._sync_reference_filters()
    relinker_window.find_edit.setText("$CACHE")

    model = relinker_window._reference_model
    assert model.data(model.index(0, 0), BACKGROUND_ROLE) is not None
    assert model.data(model.index(1, 0), BACKGROUND_ROLE) is None


def test_find_match_label_hides_when_find_is_empty(relinker_window) -> None:
    """It clears the live Find match label when Find is empty."""
    relinker_window.find_edit.setText("$CACHE")
    assert not relinker_window.find_match_label.isHidden()

    relinker_window.find_edit.clear()

    assert relinker_window.find_match_label.isHidden()
    assert relinker_window.find_match_label.text() == ""
