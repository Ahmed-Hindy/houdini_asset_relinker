"""Tests for relink preview state helpers."""

from __future__ import annotations

from houdini_asset_relinker.models import (
    AssetReference,
    ReferenceKind,
    UpdateReport,
    UpdateResult,
    UpdateStatus,
)
from houdini_asset_relinker.ui.relink_state import RelinkState, ReplaceRequest, merge_reports


def _request(find_text: str = "P:/old_show") -> ReplaceRequest:
    """Return a basic relink request."""
    return ReplaceRequest(
        find_text=find_text,
        replace_with="P:/new_show",
        case_sensitive=False,
        include_hda_libraries=False,
        uninstall_old_hda_libraries=False,
        scope="visible_rows",
    )


def _reference() -> AssetReference:
    """Return a basic file reference."""
    return AssetReference(
        kind=ReferenceKind.FILE_PARAMETER,
        raw_path="P:/old_show/cache/a.bgeo.sc",
        expanded_path="P:/old_show/cache/a.bgeo.sc",
        exists=False,
        sequence_pattern="",
        parm_path="/obj/geo1/file1/file",
        node_path="/obj/geo1",
        can_update=True,
    )


def _report(dry_run: bool) -> UpdateReport:
    """Return a basic update report."""
    status = UpdateStatus.WOULD_CHANGE if dry_run else UpdateStatus.CHANGED
    return UpdateReport(
        dry_run=dry_run,
        results=(
            UpdateResult(
                status=status,
                old_path="P:/old_show/cache/a.bgeo.sc",
                new_path="P:/new_show/cache/a.bgeo.sc",
                parm_path="/obj/geo1/file1/file",
            ),
        ),
    )


def test_relink_state_tracks_preview_request_and_references() -> None:
    """It stores the dry-run report with its request and target references."""
    state = RelinkState()
    request = _request()
    report = _report(dry_run=True)
    reference = _reference()

    state.set_preview(report, request, [reference])

    assert state.has_preview_results()
    assert state.preview_report == report
    assert state.preview_request == request
    assert state.preview_references == (reference,)
    assert state.current_report == report


def test_relink_state_retains_matching_applied_report() -> None:
    """It knows when a live-preview tick should leave an applied report alone."""
    state = RelinkState()
    request = _request()
    report = _report(dry_run=False)

    state.set_applied_report(report, request)

    assert state.should_keep_applied_report(request)
    assert not state.has_preview_results()
    assert state.current_report == report
    assert not state.current_report.dry_run


def test_relink_state_clears_reports() -> None:
    """It clears preview and applied report state together."""
    state = RelinkState()
    state.set_applied_report(_report(dry_run=False), _request())

    state.clear_report()

    assert state.preview_report is None
    assert state.preview_request is None
    assert state.preview_references == ()
    assert state.applied_request is None
    assert state.current_report is None


def test_merge_reports_preserves_result_order() -> None:
    """It flattens report results into one update report."""
    first = _report(dry_run=True)
    second = UpdateReport(
        dry_run=True,
        results=(
            UpdateResult(
                status=UpdateStatus.SKIPPED,
                old_path="P:/old_show/cache/b.bgeo.sc",
                new_path="P:/new_show/cache/b.bgeo.sc",
                parm_path="/obj/geo1/file2/file",
                message="Already current.",
            ),
        ),
    )

    merged = merge_reports(dry_run=True, reports=[first, second])

    assert merged.dry_run
    assert [result.parm_path for result in merged.results] == [
        "/obj/geo1/file1/file",
        "/obj/geo1/file2/file",
    ]
