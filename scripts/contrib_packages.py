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
