"""Tests for path utility helpers."""

from pathlib import Path

from houdini_asset_relinker.path_utils import (
    contains_sequence_token,
    path_exists,
    path_family,
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


def test_path_family_groups_windows_paths_by_root_family() -> None:
    """It groups Windows paths by drive and the first useful folders."""
    assert (
        path_family("F:/Assets 3D/Megascans/Downloaded/3d/asset/file.usd")
        == "F:/Assets 3D/Megascans/Downloaded"
    )
    assert (
        path_family("G:/projects/Data_folder/cache/Canyon_Run/sq001/cache.bgeo.sc")
        == "G:/projects/Data_folder/cache"
    )
    assert path_family("F:/Assets 3D/HDRI/sky.exr") == "F:/Assets 3D/HDRI"


def test_path_family_groups_relative_and_bare_paths() -> None:
    """It gives relative paths and bare tokens compact grouping labels."""
    assert path_family("layers/cache_Tie_Fighter_bolts.usd") == "layers"
    assert path_family("SCATTERED_ASSETS_v1.usd") == "<bare>"


def test_path_family_preserves_unc_share_root() -> None:
    """It groups UNC paths without losing their server/share prefix."""
    assert (
        path_family("//fileserver/projects/show/assets/model.usd")
        == "//fileserver/projects/show/assets"
    )
