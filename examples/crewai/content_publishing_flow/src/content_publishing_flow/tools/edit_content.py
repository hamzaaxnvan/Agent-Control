from agent_control import control


async def _edit_content(content: str, include_executive_summary: bool = False) -> str:
    """Edit content for quality. REGEX blocks PII; STEER requires exec summary."""
    if include_executive_summary:
        summary_section = (
            "## Executive Summary\n\n"
            "This press release announces key developments that position the company "
            "for significant growth. Stakeholders should note the strategic partnerships "
            "and projected impact outlined below.\n\n"
