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

        entry_points = require_table(
            project,
            "entry-points",
            path=manifest_path,
            parent_description="project",
        )
        evaluator_entries = entry_points.get(EVALUATOR_ENTRY_GROUP)
        if not isinstance(evaluator_entries, dict) or not evaluator_entries:
            raise ContribPackagesError(
                f"{display_path(manifest_path)} must define at least one "
                f'[project.entry-points."{EVALUATOR_ENTRY_GROUP}"] entry.'
            )

        expected_package_name = f"agent-control-evaluator-{candidate.name}"
        if project_name != expected_package_name:
            raise ContribPackagesError(
                f"{display_path(manifest_path)} declares project.name = {project_name!r}, "
                f"but contrib package {candidate.name!r} must use {expected_package_name!r}."
            )

        packages.append(
            ContribPackage(
                name=candidate.name,
                directory=display_path(candidate),
                package=expected_package_name,
                extra=candidate.name,
            )
        )

    return packages


def verify_contrib_packages(packages: list[ContribPackage]) -> list[str]:
    """Return human-readable verification errors for contrib wiring drift."""

    root_pyproject_path = REPO_ROOT / "pyproject.toml"
    builtin_pyproject_path = REPO_ROOT / "evaluators" / "builtin" / "pyproject.toml"

    root_pyproject = load_toml(root_pyproject_path)
    builtin_pyproject = load_toml(builtin_pyproject_path)

    tool_table = require_table(root_pyproject, "tool", path=root_pyproject_path, parent_description="")
    semantic_release = require_table(
        tool_table,
        "semantic_release",
        path=root_pyproject_path,
        parent_description="tool",
    )
    version_toml = semantic_release.get("version_toml")
    if not isinstance(version_toml, list) or not all(isinstance(item, str) for item in version_toml):
        raise ContribPackagesError(
            f"{display_path(root_pyproject_path)} must define [tool.semantic_release].version_toml "
            "as a list of strings."
        )

    builtin_project = require_table(
        builtin_pyproject,
        "project",
        path=builtin_pyproject_path,
        parent_description="",
    )
    optional_dependencies = require_table(
        builtin_project,
        "optional-dependencies",
        path=builtin_pyproject_path,
        parent_description="project",
    )

    builtin_tool = require_table(
        builtin_pyproject,
        "tool",
        path=builtin_pyproject_path,
