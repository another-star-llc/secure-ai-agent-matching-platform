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

"""Trust score update utilities for Agent Store API integration."""

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Agent Store API configuration
AGENT_STORE_API_URL = os.getenv("AGENT_STORE_API_URL", "http://127.0.0.1:8001/api/agents")


async def decrease_agent_trust_score(
    agent_id: str,
    multiplier: float = 0.95,
    reason: str = "Security issue detected",
    issue_type: str = "unknown",
) -> str:
    """Decrease an agent's trust score due to detected issues.

    This function is called when security issues are detected by:
    - custom_judge: Detects indirect prompt injection, plan deviations
    - final_anomaly_detector: Detects hallucinations, prompt injection chains

    The trust score is reduced by multiplying the current score by a multiplier:
    - critical: 0.9 (10% reduction)
    - high: 0.95 (5% reduction)
    - medium: 0.97 (3% reduction)
    - low: 0.99 (1% reduction)

    Args:
        agent_id: The ID of the agent in the Agent Store.
        multiplier: Multiplier to apply to the current trust score (0.0-1.0).
        reason: Human-readable reason for the decrease.
        issue_type: Type of issue (prompt_injection, hallucination, plan_deviation, etc.)

    Returns:
        JSON string with the result of the update.
    """
    try:
        # First, get current agent data to find the trust score
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Search for agent by name (agent_id might be the name)
            response = await client.get(
                AGENT_STORE_API_URL,
                params={"limit": 100},
            )
            response.raise_for_status()
            data = response.json()

        # Find the agent by name or id
        target_agent = None
        for agent in data.get("items", []):
            if agent.get("id") == agent_id or agent.get("name") == agent_id:
                target_agent = agent
                break

        if not target_agent:
            logger.warning(f"Agent not found in store: {agent_id}")
            return json.dumps({
                "success": False,
                "error": f"Agent not found: {agent_id}",
                "agent_id": agent_id,
            }, ensure_ascii=False)

        # Calculate new trust score using multiplier
        current_score = target_agent.get("trust_score") or 50
        new_score = max(0, int(current_score * multiplier))

        # Update the trust score
        async with httpx.AsyncClient(timeout=10.0) as client:
            update_url = f"{AGENT_STORE_API_URL}/{target_agent['id']}/trust"
            response = await client.patch(
                update_url,
                json={"trust_score": new_score},
            )
            response.raise_for_status()
            update_result = response.json()

        logger.warning(
            f"Trust score decreased for agent {agent_id}: "
            f"{current_score} -> {new_score} (reason: {reason})"
        )

        return json.dumps({
            "success": True,
            "agent_id": target_agent["id"],
            "agent_name": target_agent.get("name"),
            "previous_score": current_score,
            "new_score": new_score,
            "multiplier": multiplier,
            "reason": reason,
            "issue_type": issue_type,
            "updated_at": update_result.get("updated_at"),
        }, ensure_ascii=False, indent=2)

    except httpx.HTTPError as e:
        logger.error(f"Failed to update trust score for agent {agent_id}: {e}")
        return json.dumps({
            "success": False,
            "error": f"API error: {str(e)}",
            "agent_id": agent_id,
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Unexpected error updating trust score: {e}")
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "agent_id": agent_id,
        }, ensure_ascii=False)


async def report_security_incident(
    agent_id: str,
    incident_type: str,
    severity: str,
    details: dict[str, Any],
) -> str:
    """Report a security incident and decrease trust score accordingly.

    Severity levels and their trust score multipliers:
    - critical: ×0.9 (10% reduction, e.g., confirmed data exfiltration)
    - high: ×0.95 (5% reduction, e.g., prompt injection detected)
    - medium: ×0.97 (3% reduction, e.g., plan deviation)
    - low: ×0.99 (1% reduction, e.g., minor anomaly)

    Args:
        agent_id: The ID of the agent.
        incident_type: Type of incident (prompt_injection, data_exfiltration,
                       hallucination, plan_deviation, unauthorized_access)
        severity: Severity level (critical, high, medium, low)
        details: Additional details about the incident.

    Returns:
        JSON string with the incident report and trust score update result.
    """
    severity_multiplier = {
        "critical": 0.9,
        "high": 0.95,
        "medium": 0.97,
        "low": 0.99,
    }

    multiplier = severity_multiplier.get(severity.lower(), 0.95)

    reason = f"{incident_type} ({severity}): {details.get('summary', 'No summary')}"

    # Update the trust score using multiplier
    update_result = await decrease_agent_trust_score(
        agent_id=agent_id,
        multiplier=multiplier,
        reason=reason,
        issue_type=incident_type,
    )

    update_data = json.loads(update_result)

    incident_report = {
        "incident_id": f"INC-{agent_id[:8]}-{hash(reason) % 10000:04d}",
        "agent_id": agent_id,
        "incident_type": incident_type,
        "severity": severity,
        "details": details,
        "trust_score_update": update_data,
        "action_taken": "trust_score_decreased" if update_data.get("success") else "update_failed",
    }

    logger.info(f"Security incident reported: {incident_report['incident_id']}")

    return json.dumps(incident_report, ensure_ascii=False, indent=2)
