import json
import time

from agent_control import control


async def _publish_content(content: str, content_type: str) -> str:
    """Publish content. Final PII scan happens as a pre-check."""
    return json.dumps({
