"""Scan Houdini scenes for external asset references."""

from __future__ import annotations

from typing import Optional

from houdini_asset_relinker.hou_access import get_hou
from houdini_asset_relinker.models import AssetReference, ReferenceKind
from houdini_asset_relinker.path_utils import path_exists


def scan_assets(
    project_dir_variable: str = "HIP",
    include_all_refs: bool = True,
    include_hda_libraries: bool = True,
) -> list[AssetReference]:
    """Scan the current Houdini session for external asset references.

    Args:
        project_dir_variable: Houdini variable name used by `hou.fileReferences` to shorten paths.
        include_all_refs: Whether Houdini should include all refs or only selected refs.
        include_hda_libraries: Whether to also include `hou.hda.loadedFiles()` results.

    Returns:
        A list of asset reference records.
    """
    references = scan_file_references(project_dir_variable, include_all_refs)
    if include_hda_libraries:
        known_paths = {reference.expanded_path for reference in references}
        references.extend(
            reference
            for reference in scan_hda_libraries()
            if reference.expanded_path not in known_paths
        )
    return references


def scan_file_references(
    project_dir_variable: str = "HIP", include_all_refs: bool = True
) -> list[AssetReference]:
    """Scan file parameters using `hou.fileReferences()`.

    Args:
        project_dir_variable: Houdini variable name used to shorten matching paths.
        include_all_refs: Passed through to `hou.fileReferences()`.

    Returns:
        A list of file parameter references.
    """
    hou = get_hou()
    references = []
    for parm, path_value in hou.fileReferences(project_dir_variable, include_all_refs):
        raw_path = _raw_path_from_parm(parm, path_value)
        expanded_path = _expand_string(raw_path)
        parm_path = _safe_parm_path(parm)
        node_path = _safe_node_path(parm)
        can_update, reason = _can_update_parm(parm)
        references.append(
            AssetReference(
                kind=ReferenceKind.FILE_PARAMETER,
                raw_path=raw_path,
                expanded_path=expanded_path,
                exists=path_exists(expanded_path),
                parm_path=parm_path,
                node_path=node_path,
                can_update=can_update,
                reason=reason,
            )
        )
    return references


def scan_hda_libraries() -> list[AssetReference]:
    """Scan loaded HDA/OTL library files using `hou.hda.loadedFiles()`.

    Returns:
        A list of HDA library references.
    """
    hou = get_hou()
    references = []
    for raw_path in hou.hda.loadedFiles():
        expanded_path = _expand_string(raw_path)
        can_update = raw_path != "Embedded"
        reason = (
            "Embedded asset definition" if raw_path == "Embedded" else "Use HDA replacement API"
        )
        references.append(
            AssetReference(
                kind=ReferenceKind.HDA_LIBRARY,
                raw_path=raw_path,
                expanded_path=expanded_path,
                exists=path_exists(expanded_path) if raw_path != "Embedded" else True,
                can_update=can_update,
                reason=reason,
            )
        )
    return references


def _raw_path_from_parm(parm: object, fallback_path: str) -> str:
    """Return the raw string from a Houdini parm when possible."""
    if parm is None:
        return fallback_path
    try:
        return parm.unexpandedString()
    except Exception:
        return fallback_path


def _expand_string(path_value: str) -> str:
    """Expand Houdini variables and backtick expressions when possible."""
    hou = get_hou()
    try:
        return hou.expandString(path_value)
    except Exception:
        return path_value


def _safe_parm_path(parm: Optional[object]) -> Optional[str]:
    """Return the full parameter path when available."""
    if parm is None:
        return None
    try:
        return parm.path()
    except Exception:
        return None


def _safe_node_path(parm: Optional[object]) -> Optional[str]:
    """Return the owning node path when available."""
    if parm is None:
        return None
    try:
        return parm.node().path()
    except Exception:
        return None


def _can_update_parm(parm: Optional[object]) -> tuple[bool, str]:
    """Return whether a Houdini parm looks directly writable."""
    if parm is None:
        return False, "Reference is not stored on a parameter"
    try:
        if hasattr(parm, "isLocked") and parm.isLocked():
            return False, "Parameter is locked"
    except Exception:
        return False, "Could not query parameter lock state"
    return True, ""
