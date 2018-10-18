#!/usr/bin/env python3
"""Generate a deterministic Speakeasy overlay for short SDK method names."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

HTTP_METHOD_ORDER: tuple[str, ...] = (
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
    "trace",
)
HTTP_METHOD_RANK = {method: idx for idx, method in enumerate(HTTP_METHOD_ORDER)}
PREPOSITIONS = {"to", "from", "for", "in", "on", "of", "with", "by"}
VERB_RENAMES = {"patch": "update", "set": "update"}
METHOD_NAME_EXCEPTIONS: dict[tuple[str, str], str] = {
    ("/api/v1/controls/{control_id}", "patch"): "updateMetadata",
}


@dataclass(frozen=True)
class Operation:
    path: str
    method: str
    group: str
    group_tokens: list[str]
    tokens: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate TypeScript method-name overlay from OpenAPI schema.",
    )
    parser.add_argument(
        "--schema",
        required=True,
        help="Path to OpenAPI JSON schema.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Overlay YAML output path.",
    )
    return parser.parse_args()


def split_tokens(value: str) -> list[str]:
    raw_parts = [part for part in re.split(r"[^A-Za-z0-9]+", value) if part]
    tokens: list[str] = []
    for part in raw_parts:
        split_part = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", part).split()
        tokens.extend(piece.lower() for piece in split_part if piece)
    return tokens


