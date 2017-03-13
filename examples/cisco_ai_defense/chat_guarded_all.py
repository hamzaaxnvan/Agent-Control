"""Combined decorator-based example showing pre and post checks.

Demonstrates three cases with server-managed Cisco AI Defense Chat Inspection:
- Safe request → safe response (allowed)
- Unsafe request (pre) → blocked before model runs
- Safe request → unsafe response (post) → blocked

Prereqs:
  1) Run the server and assign API keys
  2) Install the Cisco AI Defense evaluator (this repo package) into the server env
  3) Seed controls and attach to the agent with examples/cisco_ai_defense/setup_ai_defense_controls.py
  4) Set env: AGENT_CONTROL_URL, AGENT_CONTROL_API_KEY

Run:
  uv run chat_guarded_all.py --agent-name demo-bot
"""

from __future__ import annotations

import argparse
