"""
Payload Compression Utilities for Judge Panel Token Optimization.

Compresses Security Gate and Agent Card Accuracy results to reduce token
usage while preserving essential information for judge evaluation.

Reference: docs/trusted_agent_store_design/judge_artifact_design.md
"""

from typing import Any, Dict, List, Optional

# Configuration constants
MAX_SAMPLES_BLOCKED = 3
MAX_SAMPLES_NEEDS_REVIEW = 5
MAX_SAMPLES_ERRORS = 3
MAX_FAILURES_ACA = 5
PROMPT_SNIPPET_LENGTH = 200
RESPONSE_SNIPPET_LENGTH = 300
REASON_SNIPPET_LENGTH = 200


def compress_security_results(
    enhanced_summary: Dict[str, Any],
    artifact_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compress Security Gate results for Judge Panel input.

    Transforms full enhanced_security_summary (with complete scenarios array)
    into a compact payload with summary stats, bounded samples, and artifact URI.

    Target: <2k tokens for SG=30

    Args:
        enhanced_summary: Full enhanced_security_summary dict from submissions.py
        artifact_uri: Optional Weave artifact URI for full report

    Returns:
        Compressed payload matching judge_artifact_design.md spec:
        {
            "summary": {"total", "blocked", "needs_review", "errors", "blocked_rate"},
            "by_dataset": {...},
            "samples": {"blocked": [...], "needs_review": [...], "errors": [...]},
            "artifacts": {"full_report": artifact_uri}
        }
    """
    scenarios = enhanced_summary.get("scenarios", [])

    # Group scenarios by verdict (calculate from scenarios array for accuracy)
    blocked_scenarios = [s for s in scenarios if s.get("verdict") == "blocked"]
    needs_review_scenarios = [s for s in scenarios if s.get("verdict") == "needs_review"]
    error_scenarios = [s for s in scenarios if s.get("verdict") == "error"]

    # Calculate counts from scenarios array to avoid mismatch with summary
    total = len(scenarios)
    blocked = len(blocked_scenarios)
    needs_review = len(needs_review_scenarios)
    errors = len(error_scenarios)

    # Calculate blocked rate
    blocked_rate = f"{(blocked / total * 100):.1f}%" if total > 0 else "N/A"

    def create_sample(scenario: Dict, include_response: bool = False) -> Dict:
        """Create a bounded sample with snippets from a scenario."""
        prompt = scenario.get("prompt") or scenario.get("prompt_text") or ""
        sample = {
            "prompt_snippet": prompt[:PROMPT_SNIPPET_LENGTH],
            "reason": (scenario.get("reason") or "")[:REASON_SNIPPET_LENGTH],
            "dataset": scenario.get("datasetSource") or scenario.get("dataset_source") or "unknown",
        }
        if include_response:
            response = scenario.get("response") or scenario.get("response_text") or ""
            if response:
                sample["response_snippet"] = response[:RESPONSE_SNIPPET_LENGTH]
        return sample

    # Build compressed payload
    compressed = {
        "summary": {
            "total": total,
            "blocked": blocked,
            "needs_review": needs_review,
            "errors": errors,
            "blocked_rate": blocked_rate,
        },
        "by_dataset": enhanced_summary.get("byDataset", {}),
        "samples": {
            "blocked": [
                create_sample(s) for s in blocked_scenarios[:MAX_SAMPLES_BLOCKED]
            ],
            "needs_review": [
                create_sample(s, include_response=True)
                for s in needs_review_scenarios[:MAX_SAMPLES_NEEDS_REVIEW]
            ],
            "errors": [
                create_sample(s) for s in error_scenarios[:MAX_SAMPLES_ERRORS]
            ],
        },
    }

    # Add artifact reference if available
    if artifact_uri:
        compressed["artifacts"] = {"full_report": artifact_uri}

    return compressed


def compress_functional_results(
    enhanced_summary: Dict[str, Any],
    artifact_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compress Agent Card Accuracy results for Judge Panel input.

    Transforms full enhanced_functional_summary (with complete scenarios array)
    into a compact payload with summary, skills breakdown, failures, and artifact URI.

    Target: <2k tokens for ACA=5

    Args:
        enhanced_summary: Full enhanced_functional_summary dict from submissions.py
        artifact_uri: Optional Weave artifact URI for full report

    Returns:
        Compressed payload matching judge_artifact_design.md spec:
        {
            "summary": {"total_scenarios", "passed", "failed", "avg_similarity"},
            "skills": {"SkillName": {"passed", "similarity", "reason"}},
            "failures": [{"skill", "prompt", "expected", "actual", "similarity"}],
            "artifacts": {"full_report": artifact_uri}
        }
    """
    scenarios = enhanced_summary.get("scenarios", [])

    # Extract counts from enhanced_summary
    total = enhanced_summary.get("total_scenarios", len(scenarios))
    passed = enhanced_summary.get("passed_scenarios", 0)
    failed = enhanced_summary.get("failed_scenarios", 0)

    # Get average similarity: convert from distance (distance = 1 - similarity)
    avg_distance = (
        enhanced_summary.get("embeddingAverageDistance")
        or enhanced_summary.get("averageDistance")
    )
    if avg_distance is not None:
        avg_similarity = 1.0 - avg_distance  # Convert distance to similarity
    else:
        avg_similarity = 0.0

    # Build skills breakdown and collect failures
    skills: Dict[str, Dict[str, Any]] = {}
    failures: List[Dict[str, Any]] = []

    for scenario in scenarios:
        # Extract skill name (try multiple possible field names)
        skill_name = (
            scenario.get("skill")
            or scenario.get("skillName")
            or scenario.get("use_case")
            or "unknown"
        )

        # Extract verdict (try multiple possible structures)
        verdict = scenario.get("verdict")
        if not verdict and "evaluation" in scenario:
            verdict = scenario["evaluation"].get("verdict")
        if not verdict:
            verdict = "unknown"

        # Extract similarity (try multiple possible structures)
        similarity = scenario.get("similarity")
        if similarity is None and "evaluation" in scenario:
            similarity = scenario["evaluation"].get("similarity")
        if similarity is None:
            similarity = 0.0

        # Determine if passed
        passed_flag = verdict in ("pass", "passed", "safe_pass")

        # Add to skills breakdown (first occurrence wins)
        if skill_name not in skills:
            skills[skill_name] = {
                "passed": passed_flag,
                "similarity": round(similarity, 3) if isinstance(similarity, float) else similarity,
                "reason": "" if passed_flag else (scenario.get("reason") or "")[:150],
            }

        # Collect failures
        if not passed_flag and len(failures) < MAX_FAILURES_ACA:
            prompt = scenario.get("prompt") or ""
            expected = scenario.get("expected") or scenario.get("expectedResponse") or ""
            actual = scenario.get("response") or scenario.get("actualResponse") or ""

            failures.append({
                "skill": skill_name,
                "prompt": prompt[:PROMPT_SNIPPET_LENGTH],
                "expected": expected[:150],
                "actual": actual[:RESPONSE_SNIPPET_LENGTH],
                "similarity": round(similarity, 3) if isinstance(similarity, float) else similarity,
            })

    # Build compressed payload
    compressed = {
        "summary": {
            "total_scenarios": total,
            "passed": passed,
            "failed": failed,
            "avg_similarity": round(avg_similarity, 3) if isinstance(avg_similarity, float) else avg_similarity,
        },
        "skills": skills,
        "failures": failures[:MAX_FAILURES_ACA],
    }

    # Add artifact reference if available
    if artifact_uri:
        compressed["artifacts"] = {"full_report": artifact_uri}

    return compressed
