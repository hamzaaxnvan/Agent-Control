#!/usr/bin/env python3
"""Set up the target-context demo: agent + two controls + one binding.

Layout:

- ``block-pii-output`` is attached directly to the agent. It applies on
  every call regardless of target context.
- ``block-prod-restricted-input`` is bound to ``(env, prod)`` via a
  control binding. It applies only when the SDK's session target is
  ``(env, prod)`` and is omitted from the merged set otherwise.

When the demo agent calls ``init(target_type="env", target_id="prod")``,
the server returns the de-duplicated union: both controls. Re-init for a
different ``env`` value (or no target) drops the prod-bound control from
the returned set.

Prerequisites:
    - Agent Control server running at AGENT_CONTROL_URL (default localhost:8000).

Usage:
    uv run python examples/target_context_demo/setup_controls.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

# Add the SDK to path for development.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../sdks/python/src"))
