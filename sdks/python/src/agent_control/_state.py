"""
Global state management for Agent Control SDK.

This module holds global state in a container object to avoid circular imports
between __init__.py and other modules. Both modules can import and modify
the same state object.
"""

from typing import TYPE_CHECKING, Any
