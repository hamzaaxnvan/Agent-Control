#!/usr/bin/env python3
"""Demo agent: target context fixed at SDK init().

Walks through every touchpoint of the V1 contract:

1. ``init(target_type=..., target_id=...)`` returns the merged effective
   set (direct attachments + policy-derived + target bindings).
2. ``@control()`` decorator runs automatically against that merged set.
3. ``evaluate_controls(...)`` defaults its target context from the
   session, so callers don't need to repeat themselves.
4. A per-call target that disagrees with the session target is rejected
   with a clear ``ValueError``: the SDK supports one target per session.

Prerequisites:
    - Agent Control server running.
    - ``setup_controls.py`` executed first to provision the agent + bindings.

Usage:
    uv run python examples/target_context_demo/demo_agent.py
"""

from __future__ import annotations

import asyncio
import os
import sys
