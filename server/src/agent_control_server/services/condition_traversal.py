"""Shared condition-tree traversal helpers."""

from collections.abc import Iterator

from agent_control_models import ConditionNode


def iter_condition_leaves_with_paths(
    node: ConditionNode,
    *,
    path: str,
) -> Iterator[tuple[str, ConditionNode]]:
    """Yield each leaf condition with its dotted/bracketed field path."""
    if node.is_leaf():
