"""Built-in :class:`RequestAuthorizer` implementations."""

from .header import AccessLevel, HeaderAuthProvider
from .http_upstream import HttpUpstreamAuthProvider
