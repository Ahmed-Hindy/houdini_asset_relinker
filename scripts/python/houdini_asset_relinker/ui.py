"""Minimal Houdini UI entry points using `hou.ui` dialogs."""

from __future__ import annotations

from houdini_asset_relinker.export import write_references_csv
from houdini_asset_relinker.hou_access import get_hou
from houdini_asset_relinker.scanner import scan_assets
from houdini_asset_relinker.updater import replace_path_text


def open_dialog() -> None:
    """Open a compact scan/replace dialog inside Houdini."""
    hou = get_hou()
    choice = hou.ui.displayMessage(
        "Asset Relinker\n\nChoose an action.",
        buttons=("Scan", "Find/Replace", "Cancel"),
        default_choice=0,
        close_choice=2,
        title="Asset Relinker",
    )
    if choice == 0:
        show_scan_report()
    elif choice == 1:
        show_replace_dialog()


def show_scan_report() -> None:
    """Show a report of current asset references."""
    hou = get_hou()
    references = scan_assets(include_hda_libraries=False)
    missing_count = sum(not reference.exists for reference in references)
    updatable_count = sum(reference.can_update for reference in references)
    lines = [
        f"References found: {len(references)}",
        f"Missing on disk: {missing_count}",
        f"Directly updatable: {updatable_count}",
        "",
    ]
    for index, reference in enumerate(references[:80], start=1):
        exists_label = "OK" if reference.exists else "MISSING"
        location = reference.parm_path or reference.node_path or "<session/reference>"
        lines.append(f"{index:03d}. [{exists_label}] {location}")
        lines.append(f"     {reference.raw_path}")
    if len(references) > 80:
        lines.append(f"... {len(references) - 80} more rows omitted")
    message = "\n".join(lines)
    choice = hou.ui.displayMessage(
        message,
        buttons=("Export CSV", "Close"),
        default_choice=1,
        close_choice=1,
        title="Asset Relinker Scan",
    )
    if choice == 0:
        _export_scan_csv(references)


def show_replace_dialog() -> None:
    """Ask for find/replace text and apply after a dry-run preview."""
    hou = get_hou()
    button, values = hou.ui.readMultiInput(
        "Replace text inside raw Houdini asset paths.",
        ("Find", "Replace with"),
        buttons=("Preview", "Cancel"),
        default_choice=0,
        close_choice=1,
        title="Asset Relinker Replace",
    )
    if button != 0:
        return
    find_text, replace_with = values
    if not find_text:
        hou.ui.displayMessage("Find text cannot be empty.", severity=hou.severityType.Warning)
        return
    dry_report = replace_path_text(find_text, replace_with, dry_run=True)
    if not dry_report.results:
        hou.ui.displayMessage("No matching writable file parameter paths were found.")
        return
    apply_choice = hou.ui.displayMessage(
        dry_report.to_text(),
        buttons=("Apply", "Cancel"),
        default_choice=1,
        close_choice=1,
        title="Asset Relinker Preview",
    )
    if apply_choice != 0:
        return
    report = replace_path_text(find_text, replace_with, dry_run=False)
    hou.ui.displayMessage(report.to_text(), title="Asset Relinker Applied")


def _export_scan_csv(references: object) -> None:
    """Prompt for a CSV path and write scan results."""
    hou = get_hou()
    selected_path = hou.ui.selectFile(
        title="Export Asset Relinker CSV",
        file_type=hou.fileType.Any,
        pattern="*.csv",
        default_value="$HIP/asset_relinker_report.csv",
    )
    if not selected_path:
        return
    expanded_path = hou.expandString(selected_path)
    written_path = write_references_csv(references, expanded_path)
    hou.ui.displayMessage(f"Wrote:\n{written_path}", title="Asset Relinker Export")
