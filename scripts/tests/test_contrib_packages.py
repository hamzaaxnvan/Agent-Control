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
