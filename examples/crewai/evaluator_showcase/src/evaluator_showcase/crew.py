"""CrewBase crew definition for the Evaluator Showcase."""

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from evaluator_showcase.tools import create_sql_tool, create_analysis_tool


@CrewBase
class EvaluatorShowcaseCrew:
    """Data analyst crew demonstrating all evaluator types."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def data_analyst(self) -> Agent:
        sql_tool = create_sql_tool()
