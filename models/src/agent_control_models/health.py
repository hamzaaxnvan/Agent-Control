"""Health check models."""

from .base import BaseModel


class HealthResponse(BaseModel):
    """
    Health check response model.

    Attributes:
        status: Current health status (e.g., "healthy", "degraded", "unhealthy")
        version: Application version
    """

    status: str
    version: str

