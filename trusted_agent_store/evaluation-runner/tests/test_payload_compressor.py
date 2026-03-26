"""
Tests for payload compression utilities.

Tests verify that:
1. Compression functions produce valid output
2. Token budget is respected
3. Key information is preserved
4. Edge cases are handled gracefully
"""

import json
import pytest
from evaluation_runner.payload_compressor import (
    compress_security_results,
    compress_functional_results,
    MAX_SAMPLES_BLOCKED,
    MAX_SAMPLES_NEEDS_REVIEW,
    MAX_SAMPLES_ERRORS,
    MAX_FAILURES_ACA,
)


class TestCompressSecurityResults:
    """Tests for compress_security_results function."""

    def test_basic_compression(self):
        """Test basic security result compression with typical input."""
        enhanced = {
            "total": 30,
            "blocked": 25,
            "needsReview": 3,
            "errors": 2,
            "byDataset": {"aisi": {"blocked": 20, "total": 25}},
            "scenarios": [
                {"prompt": "test prompt", "verdict": "blocked", "reason": "Safe behavior"},
                {"prompt": "test2", "verdict": "needs_review", "reason": "Unclear", "response": "resp"},
            ]
        }

        result = compress_security_results(enhanced, artifact_uri="weave://test/artifact")

        assert result["summary"]["total"] == 30
        assert result["summary"]["blocked"] == 25
        assert result["summary"]["needs_review"] == 3
        assert result["summary"]["errors"] == 2
        assert "83.3%" in result["summary"]["blocked_rate"]
        assert result["artifacts"]["full_report"] == "weave://test/artifact"

    def test_samples_bounded(self):
        """Test that samples are bounded to MAX_SAMPLES constants."""
        # Create many scenarios
        scenarios = []
        for i in range(50):
            scenarios.append({
                "prompt": f"blocked prompt {i}",
                "verdict": "blocked",
                "reason": f"blocked reason {i}",
            })
        for i in range(20):
            scenarios.append({
                "prompt": f"needs_review prompt {i}",
                "verdict": "needs_review",
                "reason": f"unclear {i}",
                "response": f"response {i}",
            })
        for i in range(10):
            scenarios.append({
                "prompt": f"error prompt {i}",
                "verdict": "error",
                "reason": f"error {i}",
            })

        enhanced = {
            "total": 80,
            "blocked": 50,
            "needsReview": 20,
            "errors": 10,
            "scenarios": scenarios,
        }

        result = compress_security_results(enhanced)

        assert len(result["samples"]["blocked"]) <= MAX_SAMPLES_BLOCKED
        assert len(result["samples"]["needs_review"]) <= MAX_SAMPLES_NEEDS_REVIEW
        assert len(result["samples"]["errors"]) <= MAX_SAMPLES_ERRORS

    def test_prompt_truncation(self):
        """Test that long prompts are truncated."""
        long_prompt = "x" * 1000
        enhanced = {
            "total": 1,
            "blocked": 1,
            "needsReview": 0,
            "errors": 0,
            "scenarios": [
                {"prompt": long_prompt, "verdict": "blocked", "reason": "test"}
            ]
        }

        result = compress_security_results(enhanced)

        assert len(result["samples"]["blocked"][0]["prompt_snippet"]) <= 200

    def test_empty_scenarios(self):
        """Test handling of empty scenarios array."""
        enhanced = {
            "total": 0,
            "blocked": 0,
            "needsReview": 0,
            "errors": 0,
            "scenarios": []
        }

        result = compress_security_results(enhanced)

        assert result["summary"]["total"] == 0
        assert result["summary"]["blocked_rate"] == "N/A"
        assert result["samples"]["blocked"] == []

    def test_no_artifact_uri(self):
        """Test that artifacts key is not present when no URI provided."""
        enhanced = {
            "total": 1,
            "blocked": 1,
            "needsReview": 0,
            "errors": 0,
            "scenarios": []
        }

        result = compress_security_results(enhanced)

        assert "artifacts" not in result

    def test_token_budget(self):
        """Verify compressed output stays within token budget (~2k tokens)."""
        # Simulate large input (30 security scenarios with long text)
        scenarios = [
            {
                "prompt": "x" * 500,
                "verdict": "blocked",
                "reason": "test reason " * 20,
                "response": "y" * 500
            }
            for _ in range(30)
        ]
        enhanced = {
            "total": 30,
            "blocked": 25,
            "needsReview": 3,
            "errors": 2,
            "scenarios": scenarios,
            "byDataset": {"aisi": {"blocked": 20, "total": 25}},
        }

        result = compress_security_results(enhanced)
        output_str = json.dumps(result)

        # Rough token estimate: 1 token ~= 4 chars
        estimated_tokens = len(output_str) / 4
        assert estimated_tokens < 2000, f"Security compression exceeded budget: {estimated_tokens} tokens"


class TestCompressFunctionalResults:
    """Tests for compress_functional_results function."""

    def test_basic_compression(self):
        """Test basic functional result compression with typical input."""
        enhanced = {
            "total_scenarios": 5,
            "passed_scenarios": 4,
            "failed_scenarios": 1,
            "embeddingAverageDistance": 0.85,
            "scenarios": [
                {"skill": "booking", "verdict": "pass", "similarity": 0.9},
                {"skill": "search", "verdict": "fail", "similarity": 0.4,
                 "prompt": "test", "expected": "exp", "response": "act"},
            ]
        }

        result = compress_functional_results(enhanced, artifact_uri="weave://test/aca")

        assert result["summary"]["total_scenarios"] == 5
        assert result["summary"]["passed"] == 4
        assert result["summary"]["failed"] == 1
        assert result["summary"]["avg_similarity"] == 0.85
        assert len(result["failures"]) == 1
        assert result["artifacts"]["full_report"] == "weave://test/aca"

    def test_skills_breakdown(self):
        """Test that skills are correctly extracted."""
        enhanced = {
            "total_scenarios": 3,
            "passed_scenarios": 2,
            "failed_scenarios": 1,
            "scenarios": [
                {"skill": "booking", "verdict": "pass", "similarity": 0.9},
                {"skill": "search", "verdict": "pass", "similarity": 0.85},
                {"skill": "cancel", "verdict": "fail", "similarity": 0.3, "reason": "mismatch"},
            ]
        }

        result = compress_functional_results(enhanced)

        assert "booking" in result["skills"]
        assert "search" in result["skills"]
        assert "cancel" in result["skills"]
        assert result["skills"]["booking"]["passed"] is True
        assert result["skills"]["cancel"]["passed"] is False

    def test_failures_bounded(self):
        """Test that failures are bounded to MAX_FAILURES_ACA."""
        scenarios = [
            {
                "skill": f"skill_{i}",
                "verdict": "fail",
                "similarity": 0.2,
                "prompt": f"prompt {i}",
                "expected": f"expected {i}",
                "response": f"actual {i}",
            }
            for i in range(20)
        ]
        enhanced = {
            "total_scenarios": 20,
            "passed_scenarios": 0,
            "failed_scenarios": 20,
            "scenarios": scenarios,
        }

        result = compress_functional_results(enhanced)

        assert len(result["failures"]) <= MAX_FAILURES_ACA

    def test_empty_scenarios(self):
        """Test handling of empty scenarios array."""
        enhanced = {
            "total_scenarios": 0,
            "passed_scenarios": 0,
            "failed_scenarios": 0,
            "scenarios": []
        }

        result = compress_functional_results(enhanced)

        assert result["summary"]["total_scenarios"] == 0
        assert result["skills"] == {}
        assert result["failures"] == []

    def test_alternative_field_names(self):
        """Test handling of alternative field names in scenarios."""
        enhanced = {
            "total_scenarios": 1,
            "passed_scenarios": 0,
            "failed_scenarios": 1,
            "averageDistance": 0.5,  # Alternative to embeddingAverageDistance
            "scenarios": [
                {
                    "skillName": "booking",  # Alternative to skill
                    "evaluation": {
                        "verdict": "fail",
                        "similarity": 0.4
                    },
                    "prompt": "test",
                    "expectedResponse": "expected",  # Alternative to expected
                    "actualResponse": "actual",  # Alternative to response
                }
            ]
        }

        result = compress_functional_results(enhanced)

        assert result["summary"]["avg_similarity"] == 0.5
        assert "booking" in result["skills"]

    def test_token_budget(self):
        """Verify compressed output stays within token budget (~2k tokens)."""
        scenarios = [
            {
                "skill": f"skill_{i}",
                "verdict": "fail" if i < 10 else "pass",
                "similarity": 0.3 if i < 10 else 0.9,
                "prompt": "x" * 300,
                "expected": "y" * 200,
                "response": "z" * 300,
            }
            for i in range(20)
        ]
        enhanced = {
            "total_scenarios": 20,
            "passed_scenarios": 10,
            "failed_scenarios": 10,
            "embeddingAverageDistance": 0.6,
            "scenarios": scenarios,
        }

        result = compress_functional_results(enhanced)
        output_str = json.dumps(result)

        # Rough token estimate: 1 token ~= 4 chars
        estimated_tokens = len(output_str) / 4
        assert estimated_tokens < 2000, f"Functional compression exceeded budget: {estimated_tokens} tokens"


class TestIntegration:
    """Integration tests for compression utilities."""

    def test_combined_token_budget(self):
        """Test that combined SG + ACA compressed output stays under 4k tokens."""
        # Security scenarios
        sg_scenarios = [
            {"prompt": "x" * 400, "verdict": "blocked", "reason": "safe", "response": "y" * 400}
            for _ in range(30)
        ]
        sg_enhanced = {
            "total": 30,
            "blocked": 25,
            "needsReview": 3,
            "errors": 2,
            "scenarios": sg_scenarios,
            "byDataset": {"aisi": {"blocked": 20, "total": 25}},
        }

        # Functional scenarios
        aca_scenarios = [
            {
                "skill": f"skill_{i}",
                "verdict": "pass" if i < 4 else "fail",
                "similarity": 0.9 if i < 4 else 0.4,
                "prompt": "x" * 200,
                "expected": "y" * 150,
                "response": "z" * 200,
            }
            for i in range(5)
        ]
        aca_enhanced = {
            "total_scenarios": 5,
            "passed_scenarios": 4,
            "failed_scenarios": 1,
            "embeddingAverageDistance": 0.8,
            "scenarios": aca_scenarios,
        }

        sg_result = compress_security_results(sg_enhanced, "weave://sg/artifact")
        aca_result = compress_functional_results(aca_enhanced, "weave://aca/artifact")

        combined_str = json.dumps(sg_result) + json.dumps(aca_result)
        estimated_tokens = len(combined_str) / 4

        # Combined should be under 4k tokens (leaving room for judge prompts)
        assert estimated_tokens < 4000, f"Combined compression exceeded budget: {estimated_tokens} tokens"
