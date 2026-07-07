"""Tests for path utility helpers."""

from pathlib import Path

from houdini_asset_relinker.path_utils import (
    build_sequence_pattern,
    contains_sequence_token,
    matches_find_text,
    missing_variables,
    normalize_path_format,
    path_exists,
    path_family,
    replace_root,
    replace_text,
    sequence_pattern,
)


def test_replace_text_defaults_to_case_insensitive() -> None:
    """It replaces Windows-style path text when only casing differs."""
    result = replace_text("P:/show/cache/a.bgeo.sc", "P:/show", "D:/show")
    assert result == "D:/show/cache/a.bgeo.sc"

    result = replace_text("P:/show/cache/a.bgeo.sc", "p:/SHOW", "D:/show", case_sensitive=False)
    assert result == "D:/show/cache/a.bgeo.sc"


def test_replace_text_exact_case_is_opt_in() -> None:
    """It can require exact letter-case matches."""
    result = replace_text("P:/show/cache/a.bgeo.sc", "P:/show", "D:/show", case_sensitive=True)
    assert result == "D:/show/cache/a.bgeo.sc"
    assert (
        replace_text("P:/show/cache/a.bgeo.sc", "p:/show", "D:/show", case_sensitive=True) is None
    )


def test_replace_text_does_not_match_longer_houdini_variables() -> None:
    """It avoids prefix matches inside longer variable names."""
    assert replace_text("$CACHE_G/sim.$F4.bgeo.sc", "$CACHE", "$CACHE_G") is None
    assert (
        replace_text("$CACHE/sim.$F4.bgeo.sc", "$CACHE", "$CACHE_G") == "$CACHE_G/sim.$F4.bgeo.sc"
    )
    assert (
        replace_text("$HIP/$CACHE/cache/file.bgeo.sc", "$CACHE", "$CACHE_G")
        == "$HIP/$CACHE_G/cache/file.bgeo.sc"
    )


def test_matches_find_text_uses_replace_text_boundaries() -> None:
    """It reports Find matches using the same rules as relink replacement."""
    assert matches_find_text("$CACHE/sim.$F4.bgeo.sc", "$CACHE")
    assert not matches_find_text("$CACHE_G/sim.$F4.bgeo.sc", "$CACHE")
    assert not matches_find_text("", "$CACHE")
    assert not matches_find_text("$CACHE/sim.$F4.bgeo.sc", "")


def test_normalize_path_format_standardizes_windows_separators_and_drive_case() -> None:
    """It cleans common Windows spelling drift without changing path segment casing."""
    assert (
        normalize_path_format("p:\\Assets 3D\\\\Megascans\\Tree\\leaf.$F4.exr")
        == "P:/Assets 3D/Megascans/Tree/leaf.$F4.exr"
    )
    assert normalize_path_format("p://show///cache/file.bgeo.sc") == ("P:/show/cache/file.bgeo.sc")


def test_normalize_path_format_preserves_houdini_tokens_unc_and_uri_roots() -> None:
    """It keeps roots and tokens intact while collapsing duplicate separator runs."""
    assert normalize_path_format("$HIP\\\\cache////sim.<UDIM>.exr") == "$HIP/cache/sim.<UDIM>.exr"
    assert (
        normalize_path_format("\\\\server\\share\\\\show\\asset.usd")
        == "//server/share/show/asset.usd"
    )
    assert normalize_path_format("file://server//share\\asset.usd") == (
        "file://server/share/asset.usd"
    )


def test_replace_root() -> None:
    """It replaces a root while preserving the suffix."""
    result = replace_root("P:/show/cache/a.bgeo.sc", "P:/show", "D:/show")
    assert result == "D:/show/cache/a.bgeo.sc"


def test_replace_root_accepts_windows_separator_variants() -> None:
    """It compares roots across common Windows path separator variants."""
    result = replace_root("P:\\show\\cache\\a.bgeo.sc", "P:/show", "D:/show")
    assert result == "D:/show/cache/a.bgeo.sc"


def test_contains_sequence_token() -> None:
    """It recognizes Houdini sequence tokens only."""
    assert contains_sequence_token("$HIP/cache/sim.$F4.bgeo.sc")
    assert contains_sequence_token("$HIP/cache/sim.$F.bgeo.sc")
    assert contains_sequence_token("$HIP/tex/char.<UDIM>.exr")
    assert not contains_sequence_token("$HIP/cache/sim.####.bgeo.sc")
    assert not contains_sequence_token("$HIP/render/image.%04d.exr")
    assert not contains_sequence_token("$HIP/tex/char.<UVTILE>.exr")


def test_missing_variables_excludes_frame_tokens_and_dedupes() -> None:
    """It reports unresolved Houdini variables without treating frames as variables."""
    missing = missing_variables(
        "$AYON_ROOT/${ASSET_ROOT}/cache/$AYON_ROOT/sim.$F4.bgeo.sc",
        lambda name: "G:/show" if name == "HIP" else None,
    )

    assert missing == ("AYON_ROOT", "ASSET_ROOT")


def test_build_sequence_pattern_preserves_tokens_through_expansion(tmp_path: Path) -> None:
    """It expands variables without losing Houdini sequence tokens."""
    pattern = build_sequence_pattern(
        "$HIP/cache/sim.$F4.bgeo.sc",
        lambda value: value.replace("$HIP", str(tmp_path)).replace("$F4", "1052"),
    )

    assert pattern.replace("\\", "/") == str(tmp_path / "cache" / "sim.*.bgeo.sc").replace(
        "\\", "/"
    )


def test_path_exists_accepts_absolute_sequence_patterns(tmp_path: Path) -> None:
    """It checks absolute sequence paths without passing them to pathlib glob."""
    cache_file = tmp_path / "sim.0001.bgeo.sc"
    cache_file.write_text("test")

    assert path_exists(str(tmp_path / "sim.$F4.bgeo.sc"))


def test_path_exists_checks_preserved_sequence_pattern_after_exact_path(tmp_path: Path) -> None:
    """It accepts a sequence when the current expanded frame is missing."""
    cache_file = tmp_path / "sim.1051.bgeo.sc"
    cache_file.write_text("test")

    assert path_exists(str(tmp_path / "sim.1052.bgeo.sc"), str(tmp_path / "sim.*.bgeo.sc"))


def test_path_exists_accepts_absolute_udim_patterns(tmp_path: Path) -> None:
    """It checks absolute UDIM paths without passing them to pathlib glob."""
    texture_file = tmp_path / "char.1001.exr"
    texture_file.write_text("test")

    assert path_exists(str(tmp_path / "char.<UDIM>.exr"))


def test_path_exists_ignores_hash_padding_patterns(tmp_path: Path) -> None:
    """It does not treat hash padding as a Houdini sequence pattern."""
    cache_file = tmp_path / "sim.0001.bgeo.sc"
    cache_file.write_text("test")

    assert not path_exists(str(tmp_path / "sim.####.bgeo.sc"))


def test_path_exists_returns_false_for_missing_sequence(tmp_path: Path) -> None:
    """It returns false when no files match a sequence pattern."""
    assert not path_exists(str(tmp_path / "missing.$F4.bgeo.sc"))


def test_sequence_pattern_ignores_non_houdini_tokens() -> None:
    """It does not treat non-Houdini patterns as Houdini sequences."""
    assert sequence_pattern("$HIP/cache/sim.####.bgeo.sc") == ""
    assert sequence_pattern("$HIP/render/image.%04d.exr") == ""
    assert sequence_pattern("$HIP/tex/char.<UVTILE>.exr") == ""


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
