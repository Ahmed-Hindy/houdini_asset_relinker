"""Houdini Asset Relinker package."""

from houdini_asset_relinker.models import AssetReference, ReferenceKind, UpdateReport, UpdateResult
from houdini_asset_relinker.scanner import scan_assets, scan_file_references, scan_hda_libraries
from houdini_asset_relinker.updater import (
    replace_hda_library_paths,
    replace_path_root,
    replace_path_text,
)

__all__ = [
    "AssetReference",
    "ReferenceKind",
    "UpdateReport",
    "UpdateResult",
    "replace_hda_library_paths",
    "replace_path_root",
    "replace_path_text",
    "scan_assets",
    "scan_file_references",
    "scan_hda_libraries",
]
