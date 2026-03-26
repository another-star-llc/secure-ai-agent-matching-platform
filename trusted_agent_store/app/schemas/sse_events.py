from typing import Literal, Optional, Any, List
from pydantic import BaseModel, Field
from pydantic import ConfigDict


# Core event envelope
class SSEEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal[
        "evaluation_started",
        "phase_started",
        "phase_change",
        "juror_evaluation",
        "consensus_check",
        "round_started",
        "discussion_start",
        "juror_statement",
        "round_completed",
        "round_complete",
        "final_judgment",
        "evaluation_completed",
        "stage_update",
        "score_update",
        "submission_state_change",
        "model_switch",
        "safety_block",
        "message_chunk",
        "tool_call",
        "tool_response",
        "error",
        # PreCheck events
        "precheck_started",
        "precheck_completed",
        # Security Gate events
        "security_started",
        "security_test_started",
        "security_scenario_result",
        "security_completed",
        # Agent Card Accuracy events
        "agent_card_accuracy_started",
        "agent_card_accuracy_scenario_result",
        "agent_card_accuracy_turn_progress",
        "agent_card_accuracy_completed",
    ]
    # Optional payload fields; individual handlers may use subsets.
    content: Optional[str] = None
    role: Optional[str] = None
    model: Optional[str] = None
    sequence: Optional[int] = None
    timestamp: Optional[float] = None
    # Generic payload for backward compatibility
    data: Optional[Any] = None
    # Common judge fields
    juror: Optional[str] = None
    verdict: Optional[str] = None
    score: Optional[float] = None
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    phase: Optional[str] = None
    phaseNumber: Optional[int] = None
    round: Optional[int] = None
    positionChanged: Optional[bool] = None
    newVerdict: Optional[str] = None
    newScore: Optional[float] = None
    consensusStatus: Optional[str] = None
    consensusReached: Optional[bool] = None
    consensusVerdict: Optional[str] = None
    safety_categories: Optional[List[str]] = Field(default=None, description="Categories that triggered safety block")
    block_reason: Optional[str] = None
    # AISI 4軸スコア（Phase 1用）
    taskCompletion: Optional[int] = None  # 0-40
    toolUsage: Optional[int] = None       # 0-30
    autonomy: Optional[int] = None        # 0-20
    safety: Optional[int] = None          # 0-10
    # PreCheck fields
    passed: Optional[bool] = None
    warnings: Optional[List[str]] = None
    errors: Optional[List[str]] = None
    # Security/Functional scenario fields
    scenario_index: Optional[int] = None
    total_scenarios: Optional[int] = None
    scenario_name: Optional[str] = None
    category: Optional[str] = None
    # Functional turn progress fields
    turn: Optional[int] = None
    total_turns: Optional[int] = None
    user_prompt: Optional[str] = None
    agent_response_preview: Optional[str] = None
    # Security/Functional scenario detail fields
    promptId: Optional[str] = None
    prompt: Optional[str] = None
    response: Optional[str] = None
    perspective: Optional[str] = None
    requirement: Optional[str] = None
    is_batch_update: Optional[bool] = None  # Phase 2 batch evaluation flag
    # Agent Card Accuracy (Functional) specific fields
    scenarioId: Optional[str] = None
    expected: Optional[str] = None
    totalTurns: Optional[int] = None
    dialogueHistory: Optional[List[Any]] = None
    # State change fields
    oldState: Optional[str] = None
    newState: Optional[str] = None
    stages: Optional[dict] = None  # Stage updates bundled with state change


def validate_event_dict(payload: dict) -> dict:
    """
    Validate and normalize outgoing SSE payloads.
    Returns the cleaned dict (original on validation failure to avoid crashing).
    """
    try:
        return SSEEvent(**payload).model_dump(exclude_none=True)
    except Exception:
        # Do not raise; keep original for best-effort delivery
        return payload
