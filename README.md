# Houdini Asset Relinker

A small Houdini 21.0 Python utility for auditing external asset paths in the current `.hip` session and safely replacing/updating those paths.

This is laid out as a Houdini package directory, not only as a generic Python repo. Runtime code lives under `scripts/python/`, and the shelf file lives under Houdini's standard `toolbar/` directory.

## Directory layout

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

## What it scans

- External file references returned by `hou.fileReferences()`.
- Optional loaded HDA library files returned by `hou.hda.loadedFiles()`.

Typical matches include geometry caches, textures, USD/Alembic paths, output paths, task graph files, and HDA/OTL library references reported by Houdini.

## Install in Houdini 21.0 on Windows

Your current package root is:

```text
F:/Users/Ahmed Hindy/Documents/houdiniTools/houdini_asset_relinker
```

Copy this file:

```text
F:/Users/Ahmed Hindy/Documents/houdiniTools/houdini_asset_relinker/package/houdini_asset_relinker.json
```

to:

```text
C:/Users/Ahmed Hindy/Documents/houdini21.0/packages/houdini_asset_relinker.json
```

Then restart Houdini.

The package JSON uses this root:

```json
{
  "load_package_once": true,
  "env": [
    {
      "ASSET_RELINKER_ROOT": "F:/Users/Ahmed Hindy/Documents/houdiniTools/houdini_asset_relinker"
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

`HOUDINI_PATH` points at the package root so Houdini can discover both `scripts/python/` and the standard `toolbar/` shelf directory. No custom toolbar path is needed.

## Verify it loaded

In Houdini's Python Shell:

```python
import houdini_asset_relinker
print(houdini_asset_relinker.__file__)
```

Expected result should include:

```text
F:/Users/Ahmed Hindy/Documents/houdiniTools/houdini_asset_relinker/scripts/python/houdini_asset_relinker/__init__.py
```

Open the UI manually:

```python
from houdini_asset_relinker.ui import open_dialog
open_dialog()
```

You should also see a toolbar/shelf tool named **Asset Relinker**.

The shelf opens a full PySide window inside Houdini. On Houdini 21.0 it uses the
Qt binding provided by Houdini, typically PySide2. The window includes:

- Scene scanning with optional HDA library references.
- Sortable and filterable reference table.
- Missing/writable/HDA summary counters.
- Selected-reference details, copy, reveal-on-disk, and select-node actions.
- CSV export.
- Dry-run find/replace preview before applying parameter path updates.
- Optional HDA library relinking with an uninstall-old-library toggle.

For standalone development outside Houdini, install the optional PySide6 extra:

```powershell
uv --system-certs sync --extra pyside6
uv --system-certs run --extra pyside6 houdini-asset-relinker
```

Standalone mode can open the interface, but scanning and applying still require
Houdini or hython because the backend reads the live `hou` session.

## Programmatic usage inside Houdini

```python
from houdini_asset_relinker.scanner import scan_assets
from houdini_asset_relinker.updater import replace_path_text

references = scan_assets(project_dir_variable="HIP", include_hda_libraries=False)
for reference in references:
    print(reference.raw_path, reference.expanded_path, reference.exists)

report = replace_path_text("P:/old_show", "P:/new_show", dry_run=True)
print(report.to_text())

# Apply after reviewing the dry run:
report = replace_path_text("P:/old_show", "P:/new_show", dry_run=False)
print(report.to_text())
```

## Development setup

From PowerShell:

```powershell
cd "F:\Users\Ahmed Hindy\Documents\houdiniTools\houdini_asset_relinker"
uv --system-certs sync
uv --system-certs run ruff check .
uv --system-certs run ruff format .
uv --system-certs run python -m pytest
```

The runtime Houdini tool does not require third-party packages installed into Houdini. `uv`, `ruff`, and `pytest` are only for development outside Houdini.

## Safety notes

- Dry run is the default for path replacement APIs.
- Parameter updates are skipped when the reference is not stored on a real `hou.Parm`.
- HDA library replacement is intentionally conservative: it installs the new library path first, then optionally uninstalls the old library path.
- Save a copy of the `.hip` before applying large path changes.
