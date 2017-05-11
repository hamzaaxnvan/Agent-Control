#!/usr/bin/env python3
"""Discover and verify real contrib evaluator packages."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EVALUATOR_ENTRY_GROUP = "agent_control.evaluators"
REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRIB_ROOT = REPO_ROOT / "evaluators" / "contrib"


class ContribPackagesError(Exception):
    """Raised when contrib package discovery or verification cannot proceed."""


@dataclass(frozen=True)
class ContribPackage:
    """Normalized metadata for a real contrib evaluator package."""

    name: str
    directory: str
    package: str
    extra: str
    entry_group: str = EVALUATOR_ENTRY_GROUP

    @property
    def version_toml_entry(self) -> str:
        return f"{self.directory}/pyproject.toml:project.version"

    @property
    def builtin_uv_source_path(self) -> str:
        return f"../contrib/{self.name}"

    def to_matrix_entry(self) -> dict[str, str]:
        return {
            "name": self.name,
            "dir": self.directory,
            "package": self.package,
            "extra": self.extra,
            "entry_group": self.entry_group,
        }


def load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file with contextual parse errors."""

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ContribPackagesError(
            f"Required file is missing: {display_path(path)}."
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ContribPackagesError(
            f"Failed to parse {display_path(path)}: {exc}."
        ) from exc

    if not isinstance(data, dict):
        raise ContribPackagesError(
            f"{display_path(path)} did not parse to a TOML table."
        )

    return data


def display_path(path: Path) -> str:
    """Render a path relative to the repo root when possible."""

    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def require_table(
    data: dict[str, Any], key: str, *, path: Path, parent_description: str
) -> dict[str, Any]:
    """Return a TOML table or raise a targeted error."""

    value = data.get(key)
    if not isinstance(value, dict):
        table_name = f"{parent_description}.{key}" if parent_description else key
        raise ContribPackagesError(
            f"{display_path(path)} must define [{table_name}] as a TOML table."
        )
    return value


def require_string(value: Any, *, path: Path, description: str) -> str:
    """Return a non-empty string or raise a targeted error."""

    if not isinstance(value, str) or not value:
        raise ContribPackagesError(
            f"{display_path(path)} must define {description} as a non-empty string."
        )
    return value


def dependency_name(requirement: str) -> str:
    """Extract the distribution name from a PEP 508 requirement string."""

    end = len(requirement)
    for index, character in enumerate(requirement):
        if character in " [<>=!~;":
            end = index
            break
    return requirement[:end].strip().lower()


def discover_contrib_packages() -> list[ContribPackage]:
    """Discover real contrib evaluator packages under evaluators/contrib."""

    packages: list[ContribPackage] = []

    if not CONTRIB_ROOT.is_dir():
        raise ContribPackagesError(
            f"Expected contrib root at {display_path(CONTRIB_ROOT)}, but it does not exist."
        )

    for candidate in sorted(CONTRIB_ROOT.iterdir(), key=lambda path: path.name):
        if not candidate.is_dir() or candidate.name == "template":
            continue

        manifest_path = candidate / "pyproject.toml"
        if not manifest_path.is_file():
            continue

        manifest = load_toml(manifest_path)
        project = require_table(manifest, "project", path=manifest_path, parent_description="")
        project_name = require_string(
            project.get("name"),
            path=manifest_path,
            description='[project].name',
        )

