"""SecureResearchCrew -- @CrewBase class definition."""

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from secure_research_crew.tools.query_database import query_database
from secure_research_crew.tools.validate_data import validate_data
from secure_research_crew.tools.write_report import write_report


@CrewBase
class SecureResearchCrew:
    """Multi-agent research crew with per-agent Agent Control policies."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["researcher"],  # type: ignore[index]
            tools=[query_database],
            verbose=True,
        )

    @agent
    def analyst(self) -> Agent:
        return Agent(
