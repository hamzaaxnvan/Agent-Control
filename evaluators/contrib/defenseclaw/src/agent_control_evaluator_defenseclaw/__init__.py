"""Agent Control DefenseClaw external evaluators."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agent-control-evaluator-defenseclaw")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

