"""Tests for contrib package discovery and verification."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent
from types import ModuleType

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "contrib_packages.py"


def _load_module() -> ModuleType:
    """Load the contrib package script as a module for testing."""

    module_name = "contrib_packages_under_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {SCRIPT_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write_text(path: Path, contents: str) -> None:
    """Write a text file, creating parent directories first."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(contents).strip() + "\n")


def _write_fake_repo(
    root: Path,
    *,
    include_version_entry: bool = True,
    include_builtin_extra: bool = True,
    include_builtin_source: bool = True,
) -> None:
    """Create a minimal repo layout that exercises contrib package wiring."""

    version_entry = (
        '"evaluators/contrib/example/pyproject.toml:project.version"'
        if include_version_entry
        else ""
    )
    extra_entry = (
        'example = ["agent-control-evaluator-example>=1.0.0"]'
        if include_builtin_extra
        else ""
    )
    source_entry = (
        'agent-control-evaluator-example = { path = "../contrib/example", editable = true }'
        if include_builtin_source
        else ""
    )

    _write_text(
        root / "pyproject.toml",
        f"""
        [project]
        name = "agent-control"
