"""Tests for CSV export rows."""

from __future__ import annotations

import csv

from houdini_asset_relinker.export import write_references_csv
from houdini_asset_relinker.models import AssetReference, ReferenceKind


def test_write_references_csv_includes_triage_columns(tmp_path) -> None:
    """It writes derived columns that make missing references easier to triage."""
    csv_path = write_references_csv(
        [
            AssetReference(
                kind=ReferenceKind.FILE_PARAMETER,
                raw_path="$ASSET_ROOT/cache/sim.$F4.bgeo.sc",
                expanded_path="$ASSET_ROOT/cache/sim.$F4.bgeo.sc",
                exists=False,
                sequence_pattern="$ASSET_ROOT/cache/sim.*.bgeo.sc",
                path_family="$ASSET_ROOT",
                parm_path="/obj/geo1/filecache1/sopoutput",
                parm_name="sopoutput",
                parm_label="Geometry File",
                node_path="/obj/geo1/filecache1",
                node_type="filecache",
                missing_variables=("ASSET_ROOT",),
                can_update=True,
            )
        ],
        str(tmp_path / "report.csv"),
    )

    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        row = next(csv.DictReader(csv_file))

    assert row["node_type"] == "filecache"
    assert row["parm_name"] == "sopoutput"
    assert row["parm_label"] == "Geometry File"
    assert row["path_role"] == "cache"
    assert row["diagnosis"] == "undefined_variable"
    assert row["missing_variables"] == "ASSET_ROOT"
    assert row["root"] == "$ASSET_ROOT"
    assert row["extension"] == ".bgeo.sc"
    assert row["sequence_pattern"] == "$ASSET_ROOT/cache/sim.*.bgeo.sc"
    assert row["suggested_action"] == (
        "Define missing variables or replace the unresolved path root."
    )
