"""Houdini Asset Relinker package."""

from importlib import metadata

from houdini_asset_relinker.models import AssetReference, ReferenceKind, UpdateReport, UpdateResult
from houdini_asset_relinker.scanner import scan_assets, scan_file_references, scan_hda_libraries
from houdini_asset_relinker.updater import (
    replace_hda_library_paths,
    replace_path_root,
    replace_path_text,
)

try:
    __version__ = f"v{metadata.version('houdini-asset-relinker')}"
except metadata.PackageNotFoundError:
    __version__ = "dev-mode"

__all__ = [
    "__version__",
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
