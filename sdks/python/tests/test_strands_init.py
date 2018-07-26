"""Unit tests for Strands integration __init__.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_strands_init_exports():
    """Test that __init__.py exports the expected classes."""
    # Mock the strands modules to avoid import errors
    with patch.dict(
        "sys.modules",
        {
            "strands": MagicMock(),
            "strands.hooks": MagicMock(),
            "strands.plugins": MagicMock(),
            "strands.experimental": MagicMock(),
            "strands.experimental.steering": MagicMock(),
        },
