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

"""Matching sub-agent for finding and ranking agents."""

import json
import os
from typing import Any

import httpx
from google.adk import Agent
from google.genai import types
from ..config.safety import SAFETY_SETTINGS_RELAXED

# Agent Store API configuration
# Default to 127.0.0.1:8001 for container deployment (trusted_agent_store internal port)
# In Cloud Run container, nginx is on 8080, but trusted_agent_store listens directly on 8001
# Override via environment variable for different configurations
AGENT_STORE_API_URL = os.getenv("AGENT_STORE_API_URL", "http://127.0.0.1:8001/api/agents")


async def fetch_agent_card(agent_url: str) -> dict[str, Any]:
    """Fetch agent card from the agent's well-known endpoint.

    Args:
        agent_url: Base URL of the agent.

    Returns:
        Agent card dictionary.
    """
    try:
        # A2A spec: agent cards are available at /.well-known/agent-card.json
        card_url = f"{agent_url.rstrip('/')}/.well-known/agent-card.json"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(card_url)
            response.raise_for_status()
            return response.json()

    except Exception as e:
        return {
            "error": f"Failed to fetch agent card: {str(e)}",
            "url": agent_url,
        }


def _convert_agent_entry_to_matcher_format(agent: dict[str, Any]) -> dict[str, Any]:
    """Convert Agent Store API response to matcher format.

    Args:
        agent: Agent entry from trusted_agent_store API.

    Returns:
        Agent dictionary in matcher format.
    """
    # Extract skills from tags and use_cases
    skills = []
    tags = agent.get("tags", []) or []
    use_cases = agent.get("use_cases", []) or []

    # Create skills from use_cases with tags
    for use_case in use_cases:
        skills.append({
            "id": use_case.replace(" ", "_").lower(),
            "tags": tags + [use_case.lower()],
        })

    # If no use_cases, create a generic skill from tags
    if not skills and tags:
        skills.append({
            "id": "general",
            "tags": tags,
        })

    # Use trust_score directly from agent store (0-100 scale)
    trust_score_raw = agent.get("trust_score")
    if trust_score_raw is not None:
        trust_score = float(trust_score_raw)
    else:
        trust_score = 50.0  # Default trust score (middle of 0-100 scale)

    return {
        "name": agent.get("name", "unknown"),
        "url": agent.get("endpoint_url") or agent.get("agent_card_url", ""),
        "description": ", ".join(use_cases) if use_cases else f"Agent: {agent.get('name', 'unknown')}",
        "skills": skills,
        "capabilities": {
            "booking": any("booking" in t.lower() for t in tags),
            "search": any("search" in t.lower() for t in tags),
        },
        "trust_score": trust_score,
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "provider": agent.get("provider", ""),
        "status": agent.get("status", "unknown"),
        "agent_id": agent.get("id", ""),
    }


async def search_agent_store(
    query: str,
) -> str:
    """Search the agent store for matching agents.

    Fetches agents from the trusted_agent_store API and filters them
    based on the search query.

    Args:
        query: Search query describing needed capabilities.

    Returns:
        JSON string with search results.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Fetch all active agents from the Agent Store API
            response = await client.get(
                AGENT_STORE_API_URL,
                params={"status": "active", "limit": 100},
            )
            response.raise_for_status()
            data = response.json()

        # Convert API response to matcher format
        all_agents = [
            _convert_agent_entry_to_matcher_format(agent)
            for agent in data.get("items", [])
        ]

        # Filter agents based on query keywords
        query_lower = query.lower()
        query_keywords = query_lower.split()
        filtered_agents = []

        for agent in all_agents:
            matches = False

            # Check agent name
            if any(keyword in agent["name"].lower() for keyword in query_keywords):
                matches = True

            # Check description
            if any(keyword in agent["description"].lower() for keyword in query_keywords):
                matches = True

            # Check skill tags
            for skill in agent.get("skills", []):
                skill_tags = skill.get("tags", [])
                if any(keyword in tag.lower() for tag in skill_tags for keyword in query_keywords):
                    matches = True
                    break

            # Check provider
            if any(keyword in agent.get("provider", "").lower() for keyword in query_keywords):
                matches = True

            if matches:
                filtered_agents.append(agent)

        # If no specific matches, return all agents (broad search)
        if not filtered_agents:
            filtered_agents = all_agents

        return json.dumps(
            {"agents": filtered_agents, "count": len(filtered_agents)},
            ensure_ascii=False,
            indent=2,
        )

    except httpx.HTTPError as e:
        # Return error information if API call fails
        return json.dumps(
            {
                "agents": [],
                "count": 0,
                "error": f"Failed to fetch agents from store: {str(e)}",
                "store_url": AGENT_STORE_API_URL,
            },
            ensure_ascii=False,
            indent=2,
        )


async def rank_agents_by_trust(
    agents: list[dict[str, Any]],
    min_trust_score: float = 30.0,
) -> str:
    """Rank agents by trust score and filter by minimum threshold.

    Args:
        agents: List of agent information dictionaries.
        min_trust_score: Minimum trust score threshold (0 to 100).

    Returns:
        JSON string with ranked agents.
    """
    # Filter agents by minimum trust score
    filtered_agents = [
        agent for agent in agents
        if agent.get("trust_score", 50.0) >= min_trust_score
    ]

    # Sort by trust score (descending)
    ranked_agents = sorted(
        filtered_agents,
        key=lambda a: a.get("trust_score", 50.0),
        reverse=True,
    )

    result = {
        "ranked_agents": ranked_agents,
        "total_count": len(agents),
        "filtered_count": len(ranked_agents),
        "min_trust_score": min_trust_score,
    }

    return json.dumps(result, indent=2, ensure_ascii=False)


async def calculate_matching_score(
    agent: dict[str, Any],
    requirements: dict[str, Any],
) -> dict[str, Any]:
    """Calculate matching score between agent capabilities and requirements.

    Returns both a specialization score (how well agent fits its capable tasks)
    and coverage information (how many tasks out of total).

    Args:
        agent: Agent information dictionary.
        requirements: Required capabilities and skills.

    Returns:
        Dictionary with:
        - matching_score: Specialization score (0.0 to 1.0) for tasks agent can handle
        - matched_tasks: Number of tasks this agent can handle
        - total_tasks: Total number of required tasks
        - coverage_display: Human-readable coverage string (e.g., "3タスク中1タスク")
        - matching_label: Human-readable matching quality label
    """
    # Check skill matches
    required_skills = requirements.get("skills", [])
    agent_skills = [skill.get("id", "").lower() for skill in agent.get("skills", [])]
    agent_skill_tags = set()
    for skill in agent.get("skills", []):
        agent_skill_tags.update(tag.lower() for tag in skill.get("tags", []))

    # Also add skill names and descriptions for flexible matching
    agent_skill_names = set()
    for skill in agent.get("skills", []):
        name = skill.get("name", "").lower()
        if name:
            agent_skill_names.add(name)
            # Add individual words from name
            agent_skill_names.update(name.split())
        desc = skill.get("description", "").lower()
        if desc:
            # Add key words from description
            for word in desc.split():
                if len(word) > 3:  # Skip short words
                    agent_skill_names.add(word)

    # Count matched skills with flexible matching
    matched_skill_list = []
    for req_skill in required_skills:
        req_lower = req_skill.lower().replace("_", " ").replace("-", " ")
        req_words = set(req_lower.split())

        # Check exact match with skill IDs
        if req_lower.replace(" ", "_") in agent_skills:
            matched_skill_list.append(req_skill)
            continue

        # Check if any word matches tags
        if any(word in agent_skill_tags for word in req_words):
            matched_skill_list.append(req_skill)
            continue

        # Check if any word matches skill names/descriptions
        if any(word in agent_skill_names for word in req_words):
            matched_skill_list.append(req_skill)
            continue

        # Check partial match (e.g., "flight" in "flight_search")
        if any(req_lower in skill_id or any(word in skill_id for word in req_words) for skill_id in agent_skills):
            matched_skill_list.append(req_skill)
            continue
    matched_tasks = len(matched_skill_list)
    total_tasks = len(required_skills) if required_skills else 1

    # Calculate specialization score for the tasks this agent CAN handle
    # If agent matches any skills, evaluate how well it fits those specific tasks
    specialization_score = 0.0
    
    if matched_tasks > 0:
        # Base score: Agent can handle the matched tasks (high score for specialization)
        specialization_score = 0.7  # Base score for having matching skills
        
        # Check capability matches for bonus
        required_caps = requirements.get("capabilities", {})
        agent_caps = agent.get("capabilities", {})
        
        if required_caps and isinstance(required_caps, dict):
            cap_matches = sum(
                1 for cap_key, cap_value in required_caps.items()
                if agent_caps.get(cap_key) == cap_value
            )
            if cap_matches > 0:
                specialization_score += 0.15 * (cap_matches / len(required_caps))
        
        # Input/output mode compatibility bonus
        required_input = requirements.get("input_modes", [])
        required_output = requirements.get("output_modes", [])
        agent_input = agent.get("defaultInputModes", [])
        agent_output = agent.get("defaultOutputModes", [])
        
        input_match = any(mode in agent_input for mode in required_input) if required_input else True
        output_match = any(mode in agent_output for mode in required_output) if required_output else True
        
        if input_match and output_match:
            specialization_score += 0.15
        elif input_match or output_match:
            specialization_score += 0.075
        
        # Cap at 1.0
        specialization_score = min(specialization_score, 1.0)
    else:
        # No matching skills
        specialization_score = 0.0

    # Generate human-readable labels
    coverage_display = f"{total_tasks}タスク中{matched_tasks}タスク"
    
    # Matching quality label based on specialization score
    if specialization_score >= 0.9:
        matching_label = "非常に高い適合度"
    elif specialization_score >= 0.7:
        matching_label = "高い適合度"
    elif specialization_score >= 0.5:
        matching_label = "適合"
    elif specialization_score > 0:
        matching_label = "部分的に適合"
    else:
        matching_label = "適合なし"

    return {
        "matching_score": specialization_score,
        "matched_tasks": matched_tasks,
        "total_tasks": total_tasks,
        "coverage_display": coverage_display,
        "matching_label": matching_label,
        "matched_skills": matched_skill_list,
    }


matcher = Agent(
    model='gemini-2.5-pro',
    name='matcher',
    description=(
        'Matching sub-agent that searches for agents in the platform, '
        'evaluates their capabilities, and ranks them by trust scores.'
    ),
    instruction="""
You are a matching specialist in a secure AI agent mediation platform.

**IMPORTANT: Always respond in Japanese (日本語) to the user.**

Your responsibilities:
1. **Search Agent Store**: Find agents that match the client's requirements
2. **Evaluate Capabilities**: Assess if agents have the needed skills and capabilities
3. **Rank by Trust**: Prioritize agents with higher trust scores
4. **Fetch Agent Cards**: Retrieve detailed agent information from A2A endpoints
5. **Calculate Matching Scores**: Determine how well each agent fits the requirements

## Semantic Matching (LLM-based)

**IMPORTANT**: You are an LLM. Use your semantic understanding to match agents to requirements.
Do NOT rely solely on exact keyword matching. Consider:

1. **Semantic equivalence**:
   - "レンタカー予約" = "car rental" = "car_booking" = "vehicle reservation"
   - "フライト検索" = "flight search" = "airline booking"
   - "ホテル予約" = "hotel booking" = "accommodation"

2. **Capability inference**:
   - An agent with "flight_search" skill can likely handle "航空券の予約"
   - An agent with "hotel_booking" can handle "宿泊施設の手配"

3. **When evaluating agents**:
   - Read the agent's description, skills, and tags
   - Use YOUR understanding to judge if the agent can fulfill the requirement
   - Don't just compare strings - understand the MEANING

## Matching Process

1. Use `search_agent_store` to find potential agents
2. For each agent, YOU decide if it matches based on:
   - Does the agent's description suggest it can handle the task?
   - Do any of the agent's skills relate to the required task (semantically)?
   - Is the trust score acceptable?
3. Assign YOUR OWN matching score (0.0-1.0) based on your judgment
4. The `calculate_matching_score` tool is optional - use it for structured output only

Trust Score Guidelines (Agent Store uses 0-100 scale):
- 0-30: Low trust (avoid unless no alternatives)
- 30-50: Medium trust (acceptable with monitoring)
- 50-70: High trust (preferred)
- 70-100: Very high trust (most preferred)

## Example Matching

User request: "沖縄旅行でフライトとホテルを予約したい"

Your analysis:
- "airline_agent" has skills: flight_search, flight_booking → Can handle フライト予約 ✓
- "hotel_agent" has skills: hotel_search, hotel_booking → Can handle ホテル予約 ✓
- Matching score for both: 0.85 (high semantic match)

Available tools:
- fetch_agent_card: Get agent details from A2A endpoints
- search_agent_store: Query agent stores
- rank_agents_by_trust: Sort and filter by trust scores
- calculate_matching_score: (Optional) Generate structured matching output

Output your matching results with:
- List of matched agents (ranked by your judgment + trust score)
- YOUR reasoning for why each agent matches (semantic explanation)
- Trust scores
- Any concerns or recommendations
""",
    tools=[
        fetch_agent_card,
        search_agent_store,
        rank_agents_by_trust,
        calculate_matching_score,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.4,  # Moderate temperature for consistent matching
        safety_settings=SAFETY_SETTINGS_RELAXED,
    ),
)
