"""UI entry points for the Houdini asset relinker."""

__all__ = ["AssetRelinkerWindow", "main", "open_dialog"]


def __getattr__(name: str) -> object:
    """Load Qt-backed UI entry points only when requested."""
    if name in __all__:
        from houdini_asset_relinker.ui import window

        return getattr(window, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
