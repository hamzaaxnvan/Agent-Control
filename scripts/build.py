#!/usr/bin/env python3
"""Build packages for PyPI distribution.

This script builds all publishable packages. For SDK and server, it copies internal
packages (models, engine, telemetry) into the source directories before building,
then cleans up afterward. This allows the published wheels to be self-contained.

Usage:
    python scripts/build.py [models|evaluators|sdk|server|contrib|all|<contrib-name>]
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from contrib_packages import ContribPackage, discover_contrib_packages

ROOT = Path(__file__).resolve().parent.parent


def get_global_version() -> str:
    """Read version from root pyproject.toml."""
    content = (ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError("Could not find version in root pyproject.toml")
    return match.group(1)


def set_package_version(pyproject_path: Path, version: str) -> None:
    """Update version in a pyproject.toml file."""
    content = pyproject_path.read_text()
    updated = re.sub(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{version}"',
        content,
        flags=re.MULTILINE,
    )
    pyproject_path.write_text(updated)


def sync_dependency_floors(pyproject_path: Path, dependency_names: list[str], version: str) -> None:
    """Update internal dependency lower bounds to the release version."""
    content = pyproject_path.read_text()
    updated = content
    for dependency_name in dependency_names:
        updated = re.sub(
            rf'("{re.escape(dependency_name)}\s*>=\s*)([^",;\]\s]+)',
            rf"\g<1>{version}",
            updated,
        )

    if updated != content:
        pyproject_path.write_text(updated)


def inject_bundle_metadata(init_file: Path, package_name: str, version: str) -> None:
    """Add bundling metadata to __init__.py for conflict detection."""
    content = init_file.read_text()

    if "__bundled_by__" in content:
        return

    metadata = f'''__bundled_by__ = "{package_name}"
__bundled_version__ = "{version}"

'''
    init_file.write_text(metadata + content)


def clean_dist_dir(package_dir: Path) -> Path:
    """Remove any previous build output and return the dist directory path."""
    dist_dir = package_dir / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    return dist_dir


