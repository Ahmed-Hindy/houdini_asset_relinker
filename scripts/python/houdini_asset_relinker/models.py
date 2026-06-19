"""Data models for Houdini asset path scanning and updating."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from houdini_asset_relinker.path_utils import (
    path_extension,
    path_family,
    path_root,
)


class ReferenceKind(str, Enum):
    """Known reference categories."""

    FILE_PARAMETER = "file_parameter"
    HDA_LIBRARY = "hda_library"


@dataclass(frozen=True)
class AssetReference:
    """A single external asset reference found in the current Houdini session.

    Attributes:
        kind: The category of reference.
        raw_path: The unexpanded path when Houdini can provide it.
        expanded_path: The path after Houdini variable expansion when possible.
        exists: Whether the expanded path exists on disk.
        sequence_pattern: Preserved glob-like pattern for Houdini sequences.
        path_family: Compact root/path-family label for grouping related references.
        parm_path: Full Houdini parameter path when the reference is stored on a parameter.
        parm_name: Houdini parameter token/name when available.
        parm_label: Houdini parameter label when available.
        node_path: Full Houdini node path owning the parameter.
        node_type: Houdini node type name when available.
        path_role: Triage role inferred from the parameter/path context.
        missing_variables: Houdini variables in the raw path that did not resolve.
        can_update: Whether the tool can update this reference directly.
        reason: Human-readable reason when the reference cannot be directly updated.
    """

    kind: ReferenceKind
    raw_path: str
    expanded_path: str
    exists: bool
    sequence_pattern: str
    path_family: str = ""
    parm_path: Optional[str] = None
    parm_name: str = ""
    parm_label: str = ""
    node_path: Optional[str] = None
    node_type: str = ""
    path_role: str = ""
    missing_variables: tuple[str, ...] = ()
    can_update: bool = False
    reason: str = ""

    def to_row(self) -> dict[str, object]:
        """Return a serializable row for CSV, JSON, or table display."""
        path_role = self.path_role or _infer_path_role(self)
        path_for_root = (
            self.raw_path if self.missing_variables else self.expanded_path or self.raw_path
        )
        return {
            "kind": self.kind.value,
            "node_path": self.node_path or "",
            "node_type": self.node_type,
            "parm_path": self.parm_path or "",
            "parm_name": self.parm_name,
            "parm_label": self.parm_label,
            "path_role": path_role,
            "raw_path": self.raw_path,
            "expanded_path": self.expanded_path,
            "root": path_root(path_for_root),
            "extension": path_extension(self.expanded_path or self.raw_path),
            "sequence_pattern": self.sequence_pattern,
            "exists": self.exists,
            "path_family": self.path_family or path_family(self.raw_path),
            "can_update": self.can_update,
            "diagnosis": _diagnosis(self),
            "missing_variables": ";".join(self.missing_variables),
            "reason": self.reason,
            "suggested_action": _suggested_action(self, path_role),
        }


@dataclass(frozen=True)
class UpdateResult:
    """The result of attempting to update one asset reference."""

    status: str
    old_path: str
    new_path: str
    parm_path: Optional[str] = None
    message: str = ""

    @property
    def changed(self) -> bool:
        """Return whether this result represents a real or planned change."""
        return self.status in {"changed", "would_change"}


@dataclass(frozen=True)
class UpdateReport:
    """Summary of a path update operation."""

    dry_run: bool
    results: tuple[UpdateResult, ...]

    @property
    def changed_count(self) -> int:
        """Return the number of changed or would-change results."""
        return sum(result.changed for result in self.results)

    @property
    def skipped_count(self) -> int:
        """Return the number of skipped results."""
        return sum(result.status == "skipped" for result in self.results)

    @property
    def failed_count(self) -> int:
        """Return the number of failed results."""
        return sum(result.status == "failed" for result in self.results)

    def to_text(self, max_rows: int = 80) -> str:
        """Build a readable report for Houdini dialogs or console output.

        Args:
            max_rows: Maximum number of row lines to include.

        Returns:
            A plain text summary.
        """
        mode = "DRY RUN" if self.dry_run else "APPLIED"
        lines = [
            f"Asset Relinker report: {mode}",
            f"Changed: {self.changed_count}",
            f"Skipped: {self.skipped_count}",
            f"Failed: {self.failed_count}",
            "",
        ]
        for index, result in enumerate(self.results[:max_rows], start=1):
            location = result.parm_path or "<session/reference>"
            lines.append(f"{index:03d}. [{result.status}] {location}")
            lines.append(f"     old: {result.old_path}")
            lines.append(f"     new: {result.new_path}")
            if result.message:
                lines.append(f"     note: {result.message}")
        remaining_count = max(0, len(self.results) - max_rows)
        if remaining_count:
            lines.append(f"... {remaining_count} more rows omitted")
        return "\n".join(lines)


def rows_from_references(references: Iterable[AssetReference]) -> list[dict[str, object]]:
    """Convert references to serializable table rows."""
    return [reference.to_row() for reference in references]


def _diagnosis(reference: AssetReference) -> str:
    """Return a compact triage diagnosis for a reference."""
    if reference.missing_variables:
        return "undefined_variable"
    if reference.kind == ReferenceKind.HDA_LIBRARY and reference.raw_path == "Embedded":
        return "embedded_hda"
    if not reference.exists:
        return "missing_path"
    if not reference.can_update:
        return "read_only"
    return "ready"


def _suggested_action(reference: AssetReference, path_role: str) -> str:
    """Return a short next-step suggestion for CSV triage."""
    if reference.missing_variables:
        return "Define missing variables or replace the unresolved path root."
    if reference.kind == ReferenceKind.HDA_LIBRARY and reference.raw_path == "Embedded":
        return "Leave embedded definition as-is or manage it in the HDA manager."
    if not reference.exists and reference.can_update:
        return "Relink to an existing asset path."
    if not reference.exists:
        return "Fix the source manually before relinking."
    if reference.kind == ReferenceKind.HDA_LIBRARY:
        return "Use the HDA replacement workflow if this library should move."
    if not reference.can_update:
        return "Review manually; this reference is not directly writable."
    if path_role in {"output", "render_output", "cache"}:
        return "Verify whether the path should be regenerated or relinked."
    return "No action needed."


def _infer_path_role(reference: AssetReference) -> str:
    """Infer the practical role of a path from Houdini parm metadata and file path."""
    if reference.kind == ReferenceKind.HDA_LIBRARY:
        return "hda_library"

    context = " ".join(
        [
            reference.parm_name,
            reference.parm_label,
            reference.parm_path or "",
            reference.raw_path,
            reference.expanded_path,
        ]
    ).casefold()
    role_markers = (
        ("render_output", ("vm_picture", "picture", "render", "/render/", "/renders/")),
        ("cache", ("cache", ".bgeo", ".sim", ".vdb", ".abc")),
        ("output", ("output", "sopoutput", "ropoutput", "export", "write")),
        ("texture", ("texture", "tex", "map", ".exr", ".tif", ".tiff", ".jpg", ".png")),
        ("input", ("input", "source", "read", "file", "filename", "import")),
    )
    for role, markers in role_markers:
        if any(marker in context for marker in markers):
            return role
    return "unknown"
