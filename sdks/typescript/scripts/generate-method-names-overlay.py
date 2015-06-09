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


def singularize(token: str) -> str:
    if token.endswith("ies") and len(token) > 3:
        return f"{token[:-3]}y"
    if token.endswith("s") and not token.endswith("ss") and len(token) > 1:
        return token[:-1]
    return token


def pluralize(token: str) -> str:
    if token.endswith("y") and len(token) > 1 and token[-2] not in "aeiou":
        return f"{token[:-1]}ies"
    if token.endswith("s"):
        return token
    return f"{token}s"


def lower_camel(tokens: list[str]) -> str:
    if not tokens:
        return "call"
    first = tokens[0].lower()
    rest = "".join(token.capitalize() for token in tokens[1:])
    return f"{first}{rest}"


def infer_group(path: str, op: dict[str, object]) -> tuple[str, list[str]]:
    tags = op.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and tag:
                tag_tokens = split_tokens(tag)
                if tag_tokens:
                    return lower_camel(tag_tokens), tag_tokens

    path_tokens = [
        segment
        for segment in path.strip("/").split("/")
        if segment and not (segment.startswith("{") and segment.endswith("}"))
    ]
    for segment in path_tokens:
        if segment in {"api", "v1"}:
            continue
        segment_tokens = split_tokens(segment)
        if segment_tokens:
            return lower_camel(segment_tokens), segment_tokens
    return "system", ["system"]


def build_tokens(path: str, method: str, op: dict[str, object]) -> list[str]:
    raw_operation_id = op.get("operationId")
    if isinstance(raw_operation_id, str) and raw_operation_id:
        prefix = re.sub(r"_api_v\d+.*$", "", raw_operation_id)
        prefix = re.sub(r"_(get|post|put|patch|delete|options|head|trace)$", "", prefix)
        operation_tokens = split_tokens(prefix)
        if len(operation_tokens) >= 3 and operation_tokens[-1] == operation_tokens[0]:
            operation_tokens = operation_tokens[:-1]
        if operation_tokens:
            return operation_tokens

    path_tokens = []
    for segment in path.strip("/").split("/"):
        if not segment or (segment.startswith("{") and segment.endswith("}")):
            continue
        path_tokens.extend(split_tokens(segment))
    return [method, *path_tokens]


