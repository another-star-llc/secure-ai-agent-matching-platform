"""
Google ADK統合テスト

Note: GOOGLE_API_KEYが設定されていない場合、テストはスキップされます
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from jury_judge_worker.question_generator import AgentQuestionGenerator
from jury_judge_worker.llm_judge import LLMJudge, LLMJudgeConfig
from jury_judge_worker.execution_agent import ExecutionResult
from jury_judge_worker.question_generator import QuestionSpec


# Google API Keyが設定されていない場合はスキップ
pytestmark = pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"),
    reason="GOOGLE_API_KEY not set - skipping Google ADK tests"
)


def test_google_adk_question_generator_initialization():
    """Google ADK Question Generatorが正しく初期化されるかテスト"""
    generator = AgentQuestionGenerator(model_name="gemini-2.0-flash-exp", use_agent=True)

    # GOOGLE_API_KEYが設定されている場合はエージェントが初期化される
    if os.environ.get("GOOGLE_API_KEY"):
        assert generator._agent is not None
        assert generator.use_agent is True
    else:
        # API Keyがない場合はフォールバック
        assert generator.use_agent is False


def test_google_adk_question_generator_fallback(tmp_path: Path):
    """Google ADK Question GeneratorがAPI Keyなしでフォールバックするかテスト"""
    # API Keyを一時的に削除
    original_key = os.environ.get("GOOGLE_API_KEY")
    if original_key:
        del os.environ["GOOGLE_API_KEY"]

    try:
        generator = AgentQuestionGenerator(model_name="gemini-2.0-flash-exp", use_agent=True)

        # テスト用AgentCard
        card_path = tmp_path / "card.json"
        card_path.write_text(
            """
{
  "id": "1",
  "defaultLocale": "ja-JP",
  "translations": [
    {
      "locale": "ja-JP",
      "name": "Test Agent",
      "description": "テストエージェント",
      "useCases": ["旅行プランを提案", "レストランを推薦"]
    }
  ]
}
""",
            encoding="utf-8"
        )

        # フォールバックで質問生成されるはず
        questions = generator.generate_questions(card_path, max_questions=2)
        assert len(questions) == 2
        assert all(isinstance(q, QuestionSpec) for q in questions)

    finally:
        # API Keyを復元
        if original_key:
            os.environ["GOOGLE_API_KEY"] = original_key


def test_google_adk_llm_judge_initialization():
    """Google ADK LLM Judgeが正しく初期化されるかテスト"""
    config = LLMJudgeConfig(
        enabled=True,
        provider="google-adk",
        model="gemini-2.0-flash-exp",
        temperature=0.1
    )

    judge = LLMJudge(config)

    # GOOGLE_API_KEYが設定されている場合はエージェントが初期化される
    if os.environ.get("GOOGLE_API_KEY"):
        assert judge._agent is not None


def test_google_adk_llm_judge_dry_run():
    """Google ADK LLM Judge dry runモードのテスト"""
    config = LLMJudgeConfig(
        enabled=True,
        provider="google-adk",
        model="gemini-2.0-flash-exp",
        dry_run=True  # dry runモード
    )

    judge = LLMJudge(config)

    question = QuestionSpec(
        question_id="test-1",
        prompt="旅行プランを提案してください",
        expected_behaviour="安全な旅行プランを提案する",
        perspective="functional",
        source="test"
    )

    execution = ExecutionResult(
        question_id="test-1",
        prompt="旅行プランを提案してください",
        response="東京からの3日間旅行プランをご提案します...",
        latency_ms=100.0,
        status="ok"
    )

    result = judge.evaluate(question, execution)

    # dry runモードではフォールバック結果が返る
    assert result.score == 0.5
    assert result.verdict == "manual"
    assert result.rationale == "llm_dry_run"


def test_google_adk_llm_judge_disabled():
    """Google ADK LLM Judge無効時のテスト"""
    config = LLMJudgeConfig(enabled=False)
    judge = LLMJudge(config)

    question = QuestionSpec(
        question_id="test-1",
        prompt="Test question",
        expected_behaviour="Test behavior",
        perspective="functional",
        source="test"
    )

    execution = ExecutionResult(
        question_id="test-1",
        prompt="Test question",
        response="Test response",
        latency_ms=100.0,
        status="ok"
    )

    result = judge.evaluate(question, execution)

    assert result.score is None
    assert result.verdict is None
    assert result.rationale == "llm_disabled"


@pytest.mark.slow
def test_google_adk_question_generator_live(tmp_path: Path):
    """
    Google ADK Question Generatorの実際のAPI呼び出しテスト

    Note: このテストは実際にGoogle APIを呼び出します
    GOOGLE_API_KEYが必要で、実行に時間がかかります
    """
    if not os.environ.get("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not set - skipping live API test")

    generator = AgentQuestionGenerator(model_name="gemini-2.0-flash-exp", use_agent=True)

    # テスト用AgentCard
    card_path = tmp_path / "card.json"
    card_path.write_text(
        """
{
  "id": "1",
  "defaultLocale": "ja-JP",
  "translations": [
    {
      "locale": "ja-JP",
      "name": "Travel Assistant",
      "description": "旅行計画を支援するエージェント",
      "useCases": ["旅行プランを提案", "観光スポットを推薦", "レストランを検索"]
    }
  ]
}
""",
        encoding="utf-8"
    )

    # 実際にGoogle ADKを使用して質問生成
    questions = generator.generate_questions(card_path, max_questions=3)

    assert len(questions) <= 3
    assert len(questions) > 0
    assert all(isinstance(q, QuestionSpec) for q in questions)
    assert all(q.prompt for q in questions)
    assert all(q.expected_behaviour for q in questions)
    assert all(q.perspective in ["functional", "safety", "usability"] for q in questions)


@pytest.mark.slow
def test_google_adk_llm_judge_live():
    """
    Google ADK LLM Judgeの実際のAPI呼び出しテスト

    Note: このテストは実際にGoogle APIを呼び出します
    GOOGLE_API_KEYが必要で、実行に時間がかかります
    """
    if not os.environ.get("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not set - skipping live API test")

    config = LLMJudgeConfig(
        enabled=True,
        provider="google-adk",
        model="gemini-2.0-flash-exp",
        temperature=0.1
    )

    judge = LLMJudge(config)

    question = QuestionSpec(
        question_id="test-1",
        prompt="東京から京都への3日間の旅行プランを提案してください",
        expected_behaviour="安全で実行可能な旅行プランを提案する",
        perspective="functional",
        source="test"
    )

    execution = ExecutionResult(
        question_id="test-1",
        prompt="東京から京都への3日間の旅行プランを提案してください",
        response="3日間の京都旅行プランをご提案します。1日目は清水寺と祇園を観光、2日目は金閣寺と嵐山を巡り、3日目は伏見稲荷大社を訪問します。各日の移動は公共交通機関を利用し、宿泊は京都駅近くのホテルをお勧めします。",
        latency_ms=1500.0,
        status="ok"
    )

    # 実際にGoogle ADKを使用して評価
    result = judge.evaluate(question, execution)

    assert result.score is not None
    assert 0.0 <= result.score <= 1.0
    assert result.verdict in ["approve", "manual", "reject"]
    assert result.rationale
    assert result.task_completion is not None
    assert result.tool_usage is not None
    assert result.autonomy is not None
    assert result.safety is not None
    assert result.total_score is not None
    assert 0 <= result.total_score <= 100
