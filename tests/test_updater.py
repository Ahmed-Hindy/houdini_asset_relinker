"""Tests for Houdini asset path updates."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from houdini_asset_relinker.models import AssetReference, ReferenceKind
from houdini_asset_relinker.updater import (
    replace_hda_library_paths,
    replace_path_root,
    replace_path_text,
)


class FakeParm:
    """Minimal stand-in for a writable Houdini parameter."""

    def __init__(self) -> None:
        self.value = ""
        self.follow_parm_reference = None

    def set(self, value: str, follow_parm_reference: bool = True) -> None:
        """Record the value passed through the updater."""
        self.value = value
        self.follow_parm_reference = follow_parm_reference


def _reference(raw_path: str, parm_path: str = "/obj/geo1/file1/file") -> AssetReference:
    """Build a writable file parameter reference for tests."""
    return AssetReference(
        kind=ReferenceKind.FILE_PARAMETER,
        raw_path=raw_path,
        expanded_path=raw_path,
        exists=False,
        parm_path=parm_path,
        node_path="/obj/geo1",
        can_update=True,
    )


def test_replace_path_text_dry_run_does_not_touch_houdini() -> None:
    """It reports planned updates without requiring a live hou module."""
    report = replace_path_text(
        "P:/old_show",
        "P:/new_show",
        dry_run=True,
        references=[_reference("P:/old_show/cache/a.bgeo.sc")],
    )

    assert report.dry_run
    assert report.changed_count == 1
    assert report.results[0].status == "would_change"
    assert report.results[0].new_path == "P:/new_show/cache/a.bgeo.sc"


def test_replace_path_text_apply_sets_houdini_parameter(monkeypatch) -> None:
    """It applies matching updates to the referenced Houdini parameter."""
    parm = FakeParm()
    fake_hou = SimpleNamespace(parm=lambda path: parm if path == "/obj/geo1/file1/file" else None)
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    report = replace_path_text(
        "P:/old_show",
        "P:/new_show",
        dry_run=False,
        references=[_reference("P:/old_show/cache/a.bgeo.sc")],
    )

    assert report.changed_count == 1
    assert report.results[0].status == "changed"
    assert parm.value == "P:/new_show/cache/a.bgeo.sc"
    assert parm.follow_parm_reference is False


def test_replace_path_root_skips_non_matching_paths() -> None:
    """It leaves paths outside the requested root unchanged."""
    report = replace_path_root(
        "P:/old_show",
        "P:/new_show",
        dry_run=True,
        references=[_reference("P:/other_show/cache/a.bgeo.sc")],
    )

    assert report.changed_count == 0
    assert report.results == ()


def test_replace_path_text_reports_missing_parameter_on_apply(monkeypatch) -> None:
    """It reports a failed result if the Houdini parameter disappears."""
    fake_hou = SimpleNamespace(parm=lambda path: None)
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    report = replace_path_text(
        "P:/old_show",
        "P:/new_show",
        dry_run=False,
        references=[_reference("P:/old_show/cache/a.bgeo.sc")],
    )

    assert report.failed_count == 1
    assert report.results[0].message == "Parameter no longer exists."


def test_replace_hda_library_paths_dry_run_accepts_prescanned_references() -> None:
    """It previews HDA library updates from scanned rows without importing hou."""
    report = replace_hda_library_paths(
        "old_show",
        "new_show",
        dry_run=True,
        case_sensitive=False,
        references=[
            AssetReference(
                kind=ReferenceKind.HDA_LIBRARY,
                raw_path="P:/OLD_SHOW/assets/tool.hda",
                expanded_path="P:/OLD_SHOW/assets/tool.hda",
                exists=True,
                can_update=True,
            ),
            _reference("P:/OLD_SHOW/cache/a.bgeo.sc"),
        ],
    )

    assert report.changed_count == 1
    assert report.results[0].status == "would_change"
    assert report.results[0].new_path == "P:/new_show/assets/tool.hda"
