"""Update Houdini asset paths discovered by the scanner."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Optional

from houdini_asset_relinker.hou_access import get_hou
from houdini_asset_relinker.models import (
    AssetReference,
    ReferenceKind,
    UpdateReport,
    UpdateResult,
    is_generated_output,
)
from houdini_asset_relinker.path_utils import replace_root, replace_text
from houdini_asset_relinker.scanner import scan_assets, scan_hda_libraries


def replace_path_text(
    find_text: str,
    replace_with: str,
    dry_run: bool = True,
    references: Optional[Iterable[AssetReference]] = None,
    case_sensitive: bool = False,
) -> UpdateReport:
    """Replace text in all writable file parameter paths.

    Args:
        find_text: Text to find in the raw Houdini path string.
        replace_with: Replacement text.
        dry_run: When True, report what would change without modifying the scene.
        references: Optional pre-scanned references. When omitted, the current scene is scanned.
        case_sensitive: Whether matching should require exact letter case. By default,
            matching ignores casing differences common in Windows paths.

    Returns:
        An update report.
    """
    from contextlib import nullcontext

    from houdini_asset_relinker.hou_access import undo_group

    current_references = (
        list(references) if references is not None else scan_assets(include_hda_libraries=False)
    )
    results = []
    context = nullcontext() if dry_run else undo_group("Replace Path Text")
    with context:
        for reference in current_references:
            if reference.kind != ReferenceKind.FILE_PARAMETER:
                continue
            if is_generated_output(reference):
                continue
            new_path = replace_text(reference.raw_path, find_text, replace_with, case_sensitive)
            if new_path is None:
                continue
            results.append(_set_reference_path(reference, new_path, dry_run))
    return UpdateReport(dry_run=dry_run, results=tuple(results))


def replace_path_root(
    old_root: str,
    new_root: str,
    dry_run: bool = True,
    references: Optional[Iterable[AssetReference]] = None,
) -> UpdateReport:
    """Replace a root path in all writable file parameter paths.

    Args:
        old_root: Existing root path to replace.
        new_root: Replacement root path.
        dry_run: When True, report what would change without modifying the scene.
        references: Optional pre-scanned references. When omitted, the current scene is scanned.

    Returns:
        An update report.
    """
    from contextlib import nullcontext

    from houdini_asset_relinker.hou_access import undo_group

    current_references = (
        list(references) if references is not None else scan_assets(include_hda_libraries=False)
    )
    results = []
    context = nullcontext() if dry_run else undo_group("Replace Path Root")
    with context:
        for reference in current_references:
            if reference.kind != ReferenceKind.FILE_PARAMETER:
                continue
            if is_generated_output(reference):
                continue
            new_path = replace_root(reference.raw_path, old_root, new_root)
            if new_path is None:
                continue
            results.append(_set_reference_path(reference, new_path, dry_run))
    return UpdateReport(dry_run=dry_run, results=tuple(results))


def replace_hda_library_paths(
    find_text: str,
    replace_with: str,
    dry_run: bool = True,
    uninstall_old: bool = False,
    references: Optional[Iterable[AssetReference]] = None,
    case_sensitive: bool = False,
) -> UpdateReport:
    """Replace loaded HDA library file paths in the current Houdini session.

    Args:
        find_text: Text to find in the loaded HDA library path.
        replace_with: Replacement text.
        dry_run: When True, report what would change without modifying the session.
        uninstall_old: When applying, uninstall old libraries after installing replacements.
        references: Optional pre-scanned references. When omitted, loaded HDA libraries are scanned.
        case_sensitive: Whether matching should require exact letter case. By default,
            matching ignores casing differences common in Windows paths.

    Returns:
        An update report.
    """
    from contextlib import nullcontext

    from houdini_asset_relinker.hou_access import undo_group

    hou = None if dry_run else get_hou()
    results = []
    current_references = list(references) if references is not None else scan_hda_libraries()
    context = nullcontext() if dry_run else undo_group("Replace HDA Library Paths")
    with context:
        for reference in current_references:
            if reference.kind != ReferenceKind.HDA_LIBRARY:
                continue
            new_path = replace_text(reference.raw_path, find_text, replace_with, case_sensitive)
            if new_path is None:
                continue
            if reference.raw_path == "Embedded":
                results.append(
                    UpdateResult(
                        status="skipped",
                        old_path=reference.raw_path,
                        new_path=new_path,
                        message="Embedded HDA definitions cannot be relinked to a file path.",
                    )
                )
                continue
            if dry_run:
                results.append(
                    UpdateResult(
                        status="would_change", old_path=reference.raw_path, new_path=new_path
                    )
                )
                continue
            try:
                if hou is None:
                    message = "Houdini module was not available for applying HDA library changes."
                    raise RuntimeError(message)
                hou.hda.installFile(new_path)
                if uninstall_old:
                    hou.hda.uninstallFile(reference.raw_path)
                results.append(
                    UpdateResult(status="changed", old_path=reference.raw_path, new_path=new_path)
                )
            except Exception as error:
                results.append(
                    UpdateResult(
                        status="failed",
                        old_path=reference.raw_path,
                        new_path=new_path,
                        message=str(error),
                    )
                )
    return UpdateReport(dry_run=dry_run, results=tuple(results))


def _set_reference_path(reference: AssetReference, new_path: str, dry_run: bool) -> UpdateResult:
    """Set a single Houdini parameter path or return the dry-run result."""
    if not reference.can_update or not reference.parm_path:
        return UpdateResult(
            status="skipped",
            old_path=reference.raw_path,
            new_path=new_path,
            parm_path=reference.parm_path,
            message=reference.reason or "Reference is not writable.",
        )
    if dry_run:
        return UpdateResult(
            status="would_change",
            old_path=reference.raw_path,
            new_path=new_path,
            parm_path=reference.parm_path,
        )
    hou = get_hou()
    parm = hou.parm(reference.parm_path)
    if parm is None:
        return UpdateResult(
            status="failed",
            old_path=reference.raw_path,
            new_path=new_path,
            parm_path=reference.parm_path,
            message="Parameter no longer exists.",
        )
    try:
        parm.set(new_path, follow_parm_reference=False)
    except TypeError:
        try:
            parm.set(new_path)
        except Exception as error:
            return _failed_result(reference, new_path, error)
    except Exception as error:
        return _failed_result(reference, new_path, error)
    return UpdateResult(
        status="changed",
        old_path=reference.raw_path,
        new_path=new_path,
        parm_path=reference.parm_path,
    )


def _failed_result(reference: AssetReference, new_path: str, error: Exception) -> UpdateResult:
    """Build a failed update result."""
    return UpdateResult(
        status="failed",
        old_path=reference.raw_path,
        new_path=new_path,
        parm_path=reference.parm_path,
        message=str(error),
    )
