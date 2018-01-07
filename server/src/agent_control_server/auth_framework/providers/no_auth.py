"""Authorizer for deployments that intentionally disable authentication."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from ...models import DEFAULT_NAMESPACE_KEY
from ..core import Operation, Principal, RequestAuthorizer


class NoAuthProvider(RequestAuthorizer):
    """Allows every operation and returns the default namespace."""

    def __init__(self, *, default_namespace_key: str = DEFAULT_NAMESPACE_KEY) -> None:
        self._default_namespace_key = default_namespace_key

    async def authorize(
