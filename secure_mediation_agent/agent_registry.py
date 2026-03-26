# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Agent registry for storing and managing agent information."""

import json
import os
from pathlib import Path
from typing import Any

from models import AgentInfo


class AgentRegistry:
    """Registry for managing agents in the platform."""

    def __init__(self, storage_path: str = "agent_store.json"):
        """Initialize the agent registry.

        Args:
            storage_path: Path to the JSON file for storing agent data.
        """
        self.storage_path = storage_path
        self.agents: dict[str, AgentInfo] = {}
        self._load_agents()

    def _load_agents(self) -> None:
        """Load agents from storage."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for agent_data in data.get("agents", []):
                        agent = AgentInfo(**agent_data)
                        self.agents[agent.name] = agent
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error loading agents: {e}")
                self.agents = {}

    def _save_agents(self) -> None:
        """Save agents to storage."""
        data = {
            "agents": [agent.to_dict() for agent in self.agents.values()]
        }
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def register_agent(self, agent: AgentInfo) -> None:
        """Register a new agent.

        Args:
            agent: The agent information to register.
        """
        self.agents[agent.name] = agent
        self._save_agents()

    def register_agent_from_card(self, card_path: str) -> AgentInfo:
        """Register an agent from an agent card JSON file.

        Args:
            card_path: Path to the agent card JSON file.

        Returns:
            The registered agent info.
        """
        with open(card_path, 'r', encoding='utf-8') as f:
            card_data = json.load(f)

        agent = AgentInfo(
            name=card_data.get("name", ""),
            description=card_data.get("description", ""),
            url=card_data.get("url", ""),
            version=card_data.get("version", "1.0.0"),
            trust_score=card_data.get("trust_score", 0.5),
            capabilities=card_data.get("capabilities", {}),
            skills=card_data.get("skills", []),
            input_modes=card_data.get("defaultInputModes", ["text/plain"]),
            output_modes=card_data.get("defaultOutputModes", ["application/json"]),
        )

        self.register_agent(agent)
        return agent

    def get_agent(self, name: str) -> AgentInfo | None:
        """Get an agent by name.

        Args:
            name: The agent name.

        Returns:
            The agent info, or None if not found.
        """
        return self.agents.get(name)

    def search_agents(
        self,
        query: str = "",
        min_trust_score: float = 0.0,
        required_skills: list[str] | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> list[AgentInfo]:
        """Search for agents matching criteria.

        Args:
            query: Text query to match against name and description.
            min_trust_score: Minimum trust score threshold.
            required_skills: List of required skill IDs or tags.
            capabilities: Required capabilities.

        Returns:
            List of matching agents.
        """
        results = []

        for agent in self.agents.values():
            # Filter by trust score
            if agent.trust_score < min_trust_score:
                continue

            # Filter by query
            if query:
                query_lower = query.lower()
                if query_lower not in agent.name.lower() and query_lower not in agent.description.lower():
                    # Check skills
                    skill_match = False
                    for skill in agent.skills:
                        skill_name = skill.get("name", "").lower()
                        skill_desc = skill.get("description", "").lower()
                        skill_tags = [tag.lower() for tag in skill.get("tags", [])]

                        if (query_lower in skill_name or
                            query_lower in skill_desc or
                            query_lower in ' '.join(skill_tags)):
                            skill_match = True
                            break

                    if not skill_match:
                        continue

            # Filter by required skills
            if required_skills:
                agent_skill_ids = {skill.get("id", "") for skill in agent.skills}
                agent_skill_tags = set()
                for skill in agent.skills:
                    agent_skill_tags.update(skill.get("tags", []))

                has_all_skills = all(
                    req_skill in agent_skill_ids or req_skill in agent_skill_tags
                    for req_skill in required_skills
                )

                if not has_all_skills:
                    continue

            # Filter by capabilities
            if capabilities:
                has_all_caps = all(
                    agent.capabilities.get(cap_key) == cap_value
                    for cap_key, cap_value in capabilities.items()
                )

                if not has_all_caps:
                    continue

            results.append(agent)

        # Sort by trust score (descending)
        results.sort(key=lambda a: a.trust_score, reverse=True)

        return results

    def update_trust_score(
        self,
        agent_name: str,
        success: bool,
        anomaly_detected: bool = False,
    ) -> None:
        """Update an agent's trust score based on execution results.

        Args:
            agent_name: The agent name.
            success: Whether the execution was successful.
            anomaly_detected: Whether an anomaly was detected.
        """
        agent = self.agents.get(agent_name)
        if not agent:
            return

        agent.execution_count += 1

        if success:
            agent.success_count += 1

        if anomaly_detected:
            agent.anomaly_count += 1

        # Calculate new trust score using exponential moving average
        # Success rate component (0-0.7)
        success_rate = agent.success_count / agent.execution_count if agent.execution_count > 0 else 0.5
        success_component = success_rate * 0.7

        # Anomaly penalty component (0-0.3)
        anomaly_rate = agent.anomaly_count / agent.execution_count if agent.execution_count > 0 else 0.0
        anomaly_component = (1 - anomaly_rate) * 0.3

        new_score = success_component + anomaly_component

        # Smooth the update with exponential moving average
        alpha = 0.3  # Learning rate
        agent.trust_score = alpha * new_score + (1 - alpha) * agent.trust_score

        # Ensure score is in [0, 1]
        agent.trust_score = max(0.0, min(1.0, agent.trust_score))

        self._save_agents()

    def list_all_agents(self) -> list[AgentInfo]:
        """List all registered agents.

        Returns:
            List of all agents.
        """
        return list(self.agents.values())
