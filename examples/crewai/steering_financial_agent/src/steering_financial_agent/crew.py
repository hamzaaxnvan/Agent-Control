"""CrewBase class for the financial operations crew."""

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from steering_financial_agent.tools.process_transfer import create_transfer_tool


@CrewBase
class SteeringFinancialCrew:
    """Financial operations crew with Agent Control steering."""

