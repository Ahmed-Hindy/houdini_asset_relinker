"""Tests for Houdini reference scanning."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from houdini_asset_relinker.models import ReferenceKind
from houdini_asset_relinker.path_utils import path_family
from houdini_asset_relinker.scanner import scan_assets, scan_file_references


class FakeNode:
    """Minimal stand-in for a Houdini node."""

    def __init__(self, path: str, type_name: str = "filecache") -> None:
        self._path = path
        self._type_name = type_name

    def path(self) -> str:
        """Return the fake node path."""
        return self._path

    def type(self):
        """Return a fake Houdini node type."""
        return SimpleNamespace(name=lambda: self._type_name)


class FakeParm:
    """Minimal stand-in for a Houdini parameter."""

    def __init__(
        self,
        path: str,
        raw_value: str,
        locked: bool = False,
        label: str = "Geometry File",
        node_type: str = "filecache",
    ) -> None:
        self._path = path
        self._raw_value = raw_value
        self._locked = locked
        self._label = label
        self._node_type = node_type

    def unexpandedString(self) -> str:
        """Return the raw parameter value."""
        return self._raw_value

    def path(self) -> str:
        """Return the fake parameter path."""
        return self._path

    def name(self) -> str:
        """Return the fake parameter name."""
        return self._path.rsplit("/", 1)[-1]

    def description(self) -> str:
        """Return the fake parameter label."""
        return self._label

    def node(self) -> FakeNode:
        """Return the owning fake node."""
        return FakeNode("/obj/geo1", self._node_type)

    def isLocked(self) -> bool:
        """Return whether the fake parameter is locked."""
        return self._locked


class FakeRootNode:
    """Minimal stand-in for the Houdini root node."""

    def __init__(self, references, children=()) -> None:
        self._references = references
        self._children = children
        self.recurse_in_locked_nodes = None

    def fileReferences(
        self,
        recurse: bool = False,
        project_dir_variable: str = "HIP",
        include_all_refs: bool = True,
    ):
        """Return fake file references from this node only."""
        del recurse, project_dir_variable, include_all_refs
        return self._references

    def allSubChildren(self, recurse_in_locked_nodes: bool = False):
        """Return fake child nodes and record locked-node traversal."""
        self.recurse_in_locked_nodes = recurse_in_locked_nodes
        return self._children


def test_scan_file_references_expands_and_reports_writable_parms(
    monkeypatch, tmp_path: Path
) -> None:
    """It scans Houdini file references into serializable reference records."""
    texture_path = tmp_path / "texture.exr"
    texture_path.write_text("test")
    parm = FakeParm("/obj/geo1/file1/file", "$HIP/texture.exr")

    root = FakeRootNode([(parm, "$HIP/texture.exr")])
    fake_hou = SimpleNamespace(
        node=lambda path: root if path == "/" else None,
        expandString=lambda value: value.replace("$HIP", str(tmp_path)),
        getenv=lambda name: str(tmp_path) if name == "HIP" else None,
    )
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    references = scan_file_references()

    assert len(references) == 1
    reference = references[0]
    assert reference.kind == ReferenceKind.FILE_PARAMETER
    assert reference.raw_path == "$HIP/texture.exr"
    assert Path(reference.expanded_path) == texture_path
    assert reference.exists
    assert reference.path_family == path_family(str(texture_path))
    assert reference.can_update
    assert reference.parm_path == "/obj/geo1/file1/file"
    assert reference.parm_name == "file"
    assert reference.parm_label == "Geometry File"
    assert reference.node_path == "/obj/geo1"
    assert reference.node_type == "filecache"
    assert reference.missing_variables == ()


def test_scan_file_references_marks_locked_parms_as_not_updatable(
    monkeypatch, tmp_path: Path
) -> None:
    """It records locked Houdini parameters without treating them as writable."""
    parm = FakeParm("/obj/geo1/file1/file", "$HIP/missing.bgeo.sc", locked=True)
    root = FakeRootNode([(parm, "$HIP/missing.bgeo.sc")])
    fake_hou = SimpleNamespace(
        node=lambda path: root if path == "/" else None,
        expandString=lambda value: value.replace("$HIP", str(tmp_path)),
        getenv=lambda name: str(tmp_path) if name == "HIP" else None,
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

    root = FakeRootNode([(parm, "$HIP/asset.hda")])
    fake_hou = SimpleNamespace(
        node=lambda path: root if path == "/" else None,
        expandString=lambda value: value.replace("$HIP", str(tmp_path)),
        hda=SimpleNamespace(loadedFiles=lambda: [str(hda_path), str(extra_hda_path)]),
        getenv=lambda _name: None,
    )
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    references = scan_assets(include_hda_libraries=True)

    assert [Path(reference.expanded_path) for reference in references] == [hda_path, extra_hda_path]


def test_scan_file_references_can_recurse_into_locked_nodes(monkeypatch, tmp_path: Path) -> None:
    """It passes the locked-node traversal option to Houdini child discovery."""
    root_parm = FakeParm("/obj/geo1/file1/file", "$HIP/root.exr")
    child_parm = FakeParm("/obj/locked/file1/file", "$HIP/locked.exr")
    child = FakeRootNode([(child_parm, "$HIP/locked.exr")])
    root = FakeRootNode([(root_parm, "$HIP/root.exr")], children=(child,))
    fake_hou = SimpleNamespace(
        node=lambda path: root if path == "/" else None,
        expandString=lambda value: value.replace("$HIP", str(tmp_path)),
        getenv=lambda name: str(tmp_path) if name == "HIP" else None,
    )
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    references = scan_file_references(recurse_in_locked_nodes=True)

    assert root.recurse_in_locked_nodes is True
    assert [reference.raw_path for reference in references] == [
        "$HIP/root.exr",
        "$HIP/locked.exr",
    ]


def test_scan_file_references_reports_missing_raw_path_variables(
    monkeypatch, tmp_path: Path
) -> None:
    """It reports unresolved Houdini variables without treating frame tokens as variables."""
    parm = FakeParm("/obj/geo1/file1/file", "$MISSING/cache/sim.$F4.bgeo.sc")
    root = FakeRootNode([(parm, "$MISSING/cache/sim.$F4.bgeo.sc")])
    fake_hou = SimpleNamespace(
        node=lambda path: root if path == "/" else None,
        expandString=lambda value: value.replace("$HIP", str(tmp_path)),
        getenv=lambda name: str(tmp_path) if name == "HIP" else None,
    )
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    references = scan_file_references()

    assert references[0].missing_variables == ("MISSING",)
