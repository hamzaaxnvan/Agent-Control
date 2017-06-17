"""Authorizer for deployments that intentionally disable authentication."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from ...models import DEFAULT_NAMESPACE_KEY
