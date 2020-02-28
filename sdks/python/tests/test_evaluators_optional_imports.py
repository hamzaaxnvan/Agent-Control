"""Coverage for the optional galileo import fallbacks in agent_control.evaluators.

The galileo extras are normally installed in the dev environment, so the
``except ImportError`` branches in ``agent_control/evaluators/__init__.py``
never fire under regular tests. This module forces those failures by hiding
the relevant modules in ``sys.modules`` and reloading the package.
"""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import sys

import pytest


def _module_available(name: str) -> bool:
    """Return whether ``name`` resolves without raising for missing parents."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        # ``find_spec`` raises ModuleNotFoundError (a subclass of ImportError)
        # when a *parent* package is missing, instead of returning None. Treat
        # that as "not installed."
        return False


_GALILEO_INSTALLED = _module_available("agent_control_evaluator_galileo.luna")
_GALILEO_LLM_INSTALLED = _module_available("agent_control_evaluator_galileo.llm")


def _reload_evaluators_with_blocked(prefix: str) -> object:
    """Reload ``agent_control.evaluators`` while ``prefix.*`` imports fail.
