"""Relink preview state and report helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

from houdini_asset_relinker.models import AssetReference, UpdateReport, UpdateResult
from houdini_asset_relinker.updater import (
    normalize_path_formats,
    replace_hda_library_paths,
    replace_path_text,
)

OPERATION_REPLACE_TEXT = "replace_text"
OPERATION_NORMALIZE_PATHS = "normalize_paths"
SCOPE_VISIBLE_ROWS = "visible_rows"
SCOPE_SELECTED_ROW = "selected_row"
SCOPE_PATH_FAMILY = "path_family"
SCOPE_MISSING_UNDER_ROOT = "missing_under_root"
SCOPE_ALL_ROWS = "all_rows"


@dataclass(frozen=True)
class ReplaceRequest:
    """User-selected path replacement settings."""

    find_text: str
    replace_with: str
    case_sensitive: bool
    include_hda_libraries: bool
    uninstall_old_hda_libraries: bool
    scope: str
    operation: str = OPERATION_REPLACE_TEXT


@dataclass
class RelinkState:
    """Mutable relink preview and apply state."""

    preview_report: Optional[UpdateReport] = None
    preview_request: Optional[ReplaceRequest] = None
    preview_references: tuple[AssetReference, ...] = ()
    applied_request: Optional[ReplaceRequest] = None
    current_report: Optional[UpdateReport] = None

    def has_preview_results(self) -> bool:
        """Return whether the current preview has any rows."""
        return self.preview_report is not None and bool(self.preview_report.results)

    def set_preview(
        self,
        report: UpdateReport,
        request: ReplaceRequest,
        references: Iterable[AssetReference],
    ) -> None:
        """Store a dry-run report and the request that produced it."""
        self.preview_report = report
        self.preview_request = request
        self.preview_references = tuple(references)
        self.current_report = report

    def clear_report(self) -> None:
        """Clear preview, applied, and current report state."""
        self.preview_report = None
        self.preview_request = None
        self.preview_references = ()
        self.applied_request = None
        self.current_report = None

    def set_applied_report(self, report: UpdateReport, request: ReplaceRequest) -> None:
        """Store the report produced by an apply operation."""
        self.preview_report = None
        self.preview_request = None
        self.preview_references = ()
        self.applied_request = request
        self.current_report = report

    def should_keep_applied_report(self, request: ReplaceRequest) -> bool:
        """Return whether the current applied report still matches the UI request."""
        return (
            self.current_report is not None
            and not self.current_report.dry_run
            and request == self.applied_request
        )

    def clear_applied_request(self) -> None:
        """Forget which request produced the current applied report."""
        self.applied_request = None


def build_replace_report(
    request: ReplaceRequest,
    references: Iterable[AssetReference],
    dry_run: bool,
) -> UpdateReport:
    """Build a combined text-path and optional HDA relink report."""
    if request.operation == OPERATION_NORMALIZE_PATHS:
        return normalize_path_formats(dry_run=dry_run, references=references)

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
    return merge_reports(dry_run, reports)


def merge_reports(dry_run: bool, reports: Iterable[UpdateReport]) -> UpdateReport:
    """Merge multiple update reports into one report."""
    results: list[UpdateResult] = []
    for report in reports:
        results.extend(report.results)
    return UpdateReport(dry_run=dry_run, results=tuple(results))
