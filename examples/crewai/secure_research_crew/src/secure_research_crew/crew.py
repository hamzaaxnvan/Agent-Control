"""SecureResearchCrew -- @CrewBase class definition."""

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from secure_research_crew.tools.query_database import query_database
from secure_research_crew.tools.validate_data import validate_data
from secure_research_crew.tools.write_report import write_report


@CrewBase
class SecureResearchCrew:
    """Multi-agent research crew with per-agent Agent Control policies."""

