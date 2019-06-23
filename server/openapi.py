"""Generate OpenAPI specification for multi-language SDK generation."""

import argparse
import json
from pathlib import Path

from agent_control_server.main import app


def generate_openapi_spec(output_path: str = "server/.generated/openapi.json") -> None:
    """
    Generate OpenAPI specification file.

    This spec can be used to generate SDKs for multiple languages using tools like:
    - openapi-generator (supports 50+ languages)
    - swagger-codegen
    - Language-specific generators (typescript-axios, go-client, etc.)
