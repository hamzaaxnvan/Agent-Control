from agent_control import control


async def _fact_check(research_text: str) -> str:
    """Fact-check research output. Returns simulated verification report."""
    # The REGEX control checks output for unverified-claim markers.
    return (
