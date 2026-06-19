"""Tests for the asset relinker Qt window workflow."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from houdini_asset_relinker.models import AssetReference, ReferenceKind, UpdateReport, UpdateResult
from houdini_asset_relinker.ui import window as window_module
from houdini_asset_relinker.ui.qt_constants import TOOLTIP_ROLE
from houdini_asset_relinker.ui.window import (
    REFERENCE_PATH_FAMILY_COLUMN,
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
        note_index = relinker._reference_model.index(0, 8)
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


def test_replacement_input_change_invalidates_preview(relinker_window) -> None:
    """It disables Apply when replacement settings diverge from the preview."""
    relinker_window.find_edit.setText("P:/old_show")
    relinker_window.replace_edit.setText("P:/new_show")

    relinker_window.preview_replace()

    assert relinker_window.apply_button.isEnabled()
    assert relinker_window._preview_request == ReplaceRequest(
        find_text="P:/old_show",
        replace_with="P:/new_show",
        case_sensitive=True,
        include_hda_libraries=False,
        uninstall_old_hda_libraries=False,
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
            case_sensitive=True,
            include_hda_libraries=False,
            uninstall_old_hda_libraries=False,
        )
    ]
