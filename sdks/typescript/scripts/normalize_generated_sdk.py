#!/usr/bin/env python3
"""Normalize generated TypeScript SDK files for deterministic output."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def _strip_generated_validation_error_context_fields(file_path: Path) -> None:
    original = file_path.read_text(encoding="utf-8")
    normalized = original
    normalized = re.sub(r"export type Context = \{\};\n\n", "", normalized)
    normalized = re.sub(
        r"\n  ctx\?: Context \| undefined;\n  input\?: any \| undefined;",
        "",
        normalized,
    )
    normalized = re.sub(
        r"/\*\* @internal \*/\n"
        r"export const Context\$inboundSchema: z\.ZodMiniType<Context, unknown> = z\.object\(\n"
        r"  \{},\n"
        r"\);\n\n"
        r"export function contextFromJSON\(\n"
        r"  jsonString: string,\n"
        r"\): SafeParseResult<Context, SDKValidationError> \{\n"
        r"  return safeParse\(\n"
        r"    jsonString,\n"
        r"    \(x\) => Context\$inboundSchema\.parse\(JSON\.parse\(x\)\),\n"
        r"    `Failed to parse 'Context' from JSON`,\n"
        r"  \);\n"
        r"\}\n\n",
        "",
        normalized,
    )
    normalized = re.sub(
        r"  ctx: types\.optional\(z\.lazy\(\(\) => Context\$inboundSchema\)\),\n"
        r"  input: types\.optional\(z\.any\(\)\),\n",
        "",
        normalized,
    )

    if normalized != original:
        file_path.write_text(normalized, encoding="utf-8")


def _normalize_sdk_metadata_version(file_path: Path) -> None:
    original = file_path.read_text(encoding="utf-8")
    normalized = re.sub(
        r'openapiDocVersion: "[^"]+",',
        'openapiDocVersion: "0.0.0",',
        original,
    )
    normalized = re.sub(
        r'userAgent: "speakeasy-sdk/typescript ([^"]+) ([^"]+) [^"]+ ([^"]+)",',
        r'userAgent: "speakeasy-sdk/typescript \1 \2 0.0.0 \3",',
        normalized,
    )

    if normalized != original:
        file_path.write_text(normalized, encoding="utf-8")


def _strip_unstable_type_comments(file_path: Path) -> None:
    original = file_path.read_text(encoding="utf-8")
