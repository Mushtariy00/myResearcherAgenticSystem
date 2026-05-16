from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent

from agentic_ai_system.tools import ArxivSearchTool, SemanticScholarSearchTool

@CrewBase
class AgenticAiSystem():
    """AgenticAiSystem crew"""

    agents: list[BaseAgent]
    tasks: list[Task]
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # Learn more about YAML configuration files here:
    # Agents: https://docs.crewai.com/concepts/agents#yaml-configuration-recommended
    # Tasks: https://docs.crewai.com/concepts/tasks#yaml-configuration-recommended
    
    # If you would like to add tools to your agents, you can learn more about it here:
    # https://docs.crewai.com/concepts/agents#agent-tools
    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config['researcher'], # type: ignore[index]
            tools=[ArxivSearchTool(), SemanticScholarSearchTool()],
            verbose=True
        )

    @agent
    def research_synthesizer(self) -> Agent:
        return Agent(
            config=self.agents_config['researcher'], # type: ignore[index]
            verbose=True
        )

    @agent
    def reporting_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['reporting_analyst'], # type: ignore[index]
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

    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config['research_task'], # type: ignore[index]
        )

    @task
    def reporting_task(self) -> Task:
        return Task(
            config=self.tasks_config['reporting_task'], # type: ignore[index]
            output_file='report.md'
        )

    @crew
    def crew(self) -> Crew:
        """Creates the AgenticAiSystem crew"""
        # To learn how to add knowledge sources to your crew, check out the documentation:
        # https://docs.crewai.com/concepts/knowledge#what-is-knowledge

        return Crew(
            agents=self.agents, # Automatically created by the @agent decorator
            tasks=self.tasks, # Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
            # process=Process.hierarchical, # In case you wanna use that instead https://docs.crewai.com/how-to/Hierarchical/
        )
