"""Helpers for Houdini-specific UI integration."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from houdini_asset_relinker.hou_access import get_hou
from houdini_asset_relinker.qt import QtWidgets


def houdini_parent() -> Optional[QtWidgets.QWidget]:
    """Return Houdini's main Qt window when available."""
    try:
        hou = get_hou()
        return hou.qt.mainWindow()
    except Exception:
        return None


def default_export_path() -> str:
    """Return the preferred CSV export path for the current session."""
    try:
        hou = get_hou()
        expanded = hou.expandString("$HIP/asset_relinker_report.csv")
        if expanded:
            return expanded
    except Exception:
        pass
    return str(Path.cwd() / "asset_relinker_report.csv")


def network_editor_for_current_desktop(hou: object) -> Optional[object]:
    """Return a network editor pane for the current Houdini desktop."""
    hou_ui = getattr(hou, "ui", None)
    current_desktop = getattr(hou_ui, "curDesktop", None)
    if current_desktop is None:
        return None
    desktop = current_desktop()
    if desktop is None:
        return None

    pane_tab_type = getattr(hou, "paneTabType", None)
    network_editor_type = getattr(pane_tab_type, "NetworkEditor", None)
    pane_tab_of_type = getattr(desktop, "paneTabOfType", None)
    if pane_tab_of_type is not None and network_editor_type is not None:
        network_editor = pane_tab_of_type(network_editor_type)
        if network_editor is not None:
            return network_editor

    pane_tabs = getattr(desktop, "paneTabs", None)
    if pane_tabs is None:
        return None
    for pane_tab in pane_tabs():
        pane_type = getattr(pane_tab, "type", None)
        if network_editor_type is not None and pane_type is not None:
            if pane_type() != network_editor_type:
                continue
        if getattr(pane_tab, "setPwd", None) is not None:
            return pane_tab
    return None


def jump_network_editor_to_node(network_editor: object, node: object) -> None:
    """Point a network editor at a Houdini node's parent context."""
    parent_node = None
    parent = getattr(node, "parent", None)
    if parent is not None:
        parent_node = parent()

    set_pwd = getattr(network_editor, "setPwd", None)
    if set_pwd is not None:
        set_pwd(parent_node or node)

    set_current_node = getattr(network_editor, "setCurrentNode", None)
    if set_current_node is not None:
        set_current_node(node)


def frame_network_editor_selection(network_editor: object) -> None:
    """Frame the selected node in a Houdini network editor when supported."""
    for method_name in ("homeToSelection", "frameSelection"):
        frame_selection = getattr(network_editor, method_name, None)
        if frame_selection is not None:
            frame_selection()
            return
