"""Tests for path utility helpers."""

from houdini_asset_relinker.path_utils import contains_sequence_token, replace_root, replace_text


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
