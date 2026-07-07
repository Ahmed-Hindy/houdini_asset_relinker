"""Path utility helpers for Houdini asset relinking."""

from __future__ import annotations

import os
import re
from glob import glob
from pathlib import Path
from typing import Callable, Optional

_FRAME_TOKEN_PATTERN = re.compile(r"(\$F\d*|<UDIM>)", re.IGNORECASE)
_HOUDINI_VARIABLE_PATTERN = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))"
)
_WINDOWS_DRIVE_PATTERN = re.compile(r"^([A-Za-z]:)(?:/(.*))?$")
_URI_SCHEME_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")

PATH_FAMILY_DEPTH = 3


def build_sequence_pattern(
    path_value: str, expand_string: Optional[Callable[[str], str]] = None
) -> str:
    """Return a glob pattern for Houdini frame or tile tokens.

    Args:
        path_value: Raw path value that may contain Houdini sequence tokens.
        expand_string: Optional Houdini-style expansion function. Tokens are protected
            before expansion so variables expand without losing the sequence pattern.

    Returns:
        A glob-like path pattern, or an empty string for non-sequence paths.
    """
    if not contains_sequence_token(path_value):
        return ""
    if expand_string is None:
        return sequence_pattern(path_value)

    protected_path, tokens = _protect_sequence_tokens(path_value)
    try:
        expanded_path = expand_string(protected_path)
    except Exception:
        expanded_path = protected_path
    restored_path = _restore_sequence_tokens(expanded_path, tokens)
    return sequence_pattern(restored_path)


def contains_sequence_token(path_value: str) -> bool:
    """Return whether a path string appears to contain a frame or tile token."""
    return bool(_FRAME_TOKEN_PATTERN.search(path_value))


def normalize_for_compare(path_value: str) -> str:
    """Normalize a path for prefix/equality comparisons without changing stored values."""
    normalized = path_value.replace("\\", "/")
    normalized = re.sub(r"/+", "/", normalized)
    return os.path.normcase(normalized.rstrip("/")).replace("\\", "/")


def normalize_path_format(path_value: str) -> str:
    """Return a display-safe path spelling with consistent separators.

    This keeps Houdini variables, frame tokens, URI schemes, UNC roots, and
    directory/file casing intact. Only path separators, duplicate slash runs,
    and Windows drive-letter casing are normalized.
    """
    normalized = path_value.replace("\\", "/")
    normalized = _collapse_path_separators(normalized)
    drive_match = _WINDOWS_DRIVE_PATTERN.match(normalized)
    if not drive_match:
        return normalized
    drive = drive_match.group(1).upper()
    tail = drive_match.group(2)
    return drive if tail is None else f"{drive}/{tail}"


def normalize_existing_path_case(path_value: str) -> Optional[str]:
    """Return ``path_value`` with filesystem casing when Windows can provide it."""
    normalized = normalize_path_format(path_value)
    path = Path(normalized)
    if os.name != "nt" or not path.is_absolute() or not path.exists():
        return None

    try:
        import ctypes
    except ImportError:
        return None

    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:
        return None

    windows_path = normalized.replace("/", "\\")
    short_path = _read_windows_path_name(ctypes, kernel32.GetShortPathNameW, windows_path)
    if short_path is None:
        return None
    long_path = _read_windows_path_name(ctypes, kernel32.GetLongPathNameW, short_path)
    if long_path is None:
        return None
    return normalize_path_format(long_path)


def _read_windows_path_name(
    ctypes_module: object, path_function: object, path_value: str
) -> Optional[str]:
    """Read a Windows path transform from a size-probed Win32 path function."""
    size = path_function(path_value, None, 0)
    if size <= 0:
        return None
    buffer = ctypes_module.create_unicode_buffer(size)
    result = path_function(path_value, buffer, size)
    if result <= 0 or result > size:
        return None
    return buffer.value


def path_exists(expanded_path: str, sequence_path_pattern: str = "") -> bool:
    """Return whether an expanded path exists.

    Sequence and UDIM tokens are treated as a glob-like check where possible.
    """
    if not expanded_path:
        return False
    if Path(expanded_path).exists():
        return True
    glob_pattern = sequence_path_pattern or sequence_pattern(expanded_path)
    if glob_pattern:
        return bool(glob(glob_pattern))
    return False


def missing_variables(
    path_value: str, variable_lookup: Optional[Callable[[str], Optional[str]]] = None
) -> tuple[str, ...]:
    """Return Houdini variable names that do not resolve through the provided lookup.

    Args:
        path_value: Raw path value to inspect.
        variable_lookup: Optional function that returns a variable value by name.

    Returns:
        Missing variable names in first-seen order.
    """
    if variable_lookup is None:
        return ()
    missing = []
    seen = set()
    for match in _HOUDINI_VARIABLE_PATTERN.finditer(path_value):
        if _FRAME_TOKEN_PATTERN.fullmatch(match.group(0)):
            continue
        variable_name = match.group(1) or match.group(2)
        if variable_name in seen:
            continue
        try:
            variable_value = variable_lookup(variable_name)
        except Exception:
            variable_value = None
        if not variable_value:
            missing.append(variable_name)
            seen.add(variable_name)
    return tuple(missing)


def path_root(path_value: str) -> str:
    """Return the drive, UNC share, URI scheme, or absolute root for a path."""
    cleaned_path = path_value.strip().replace("\\", "/")
    if not cleaned_path:
        return ""

    if cleaned_path.startswith("//"):
        parts = _path_parts(cleaned_path)
        if len(parts) >= 2:
            return "//" + "/".join(parts[:2])
        return cleaned_path.rstrip("/")

    drive_match = _WINDOWS_DRIVE_PATTERN.match(cleaned_path)
    if drive_match:
        return drive_match.group(1)

    uri_match = _URI_SCHEME_PATTERN.match(cleaned_path)
    if uri_match:
        return f"{uri_match.group(1)}:"

    if cleaned_path.startswith("/"):
        return "/"

    parts = _path_parts(cleaned_path)
    return parts[0] if parts else ""


def path_extension(path_value: str) -> str:
    """Return the full file extension, preserving compound extensions."""
    file_name = path_value.strip().replace("\\", "/").rsplit("/", 1)[-1]
    if not file_name:
        return ""
    file_name = _FRAME_TOKEN_PATTERN.sub("", file_name)
    return "".join(suffix for suffix in Path(file_name).suffixes if suffix != ".")


def sequence_pattern(path_value: str) -> str:
    """Return a glob-like sequence pattern when the path has frame or tile tokens."""
    if not contains_sequence_token(path_value):
        return ""
    return _FRAME_TOKEN_PATTERN.sub("*", path_value)


def _protect_sequence_tokens(path_value: str) -> tuple[str, tuple[str, ...]]:
    """Replace sequence tokens with sentinels before Houdini expansion."""
    tokens: list[str] = []

    def replace_token(match: re.Match[str]) -> str:
        tokens.append(match.group(0))
        return f"__HAR_SEQUENCE_TOKEN_{len(tokens) - 1}__"

    return _FRAME_TOKEN_PATTERN.sub(replace_token, path_value), tuple(tokens)


def _restore_sequence_tokens(path_value: str, tokens: tuple[str, ...]) -> str:
    """Restore protected sequence tokens after Houdini expansion."""
    restored = path_value
    for index, token in enumerate(tokens):
        restored = restored.replace(f"__HAR_SEQUENCE_TOKEN_{index}__", token)
    return restored


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


_PATH_TOKEN_CHAR = r"A-Za-z0-9_"


def replace_text(
    path_value: str, find_text: str, replace_with: str, case_sensitive: bool = False
) -> Optional[str]:
    """Replace text in a path and return None when there is no match.

    Matching is case-insensitive by default so Windows-style path casing
    differences do not block relinks. Pass ``case_sensitive=True`` to require
    exact letter-case matches.

    Matches must sit on path token boundaries so shorter Houdini variables such
    as ``$CACHE`` do not match inside longer names like ``$CACHE_G``.
    """
    if not find_text:
        return None
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(
        rf"(?<![{_PATH_TOKEN_CHAR}]){re.escape(find_text)}(?![{_PATH_TOKEN_CHAR}])",
        flags,
    )
    if not pattern.search(path_value):
        return None
    return pattern.sub(lambda _match: replace_with, path_value)


def matches_find_text(path_value: str, find_text: str, case_sensitive: bool = False) -> bool:
    """Return whether ``find_text`` matches inside ``path_value`` using relink Find rules."""
    if not find_text:
        return False
    return replace_text(path_value, find_text, find_text, case_sensitive) is not None


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


def _collapse_path_separators(path_value: str) -> str:
    """Collapse duplicate separators without breaking UNC roots or URI schemes."""
    if re.match(r"^[A-Za-z]:/", path_value):
        return re.sub(r"/+", "/", path_value)

    uri_match = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*://)(.*)$", path_value)
    if uri_match:
        return uri_match.group(1) + re.sub(r"/+", "/", uri_match.group(2))

    if path_value.startswith("//"):
        return "//" + re.sub(r"/+", "/", path_value[2:])

    return re.sub(r"/+", "/", path_value)


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
