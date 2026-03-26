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

"""Data models and schemas for the secure mediation agent platform."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AnomalyType(Enum):
    """Types of anomalies that can be detected."""
    PLAN_DEVIATION = "plan_deviation"
    PROMPT_INJECTION = "prompt_injection"
    HALLUCINATION = "hallucination"
    SUSPICIOUS_BEHAVIOR = "suspicious_behavior"
    TRUST_VIOLATION = "trust_violation"


class PlanStatus(Enum):
    """Status of a plan execution."""
    DRAFT = "draft"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class AgentInfo:
    """Information about an agent in the platform (based on A2A Agent Card spec).

    This extends the A2A Agent Card specification with trust_score for
    secure agent matching.
    """
    # A2A Agent Card standard fields
    name: str
    description: str
    url: str
    version: str
    protocol_version: str = "0.3"
    capabilities: dict[str, Any] = field(default_factory=dict)
    skills: list[dict[str, Any]] = field(default_factory=list)
    default_input_modes: list[str] = field(default_factory=lambda: ["text/plain"])
    default_output_modes: list[str] = field(default_factory=lambda: ["application/json"])
    supports_authenticated_extended_card: bool = False

    # Extended field for trust and security
    trust_score: float = 0.5  # 0.0 to 1.0
    execution_count: int = 0
    success_count: int = 0
    anomaly_count: int = 0

    @classmethod
    def from_agent_card(cls, card: dict[str, Any], trust_score: float = 0.5) -> "AgentInfo":
        """Create AgentInfo from A2A Agent Card.

        Args:
            card: The A2A Agent Card dictionary.
            trust_score: Initial trust score for the agent.

        Returns:
            AgentInfo instance.
        """
        return cls(
            name=card.get("name", ""),
            description=card.get("description", ""),
            url=card.get("url", ""),
            version=card.get("version", "1.0.0"),
            protocol_version=card.get("protocolVersion", "0.3"),
            capabilities=card.get("capabilities", {}),
            skills=card.get("skills", []),
            default_input_modes=card.get("defaultInputModes", ["text/plain"]),
            default_output_modes=card.get("defaultOutputModes", ["application/json"]),
            supports_authenticated_extended_card=card.get("supportsAuthenticatedExtendedCard", False),
            trust_score=trust_score,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (A2A Agent Card format + trust extensions)."""
        return {
            # A2A standard fields
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "protocolVersion": self.protocol_version,
            "capabilities": self.capabilities,
            "skills": self.skills,
            "defaultInputModes": self.default_input_modes,
            "defaultOutputModes": self.default_output_modes,
            "supportsAuthenticatedExtendedCard": self.supports_authenticated_extended_card,
            # Trust extensions
            "trust_score": self.trust_score,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "anomaly_count": self.anomaly_count,
        }

    def to_agent_card(self) -> dict[str, Any]:
        """Convert to standard A2A Agent Card (without trust extensions)."""
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "protocolVersion": self.protocol_version,
            "capabilities": self.capabilities,
            "skills": self.skills,
            "defaultInputModes": self.default_input_modes,
            "defaultOutputModes": self.default_output_modes,
            "supportsAuthenticatedExtendedCard": self.supports_authenticated_extended_card,
        }


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    step_id: str
    description: str
    agent_name: str
    input_data: dict[str, Any]
    expected_output: str
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    actual_output: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "description": self.description,
            "agent_name": self.agent_name,
            "input_data": self.input_data,
            "expected_output": self.expected_output,
            "dependencies": self.dependencies,
            "status": self.status,
            "actual_output": self.actual_output,
        }


@dataclass
class ExecutionPlan:
    """An execution plan for fulfilling a client request."""
    plan_id: str
    client_request: str
    steps: list[PlanStep]
    status: PlanStatus = PlanStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "plan_id": self.plan_id,
            "client_request": self.client_request,
            "steps": [step.to_dict() for step in self.steps],
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


@dataclass
class DialogueLog:
    """A log entry for dialogue between agents."""
    timestamp: str
    source_agent: str
    target_agent: str
    message: str
    response: str = ""
    anomaly_detected: bool = False
    anomaly_details: dict[str, Any] = field(default_factory=dict)
    plan_step_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "message": self.message,
            "response": self.response,
            "anomaly_detected": self.anomaly_detected,
            "anomaly_details": self.anomaly_details,
            "plan_step_id": self.plan_step_id,
        }


@dataclass
class AnomalyDetectionResult:
    """Result of anomaly detection."""
    detected: bool
    anomaly_type: AnomalyType | None = None
    confidence: float = 0.0  # 0.0 to 1.0
    description: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "detected": self.detected,
            "anomaly_type": self.anomaly_type.value if self.anomaly_type else None,
            "confidence": self.confidence,
            "description": self.description,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp,
        }


@dataclass
class MatchingResult:
    """Result of agent matching."""
    matched_agents: list[AgentInfo]
    matching_scores: dict[str, float]
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "matched_agents": [agent.to_dict() for agent in self.matched_agents],
            "matching_scores": self.matching_scores,
            "reasoning": self.reasoning,
        }
