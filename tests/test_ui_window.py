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
from houdini_asset_relinker.ui.qt_constants import TOOLTIP_ROLE
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


def test_replacement_input_change_invalidates_preview(relinker_window) -> None:
    """It disables Apply when replacement settings diverge from the preview."""
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")

    relinker_window.preview_replace()

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

    assert relinker_window._preview_report is None
    assert relinker_window._preview_request is None
    assert not relinker_window.apply_button.isEnabled()
    assert relinker_window._report_model.rowCount() == 0


def test_apply_uses_the_stored_preview_request(monkeypatch, relinker_window) -> None:
    """It applies the request that produced the preview."""
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")
    relinker_window.preview_replace()

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


def test_apply_uses_preview_references_when_filters_change(monkeypatch, relinker_window) -> None:
    """It applies the exact target set that produced the preview."""
    relinker_window._reference_model.set_references(
        [
            _reference("P:/old_show/cache/a.bgeo.sc"),
            _reference("P:/old_show/cache/b.bgeo.sc"),
        ]
    )
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")
    relinker_window.preview_replace()

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
    relinker_window.search_edit.setText("no rows visible")

    relinker_window.apply_replace()

    assert applied_references == [
        "P:/old_show/cache/a.bgeo.sc",
        "P:/old_show/cache/b.bgeo.sc",
    ]
