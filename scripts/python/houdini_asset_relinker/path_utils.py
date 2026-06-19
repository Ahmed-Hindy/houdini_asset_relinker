"""Path utility helpers for Houdini asset relinking."""

from __future__ import annotations

import os
import re
from glob import glob
from pathlib import Path
from typing import Optional

_FRAME_TOKEN_PATTERN = re.compile(r"(\$F\d*|%0?\d*d|#+|<UDIM>|<UVTILE>)", re.IGNORECASE)
_WINDOWS_DRIVE_PATTERN = re.compile(r"^([A-Za-z]:)(?:/(.*))?$")
_URI_SCHEME_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")

PATH_FAMILY_DEPTH = 3


def contains_sequence_token(path_value: str) -> bool:
    """Return whether a path string appears to contain a frame or tile token."""
    return bool(_FRAME_TOKEN_PATTERN.search(path_value))


def normalize_for_compare(path_value: str) -> str:
    """Normalize a path for prefix/equality comparisons without changing stored values."""
    normalized = path_value.replace("\\", "/")
    normalized = re.sub(r"/+", "/", normalized)
    return os.path.normcase(normalized.rstrip("/")).replace("\\", "/")


def path_exists(expanded_path: str) -> bool:
    """Return whether an expanded path exists.

    Sequence and UDIM tokens are treated as a glob-like check where possible.
    """
    if not expanded_path:
        return False
    if contains_sequence_token(expanded_path):
        glob_pattern = _FRAME_TOKEN_PATTERN.sub("*", expanded_path)
        return bool(glob(glob_pattern))
    return Path(expanded_path).exists()


def path_family(expanded_path: str, depth: int = PATH_FAMILY_DEPTH) -> str:
    """Return a stable root/path-family label for grouping scanned paths.

    Args:
        expanded_path: Path after Houdini expansion.
        depth: Number of path segments to keep after a Windows drive or UNC share.

    Returns:
        A compact path-family label suitable for table grouping and CSV reports.
    """
    path_value = expanded_path.strip().replace("\\", "/")
    if not path_value:
        return ""

    if path_value.startswith("//"):
        return _unc_path_family(path_value, depth)

    drive_match = _WINDOWS_DRIVE_PATTERN.match(path_value)
    if drive_match:
        drive = drive_match.group(1)
        tail = drive_match.group(2) or ""
        parts = _path_parts(tail)
        if not parts:
            return drive
        return "/".join([drive, *_family_parts(parts, depth)])

    uri_match = _URI_SCHEME_PATTERN.match(path_value)
    if uri_match:
        return f"{uri_match.group(1)}:"

    if path_value.startswith("/"):
        parts = _path_parts(path_value)
        if not parts:
            return "/"
        return "/" + "/".join(_family_parts(parts, depth))

    parts = _path_parts(path_value)
    if len(parts) > 1:
        return parts[0]
    return "<bare>"


def replace_text(
    path_value: str, find_text: str, replace_with: str, case_sensitive: bool = True
) -> Optional[str]:
    """Replace text in a path and return None when there is no match."""
    if not find_text:
        return None
    if case_sensitive:
        if find_text not in path_value:
            return None
        return path_value.replace(find_text, replace_with)
    pattern = re.compile(re.escape(find_text), re.IGNORECASE)
    if not pattern.search(path_value):
        return None
    return pattern.sub(lambda _match: replace_with, path_value)


def _unc_path_family(path_value: str, depth: int) -> str:
    """Return a UNC path family preserving the server and share."""
    parts = _path_parts(path_value)
    if len(parts) < 2:
        return path_value.rstrip("/")
    share_parts = parts[:2]
    tail_parts = _family_parts(parts[2:], depth)
    return "//" + "/".join([*share_parts, *tail_parts])


def _family_parts(parts: list[str], depth: int) -> list[str]:
    """Return leading path parts, avoiding an obvious filename for shallow paths."""
    if len(parts) <= depth and parts and _looks_like_file_name(parts[-1]):
        return parts[:-1] or parts
    return parts[:depth]


def _path_parts(path_value: str) -> list[str]:
    """Split a normalized path into non-empty components."""
    return [part for part in path_value.split("/") if part]


def _looks_like_file_name(path_part: str) -> bool:
    """Return whether a path segment has a file-like extension."""
    return "." in path_part.strip(".")


def replace_root(path_value: str, old_root: str, new_root: str) -> Optional[str]:
    """Replace a path root while preserving the suffix after the root.

    Args:
        path_value: Path to rewrite.
        old_root: Current root, for example `P:/show_a`.
        new_root: New root, for example `P:/show_b`.

    Returns:
        The rewritten path, or None when `path_value` is not under `old_root`.
    """
    normalized_path = normalize_for_compare(path_value)
    normalized_old_root = normalize_for_compare(old_root)
    cleaned_new_root = new_root.rstrip("/\\")

    if normalized_path == normalized_old_root:
        return cleaned_new_root

    prefix = f"{normalized_old_root}/"
    if not normalized_path.startswith(prefix):
        return None

    suffix = path_value.replace("\\", "/")[len(old_root.replace("\\", "/").rstrip("/")) :]
    return f"{cleaned_new_root}{suffix}"
