<p align="center">
  <img
    src="docs/images/AgentControl-logo-light.svg#gh-light-mode-only"
    alt="Agent Control Logo (light)"
    width="120"
  />
  <img
    src="docs/images/AgentControl-logo-dark.svg#gh-dark-mode-only"
    alt="Agent Control Logo (dark)"
    width="120"
  />
</p>

<h1 align="center">Agent Control</h1>

<p align="center">
</p>

<p align="center">
  <a href="https://agentcontrol.dev">Agent Control Website</a> |
  <a href="https://docs.agentcontrol.dev/">Docs</a> |
  <a href="https://docs.agentcontrol.dev/core/quickstart">Quickstart</a> |
  <a href="examples/README.md">Examples</a> |
  <a href="https://join.slack.com/t/agentcontrol/shared_invite/zt-3se2g6d68-iGmNdRfGcD31cZ0vELMPxw">Slack</a>
</p>

Enforce runtime guardrails through a centralized control layer—configure once and apply across all agents. Agent Control evaluates inputs and outputs against configurable rules to block prompt injections, PII leakage, and other risks without changing your agent’s code.

![Agent Control Overview](docs/images/AgentControlDiagram.png)

- **Centralized safety** - define controls once, apply across agents, update without redeploying
- **Runtime configuration** - manage controls via API or UI, no code changes needed
- **Pluggable evaluators** - built-in (regex, list, JSON, SQL) or bring your own
- **Framework support** - works with LangChain, CrewAI, Google ADK, AWS Strands, and more

## Quick Start

Prerequisites: Docker (or Podman, see [Podman setup](#podman-setup)) and Python 3.12+.

Quick start flow:

```
Start server
  ↓
Install SDK
  ↓
Wrap a model or tool call with @control() and register your agent
  ↓
Create controls (UI or SDK/API)
```

### 1. Start the server

No repo clone required:

```bash
curl -L https://raw.githubusercontent.com/agentcontrol/agent-control/refs/heads/main/docker-compose.yml | docker compose -f - up -d
```

This starts PostgreSQL and Agent Control at `http://localhost:8000`, including
the UI/dashboard.  

Note: This starts server without API keys configured which is dangerous for any real world usage.  

Set appropirate env vars to override defaults like:
 * Exposed ports
 * Agent and admin API keys
 * Postgres DB Password

```bash
export AGENT_CONTROL_SERVER_HOST_PORT=18000
export AGENT_CONTROL_DB_HOST_PORT=15432
export AGENT_CONTROL_API_KEY_ENABLED=true
export AGENT_CONTROL_API_KEYS="agent-api-key"
export AGENT_CONTROL_ADMIN_API_KEYS="admin-api-key"
export AGENT_CONTROL_POSTGRES_PASSWORD="postgres-password"

curl -L https://raw.githubusercontent.com/agentcontrol/agent-control/refs/heads/main/docker-compose.yml | docker compose -f - up -d
```

Verify it is up:

```bash
curl http://localhost:8000/health
```

If you changed `AGENT_CONTROL_SERVER_HOST_PORT`, use that port in the health check URL.

### 2. Install the SDK

Run this in your agent project directory.

Python:

```bash
uv venv
source .venv/bin/activate
uv pip install agent-control-sdk
```

TypeScript:

- See the [TypeScript SDK example](examples/typescript_sdk/README.md).

### 3. Wrap a call and register your agent

```python
# my_agent.py

import asyncio
import agent_control
from agent_control import control, ControlViolationError

# Protect any function (like LLM calls)

@control()
async def chat(message: str) -> str:
    # In production: response = await LLM.ainvoke(message)
    # For demo: simulate LLM that might leak sensitive data
    if "test" in message.lower():
        return "Your SSN is 123-45-6789"  # Will be blocked!
    return f"Echo: {message}"

# Initialize your agent

agent_control.init(
    agent_name="awesome_bot_3000",  # Unique name
    agent_description="My Chatbot",
)

async def main():
    try:
        print(await chat("test"))  # ❌ Blocked
    except ControlViolationError as e:
        print(f"❌ Blocked: {e.control_name}")
    finally:
        await agent_control.ashutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

Use `agent_control.shutdown()` or `await agent_control.ashutdown()` before process exit so short-lived scripts flush pending observability events cleanly.

External integrations can register a sink for the same finalized
control-event payloads and then select it through observability config:

```python
from agent_control import (
    register_control_event_sink,
    unregister_control_event_sink,
)
from agent_control_telemetry import BaseControlEventSink, SinkResult

class MyControlEventSink(BaseControlEventSink):
    def write_events(self, events):
        for event in events:
            forward_to_external_system(event.model_dump(mode="json"))
        return SinkResult(accepted=len(events), dropped=0)

sink = MyControlEventSink()
register_control_event_sink(sink)

# Select registered sinks instead of the default SDK -> server sink.
agent_control.init(
    agent_name="awesome_bot_3000",
    observability_enabled=True,
    observability_sink_name="registered",
)

# Later, when tearing down the integration:
unregister_control_event_sink(sink)
```

Registered sinks receive the same local, server, and merged control-execution
events the SDK emits through its normal event-construction flow. The default
SDK sink remains the OSS path to the Agent Control server. To use registered
or named custom sinks, set `observability_sink_name` explicitly.

The SDK also includes a built-in OpenTelemetry sink. Install the OTEL extra,
