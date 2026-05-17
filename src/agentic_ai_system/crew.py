from crewai import Agent
from crewai.project import CrewBase, agent
from crewai.agents.agent_builder.base_agent import BaseAgent

@CrewBase
class AgenticAiSystem():
    """Agent factory used by the supervisor flow."""

    agents: list[BaseAgent]
    agents_config = "config/agents.yaml"

    @agent
    def research_synthesizer(self) -> Agent:
        return Agent(
            config=self.agents_config['researcher'], # type: ignore[index]
            verbose=True
        )

    @agent
    def method_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['method_analyst'], # type: ignore[index]
            verbose=True
        )

    @agent
    def coding_architect(self) -> Agent:
        return Agent(
            config=self.agents_config['coding_architect'], # type: ignore[index]
            verbose=True
        )

    @agent
    def experiment_designer(self) -> Agent:
        return Agent(
            config=self.agents_config['experiment_designer'], # type: ignore[index]
            verbose=True
        )

    @agent
    def writing_strategist(self) -> Agent:
        return Agent(
            config=self.agents_config['writing_strategist'], # type: ignore[index]
            verbose=True
        )
