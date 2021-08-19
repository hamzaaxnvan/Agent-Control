"""Agent Control Engine - Rule execution logic and evaluator system."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agent-control-engine")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"
