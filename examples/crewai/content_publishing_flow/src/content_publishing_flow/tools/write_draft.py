from agent_control import control


async def _write_draft(topic: str, audience: str, content_type: str, research: str) -> str:
    """Write a content draft based on research. Returns simulated draft."""
    # The REGEX control blocks PII; the LIST control blocks banned topics.
    if content_type == "blog_post":
        return (
            f"# {topic}: What You Need to Know\n\n"
            f"*Written for {audience}*\n\n"
            f"## Introduction\n"
            f"The landscape of {topic} is evolving rapidly. Industry leaders are "
            f"taking notice, and for good reason.\n\n"
            f"## Key Findings\n"
            f"Our research reveals several important trends that professionals "
            f"should be aware of. Early adopters are seeing measurable returns.\n\n"
            f"## What This Means For You\n"
            f"Whether you are a seasoned professional or just getting started, "
            f"understanding these trends is essential for staying competitive.\n\n"
            f"## Conclusion\n"
            f"The data is clear: {topic} represents a significant opportunity. "
            f"Now is the time to act.\n"
        )
    elif content_type == "press_release":
        return (
            f"FOR IMMEDIATE RELEASE\n\n"
            f"{topic}\n\n"
