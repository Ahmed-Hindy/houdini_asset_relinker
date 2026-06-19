"""Export helpers for asset reference reports."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from houdini_asset_relinker.models import AssetReference

_FIELDNAMES = [
    "kind",
    "node_path",
    "node_type",
    "parm_path",
    "parm_name",
    "parm_label",
    "path_role",
    "raw_path",
    "expanded_path",
    "root",
    "extension",
    "sequence_pattern",
    "path_family",
    "exists",
    "can_update",
    "diagnosis",
    "missing_variables",
    "reason",
    "suggested_action",
]


def write_references_csv(references: Iterable[AssetReference], output_path: str) -> Path:
    """Write scanned references to a CSV file.

    Args:
        references: Asset references to export.
        output_path: Destination CSV file path.

    Returns:
        The written path.
    """
    csv_path = Path(output_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for reference in references:
            writer.writerow(reference.to_row())
    return csv_path
