"""Build a Houdini-installable release archive."""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "scripts" / "python" / "houdini_asset_relinker" / "_version.py"
ROOT_VERSION_FILE = REPO_ROOT / "VERSION"
PYPROJECT_FILE = REPO_ROOT / "pyproject.toml"

PACKAGE_DIRS = ("package", "toolbar", "images")
PACKAGE_FILES = ("README.md", "DEVELOPER.md", "VERSION")


def read_runtime_version() -> str:
    """Read VERSION from the runtime package without importing Houdini code."""
    module = ast.parse(VERSION_FILE.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "VERSION":
                    value = ast.literal_eval(node.value)
                    if isinstance(value, str):
                        return value
    raise RuntimeError(f"Could not find VERSION in {VERSION_FILE}")


def read_pyproject_version() -> str:
    """Read the static project version from pyproject.toml."""
    match = re.search(
        r'(?m)^version\s*=\s*"([^"]+)"\s*$',
        PYPROJECT_FILE.read_text(encoding="utf-8"),
    )
    if not match:
        raise RuntimeError(f"Could not find project.version in {PYPROJECT_FILE}")
    return match.group(1)


def validate_versions(expected_version: str | None = None) -> str:
    """Validate every release version marker before building.

    Args:
        expected_version: Optional version expected by CI, usually from the git tag.

    Returns:
        The validated runtime version.

    Raises:
        RuntimeError: If any version marker disagrees.
    """
    runtime_version = read_runtime_version()
    pyproject_version = read_pyproject_version()
    root_version = ROOT_VERSION_FILE.read_text(encoding="utf-8").strip()

    mismatches = []
    if pyproject_version != runtime_version:
        mismatches.append(f"pyproject.toml={pyproject_version}")
    if root_version != runtime_version:
        mismatches.append(f"VERSION={root_version}")
    if expected_version and expected_version != runtime_version:
        mismatches.append(f"expected={expected_version}")

    if mismatches:
        details = ", ".join(mismatches)
        raise RuntimeError(f"Version mismatch: runtime={runtime_version}, {details}")

    return runtime_version


def ignore_build_noise(_directory: str, names: list[str]) -> set[str]:
    """Return generated files that should not enter the artist package."""
    ignored = {"__pycache__", ".pytest_cache", ".ruff_cache"}
    ignored.update(name for name in names if name.endswith((".pyc", ".pyo")))
    return ignored


def copy_release_tree(staging_dir: Path) -> None:
    """Copy the Houdini package layout into a staging directory."""
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    for dirname in PACKAGE_DIRS:
        source = REPO_ROOT / dirname
        if source.exists():
            shutil.copytree(source, staging_dir / dirname, ignore=ignore_build_noise)

    shutil.copytree(
        REPO_ROOT / "scripts" / "python",
        staging_dir / "scripts" / "python",
        ignore=ignore_build_noise,
    )

    for filename in PACKAGE_FILES:
        source = REPO_ROOT / filename
        if source.exists():
            shutil.copy2(source, staging_dir / filename)


def create_zip(staging_dir: Path, archive_path: Path) -> None:
    """Create a deterministic zip archive from the staged release tree."""
    if archive_path.exists():
        archive_path.unlink()

    root_name = staging_dir.name
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging_dir.rglob("*")):
            if path.is_file():
                archive.write(path, Path(root_name) / path.relative_to(staging_dir))


def write_sha256(archive_path: Path) -> Path:
    """Write a SHA256 checksum next to the archive."""
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = archive_path.with_suffix(f"{archive_path.suffix}.sha256")
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    return checksum_path


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--expected-version")
    return parser.parse_args()


def main() -> int:
    """Build the release artifact."""
    args = parse_args()
    version = validate_versions(args.expected_version)

    out_dir = args.out_dir.resolve()
    staging_dir = out_dir / f"houdini_asset_relinker-{version}"
    archive_path = out_dir / f"houdini_asset_relinker-{version}.zip"

    out_dir.mkdir(parents=True, exist_ok=True)
    copy_release_tree(staging_dir)
    create_zip(staging_dir, archive_path)
    checksum_path = write_sha256(archive_path)
    shutil.rmtree(staging_dir)

    print(archive_path)
    print(checksum_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
