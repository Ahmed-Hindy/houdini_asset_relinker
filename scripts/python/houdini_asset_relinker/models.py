"""Data models for Houdini asset path scanning and updating."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Optional


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
        path_family: Compact root/path-family label for grouping related references.
        parm_path: Full Houdini parameter path when the reference is stored on a parameter.
        node_path: Full Houdini node path owning the parameter.
        can_update: Whether the tool can update this reference directly.
        reason: Human-readable reason when the reference cannot be directly updated.
    """

    kind: ReferenceKind
    raw_path: str
    expanded_path: str
    exists: bool
    path_family: str = ""
    parm_path: Optional[str] = None
    node_path: Optional[str] = None
    can_update: bool = False
    reason: str = ""

    def to_row(self) -> dict[str, object]:
        """Return a serializable row for CSV, JSON, or table display."""
        return {
            "kind": self.kind.value,
            "node_path": self.node_path or "",
            "parm_path": self.parm_path or "",
            "raw_path": self.raw_path,
            "expanded_path": self.expanded_path,
            "exists": self.exists,
            "path_family": self.path_family,
            "can_update": self.can_update,
            "reason": self.reason,
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
