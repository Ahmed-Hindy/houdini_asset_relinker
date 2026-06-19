"""Scan Houdini scenes for external asset references."""

from __future__ import annotations

from typing import Optional

from houdini_asset_relinker.hou_access import get_hou
from houdini_asset_relinker.models import AssetReference, ReferenceKind
from houdini_asset_relinker.path_utils import (
    build_sequence_pattern,
    missing_variables,
    normalize_for_compare,
    path_exists,
    path_family,
)

_IGNORED_FILE_REFERENCE_PARMS = {"descriptivelabel", "licensefile"}
_OUTPUT_FILE_REFERENCE_PARMS = {  # Common output file parameters. Shouldn't be checked if missing .
    "vm_picture",
    "ar_picture",
    "ar_ass_file",
    "lopoutput",
    "sopoutput",
    "picture",
    "productname",
    "output",
    "soho_diskfile",
    "vm_tmpsharedstorage",
    "vm_tmplocalstorage",
    "exportpath",
    "savetodirectory",
    "ropoutput",
    "copoutput",
    "filename",
}


def scan_assets(
    project_dir_variable: str = "HIP",
    include_all_refs: bool = True,
    include_hda_libraries: bool = True,
    recurse_in_locked_nodes: bool = False,
) -> list[AssetReference]:
    """Scan the current Houdini session for external asset references.

    Args:
        project_dir_variable: Houdini variable name used by `hou.fileReferences` to shorten paths.
        include_all_refs: Whether Houdini should include all refs or only selected refs.
        include_hda_libraries: Whether to also include `hou.hda.loadedFiles()` results.
        recurse_in_locked_nodes: Whether to inspect child nodes inside locked assets.

    Returns:
        A list of asset reference records.
    """
    references = scan_file_references(
        project_dir_variable,
        include_all_refs,
        recurse_in_locked_nodes=recurse_in_locked_nodes,
    )
    if include_hda_libraries:
        known_paths = {normalize_for_compare(reference.expanded_path) for reference in references}
        references.extend(
            reference
            for reference in scan_hda_libraries()
            if normalize_for_compare(reference.expanded_path) not in known_paths
        )
    return references


def scan_file_references(
    project_dir_variable: str = "HIP",
    include_all_refs: bool = True,
    recurse_in_locked_nodes: bool = False,
) -> list[AssetReference]:
    """Scan file parameters using `hou.fileReferences()`.

    Args:
        project_dir_variable: Houdini variable name used to shorten matching paths.
        include_all_refs: Passed through to `hou.fileReferences()`.
        recurse_in_locked_nodes: Whether to inspect child nodes inside locked assets.

    Returns:
        A list of file parameter references.
    """
    hou = get_hou()
    references = []
    root = hou.node("/")
    if root is None:
        return references
    nodes = (root, *root.allSubChildren(recurse_in_locked_nodes=recurse_in_locked_nodes))
    for node in nodes:
        for parm, path_value in node.fileReferences(
            recurse=False,
            project_dir_variable=project_dir_variable,
            include_all_refs=include_all_refs,
        ):
            if not _should_include_file_reference_parm(parm):
                continue
            references.append(_reference_from_parm(parm, path_value))
    return references


def _reference_from_parm(parm: object, path_value: str) -> AssetReference:
    """Build an asset reference from a Houdini parameter and path."""
    raw_path = _raw_path_from_parm(parm, path_value)
    expanded_path, missing_variable_names, sequence_path_pattern, exists = _analyze_path(raw_path)
    parm_path = _safe_parm_path(parm)
    node_path = _safe_node_path(parm)
    node_type = _safe_node_type(parm)
    parm_name = _safe_parm_name(parm, parm_path)
    parm_label = _safe_parm_label(parm)
    can_update, reason = _can_update_parm(parm)
    return AssetReference(
        kind=ReferenceKind.FILE_PARAMETER,
        raw_path=raw_path,
        expanded_path=expanded_path,
        exists=exists,
        sequence_pattern=sequence_path_pattern,
        path_family=path_family(raw_path),
        parm_path=parm_path,
        parm_name=parm_name,
        parm_label=parm_label,
        node_path=node_path,
        node_type=node_type,
        missing_variables=missing_variable_names,
        can_update=can_update,
        reason=reason,
    )


def scan_hda_libraries() -> list[AssetReference]:
    """Scan loaded HDA/OTL library files using `hou.hda.loadedFiles()`.

    Returns:
        A list of HDA library references.
    """
    hou = get_hou()
    references = []
    for raw_path in hou.hda.loadedFiles():
        expanded_path, missing_variable_names, sequence_path_pattern, exists = _analyze_path(
            raw_path
        )
        can_update = raw_path != "Embedded"
        reason = (
            "Embedded asset definition" if raw_path == "Embedded" else "Use HDA replacement API"
        )
        references.append(
            AssetReference(
                kind=ReferenceKind.HDA_LIBRARY,
                raw_path=raw_path,
                expanded_path=expanded_path,
                exists=exists if raw_path != "Embedded" else True,
                sequence_pattern=sequence_path_pattern,
                path_family=path_family(raw_path) if raw_path != "Embedded" else "Embedded",
                path_role="hda_library",
                missing_variables=missing_variable_names if raw_path != "Embedded" else (),
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


def _analyze_path(raw_path: str) -> tuple[str, tuple[str, ...], str, bool]:
    """Return expanded path details used by scanner rows."""
    missing_variable_names = _missing_variables(raw_path)
    expanded_path = _expand_string(raw_path)
    sequence_path_pattern = build_sequence_pattern(raw_path, _expand_string)
    exists = False
    if not missing_variable_names:
        exists = path_exists(expanded_path, sequence_path_pattern)
    return expanded_path, missing_variable_names, sequence_path_pattern, exists


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


def _safe_node_type(parm: Optional[object]) -> str:
    """Return the owning node type name when available."""
    if parm is None:
        return ""
    try:
        return str(parm.node().type().name())
    except Exception:
        return ""


def _safe_parm_name(parm: Optional[object], parm_path: Optional[str]) -> str:
    """Return the parameter token name when available."""
    if parm is not None:
        try:
            return str(parm.name())
        except Exception:
            pass
    if parm_path:
        return parm_path.rsplit("/", 1)[-1]
    return ""


def _safe_parm_label(parm: Optional[object]) -> str:
    """Return the parameter label when available."""
    if parm is None:
        return ""
    try:
        return str(parm.description())
    except Exception:
        return ""


def _should_include_file_reference_parm(parm: Optional[object]) -> bool:
    """Return whether a Houdini file reference parm should be relinkable."""
    if parm is None:
        return False

    parm_name = _safe_parm_name(parm, _safe_parm_path(parm)).casefold()
    if parm_name in _IGNORED_FILE_REFERENCE_PARMS:
        return False

    if not _is_file_reference_string_parm(parm):
        return False

    if _is_default_parm(parm):
        return False

    if _is_indirect_or_expression_parm(parm):
        return False

    return True


def _is_file_reference_string_parm(parm: object) -> bool:
    """Return whether the parameter template is a file-reference string parm."""
    try:
        parm_template = parm.parmTemplate()
    except Exception:
        return True

    try:
        string_type = parm_template.stringType()
    except AttributeError:
        return False
    except Exception:
        return True

    return str(string_type).replace("_", "").casefold().endswith("filereference")


def _is_default_parm(parm: object) -> bool:
    """Return whether the parameter still has its untouched default value."""
    try:
        return bool(parm.isAtDefault())
    except Exception:
        return False


def _is_indirect_or_expression_parm(parm: object) -> bool:
    """Return whether a parm stores an expression or references another parm."""
    parm_path = _safe_parm_path(parm)
    try:
        referenced_parm = parm.getReferencedParm()
        referenced_path = _safe_parm_path(referenced_parm)
    except Exception:
        referenced_path = None
    if parm_path and referenced_path and referenced_path != parm_path:
        return True

    try:
        expression = parm.expression()
    except Exception:
        return False
    return bool(str(expression).strip())


def _missing_variables(raw_path: str) -> tuple[str, ...]:
    """Return unresolved variables in a raw Houdini path."""
    hou = get_hou()
    return missing_variables(raw_path, getattr(hou, "getenv", None))


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
