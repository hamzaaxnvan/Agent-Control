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
