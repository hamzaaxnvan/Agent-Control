import json

from agent_control import control


async def _validate_request(request: dict) -> str:
    """Validate that the content request has required fields."""
    # The JSON evaluator on the server checks for topic, audience, content_type.
    # If they are present the control passes; if missing it denies.
    topic = request.get("topic", "")
    audience = request.get("audience", "")
