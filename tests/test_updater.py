"""Tests for Houdini asset path updates."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from houdini_asset_relinker.models import (
    AssetReference,
    ReferenceKind,
    ReferenceRole,
    UpdateStatus,
)
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
        sequence_pattern="",
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
    assert report.results[0].status == UpdateStatus.WOULD_CHANGE
    assert report.results[0].new_path == "P:/new_show/cache/a.bgeo.sc"


def test_replace_path_text_skips_longer_houdini_variable_prefixes() -> None:
    """It does not relink paths that only share a shorter variable prefix."""
    report = replace_path_text(
        "$CACHE",
        "$CACHE_G",
        dry_run=True,
        references=[
            _reference("$CACHE/sim.$F4.bgeo.sc"),
            _reference("$CACHE_G/sim.$F4.bgeo.sc"),
        ],
    )

    assert report.changed_count == 1
    assert report.results[0].old_path == "$CACHE/sim.$F4.bgeo.sc"
    assert report.results[0].new_path == "$CACHE_G/sim.$F4.bgeo.sc"


def test_replace_path_text_defaults_to_case_insensitive_windows_paths() -> None:
    """It relinks Windows-style paths when only the drive or folder casing differs."""
    report = replace_path_text(
        "p:/old_show/cache",
        "P:/new_show/cache",
        dry_run=True,
        references=[_reference("P:/OLD_SHOW/Cache/a.bgeo.sc")],
    )

    assert report.changed_count == 1
    assert report.results[0].new_path == "P:/new_show/cache/a.bgeo.sc"


def test_replace_path_text_exact_case_opt_in_skips_case_mismatch() -> None:
    """It leaves case-mismatched Windows-style paths alone when exact case is requested."""
    report = replace_path_text(
        "p:/old_show/cache",
        "P:/new_show/cache",
        dry_run=True,
        case_sensitive=True,
        references=[_reference("P:/OLD_SHOW/Cache/a.bgeo.sc")],
    )

    assert report.changed_count == 0
    assert report.results == ()


def test_replace_path_text_apply_sets_houdini_parameter(monkeypatch) -> None:
    """It applies matching updates to the referenced Houdini parameter."""
    from contextlib import contextmanager

    class FakeUndos:
        @contextmanager
        def group(self, label: str):
            yield

    parm = FakeParm()
    fake_hou = SimpleNamespace(
        parm=lambda path: parm if path == "/obj/geo1/file1/file" else None,
        undos=FakeUndos(),
    )
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    report = replace_path_text(
        "P:/old_show",
        "P:/new_show",
        dry_run=False,
        references=[_reference("P:/old_show/cache/a.bgeo.sc")],
    )

    assert report.changed_count == 1
    assert report.results[0].status == UpdateStatus.CHANGED
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


def test_replace_path_text_skips_generated_output_context_rows() -> None:
    """It does not preview generated outputs as relink targets."""
    report = replace_path_text(
        "P:/old_show",
        "P:/new_show",
        dry_run=True,
        references=[
            _reference("P:/old_show/textures/diffuse.exr"),
            AssetReference(
                kind=ReferenceKind.FILE_PARAMETER,
                reference_role=ReferenceRole.GENERATED_OUTPUT.value,
                raw_path="P:/old_show/cache/out.$F4.bgeo.sc",
                expanded_path="P:/old_show/cache/out.1052.bgeo.sc",
                exists=False,
                sequence_pattern="P:/old_show/cache/out.*.bgeo.sc",
                parm_path="/obj/geo1/filecache1/sopoutput",
                node_path="/obj/geo1/filecache1",
                can_update=False,
            ),
        ],
    )

    assert [result.old_path for result in report.results] == ["P:/old_show/textures/diffuse.exr"]


def test_replace_path_text_reports_missing_parameter_on_apply(monkeypatch) -> None:
    """It reports a failed result if the Houdini parameter disappears."""
    from contextlib import contextmanager

    class FakeUndos:
        @contextmanager
        def group(self, label: str):
            yield

    fake_hou = SimpleNamespace(
        parm=lambda path: None,
        undos=FakeUndos(),
    )
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
                sequence_pattern="",
                can_update=True,
            ),
            _reference("P:/OLD_SHOW/cache/a.bgeo.sc"),
        ],
    )

    assert report.changed_count == 1
    assert report.results[0].status == UpdateStatus.WOULD_CHANGE
    assert report.results[0].new_path == "P:/new_show/assets/tool.hda"


def test_undo_group_active(monkeypatch) -> None:
    """It enters the hou.undos.group context manager when hou has undos."""
    from contextlib import contextmanager

    entered_label = None

    class FakeUndos:
        @contextmanager
        def group(self, label: str):
            nonlocal entered_label
            entered_label = label
            yield

    fake_hou = SimpleNamespace(undos=FakeUndos())
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    from houdini_asset_relinker.hou_access import undo_group

    with undo_group("Test Undo Group"):
        pass

    assert entered_label == "Test Undo Group"
