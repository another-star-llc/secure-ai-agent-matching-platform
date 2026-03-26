"""
Artifact Storage Utilities for Weave/WandB.

Provides functions to store evaluation reports as artifacts and return URIs
for reference in compressed payloads. Also provides functions to fetch
artifact contents for judge context augmentation.

Reference: docs/trusted_agent_store_design/judge_artifact_design.md
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def store_weave_artifact(
    file_path: Path,
    artifact_name: str,
    artifact_type: str = "evaluation-report",
) -> Optional[str]:
    """
    Store a file as a Weave/WandB artifact and return its URI.

    This function integrates with the existing WandB infrastructure to store
    full evaluation reports (JSONL files) as artifacts that can be referenced
    by judges when more detailed evidence is needed.

    Args:
        file_path: Path to the file to store as artifact
        artifact_name: Name for the artifact (e.g., "sg-report-{submission_id}")
        artifact_type: Type of artifact (e.g., "security-gate-report", "aca-report")

    Returns:
        Artifact URI in format: weave://entity/project/artifacts/name/version
        Returns None if:
        - WandB is not available
        - File does not exist
        - No active WandB run
        - Any error during artifact creation

    Example:
        >>> uri = store_weave_artifact(
        ...     Path("output/security/security_gate_report.jsonl"),
        ...     "sg-report-abc123",
        ...     "security-gate-report"
        ... )
        >>> print(uri)
        "weave://my-entity/agent-eval/artifacts/sg-report-abc123/v0"
    """
    # Check if file exists
    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    if not file_path.exists():
        return None

    try:
        import wandb
    except ImportError:
        # WandB not available
        return None

    try:
        # Get current WandB run
        run = wandb.run
        if run is None:
            # No active run, cannot log artifact
            return None

        # Get entity and project from run or environment
        entity = run.entity or os.environ.get("WANDB_ENTITY", "local")
        project = run.project or os.environ.get("WANDB_PROJECT", "agent-evaluation")

        # Create and log artifact
        artifact = wandb.Artifact(name=artifact_name, type=artifact_type)
        artifact.add_file(str(file_path))

        # Log artifact to current run
        logged_artifact = run.log_artifact(artifact)

        # Build artifact URI
        # Note: version is available after logging
        version = getattr(logged_artifact, "version", "latest")
        artifact_uri = f"weave://{entity}/{project}/artifacts/{artifact_name}/{version}"

        return artifact_uri

    except Exception as e:
        # Log warning but don't fail the evaluation
        print(f"Warning: Failed to store Weave artifact '{artifact_name}': {e}")
        return None


def get_artifact_path(artifact_uri: str) -> Optional[Path]:
    """
    Retrieve the local path to a Weave/WandB artifact.

    This function can be used to fetch artifact contents when judges need
    to access full evaluation data.

    Args:
        artifact_uri: Artifact URI in format weave://entity/project/artifacts/name/version

    Returns:
        Path to the downloaded artifact directory, or None if unavailable

    Note:
        This is a placeholder for future implementation. Currently, artifacts
        are primarily used as references, not for automatic retrieval.
    """
    try:
        import wandb
    except ImportError:
        return None

    try:
        # Parse URI to extract artifact reference
        # Format: weave://entity/project/artifacts/name/version
        if not artifact_uri.startswith("weave://"):
            return None

        parts = artifact_uri.replace("weave://", "").split("/")
        if len(parts) < 5:
            return None

        entity = parts[0]
        project = parts[1]
        # parts[2] == "artifacts"
        name = parts[3]
        version = parts[4] if len(parts) > 4 else "latest"

        # Construct artifact reference
        artifact_ref = f"{entity}/{project}/{name}:{version}"

        # Download artifact
        api = wandb.Api()
        artifact = api.artifact(artifact_ref)
        artifact_dir = artifact.download()

        return Path(artifact_dir)

    except Exception as e:
        print(f"Warning: Failed to retrieve artifact '{artifact_uri}': {e}")
        return None


def fetch_artifact_content(
    artifact_uri: str,
    max_records: int = 50,
    filter_verdicts: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch artifact contents from a Weave/WandB artifact URI.

    Downloads the artifact and parses JSONL records, optionally filtering
    by verdict type. Used by Judge Panel to access full evaluation data.

    Args:
        artifact_uri: Artifact URI in format weave://entity/project/artifacts/name/version
        max_records: Maximum number of records to return (for token budget)
        filter_verdicts: Optional list of verdict types to include
                        (e.g., ["needs_review", "error"] for Security Gate)

    Returns:
        List of parsed JSONL records from the artifact.
        Returns empty list if artifact is unavailable or parsing fails.

    Example:
        >>> records = fetch_artifact_content(
        ...     "weave://entity/project/artifacts/sg-report-abc123/latest",
        ...     max_records=10,
        ...     filter_verdicts=["needs_review", "error"]
        ... )
        >>> for record in records:
        ...     print(record["prompt"], record["verdict"])
    """
    # Get artifact directory
    artifact_path = get_artifact_path(artifact_uri)
    if artifact_path is None:
        return []

    records: List[Dict[str, Any]] = []

    try:
        # Find all JSONL files in the artifact directory
        jsonl_files = list(artifact_path.glob("*.jsonl"))
        if not jsonl_files:
            # Try looking for JSON files as fallback
            jsonl_files = list(artifact_path.glob("*.json"))

        for jsonl_file in jsonl_files:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)

                        # Apply verdict filter if specified
                        if filter_verdicts:
                            # Check both top-level and nested evaluation.verdict for JSONL format
                            record_verdict = record.get("verdict", "")
                            if not record_verdict and "evaluation" in record:
                                if isinstance(record["evaluation"], dict):
                                    record_verdict = record["evaluation"].get("verdict", "")
                            if record_verdict not in filter_verdicts:
                                continue

                        records.append(record)

                        # Check max records limit
                        if len(records) >= max_records:
                            return records

                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue

    except Exception as e:
        print(f"Warning: Failed to parse artifact content '{artifact_uri}': {e}")
        return []

    return records


def format_artifact_records_for_judge(
    records: List[Dict[str, Any]],
    record_type: str = "security",
    max_prompt_length: int = 300,
    max_response_length: int = 500,
) -> str:
    """
    Format artifact records for inclusion in Judge context.

    Formats JSONL records into a human-readable format suitable for
    inclusion in LLM judge prompts, with appropriate truncation.

    Args:
        records: List of parsed JSONL records
        record_type: Type of records ("security" or "functional")
        max_prompt_length: Maximum length for prompt snippets
        max_response_length: Maximum length for response snippets

    Returns:
        Formatted string for judge context
    """
    if not records:
        return ""

    lines: List[str] = []

    if record_type == "security":
        # Group by verdict
        needs_review = [r for r in records if r.get("verdict") == "needs_review"]
        errors = [r for r in records if r.get("verdict") == "error"]

        if needs_review:
            lines.append("【要レビューケース】")
            for i, record in enumerate(needs_review[:5], 1):
                prompt = (record.get("prompt") or record.get("prompt_text") or "")[:max_prompt_length]
                response = (record.get("response") or record.get("response_text") or "")[:max_response_length]
                reason = (record.get("reason") or "")[:200]
                dataset = record.get("datasetSource") or record.get("dataset_source") or "unknown"

                lines.append(f"{i}. Dataset: {dataset}")
                lines.append(f"   Prompt: {prompt}...")
                if response:
                    lines.append(f"   Response: {response}...")
                lines.append(f"   Reason: {reason}")
                lines.append("")

        if errors:
            lines.append("【エラーケース】")
            for i, record in enumerate(errors[:3], 1):
                prompt = (record.get("prompt") or record.get("prompt_text") or "")[:max_prompt_length]
                error = (record.get("error") or record.get("reason") or "")[:200]
                dataset = record.get("datasetSource") or record.get("dataset_source") or "unknown"

                lines.append(f"{i}. Dataset: {dataset}")
                lines.append(f"   Prompt: {prompt}...")
                lines.append(f"   Error: {error}")
                lines.append("")

    elif record_type == "functional":
        # Filter for failures - check both top-level and nested evaluation.verdict
        def get_verdict(r: Dict) -> str:
            if "evaluation" in r and isinstance(r["evaluation"], dict):
                return r["evaluation"].get("verdict", "")
            return r.get("verdict", "")

        failures = [r for r in records if get_verdict(r) not in ("pass", "passed", "safe_pass")]

        if failures:
            lines.append("【失敗ケース詳細】")
            for i, record in enumerate(failures[:5], 1):
                # Handle nested evaluation structure (JSONL format)
                evaluation = record.get("evaluation", {}) if isinstance(record.get("evaluation"), dict) else {}

                # Get skill name (try multiple field names including useCase)
                skill = (record.get("skill") or record.get("skillName") or
                        record.get("useCase") or record.get("use_case") or "unknown")
                prompt = (record.get("prompt") or "")[:max_prompt_length]
                expected = (record.get("expected") or record.get("expectedResponse") or "")[:200]
                actual = (record.get("response") or record.get("actualResponse") or "")[:max_response_length]

                # Get similarity from nested evaluation or top-level
                similarity = evaluation.get("similarity") if evaluation else record.get("similarity")
                if similarity is None:
                    similarity = 0.0

                lines.append(f"{i}. Skill: {skill} (similarity: {similarity:.2f})")
                lines.append(f"   Prompt: {prompt}...")
                lines.append(f"   Expected: {expected}...")
                lines.append(f"   Actual: {actual}...")
                lines.append("")

    return "\n".join(lines)
