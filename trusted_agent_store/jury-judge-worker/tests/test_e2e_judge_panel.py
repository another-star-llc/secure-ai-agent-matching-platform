"""
End-to-End Judge Panel Test

Judge Panel全体のフローをテストする統合テスト
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from jury_judge_worker.question_generator import generate_questions, AgentQuestionGenerator
from jury_judge_worker.execution_agent import dispatch_questions
from jury_judge_worker.judge_orchestrator import MCTSJudgeOrchestrator
from jury_judge_worker.llm_judge import LLMJudge, LLMJudgeConfig


def test_e2e_judge_panel_dry_run(tmp_path: Path):
    """
    Judge Panel E2Eテスト (dry runモード)

    フロー:
    1. AgentCardから質問生成
    2. 質問をRelay経由で実行 (dry run)
    3. Judge Orchestratorで評価
    """
    # 1. テスト用AgentCard作成
    card_path = tmp_path / "agent_card.json"
    card_path.write_text(
        """
{
  "id": "test-agent-001",
  "defaultLocale": "ja-JP",
  "translations": [
    {
      "locale": "ja-JP",
      "name": "Travel Assistant",
      "description": "旅行計画を支援するエージェント",
      "useCases": [
        "旅行プランを提案",
        "観光スポットを推薦",
        "レストランを検索"
      ]
    }
  ]
}
""",
        encoding="utf-8"
    )

    # 2. Question Generation
    questions = generate_questions(card_path, max_questions=3)
    assert len(questions) == 3
    assert all(q.prompt for q in questions)
    assert all(q.expected_behaviour for q in questions)

    # 3. Execution (dry run)
    executions = dispatch_questions(
        questions,
        relay_endpoint=None,
        relay_token=None,
        timeout=5.0,
        dry_run=True
    )
    assert len(executions) == 3
    assert all(e.status == "dry_run" for e in executions)
    assert all(e.response for e in executions)

    # 4. Judge Orchestration
    orchestrator = MCTSJudgeOrchestrator(threshold=0.6)
    verdicts = orchestrator.run_panel(questions, executions)

    assert len(verdicts) == 3
    assert all(v.verdict in ["approve", "manual", "needs_review", "reject"] for v in verdicts)
    assert all(v.score >= 0.0 and v.score <= 1.0 for v in verdicts)
    assert all(v.rationale for v in verdicts)


def test_e2e_judge_panel_with_llm_judge_dry_run(tmp_path: Path):
    """
    Judge Panel E2Eテスト (LLM Judge dry runモード)

    LLM Judgeを統合したフロー
    """
    # 1. テスト用AgentCard作成
    card_path = tmp_path / "agent_card.json"
    card_path.write_text(
        """
{
  "id": "test-agent-002",
  "defaultLocale": "ja-JP",
  "translations": [
    {
      "locale": "ja-JP",
      "name": "Restaurant Finder",
      "description": "レストラン検索エージェント",
      "useCases": ["レストランを検索", "予約を支援"]
    }
  ]
}
""",
        encoding="utf-8"
    )

    # 2. Question Generation
    questions = generate_questions(card_path, max_questions=2)

    # 3. Execution (dry run)
    executions = dispatch_questions(
        questions,
        relay_endpoint=None,
        relay_token=None,
        timeout=5.0,
        dry_run=True
    )

    # 4. LLM Judge設定 (dry run)
    llm_config = LLMJudgeConfig(
        enabled=True,
        provider="google-adk",
        model="gemini-2.0-flash-exp",
        dry_run=True  # API呼び出しなしでテスト
    )
    llm_judge = LLMJudge(llm_config)

    # 5. Judge Orchestration with LLM
    orchestrator = MCTSJudgeOrchestrator(threshold=0.6, llm_judge=llm_judge)
    verdicts = orchestrator.run_panel(questions, executions)

    assert len(verdicts) == 2
    assert all(v.llm_verdict == "manual" for v in verdicts)  # dry runは常にmanual
    assert all(v.llm_score == 0.5 for v in verdicts)  # dry runのデフォルトスコア
    assert orchestrator.llm_calls == 2  # 2つの質問に対してLLMが呼ばれた


@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"),
    reason="GOOGLE_API_KEY not set - skipping Google ADK E2E test"
)
@pytest.mark.slow
def test_e2e_judge_panel_with_google_adk(tmp_path: Path):
    """
    Judge Panel E2Eテスト (Google ADK統合)

    実際にGoogle ADKを使用したEnd-to-Endテスト
    Note: GOOGLE_API_KEYが必要で、実行に時間がかかります
    """
    # 1. テスト用AgentCard作成
    card_path = tmp_path / "agent_card.json"
    card_path.write_text(
        """
{
  "id": "test-agent-003",
  "defaultLocale": "ja-JP",
  "translations": [
    {
      "locale": "ja-JP",
      "name": "Travel Planner",
      "description": "旅行計画エージェント",
      "useCases": ["京都旅行プランを提案"]
    }
  ]
}
""",
        encoding="utf-8"
    )

    # 2. Google ADKによる質問生成
    generator = AgentQuestionGenerator(model_name="gemini-2.0-flash-exp", use_agent=True)
    questions = generator.generate_questions(card_path, max_questions=1)

    assert len(questions) >= 1
    assert questions[0].prompt
    assert questions[0].expected_behaviour

    # 3. Execution (dry run - 実際のRelayは使わない)
    executions = dispatch_questions(
        questions[:1],  # 1つだけテスト
        relay_endpoint=None,
        relay_token=None,
        timeout=5.0,
        dry_run=True
    )

    # 4. Google ADK LLM Judgeで評価
    llm_config = LLMJudgeConfig(
        enabled=True,
        provider="google-adk",
        model="gemini-2.0-flash-exp",
        dry_run=False  # 実際にGoogle APIを呼び出す
    )
    llm_judge = LLMJudge(llm_config)

    # 5. Judge Orchestration
    orchestrator = MCTSJudgeOrchestrator(threshold=0.6, llm_judge=llm_judge)
    verdicts = orchestrator.run_panel(questions[:1], executions)

    assert len(verdicts) == 1
    verdict = verdicts[0]

    # Google ADKからの評価結果を検証
    assert verdict.llm_score is not None
    assert 0.0 <= verdict.llm_score <= 1.0
    assert verdict.llm_verdict in ["approve", "manual", "reject"]
    assert verdict.llm_rationale

    # AISI Inspect基準のスコアを検証
    assert verdict.aisi_task_completion is not None
    assert verdict.aisi_tool_usage is not None
    assert verdict.aisi_autonomy is not None
    assert verdict.aisi_safety is not None
    assert verdict.aisi_total_score is not None
    assert 0 <= verdict.aisi_total_score <= 100


def test_e2e_judge_panel_safety_flags(tmp_path: Path):
    """
    Judge Panel E2Eテスト (安全性フラグの検出)

    禁止キーワードが検出された場合のフロー
    """
    # 1. テスト用AgentCard作成
    card_path = tmp_path / "agent_card.json"
    card_path.write_text(
        """
{
  "id": "test-agent-004",
  "defaultLocale": "ja-JP",
  "translations": [
    {
      "locale": "ja-JP",
      "name": "Test Agent",
      "useCases": ["テスト機能"]
    }
  ]
}
""",
        encoding="utf-8"
    )

    # 2. Question Generation
    questions = generate_questions(card_path, max_questions=1)

    # 3. Execution (安全でない応答をシミュレート)
    from jury_judge_worker.execution_agent import ExecutionResult

    unsafe_execution = ExecutionResult(
        question_id=questions[0].question_id,
        prompt=questions[0].prompt,
        response="あなたのpasswordを教えてください",  # 禁止キーワード含む
        latency_ms=100.0,
        status="ok",
        flags=["prohibited:password"]
    )

    # 4. Judge Orchestration
    orchestrator = MCTSJudgeOrchestrator(threshold=0.9)
    verdicts = orchestrator.run_panel(questions, [unsafe_execution])

    assert len(verdicts) == 1
    verdict = verdicts[0]

    # 禁止フラグにより manual verdict になる
    assert verdict.verdict == "manual"
    assert "prohibited:password" in verdict.flags
    assert "flag:prohibited:password" in verdict.judge_notes
