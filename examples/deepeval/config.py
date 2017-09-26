"""Configuration models for DeepEval GEval evaluator.

Based on DeepEval's GEval metric: https://deepeval.com/docs/metrics-llm-evals
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# DeepEval's LLMTestCaseParams enum values
DeepEvalTestCaseParam = Literal[
    "input",
    "actual_output",
    "expected_output",
    "context",
    "retrieval_context",
    "tools_called",
    "expected_tools",
    "mcp_servers",
    "mcp_tools_called",
    "mcp_resources_called",
    "mcp_prompts_called",
]


class DeepEvalEvaluatorConfig(BaseModel):
    """Configuration for DeepEval GEval evaluator.

    DeepEval's GEval uses LLM-as-a-judge with chain-of-thoughts (CoT) to evaluate
    LLM outputs based on custom criteria. It's capable of evaluating almost any
    use case with human-like accuracy.

    Example (with criteria):
        ```python
        config = DeepEvalEvaluatorConfig(
            name="Correctness",
            criteria="Determine if the actual output is correct based on the expected output.",
            evaluation_params=["actual_output", "expected_output"],
            threshold=0.5,
        )
        ```

    Example (with evaluation_steps):
        ```python
        config = DeepEvalEvaluatorConfig(
            name="Correctness",
            evaluation_steps=[
                "Check whether facts in actual output contradict expected output",
                "Heavily penalize omission of detail",
                "Vague language or contradicting opinions are acceptable"
            ],
            evaluation_params=["actual_output", "expected_output"],
            threshold=0.5,
        )
        ```
    """

    name: str = Field(
        description="Name identifier for the custom metric (e.g., 'Correctness', 'Relevance')"
    )

    criteria: str | None = Field(
        default=None,
        description="Description outlining the specific evaluation aspects. Either provide criteria OR evaluation_steps, not both.",
    )

    evaluation_steps: list[str] | None = Field(
        default=None,
