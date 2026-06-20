# Houdini Asset Relinker - Developer & Technical Guide

This document contains technical details, installation instructions, programmatic APIs, and development setup info for Technical Directors (TDs) and developers working with the **Houdini Asset Relinker**.

For artist-focused instructions on how to use the GUI tool, please refer to the main [README.md](README.md).

---

## Directory Layout

```text
houdini_asset_relinker/
├─ package/
│  └─ houdini_asset_relinker.json      # Copy this to your houdini21.0/packages folder
├─ toolbar/
│  └─ asset_relinker.shelf             # Standard Houdini shelf location under HOUDINI_PATH
├─ scripts/
│  └─ python/
│     └─ houdini_asset_relinker/       # Importable Houdini Python package
├─ tests/
│  └─ test_path_utils.py
├─ pyproject.toml                      # uv / ruff / pytest config
└─ README.md
```

- **package/**: Contains the Houdini package definition JSON.
- **toolbar/**: Standard shelf file (`asset_relinker.shelf`).
- **scripts/python/**: Runtime Python module path. Placed in `HOUDINI_PATH` so Houdini automatically appends it to `sys.path`.
- **houdini_asset_relinker._version**: Single source of truth for the release version. No wheel metadata is required at runtime.

---

## Installation in Houdini 21.0 (Windows)

To set up the tool in Houdini:

1. **Identify Package Root**:
   Locate your repository directory (e.g., `C:/Users/$USERNAME/Documents/houdiniTools/houdini_asset_relinker`).

2. **Copy Package JSON**:
   Copy the file:
   `C:/Users/$USERNAME/Documents/houdiniTools/houdini_asset_relinker/package/houdini_asset_relinker.json`

   to your local Houdini packages directory:
   `C:/Users/$USERNAME/Documents/houdini21.0/packages/houdini_asset_relinker.json`

3. **Verify/Update Root Path**:
   Ensure the `"ASSET_RELINKER_ROOT"` environment variable in the package JSON points to the absolute path of your workspace root:

   ```json
   {
     "load_package_once": true,
     "env": [
       {
         "ASSET_RELINKER_ROOT": "C:/Users/$USERNAME/Documents/houdiniTools/houdini_asset_relinker"
       },
       {
         "HOUDINI_PATH": {
           "method": "prepend",
           "value": "$ASSET_RELINKER_ROOT"
         }
       }
     ]
   }
   ```

4. **Restart Houdini**. The package will prepend the root to `HOUDINI_PATH`, allowing Houdini to discover the shelf file and Python modules automatically.

---

## Verification & Manual UI Open

To verify that the module loaded correctly, run this in Houdini's Python Shell:

```python
import houdini_asset_relinker
print(houdini_asset_relinker.__file__)
```

Expected output:
`C:/Users/$USERNAME/Documents/houdiniTools/houdini_asset_relinker/scripts/python/houdini_asset_relinker/__init__.py`

To open the dialog programmatically:

```python
from houdini_asset_relinker.ui import open_dialog
open_dialog()
```

---

## Programmatic Usage

You can scan and replace paths in the live session headlessly or from scripts inside Houdini:

```python
from houdini_asset_relinker.scanner import scan_assets
from houdini_asset_relinker.updater import replace_path_text

# 1. Scan session references
# project_dir_variable defines which path context to evaluate (e.g., 'HIP', 'JOB')
references = scan_assets(project_dir_variable="HIP", include_hda_libraries=False)
for ref in references:
    print(ref.raw_path, ref.expanded_path, ref.exists)

# 2. Dry run path replacement
# Matching is case-insensitive by default; pass case_sensitive=True for exact-case relinks.
report = replace_path_text("P:/old_show", "P:/new_show", dry_run=True)
print(report.to_text())

# 3. Apply path replacement
report = replace_path_text("P:/old_show", "P:/new_show", dry_run=False)
print(report.to_text())
```

---

## Standalone GUI Mode (Development Only)

For standalone interface design/development outside Houdini, install the optional PySide6 dependencies:

```powershell
uv sync --group pyside6
$env:PYTHONPATH = "scripts/python"
uv run --group pyside6 python -m houdini_asset_relinker.ui
```

> [!NOTE]
> Standalone mode loads the PySide UI, but operations like scanning and applying changes will fail or be stubbed since they rely on the live `hou` module.

---

## Versioning & Release Artifacts

This project is distributed as a Houdini package folder, not as a Python wheel. The single source of truth for the runtime and release version is:

- `scripts/python/houdini_asset_relinker/_version.py`

The release artifact builder validates the version against the release tag before producing the zip:

```powershell
uv run python scripts/build_release_artifact.py --out-dir dist --expected-version X.Y.Z
```

Release tags should use the `vX.Y.Z` form. The GitHub Actions release workflow builds `dist/houdini_asset_relinker-X.Y.Z.zip`, writes a generated `VERSION` file into that artifact, writes a `.sha256` checksum, uploads both as workflow artifacts, and attaches them to the matching GitHub release.

---

## Development Setup

We use `uv` for python tooling.

```powershell
# Sync workspace environment
uv sync

# Refresh lockfile for the Houdini-compatible Python floor
uv --system-certs lock --python 3.9

# Check code formatting & linting
uv run ruff check .
uv run ruff format .

# Run pytest suite
uv run python -m pytest
```

---

## Technical & Safety Details

- **Dry Run**: Always defaults to `True` for safety.
- **Skipping Parameters**: Parameter updates are skipped when the scanned reference is not stored on a real `hou.Parm` (e.g., read-only internal system references).
- **HDA Library Replacement**: Highly conservative. It first installs the target library path, then optionally uninstalls the old one to avoid losing node types mid-operation.
- **Houdini 21.0 Qt Binding**: Uses the default Qt library provided by Houdini (typically PySide2).
