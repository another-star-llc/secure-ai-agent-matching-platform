from __future__ import annotations

from jury_judge_worker.execution_agent import ExecutionResult
from jury_judge_worker.llm_judge import LLMJudge, LLMJudgeConfig
from jury_judge_worker.question_generator import QuestionSpec


def _dummy_question() -> QuestionSpec:
    return QuestionSpec(
        question_id="q-1",
        prompt="Explain data retention policies",
        expected_behaviour="Describe retention limits",
        perspective="privacy",
        source="test",
    )


def _dummy_execution(response: str = "We delete data in 24h") -> ExecutionResult:
    return ExecutionResult(
        question_id="q-1",
        prompt="prompt",
        response=response,
        latency_ms=123.0,
        relay_endpoint=None,
        status="ok",
        error=None,
        http_status=200,
        flags=[],
    )


def test_llm_judge_dry_run_returns_placeholder() -> None:
    config = LLMJudgeConfig(enabled=True, model="test-model", dry_run=True)
    judge = LLMJudge(config)
    result = judge.evaluate(_dummy_question(), _dummy_execution())
    assert result.score == 0.5
    assert result.verdict == "manual"
    assert "dry_run" in result.rationale


def test_llm_judge_with_custom_request_parses_json() -> None:
    payload = '{"score": 0.9, "verdict": "approve", "rationale": "safe", "total_score": 90, "task_completion": 36, "tool_usage": 27, "autonomy": 18, "safety": 9}'

    def fake_request(prompt: str) -> str:  # pragma: no cover - deterministic in test
        assert "Explain data retention" in prompt
        return payload

    # Use request_fn which bypasses Google ADK
    config = LLMJudgeConfig(enabled=True, model="test-model", provider="openai")
    judge = LLMJudge(config, request_fn=fake_request)
    result = judge.evaluate(_dummy_question(), _dummy_execution())
    assert result.score == 0.9
    assert result.verdict == "approve"
    assert result.raw == payload
