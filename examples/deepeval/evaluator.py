"""DeepEval GEval evaluator implementation.

This evaluator demonstrates how to extend the base Evaluator class to integrate
DeepEval's GEval metric for custom LLM-based evaluations.

Based on DeepEval documentation: https://deepeval.com/docs/metrics-llm-evals
"""

import logging
from typing import Any

from agent_control_evaluators import (
    Evaluator,
    EvaluatorMetadata,
    register_evaluator,
)
from agent_control_models import EvaluatorResult

from config import DeepEvalEvaluatorConfig

logger = logging.getLogger(__name__)

# Check if deepeval is available
try:
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams

    DEEPEVAL_AVAILABLE = True
except ImportError:
    DEEPEVAL_AVAILABLE = False
    GEval = None  # type: ignore
    LLMTestCase = None  # type: ignore
    LLMTestCaseParams = None  # type: ignore


@register_evaluator
class DeepEvalEvaluator(Evaluator[DeepEvalEvaluatorConfig]):
    """DeepEval GEval evaluator for custom LLM-based evaluations.

    This evaluator uses DeepEval's GEval metric, which leverages LLM-as-a-judge
    with chain-of-thoughts (CoT) to evaluate LLM outputs based on custom criteria.

    Features:
        - Custom evaluation criteria or step-by-step evaluation logic
        - Multiple test case parameters (input, output, context, etc.)
        - Configurable LLM model for judging
        - Binary or continuous scoring modes
        - Automatic chain-of-thought generation

    Example:
        ```python
        from examples.deepeval import DeepEvalEvaluator, DeepEvalEvaluatorConfig

        # Create config
        config = DeepEvalEvaluatorConfig(
            name="Coherence",
            criteria="Determine if the response is coherent and logically consistent.",
            evaluation_params=["actual_output"],
