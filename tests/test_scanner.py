"""Tests for Houdini reference scanning."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from houdini_asset_relinker.models import ReferenceKind
from houdini_asset_relinker.scanner import scan_assets, scan_file_references


class FakeNode:
    """Minimal stand-in for a Houdini node."""

    def __init__(self, path: str) -> None:
        self._path = path

    def path(self) -> str:
        """Return the fake node path."""
        return self._path


class FakeParm:
    """Minimal stand-in for a Houdini parameter."""

    def __init__(self, path: str, raw_value: str, locked: bool = False) -> None:
        self._path = path
        self._raw_value = raw_value
        self._locked = locked

    def unexpandedString(self) -> str:
        """Return the raw parameter value."""
        return self._raw_value

    def path(self) -> str:
        """Return the fake parameter path."""
        return self._path

    def node(self) -> FakeNode:
        """Return the owning fake node."""
        return FakeNode("/obj/geo1")

    def isLocked(self) -> bool:
        """Return whether the fake parameter is locked."""
        return self._locked


def test_scan_file_references_expands_and_reports_writable_parms(
    monkeypatch, tmp_path: Path
) -> None:
    """It scans Houdini file references into serializable reference records."""
    texture_path = tmp_path / "texture.exr"
    texture_path.write_text("test")
    parm = FakeParm("/obj/geo1/file1/file", "$HIP/texture.exr")

    fake_hou = SimpleNamespace(
        fileReferences=lambda project_var, include_all: [(parm, "$HIP/texture.exr")],
        expandString=lambda value: value.replace("$HIP", str(tmp_path)),
    )
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    references = scan_file_references()

    assert len(references) == 1
    reference = references[0]
    assert reference.kind == ReferenceKind.FILE_PARAMETER
    assert reference.raw_path == "$HIP/texture.exr"
    assert Path(reference.expanded_path) == texture_path
    assert reference.exists
    assert reference.can_update
    assert reference.parm_path == "/obj/geo1/file1/file"
    assert reference.node_path == "/obj/geo1"


def test_scan_file_references_marks_locked_parms_as_not_updatable(
    monkeypatch, tmp_path: Path
) -> None:
    """It records locked Houdini parameters without treating them as writable."""
    parm = FakeParm("/obj/geo1/file1/file", "$HIP/missing.bgeo.sc", locked=True)
    fake_hou = SimpleNamespace(
        fileReferences=lambda project_var, include_all: [(parm, "$HIP/missing.bgeo.sc")],
        expandString=lambda value: value.replace("$HIP", str(tmp_path)),
    )
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    references = scan_file_references()

    assert not references[0].can_update
    assert references[0].reason == "Parameter is locked"


def test_scan_assets_can_include_hda_libraries(monkeypatch, tmp_path: Path) -> None:
    """It appends HDA library references that are not already known."""
    parm = FakeParm("/obj/geo1/file1/file", "$HIP/asset.hda")
    hda_path = tmp_path / "asset.hda"
    hda_path.write_text("test")
    extra_hda_path = tmp_path / "extra.hda"
    extra_hda_path.write_text("test")

    fake_hou = SimpleNamespace(
        fileReferences=lambda project_var, include_all: [(parm, "$HIP/asset.hda")],
        expandString=lambda value: value.replace("$HIP", str(tmp_path)),
        hda=SimpleNamespace(loadedFiles=lambda: [str(hda_path), str(extra_hda_path)]),
    )
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    references = scan_assets(include_hda_libraries=True)

    assert [Path(reference.expanded_path) for reference in references] == [hda_path, extra_hda_path]
