"""Shared display text for scanned asset references."""

from __future__ import annotations

from typing import Literal

from houdini_asset_relinker.models import AssetReference, is_generated_output

REFERENCE_STATUS_GENERATED_OUTPUT = "generated_output"
REFERENCE_STATUS_UNDEFINED_VARIABLE = "undefined_variable"
REFERENCE_STATUS_MISSING = "missing"
REFERENCE_STATUS_READ_ONLY = "read_only"
REFERENCE_STATUS_READY = "ready"

_STATUS_TEXT = {
    REFERENCE_STATUS_GENERATED_OUTPUT: {
        "lower": "generated output",
        "sentence": "Generated output",
    },
    REFERENCE_STATUS_UNDEFINED_VARIABLE: {
        "lower": "undefined variable",
        "sentence": "Undefined variable",
    },
    REFERENCE_STATUS_MISSING: {
        "lower": "missing",
        "sentence": "Missing",
    },
    REFERENCE_STATUS_READ_ONLY: {
        "lower": "read only",
        "sentence": "Read only",
    },
    REFERENCE_STATUS_READY: {
        "lower": "ready",
        "sentence": "Ready",
    },
}


def reference_status(reference: AssetReference) -> str:
    """Return the shared reference status identifier."""
    if is_generated_output(reference):
        return REFERENCE_STATUS_GENERATED_OUTPUT
    if reference.missing_variables:
        return REFERENCE_STATUS_UNDEFINED_VARIABLE
    if not reference.exists:
        return REFERENCE_STATUS_MISSING
    if not reference.can_update:
        return REFERENCE_STATUS_READ_ONLY
    return REFERENCE_STATUS_READY


def reference_status_text(
    reference: AssetReference,
    *,
    style: Literal["lower", "sentence"] = "sentence",
) -> str:
    """Return user-facing reference status text.

    Args:
        reference: Scanned reference to describe.
        style: Text casing style for the target UI surface.

    Returns:
        The status label for the requested display style.
    """
    return _STATUS_TEXT[reference_status(reference)][style]


def reference_note_text(reference: AssetReference) -> str:
    """Return the shared user-facing note for a reference."""
    if is_generated_output(reference):
        return reference.reason or "Generated output path kept for context"
    if reference.missing_variables:
        return missing_variables_text(reference)
    return reference.reason or ("Writable reference" if reference.can_update else "Not writable")


def missing_variables_text(reference: AssetReference) -> str:
    """Return a readable undefined-variable note."""
    if not reference.missing_variables:
        return ""
    return f"Undefined variables: {', '.join(reference.missing_variables)}"
