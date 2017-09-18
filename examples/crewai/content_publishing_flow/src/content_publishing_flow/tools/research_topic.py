from agent_control import control


async def _research_topic(topic: str, audience: str) -> str:
    """Research a topic. Returns simulated research notes."""
    # Simulated output - the LIST control checks for banned sources in output.
    return (
        f"Research findings on '{topic}' for {audience}:\n\n"
        f"1. Industry reports from McKinsey and Gartner highlight growing adoption.\n"
        f"2. Academic papers from MIT and Stanford confirm key trends.\n"
