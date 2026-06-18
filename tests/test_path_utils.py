"""Tests for path utility helpers."""

from pathlib import Path

from houdini_asset_relinker.path_utils import (
    contains_sequence_token,
    path_exists,
    replace_root,
    replace_text,
)


def test_replace_text_case_sensitive() -> None:
    """It replaces matching text only when the case matches."""
    result = replace_text("P:/show/cache/a.bgeo.sc", "P:/show", "D:/show")
    assert result == "D:/show/cache/a.bgeo.sc"
    assert replace_text("P:/show/cache/a.bgeo.sc", "p:/show", "D:/show") is None


def test_replace_text_case_insensitive() -> None:
    """It can replace text case-insensitively."""
    result = replace_text("P:/show/cache/a.bgeo.sc", "p:/SHOW", "D:/show", case_sensitive=False)
    assert result == "D:/show/cache/a.bgeo.sc"


def test_replace_root() -> None:
    """It replaces a root while preserving the suffix."""
    result = replace_root("P:/show/cache/a.bgeo.sc", "P:/show", "D:/show")
    assert result == "D:/show/cache/a.bgeo.sc"


def test_replace_root_accepts_windows_separator_variants() -> None:
    """It compares roots across common Windows path separator variants."""
    result = replace_root("P:\\show\\cache\\a.bgeo.sc", "P:/show", "D:/show")
    assert result == "D:/show/cache/a.bgeo.sc"


def test_contains_sequence_token() -> None:
    """It recognizes common Houdini and renderer sequence tokens."""
    assert contains_sequence_token("$HIP/cache/sim.$F4.bgeo.sc")
    assert contains_sequence_token("$HIP/tex/char.<UDIM>.exr")
    assert contains_sequence_token("$HIP/render/image.%04d.exr")


def test_path_exists_accepts_absolute_sequence_patterns(tmp_path: Path) -> None:
    """It checks absolute sequence paths without passing them to pathlib glob."""
    cache_file = tmp_path / "sim.0001.bgeo.sc"
    cache_file.write_text("test")

    assert path_exists(str(tmp_path / "sim.$F4.bgeo.sc"))


def test_path_exists_accepts_absolute_udim_patterns(tmp_path: Path) -> None:
    """It checks absolute UDIM paths without passing them to pathlib glob."""
    texture_file = tmp_path / "char.1001.exr"
    texture_file.write_text("test")

    assert path_exists(str(tmp_path / "char.<UDIM>.exr"))


def test_path_exists_returns_false_for_missing_sequence(tmp_path: Path) -> None:
    """It returns false when no files match a sequence pattern."""
    assert not path_exists(str(tmp_path / "missing.$F4.bgeo.sc"))
